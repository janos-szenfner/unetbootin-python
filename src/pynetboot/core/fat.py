"""Read-only FAT12/16/32 parser.

Only what a bootloader installer needs: locate a file in the root directory
and list the sectors that hold it. It reads through a caller-supplied
``read(offset, length)`` callable, so the same code works against a mounted
device read via ``dd``, a raw file handle, or a disk image in a test.

This replaces the sector-mapping half of syslinux's ``libfat``; without it
the installer could not tell the boot sector where ``ldlinux.sys`` lives.
"""

import logging
import struct
from typing import Callable, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

SECTOR_SIZE = 512

# Directory entry layout (32 bytes).
_DIR_ENTRY_SIZE = 32
_ATTR_LONG_NAME = 0x0F
_ATTR_VOLUME_ID = 0x08
_ENTRY_FREE = 0xE5
_ENTRY_END = 0x00


class FatError(Exception):
    """The volume is not a FAT filesystem this parser understands."""


class FatVolume:
    """A FAT filesystem, addressed in sectors relative to its own start."""

    def __init__(self, read: Callable[[int, int], bytes]):
        """`read(offset, length)` returns bytes from the start of the volume."""
        self._read = read
        self._fat_cache: dict = {}

        boot = read(0, SECTOR_SIZE)
        if len(boot) < SECTOR_SIZE:
            raise FatError("Could not read the boot sector")
        if boot[510:512] != b'\x55\xaa':
            raise FatError("No 0xAA55 boot signature: not a FAT volume")

        self.bytes_per_sector = struct.unpack_from('<H', boot, 11)[0]
        self.sectors_per_cluster = boot[13]
        self.reserved_sectors = struct.unpack_from('<H', boot, 14)[0]
        self.num_fats = boot[16]
        root_entries = struct.unpack_from('<H', boot, 17)[0]
        total_sectors_16 = struct.unpack_from('<H', boot, 19)[0]
        fat_size_16 = struct.unpack_from('<H', boot, 22)[0]
        total_sectors_32 = struct.unpack_from('<I', boot, 32)[0]

        if self.bytes_per_sector != SECTOR_SIZE:
            raise FatError(
                f"Unsupported sector size {self.bytes_per_sector} "
                f"(only {SECTOR_SIZE} is supported)")
        if self.sectors_per_cluster == 0 or self.num_fats == 0:
            raise FatError("Boot sector has no usable BPB")

        self.fat_size = fat_size_16 or struct.unpack_from('<I', boot, 36)[0]
        self.total_sectors = total_sectors_16 or total_sectors_32
        self.root_entries = root_entries
        # A FAT32 volume has no fixed root directory area; its root is an
        # ordinary cluster chain named in the BPB.
        self.root_cluster = struct.unpack_from('<I', boot, 44)[0]

        self.root_dir_sectors = (
            (root_entries * _DIR_ENTRY_SIZE + self.bytes_per_sector - 1)
            // self.bytes_per_sector)
        self.fat_start = self.reserved_sectors
        self.root_dir_start = self.fat_start + self.num_fats * self.fat_size
        self.data_start = self.root_dir_start + self.root_dir_sectors

        if self.fat_size == 0 or self.data_start >= self.total_sectors:
            raise FatError("Boot sector describes an impossible geometry")

        clusters = ((self.total_sectors - self.data_start)
                    // self.sectors_per_cluster)
        self.cluster_count = clusters
        # The cluster count alone defines the FAT width -- this is the
        # Microsoft-documented rule, not a heuristic.
        if clusters < 4085:
            self.fat_bits = 12
        elif clusters < 65525:
            self.fat_bits = 16
        else:
            self.fat_bits = 32

        self.boot_sector = boot

    def __str__(self) -> str:
        return (f"FAT{self.fat_bits} "
                f"({self.cluster_count} clusters of "
                f"{self.sectors_per_cluster} sectors, "
                f"data at sector {self.data_start})")

    # -- cluster arithmetic -------------------------------------------------

    @property
    def end_of_chain(self) -> int:
        return {12: 0x0FF8, 16: 0xFFF8, 32: 0x0FFFFFF8}[self.fat_bits]

    def cluster_to_sector(self, cluster: int) -> int:
        return self.data_start + (cluster - 2) * self.sectors_per_cluster

    def _fat_entry(self, cluster: int) -> int:
        """Return the raw FAT entry for `cluster`, reading in 4 KiB blocks."""
        if self.fat_bits == 32:
            offset, width = cluster * 4, 4
        elif self.fat_bits == 16:
            offset, width = cluster * 2, 2
        else:
            offset, width = cluster + (cluster >> 1), 2

        base = self.fat_start * self.bytes_per_sector + offset
        # Cache blocks rather than sectors: a chain walk is sequential, and
        # every miss can cost a privileged read.
        block, within = divmod(base, 4096)
        chunk = self._fat_cache.get(block)
        if chunk is None:
            chunk = self._read(block * 4096, 4096 + 4)
            self._fat_cache[block] = chunk
        if within + width > len(chunk):
            raise FatError(f"FAT entry for cluster {cluster} is out of range")

        value = int.from_bytes(chunk[within:within + width], 'little')
        if self.fat_bits == 12:
            value = (value >> 4) if (cluster & 1) else (value & 0x0FFF)
        elif self.fat_bits == 32:
            value &= 0x0FFFFFFF
        return value

    def chain(self, first_cluster: int, max_clusters: int = 1 << 20) -> Iterator[int]:
        """Yield the clusters of a file, starting at `first_cluster`."""
        cluster = first_cluster
        seen = 0
        while 2 <= cluster < self.end_of_chain and seen < max_clusters:
            yield cluster
            seen += 1
            cluster = self._fat_entry(cluster)

    def sectors_of(self, first_cluster: int, count: int) -> List[int]:
        """Return the first `count` sectors holding a file, in order.

        Sector numbers are relative to the start of the volume, which is what
        the syslinux boot sector expects.
        """
        sectors: List[int] = []
        for cluster in self.chain(first_cluster):
            start = self.cluster_to_sector(cluster)
            for i in range(self.sectors_per_cluster):
                sectors.append(start + i)
                if len(sectors) == count:
                    return sectors
        return sectors

    # -- directory ----------------------------------------------------------

    def _root_dir_entries(self) -> Iterator[bytes]:
        """Yield the 32-byte entries of the root directory."""
        if self.fat_bits == 32:
            for cluster in self.chain(self.root_cluster):
                offset = (self.cluster_to_sector(cluster)
                          * self.bytes_per_sector)
                data = self._read(
                    offset,
                    self.sectors_per_cluster * self.bytes_per_sector)
                for i in range(0, len(data), _DIR_ENTRY_SIZE):
                    yield data[i:i + _DIR_ENTRY_SIZE]
        else:
            data = self._read(self.root_dir_start * self.bytes_per_sector,
                              self.root_dir_sectors * self.bytes_per_sector)
            for i in range(0, len(data), _DIR_ENTRY_SIZE):
                yield data[i:i + _DIR_ENTRY_SIZE]

    def find_in_root(self, short_name: str) -> Optional[Tuple[int, int]]:
        """Look up an 8.3 name (e.g. 'LDLINUX SYS') in the root directory.

        Returns (first cluster, size in bytes), or None if it is not there.
        Long-name entries are skipped: the installer writes the file itself
        and knows its short name.
        """
        wanted = short_name.encode('ascii')
        if len(wanted) != 11:
            raise ValueError("An 8.3 name must be exactly 11 characters")

        for entry in self._root_dir_entries():
            if len(entry) < _DIR_ENTRY_SIZE or entry[0] == _ENTRY_END:
                break
            if entry[0] == _ENTRY_FREE:
                continue
            attrs = entry[11]
            if attrs & _ATTR_LONG_NAME == _ATTR_LONG_NAME:
                continue
            if attrs & _ATTR_VOLUME_ID:
                continue
            if entry[0:11] != wanted:
                continue
            high, low = struct.unpack_from('<H', entry, 20)[0], \
                struct.unpack_from('<H', entry, 26)[0]
            size = struct.unpack_from('<I', entry, 28)[0]
            return ((high << 16) | low, size)
        return None
