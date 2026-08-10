"""Native syslinux installer -- no external syslinux binary required.

Installing syslinux on a FAT volume means three things: write ``ldlinux.sys``
onto the filesystem, tell the boot sector where its sectors are, and merge
syslinux's boot code into that sector while keeping the volume's own BPB.
Upstream ships one installer binary per platform to do it; this module does
the same work in Python, so a build with no runnable syslinux binary (macOS,
or a non-x86 Linux) still produces a bootable drive without asking the user
to install anything.

The patching follows syslinux 6.03 ``libinstaller/syslxmod.c`` -- the same
version whose ``ldlinux.sys``, ``ldlinux.bss`` and ``*.c32`` modules are
bundled in ``resources/bootloader``. The two must stay in step: the patch
area layout is per-version.

Everything here works through ``read``/``write`` callables, so the caller
decides how the device is reached (directly when root, via ``dd`` under
elevation otherwise) and the logic stays testable against a disk image.
"""

import logging
import os
import struct
import subprocess
import tempfile
from typing import Callable, List, NamedTuple, Optional, Tuple

from pynetboot.core.fat import FatVolume, FatError, SECTOR_SIZE

logger = logging.getLogger(__name__)

# --- syslinux 6.03 on-disk constants ---------------------------------------

LDLINUX_MAGIC = 0x3EB202FE

# The Auxiliary Data Vector: two sectors appended to ldlinux.sys where
# syslinux keeps boot-once/menu-save state.
ADV_SIZE = 512
ADV_MAGIC1 = 0x5A2D2FA5
ADV_MAGIC2 = 0xA3041767
ADV_MAGIC3 = 0xDD28BF64

# struct patch_area, at the LDLINUX_MAGIC marker inside ldlinux.sys.
_PATCH_AREA = '<IIHHIIHH'   # magic, instance, data_sectors, adv_sectors,
#                             dwords, checksum, maxtransfer, epaoffset
_OFF_DATA_SECTORS = 8
_OFF_ADV_SECTORS = 10
_OFF_DWORDS = 12
_OFF_CHECKSUM = 16
_OFF_MAXTRANSFER = 20
_OFF_EPAOFFSET = 22

# struct ext_patch_area, at patch_area.epaoffset (all uint16).
_EPA_FIELDS = ('advptroffset', 'diroffset', 'dirlen', 'subvoloffset',
               'subvollen', 'secptroffset', 'secptrcnt',
               'sect1ptr0', 'sect1ptr1', 'raidpatch')

# A FAT boot sector keeps its BPB in bytes 11..89; syslinux owns the jump
# instruction and OEM name before it and the code after it.
_BS_HEAD_LEN = 11
_BS_CODE_START = 90
_BS_CODE_END = 510

_EXTENT_STRUCT = struct.Struct('<QH')   # syslinux_extent: lba, len


class SyslinuxError(Exception):
    """The native syslinux install could not be completed."""


# --- the pieces ------------------------------------------------------------

def build_adv() -> bytes:
    """Build the two-sector vacuous ADV appended to ldlinux.sys."""
    adv = bytearray(ADV_SIZE)
    struct.pack_into('<I', adv, 0, ADV_MAGIC1)
    # The checksum makes the whole ADV sum to ADV_MAGIC2; every data word is
    # zero here, so it is just the magic itself.
    csum = ADV_MAGIC2
    for i in range(8, ADV_SIZE - 4, 4):
        csum = (csum - struct.unpack_from('<I', adv, i)[0]) & 0xFFFFFFFF
    struct.pack_into('<I', adv, 4, csum)
    struct.pack_into('<I', adv, ADV_SIZE - 4, ADV_MAGIC3)
    return bytes(adv) * 2


def file_payload(ldlinux: bytes) -> bytes:
    """The exact bytes to write to the volume as ``ldlinux.sys``.

    The ADV has to be part of the file, otherwise the sectors the boot code
    is told about do not exist.
    """
    return ldlinux + build_adv()


def _find_patch_area(image: bytes) -> int:
    """Return the offset of LDLINUX_MAGIC, which marks the patch area."""
    for offset in range(0, len(image) - 4, 4):
        if struct.unpack_from('<I', image, offset)[0] == LDLINUX_MAGIC:
            return offset
    raise SyslinuxError(
        "No patch area in ldlinux.sys: the bundled bootloader is corrupt")


def _read_epa(image: bytes, epa_offset: int) -> dict:
    values = struct.unpack_from('<10H', image, epa_offset)
    return dict(zip(_EPA_FIELDS, values))


def generate_extents(sectors: List[int], max_extents: int) -> bytes:
    """Pack a sector list into syslinux extents.

    Runs of consecutive sectors collapse into one extent, subject to the two
    limits the boot code has: an extent may not exceed 64 KiB, and it may not
    straddle a 64 KiB real-mode segment boundary in the load buffer.
    """
    packed = bytearray()
    count = 0
    addr = 0x8000          # where ldlinux.sys starts loading
    base = addr
    lba = 0
    length = 0

    def emit(lba_: int, len_: int) -> None:
        nonlocal count
        if count >= max_extents:
            raise SyslinuxError(
                "ldlinux.sys is too fragmented for the boot sector "
                "(reformat the drive and retry)")
        packed.extend(_EXTENT_STRUCT.pack(lba_, len_))
        count += 1

    for sector in sectors:
        if length:
            xbytes = (length + 1) * SECTOR_SIZE
            if (sector == lba + length and xbytes < 65536
                    and ((addr ^ (base + xbytes - 1)) & 0xFFFF0000) == 0):
                length += 1
                addr += SECTOR_SIZE
                continue
            emit(lba, length)
        base = addr
        lba = sector
        length = 1
        addr += SECTOR_SIZE

    if length:
        emit(lba, length)

    # The rest of the pointer array must be zeroed: the boot code reads until
    # it finds a zero-length extent.
    return bytes(packed).ljust(max_extents * _EXTENT_STRUCT.size, b'\0')


def patch(ldlinux: bytes, boot_template: bytes, sectors: List[int],
          subdir: Optional[str] = None,
          raid_mode: bool = False,
          stupid_mode: bool = False) -> Tuple[bytes, bytes, int]:
    """Patch ldlinux.sys and the boot sector template with a sector map.

    `sectors` lists every sector of the on-disk ldlinux.sys, including its two
    ADV sectors. Returns (patched ldlinux.sys, patched boot sector template,
    number of bytes of ldlinux.sys that changed).
    """
    image = bytearray(ldlinux)
    boot = bytearray(boot_template)

    # Two ADV sectors follow the image itself.
    nsect = ((len(ldlinux) + SECTOR_SIZE - 1) // SECTOR_SIZE) + 2
    if len(sectors) < nsect:
        raise SyslinuxError(
            f"ldlinux.sys occupies {len(sectors)} sectors on disk, "
            f"but {nsect} are needed")

    patch_area = _find_patch_area(image)
    epa_offset = struct.unpack_from(
        '<H', image, patch_area + _OFF_EPAOFFSET)[0]
    epa = _read_epa(image, epa_offset)

    # The boot sector loads the first sector on its own; everything after it
    # is found through the extent list.
    struct.pack_into('<I', boot, epa['sect1ptr0'], sectors[0] & 0xFFFFFFFF)
    struct.pack_into('<I', boot, epa['sect1ptr1'], sectors[0] >> 32)
    if raid_mode:
        # INT 18h: hand back to the BIOS to try the next boot device.
        struct.pack_into('<H', boot, epa['raidpatch'], 0x18CD)

    dwords = len(ldlinux) >> 2
    struct.pack_into('<H', image, patch_area + _OFF_DATA_SECTORS, nsect - 2)
    struct.pack_into('<H', image, patch_area + _OFF_ADV_SECTORS, 2)
    struct.pack_into('<I', image, patch_area + _OFF_DWORDS, dwords)
    if stupid_mode:
        struct.pack_into('<H', image, patch_area + _OFF_MAXTRANSFER, 1)

    # Sector 0 is in the boot sector and the last two sectors are the ADVs,
    # so the extent list covers what is left.
    extents = generate_extents(sectors[1:nsect - 2], epa['secptrcnt'])
    image[epa['secptroffset']:epa['secptroffset'] + len(extents)] = extents

    struct.pack_into('<Q', image, epa['advptroffset'], sectors[nsect - 2])
    struct.pack_into('<Q', image, epa['advptroffset'] + 8, sectors[nsect - 1])

    if subdir:
        encoded = subdir.encode('ascii') + b'\0'
        if len(encoded) > epa['dirlen']:
            raise SyslinuxError(f"Subdirectory path too long: {subdir}")
        image[epa['diroffset']:epa['diroffset'] + len(encoded)] = encoded

    # Checksum last: it covers the fields patched above.
    struct.pack_into('<I', image, patch_area + _OFF_CHECKSUM, 0)
    csum = LDLINUX_MAGIC
    for i in range(dwords):
        csum = (csum - struct.unpack_from('<I', image, i * 4)[0]) & 0xFFFFFFFF
    struct.pack_into('<I', image, patch_area + _OFF_CHECKSUM, csum)

    return bytes(image), bytes(boot), dwords << 2


def merge_boot_sector(existing: bytes, template: bytes) -> bytes:
    """Put syslinux's boot code into a FAT boot sector, keeping its BPB.

    Overwriting the whole sector would destroy the geometry the filesystem
    was formatted with and the volume would no longer mount.
    """
    if len(existing) < SECTOR_SIZE or len(template) < SECTOR_SIZE:
        raise SyslinuxError("Boot sectors must be 512 bytes")
    merged = bytearray(existing[:SECTOR_SIZE])
    merged[0:_BS_HEAD_LEN] = template[0:_BS_HEAD_LEN]
    merged[_BS_CODE_START:_BS_CODE_END] = \
        template[_BS_CODE_START:_BS_CODE_END]
    return bytes(merged)


# --- installation ----------------------------------------------------------

def install(read: Callable[[int, int], bytes],
            write: Callable[[int, bytes], None],
            ldlinux: bytes, boot_template: bytes,
            filename: str = 'LDLINUX SYS',
            prefetch: Optional[Callable[[int, int], None]] = None) -> 'Written':
    """Finish a syslinux install on a FAT volume reached via read/write.

    ``ldlinux.sys`` (with its ADV) must already have been copied onto the
    volume; this maps it, patches it in place and writes the boot sector.

    `prefetch(offset, length)` is an optional hint that the given span is
    about to be read. Where each read costs an elevated command, fetching the
    FAT and the root directory in one go turns a handful of password prompts
    into one.

    Returns what the drive must now hold, for the caller to read back and
    check with `Written.check`. Verifying is left to the caller so the
    read-back can ride along with the write instead of costing its own
    elevation.
    """
    try:
        volume = FatVolume(read)
    except FatError as e:
        raise SyslinuxError(f"Target is not a usable FAT volume: {e}")
    logger.info(f"Native syslinux install on {volume}")

    if prefetch is not None:
        # Everything the sector map needs lives between the first FAT and the
        # start of the data area, plus the first root directory clusters.
        start = volume.fat_start * SECTOR_SIZE
        end = (volume.data_start + volume.sectors_per_cluster * 8) * SECTOR_SIZE
        prefetch(start, end - start)

    entry = volume.find_in_root(filename)
    if entry is None:
        raise SyslinuxError(
            f"{filename.strip()} is not in the root directory of the target")
    first_cluster, size = entry

    expected = len(ldlinux) + 2 * ADV_SIZE
    if size != expected:
        raise SyslinuxError(
            f"ldlinux.sys on the target is {size} bytes, expected {expected}")

    nsectors = (size + SECTOR_SIZE - 1) // SECTOR_SIZE
    sectors = volume.sectors_of(first_cluster, nsectors)
    if len(sectors) < nsectors:
        raise SyslinuxError(
            f"Could only map {len(sectors)} of {nsectors} sectors of "
            f"ldlinux.sys; the FAT chain is broken")
    logger.info(
        f"ldlinux.sys maps to {nsectors} sectors starting at {sectors[0]}")

    image, boot_code, modified = patch(ldlinux, boot_template, sectors)
    # Rebuild exactly what the file looks like on disk, so the last sector --
    # part ldlinux.sys, part ADV -- is written back intact.
    on_disk = (image + build_adv()).ljust(nsectors * SECTOR_SIZE, b'\0')

    # Write back only what changed, in runs of consecutive sectors so a
    # device reached through dd is not written a sector at a time.
    changed = (modified + SECTOR_SIZE - 1) // SECTOR_SIZE
    index = 0
    for start, count in _runs(sectors[:changed]):
        write(start * SECTOR_SIZE,
              on_disk[index * SECTOR_SIZE:(index + count) * SECTOR_SIZE])
        index += count
    logger.info(f"Patched the first {changed} sectors of ldlinux.sys")

    # Re-read the boot sector: copying files may have changed it (FAT32
    # keeps a dirty flag there).
    current = read(0, SECTOR_SIZE)
    expected_boot = merge_boot_sector(current, boot_code)
    write(0, expected_boot)
    logger.info("Wrote the syslinux boot sector")

    return Written(first_sector=sectors[0], boot_sector=expected_boot,
                   first_ldlinux_sector=on_disk[:SECTOR_SIZE])


class Written(NamedTuple):
    """What the drive must hold once an install has been written.

    Only the two sectors that decide whether it boots at all: the boot sector
    the BIOS jumps into, and the first sector of ldlinux.sys that it loads
    next.
    """

    first_sector: int
    boot_sector: bytes
    first_ldlinux_sector: bytes

    def spans(self) -> List[Tuple[int, int]]:
        """Where to read from, to check what was written."""
        return [(0, SECTOR_SIZE),
                (self.first_sector * SECTOR_SIZE, SECTOR_SIZE)]

    def check(self, boot: bytes, first_ldlinux: bytes) -> None:
        """Compare what the drive returned; raise if it is not what we wrote."""
        if boot != self.boot_sector:
            raise SyslinuxError(
                "The boot sector read back differently from what was "
                "written; the drive did not accept the write")
        if first_ldlinux != self.first_ldlinux_sector:
            raise SyslinuxError(
                f"Sector {self.first_sector} does not hold the patched "
                f"ldlinux.sys; the filesystem may have moved the file")
        logger.info(
            "Verified the boot sector and the first sector of ldlinux.sys")


def _runs(sectors: List[int]) -> List[Tuple[int, int]]:
    """Collapse a sector list into (start, count) runs of consecutive sectors."""
    runs: List[Tuple[int, int]] = []
    for sector in sectors:
        if runs and sector == runs[-1][0] + runs[-1][1]:
            start, count = runs[-1]
            runs[-1] = (start, count + 1)
        else:
            runs.append((sector, 1))
    return runs


# --- device access ---------------------------------------------------------

class ElevatedBatch:
    """Commands from several devices, run together under one elevation.

    macOS authorises each elevated command separately -- the admin right is
    not shared between processes -- so a password prompt per dd would mean
    about ten for one install. Collecting the reads into one batch and the
    writes into another brings it down to two.

    Results are handed back through tokens because nothing can be read until
    the batch has actually run.
    """

    def __init__(self) -> None:
        self._commands: List[List[str]] = []
        self._reads: List[Tuple[str, int, int, Optional[Callable]]] = []
        self._temps: List[str] = []
        self._results: dict = {}

    def __enter__(self) -> 'ElevatedBatch':
        return self

    def __exit__(self, *exc_info) -> None:
        self.discard()

    @property
    def pending(self) -> int:
        return len(self._commands)

    def _temp_file(self, data: Optional[bytes] = None) -> str:
        handle = tempfile.NamedTemporaryFile(prefix='pynetboot_dd_',
                                             delete=False)
        if data is not None:
            handle.write(data)
        handle.close()
        self._temps.append(handle.name)
        return handle.name

    def add_read(self, path: str, offset: int, length: int,
                 into: Optional[Callable[[int, bytes], None]] = None) -> int:
        """Queue a read; returns a token for `result` once the batch has run."""
        first = offset // SECTOR_SIZE
        last = (offset + length + SECTOR_SIZE - 1) // SECTOR_SIZE
        target = self._temp_file()
        token = len(self._reads)
        self._reads.append((target, first * SECTOR_SIZE,
                            offset - first * SECTOR_SIZE, into))
        self._commands.append(
            ['dd', f'if={path}', f'of={target}', f'bs={SECTOR_SIZE}',
             f'skip={first}', f'count={last - first}', 'conv=notrunc'])
        return token

    def add_write(self, path: str, sector: int, data: bytes) -> None:
        """Queue a whole-sector write."""
        source = self._temp_file(data)
        self._commands.append(
            ['dd', f'if={source}', f'of={path}', f'bs={SECTOR_SIZE}',
             f'seek={sector}', f'count={len(data) // SECTOR_SIZE}',
             'conv=notrunc'])

    def run(self, what: str) -> None:
        """Run everything queued so far as a single elevated script."""
        if not self._commands:
            return
        commands, self._commands = self._commands, []
        reads, self._reads = self._reads, []
        logger.info(f"Elevating once to {what} ({len(commands)} commands)")
        _run_elevated_script(commands, what)

        for token, (path, base, start, into) in enumerate(reads):
            with open(path, 'rb') as handle:
                data = handle.read()
            self._results[token] = data[start:] if start else data
            if into is not None:
                into(base, data)

    def result(self, token: int) -> bytes:
        """The bytes a queued read returned."""
        if token not in self._results:
            raise SyslinuxError("That read has not been run yet")
        return self._results[token]

    def discard(self) -> None:
        """Drop anything still queued and remove the temporary files."""
        self._commands.clear()
        self._reads.clear()
        for path in self._temps:
            try:
                os.unlink(path)
            except OSError:
                pass
        self._temps.clear()


class RawDevice:
    """Sector-level access to a partition, direct or through elevation.

    A partition device is only writable by root. When the process is already
    root (Linux run under pkexec, Windows running elevated, or a plain image
    file in a test) it is opened directly; otherwise every access goes through
    ``dd`` under the app's normal elevation.

    On macOS each elevated command is its own authorization -- the
    ``system.privilege.admin`` right is not shared between processes -- so one
    command per sector would mean a password prompt per sector. Reads are
    therefore served from a prefetched span where possible, and writes are
    collected and issued as a single elevated script when the device closes.
    """

    def __init__(self, path: str, elevated: Optional[bool] = None,
                 batch: Optional['ElevatedBatch'] = None):
        self.path = path
        if elevated is None:
            elevated = not _can_open_directly(path)
        self.elevated = elevated
        # With a batch, reads and writes are queued for the caller to run
        # alongside every other device's; without one they go out as they
        # come.
        self._batch = batch if elevated else None
        self._handle = None
        # Spans already read from the device: (offset, data).
        self._cache: List[Tuple[int, bytes]] = []
        # Whole-sector writes waiting to be issued: (sector, data).
        self._pending: List[Tuple[int, bytes]] = []

    def __enter__(self) -> 'RawDevice':
        if not self.elevated:
            self._handle = open(self.path, 'rb+')
        logger.info(
            f"Raw access to {self.path}: "
            f"{'elevated (dd)' if self.elevated else 'direct'}")
        return self

    def __exit__(self, exc_type, *exc_info) -> None:
        try:
            # A failed install must not leave half its sectors on the drive.
            if exc_type is None:
                self.flush()
            elif self._pending:
                logger.warning(
                    f"Discarding {len(self._pending)} pending writes to "
                    f"{self.path} after an error")
                self._pending.clear()
        finally:
            if self._handle is not None:
                self._handle.flush()
                os.fsync(self._handle.fileno())
                self._handle.close()
                self._handle = None

    # -- reading ------------------------------------------------------------

    def prefetch(self, offset: int, length: int) -> None:
        """Read a span up front so later reads inside it cost nothing.

        With a batch attached the read is queued instead, and lands in the
        cache when the batch runs.
        """
        if self._handle is not None or length <= 0:
            return
        if self._from_cache(offset, length) is not None:
            return
        if self._batch is not None:
            self._batch.add_read(self.path, offset, length,
                                 into=self._cache_span)
            return
        first = offset // SECTOR_SIZE
        last = (offset + length + SECTOR_SIZE - 1) // SECTOR_SIZE
        data = self._dd_read(first, last - first)
        if data:
            self._cache_span(first * SECTOR_SIZE, data)

    def _cache_span(self, base: int, data: bytes) -> None:
        if not data:
            return
        self._cache.append((base, data))
        logger.info(f"Holding {len(data) // SECTOR_SIZE} sectors of "
                    f"{self.path} from sector {base // SECTOR_SIZE}")

    def read(self, offset: int, length: int) -> bytes:
        if self._handle is not None:
            self._handle.seek(offset)
            return self._handle.read(length)

        cached = self._from_cache(offset, length)
        if cached is not None:
            return cached

        # dd works in whole sectors, so read the sectors that cover the range.
        first = offset // SECTOR_SIZE
        last = (offset + length + SECTOR_SIZE - 1) // SECTOR_SIZE
        data = self._dd_read(first, last - first)
        self._cache.append((first * SECTOR_SIZE, data))
        start = offset - first * SECTOR_SIZE
        return data[start:start + length]

    def read_many(self, spans: List[Tuple[int, int]]) -> List[bytes]:
        """Read several spans from the device under a single elevation.

        Buffered writes are committed first and the cache is not consulted:
        this exists to see what the drive actually holds.
        """
        self.flush()
        if self._handle is not None:
            return [self.read(offset, length) for offset, length in spans]

        commands, temps, sectors = [], [], []
        for offset, length in spans:
            first = offset // SECTOR_SIZE
            last = (offset + length + SECTOR_SIZE - 1) // SECTOR_SIZE
            handle = tempfile.NamedTemporaryFile(
                prefix='pynetboot_dd_', delete=False)
            handle.close()
            temps.append(handle.name)
            sectors.append((first, offset - first * SECTOR_SIZE, length))
            commands.append(
                ['dd', f'if={self.path}', f'of={handle.name}',
                 f'bs={SECTOR_SIZE}', f'skip={first}', f'count={last - first}',
                 'conv=notrunc'])
        try:
            _run_elevated_script(
                commands, f"read {len(spans)} spans from {self.path}")
            out = []
            for path, (_first, start, length) in zip(temps, sectors):
                with open(path, 'rb') as fh:
                    out.append(fh.read()[start:start + length])
            return out
        finally:
            for path in temps:
                try:
                    os.unlink(path)
                except OSError:
                    pass

    def _from_cache(self, offset: int, length: int) -> Optional[bytes]:
        # Newest first: a pending write must win over the sectors a prefetch
        # captured before it.
        for base, data in reversed(self._cache):
            if base <= offset and offset + length <= base + len(data):
                start = offset - base
                return data[start:start + length]
        return None

    def read_uncached(self, offset: int, length: int) -> bytes:
        """Read from the device itself, ignoring anything already held.

        Verification has to see what the drive stored, not what we meant to
        store, so pending writes are committed and the cache is skipped.
        """
        self.flush()
        if self._handle is not None:
            return self.read(offset, length)
        first = offset // SECTOR_SIZE
        last = (offset + length + SECTOR_SIZE - 1) // SECTOR_SIZE
        data = self._dd_read(first, last - first)
        start = offset - first * SECTOR_SIZE
        return data[start:start + length]

    # -- writing ------------------------------------------------------------

    def write(self, offset: int, data: bytes) -> None:
        if self._handle is not None:
            self._handle.seek(offset)
            self._handle.write(data)
            self._handle.flush()
            return

        if offset % SECTOR_SIZE or len(data) % SECTOR_SIZE:
            raise SyslinuxError(
                "Elevated writes must be whole sectors "
                f"(offset {offset}, {len(data)} bytes)")
        self._pending.append((offset // SECTOR_SIZE, data))
        # Anything read back later must see what was written, not the stale
        # sectors a prefetch captured.
        self._cache.append((offset, data))

    def flush(self) -> None:
        """Issue every pending write as one elevated command.

        With a batch attached the writes are queued into it instead; the
        caller runs the batch, which is what keeps the whole install down to
        one elevation for reading and one for writing.
        """
        if not self._pending:
            return
        pending, self._pending = self._pending, []

        if self._batch is not None:
            for sector, data in pending:
                self._batch.add_write(self.path, sector, data)
            return

        paths = []
        commands = []
        try:
            for sector, data in pending:
                handle = tempfile.NamedTemporaryFile(
                    prefix='pynetboot_dd_', delete=False)
                handle.write(data)
                handle.close()
                paths.append(handle.name)
                commands.append(
                    ['dd', f'if={handle.name}', f'of={self.path}',
                     f'bs={SECTOR_SIZE}', f'seek={sector}',
                     f'count={len(data) // SECTOR_SIZE}', 'conv=notrunc'])
            sectors = sum(len(d) // SECTOR_SIZE for _s, d in pending)
            _run_elevated_script(
                commands,
                f"write {sectors} sectors to {self.path} "
                f"in {len(commands)} runs")
        finally:
            for path in paths:
                try:
                    os.unlink(path)
                except OSError:
                    pass

    # -- dd plumbing --------------------------------------------------------

    def _dd_read(self, sector: int, count: int) -> bytes:
        if count <= 0:
            return b''
        with tempfile.NamedTemporaryFile(prefix='pynetboot_dd_') as tmp:
            _run_elevated_script([
                ['dd', f'if={self.path}', f'of={tmp.name}',
                 f'bs={SECTOR_SIZE}', f'skip={sector}', f'count={count}',
                 'conv=notrunc'],
            ], f"read {count} sectors at {sector} from {self.path}")
            with open(tmp.name, 'rb') as fh:
                return fh.read()


def _run_elevated_script(commands: List[List[str]], what: str) -> None:
    """Run several commands under a single elevation.

    They go into a shell script that is run as one elevated command: on macOS
    that is one password prompt for the batch instead of one per command, and
    the elevated command line stays two fixed arguments regardless of what is
    being run.
    """
    from pynetboot.core.elevation import run_elevated
    import shlex

    script = "#!/bin/sh\nset -e\n" + "".join(
        shlex.join(command) + "\n" for command in commands)
    handle = tempfile.NamedTemporaryFile(
        prefix='pynetboot_batch_', suffix='.sh', mode='w', delete=False)
    handle.write(script)
    handle.close()
    os.chmod(handle.name, 0o755)

    try:
        returncode, _stdout, stderr = run_elevated(
            ['/bin/sh', handle.name], timeout=300)
    except Exception as e:                    # elevation errors vary by OS
        raise SyslinuxError(f"Could not {what}: {e}")
    finally:
        try:
            os.unlink(handle.name)
        except OSError:
            pass

    if returncode != 0:
        raise SyslinuxError(f"Could not {what}: {(stderr or '').strip()}")


def _can_open_directly(path: str) -> bool:
    """True if this process can already write the device without elevation."""
    try:
        with open(path, 'rb+'):
            return True
    except OSError:
        return False


def sync_disks() -> None:
    """Flush the OS cache so raw writes reach the device."""
    try:
        subprocess.run(['sync'], capture_output=True, timeout=30)
    except (subprocess.SubprocessError, OSError) as e:
        logger.debug(f"sync failed: {e}")
