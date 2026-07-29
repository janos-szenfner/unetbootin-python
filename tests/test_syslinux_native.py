"""Tests for the built-in syslinux installer and its FAT parser.

The installer writes a boot sector that a BIOS executes, so the checks here
are on the actual on-disk bytes: the sector map the boot code will follow,
the checksum it verifies before running, and the BPB it must not lose. The
volume is a FAT32 image built in memory, which lets a deliberately
fragmented ldlinux.sys be tested -- something a real filesystem driver will
not reliably produce on demand.
"""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from pynetboot.core import syslinux_native as native
from pynetboot.core.fat import FatVolume, FatError, SECTOR_SIZE
from pynetboot.resources import bootloader_path

BOOTLOADER = bootloader_path('')


def _payload(name):
    with open(bootloader_path(name), 'rb') as handle:
        return handle.read()


class FatImage:
    """A minimal FAT32 volume in memory, with one file placed by hand."""

    BYTES_PER_SECTOR = SECTOR_SIZE
    SECTORS_PER_CLUSTER = 1
    RESERVED = 32
    NUM_FATS = 2
    FAT_SECTORS = 600
    TOTAL_SECTORS = 70000
    ROOT_CLUSTER = 2

    def __init__(self):
        self.data = bytearray(self.TOTAL_SECTORS * SECTOR_SIZE)
        self.fat_start = self.RESERVED
        self.data_start = self.RESERVED + self.NUM_FATS * self.FAT_SECTORS
        self._write_boot_sector()
        self._set_fat(self.ROOT_CLUSTER, 0x0FFFFFFF)

    # -- construction ---------------------------------------------------

    def _write_boot_sector(self):
        boot = bytearray(SECTOR_SIZE)
        boot[0:3] = b'\xeb\x58\x90'
        boot[3:11] = b'PYNBTEST'
        struct.pack_into('<H', boot, 11, self.BYTES_PER_SECTOR)
        boot[13] = self.SECTORS_PER_CLUSTER
        struct.pack_into('<H', boot, 14, self.RESERVED)
        boot[16] = self.NUM_FATS
        struct.pack_into('<H', boot, 17, 0)          # no fixed root dir
        struct.pack_into('<H', boot, 19, 0)          # use the 32-bit count
        boot[21] = 0xF8
        struct.pack_into('<H', boot, 22, 0)          # FAT16 size unused
        struct.pack_into('<I', boot, 32, self.TOTAL_SECTORS)
        struct.pack_into('<I', boot, 36, self.FAT_SECTORS)
        struct.pack_into('<I', boot, 44, self.ROOT_CLUSTER)
        boot[510:512] = b'\x55\xaa'
        self.data[0:SECTOR_SIZE] = boot

    def _set_fat(self, cluster, value):
        for copy in range(self.NUM_FATS):
            offset = ((self.fat_start + copy * self.FAT_SECTORS)
                      * SECTOR_SIZE + cluster * 4)
            struct.pack_into('<I', self.data, offset, value)

    def cluster_offset(self, cluster):
        sector = self.data_start + (cluster - 2) * self.SECTORS_PER_CLUSTER
        return sector * SECTOR_SIZE

    def add_file(self, short_name, content, clusters):
        """Place `content` in the given clusters and add a root directory entry."""
        needed = -(-len(content) // (self.SECTORS_PER_CLUSTER * SECTOR_SIZE))
        assert len(clusters) >= needed, "not enough clusters for the file"

        per_cluster = self.SECTORS_PER_CLUSTER * SECTOR_SIZE
        for index, cluster in enumerate(clusters):
            chunk = content[index * per_cluster:(index + 1) * per_cluster]
            offset = self.cluster_offset(cluster)
            self.data[offset:offset + len(chunk)] = chunk
            self._set_fat(cluster,
                          clusters[index + 1] if index + 1 < len(clusters)
                          else 0x0FFFFFFF)

        entry = bytearray(32)
        entry[0:11] = short_name.encode('ascii')
        entry[11] = 0x20                                    # archive
        struct.pack_into('<H', entry, 20, clusters[0] >> 16)
        struct.pack_into('<H', entry, 26, clusters[0] & 0xFFFF)
        struct.pack_into('<I', entry, 28, len(content))

        root = self.cluster_offset(self.ROOT_CLUSTER)
        for slot in range(0, per_cluster, 32):
            if self.data[root + slot] == 0:
                self.data[root + slot:root + slot + 32] = entry
                return
        raise AssertionError("root directory is full")

    # -- device interface -----------------------------------------------

    def read(self, offset, length):
        return bytes(self.data[offset:offset + length])

    def write(self, offset, payload):
        self.data[offset:offset + len(payload)] = payload


class TestFatVolume(unittest.TestCase):
    def setUp(self):
        self.image = FatImage()

    def test_parses_geometry(self):
        volume = FatVolume(self.image.read)
        self.assertEqual(volume.fat_bits, 32)
        self.assertEqual(volume.data_start, self.image.data_start)
        self.assertEqual(volume.sectors_per_cluster, 1)

    def test_rejects_non_fat(self):
        self.image.data[510:512] = b'\x00\x00'
        with self.assertRaises(FatError):
            FatVolume(self.image.read)

    def test_finds_file_and_follows_a_fragmented_chain(self):
        clusters = [100, 101, 102, 500, 501, 900]
        content = bytes(range(256)) * 12                    # 3072 bytes
        self.image.add_file('TESTFILE   ', content, clusters)

        volume = FatVolume(self.image.read)
        found = volume.find_in_root('TESTFILE   ')
        self.assertIsNotNone(found)
        first_cluster, size = found
        self.assertEqual(first_cluster, 100)
        self.assertEqual(size, len(content))

        sectors = volume.sectors_of(first_cluster, 6)
        self.assertEqual(
            sectors, [volume.cluster_to_sector(c) for c in clusters])

    def test_missing_file(self):
        volume = FatVolume(self.image.read)
        self.assertIsNone(volume.find_in_root('NOTHERE SYS'))


class TestExtents(unittest.TestCase):
    def _decode(self, packed):
        out = []
        for i in range(0, len(packed), 10):
            lba, length = struct.unpack_from('<QH', packed, i)
            if length == 0:
                break
            out.append((lba, length))
        return out

    def test_consecutive_sectors_merge(self):
        packed = native.generate_extents([10, 11, 12, 13], 64)
        self.assertEqual(self._decode(packed), [(10, 4)])

    def test_gaps_start_a_new_extent(self):
        packed = native.generate_extents([10, 11, 40, 41, 42], 64)
        self.assertEqual(self._decode(packed), [(10, 2), (40, 3)])

    def test_extent_stops_at_64k(self):
        # 128 sectors is exactly 64 KiB, which the boot code cannot load in
        # one go, so the run has to be split.
        packed = native.generate_extents(list(range(1000, 1000 + 200)), 64)
        decoded = self._decode(packed)
        self.assertGreater(len(decoded), 1)
        self.assertTrue(all(length <= 127 for _lba, length in decoded))
        self.assertEqual(sum(length for _lba, length in decoded), 200)

    def test_too_fragmented_is_reported(self):
        scattered = list(range(0, 200, 2))               # no two adjacent
        with self.assertRaises(native.SyslinuxError):
            native.generate_extents(scattered, 8)

    def test_unused_pointers_are_zeroed(self):
        packed = native.generate_extents([5, 6], 64)
        self.assertEqual(len(packed), 64 * 10)
        self.assertEqual(packed[10:], b'\0' * (63 * 10))


class TestAdv(unittest.TestCase):
    def test_adv_is_consistent(self):
        adv = native.build_adv()
        self.assertEqual(len(adv), 2 * native.ADV_SIZE)
        self.assertEqual(adv[:512], adv[512:])
        self.assertEqual(struct.unpack_from('<I', adv, 0)[0], native.ADV_MAGIC1)
        self.assertEqual(struct.unpack_from('<I', adv, 508)[0],
                         native.ADV_MAGIC3)
        total = 0
        for i in range(4, 508, 4):
            total = (total + struct.unpack_from('<I', adv, i)[0]) & 0xFFFFFFFF
        self.assertEqual(total, native.ADV_MAGIC2)


class TestBootSector(unittest.TestCase):
    def test_bpb_is_preserved(self):
        existing = bytearray(range(256)) * 2
        existing[510:512] = b'\x55\xaa'
        template = bytes([0xAA]) * 512

        merged = native.merge_boot_sector(bytes(existing), template)
        self.assertEqual(merged[0:11], template[0:11])
        self.assertEqual(merged[11:90], bytes(existing[11:90]))
        self.assertEqual(merged[90:510], template[90:510])
        self.assertEqual(merged[510:512], b'\x55\xaa')

    def test_short_sector_is_rejected(self):
        with self.assertRaises(native.SyslinuxError):
            native.merge_boot_sector(b'\0' * 100, b'\0' * 512)


class TestNativeInstall(unittest.TestCase):
    """Install onto an in-memory volume and read back what a BIOS would."""

    def setUp(self):
        self.ldlinux = _payload('ldlinux.sys')
        self.bss = _payload('ldlinux.bss')
        self.image = FatImage()

        payload = native.file_payload(self.ldlinux)
        self.nsectors = -(-len(payload) // SECTOR_SIZE)
        # Deliberately fragmented: three runs with gaps between them.
        self.clusters = (list(range(10, 60)) + list(range(500, 560))
                         + list(range(900, 900 + self.nsectors - 110)))
        self.image.add_file('LDLINUX SYS', payload, self.clusters)
        self.original_bpb = bytes(self.image.data[11:90])

        native.install(self.image.read, self.image.write,
                       self.ldlinux, self.bss)

        self.volume = FatVolume(self.image.read)
        first, _size = self.volume.find_in_root('LDLINUX SYS')
        self.sectors = self.volume.sectors_of(first, self.nsectors)
        self.on_disk = b''.join(
            self.image.read(s * SECTOR_SIZE, SECTOR_SIZE) for s in self.sectors)
        self.boot = self.image.read(0, SECTOR_SIZE)

        patch_area = native._find_patch_area(self.on_disk)
        self.patch_area = patch_area
        epa_offset = struct.unpack_from(
            '<H', self.on_disk, patch_area + native._OFF_EPAOFFSET)[0]
        self.epa = native._read_epa(self.on_disk, epa_offset)

    def test_boot_sector_keeps_the_bpb(self):
        self.assertEqual(self.boot[11:90], self.original_bpb)
        self.assertEqual(self.boot[0:11], self.bss[0:11])
        self.assertEqual(self.boot[510:512], b'\x55\xaa')

    def test_boot_sector_points_at_the_first_sector(self):
        low = struct.unpack_from('<I', self.boot, self.epa['sect1ptr0'])[0]
        high = struct.unpack_from('<I', self.boot, self.epa['sect1ptr1'])[0]
        self.assertEqual(low, self.sectors[0])
        self.assertEqual(high, 0)

    def test_checksum_verifies(self):
        dwords = struct.unpack_from(
            '<I', self.on_disk, self.patch_area + native._OFF_DWORDS)[0]
        self.assertEqual(dwords, len(self.ldlinux) >> 2)
        total = native.LDLINUX_MAGIC
        for i in range(dwords):
            total = (total
                     - struct.unpack_from('<I', self.on_disk, i * 4)[0]
                     ) & 0xFFFFFFFF
        self.assertEqual(total, 0)

    def test_sector_counts(self):
        data_sectors, adv_sectors = struct.unpack_from(
            '<HH', self.on_disk, self.patch_area + native._OFF_DATA_SECTORS)
        self.assertEqual(data_sectors, self.nsectors - 2)
        self.assertEqual(adv_sectors, 2)

    def test_extents_describe_the_rest_of_the_file(self):
        listed = []
        offset = self.epa['secptroffset']
        for i in range(self.epa['secptrcnt']):
            lba, length = struct.unpack_from('<QH', self.on_disk,
                                             offset + i * 10)
            if length == 0:
                break
            listed.extend(range(lba, lba + length))
        self.assertEqual(listed, self.sectors[1:self.nsectors - 2])

    def test_adv_pointers_and_content(self):
        pointers = struct.unpack_from('<QQ', self.on_disk,
                                      self.epa['advptroffset'])
        self.assertEqual(list(pointers), self.sectors[self.nsectors - 2:])
        adv = self.on_disk[len(self.ldlinux):len(self.ldlinux) + 1024]
        self.assertEqual(adv, native.build_adv())

    def test_payload_outside_the_patch_is_untouched(self):
        dwords = struct.unpack_from(
            '<I', self.on_disk, self.patch_area + native._OFF_DWORDS)[0]
        tail = ((dwords * 4 + SECTOR_SIZE - 1) // SECTOR_SIZE) * SECTOR_SIZE
        self.assertEqual(self.on_disk[tail:len(self.ldlinux)],
                         self.ldlinux[tail:])

    def test_missing_file_is_reported(self):
        image = FatImage()
        with self.assertRaises(native.SyslinuxError):
            native.install(image.read, image.write, self.ldlinux, self.bss)

    def test_wrong_size_is_reported(self):
        image = FatImage()
        image.add_file('LDLINUX SYS', b'too short', [10])
        with self.assertRaises(native.SyslinuxError):
            native.install(image.read, image.write, self.ldlinux, self.bss)


class TestRawDevice(unittest.TestCase):
    """The dd path is what macOS and unprivileged Linux actually use."""

    def setUp(self):
        import tempfile

        self.image = FatImage()
        handle = tempfile.NamedTemporaryFile(prefix='pynetboot_test_',
                                             delete=False)
        handle.write(self.image.data)
        handle.close()
        self.path = handle.name
        self.addCleanup(os.unlink, self.path)

        # Run the dd commands directly instead of elevating them: the point
        # is the sector arithmetic and the temp-file plumbing around dd.
        import subprocess

        import pynetboot.core.elevation as elevation

        self.commands = []
        self._real = elevation.run_elevated

        def stub(command, timeout=None, **kwargs):
            self.commands.append(command)
            done = subprocess.run(command, capture_output=True, text=True)
            return (done.returncode, done.stdout, done.stderr)

        elevation.run_elevated = stub
        self.addCleanup(setattr, elevation, 'run_elevated', self._real)

    def test_reads_match_the_file_including_unaligned_ranges(self):
        with open(self.path, 'rb') as handle:
            with native.RawDevice(self.path, elevated=True) as device:
                for offset, length in [(0, 512), (11, 79), (4099, 4100),
                                       (1234567, 33)]:
                    handle.seek(offset)
                    self.assertEqual(device.read(offset, length),
                                     handle.read(length))
        first = self.commands[0]
        self.assertEqual(first[0], 'dd')
        self.assertIn(f'if={self.path}', first)
        self.assertIn('bs=512', first)

    def test_writes_land_at_the_right_offset(self):
        payload = bytes([0x5A]) * 1024
        with native.RawDevice(self.path, elevated=True) as device:
            device.write(8192, payload)
        with open(self.path, 'rb') as handle:
            handle.seek(8192)
            self.assertEqual(handle.read(1024), payload)

    def test_unaligned_writes_are_refused(self):
        with native.RawDevice(self.path, elevated=True) as device:
            with self.assertRaises(native.SyslinuxError):
                device.write(100, b'\0' * 512)
            with self.assertRaises(native.SyslinuxError):
                device.write(512, b'\0' * 100)

    def test_full_install_over_dd(self):
        ldlinux = _payload('ldlinux.sys')
        bss = _payload('ldlinux.bss')
        payload = native.file_payload(ldlinux)
        nsectors = -(-len(payload) // SECTOR_SIZE)

        image = FatImage()
        image.add_file('LDLINUX SYS', payload,
                       list(range(10, 10 + nsectors)))
        with open(self.path, 'wb') as handle:
            handle.write(image.data)

        with native.RawDevice(self.path, elevated=True) as device:
            native.install(device.read, device.write, ldlinux, bss)

        with open(self.path, 'rb') as handle:
            written = handle.read()
        # The boot sector must now be syslinux's, with the volume's own BPB.
        self.assertEqual(written[0:11], bss[0:11])
        self.assertEqual(written[11:90], bytes(image.data[11:90]))
        self.assertEqual(written[510:512], b'\x55\xaa')


class TestPartitionIndex(unittest.TestCase):
    """The boot flag has to land on the target's own partition table entry."""

    def setUp(self):
        from pynetboot.core.installer import USBInstaller

        self.index = USBInstaller._partition_index

    def test_partitions(self):
        for device, expected in [('/dev/sdb1', 1), ('/dev/sdc2', 2),
                                 ('/dev/nvme0n1p1', 1),
                                 ('/dev/mmcblk0p3', 3),
                                 ('/dev/disk4s1', 1), ('/dev/disk11s2', 2)]:
            self.assertEqual(self.index(device), expected, device)

    def test_whole_disks_have_no_index(self):
        # /dev/disk4 must not read as "partition 4".
        for device in ['/dev/sdb', '/dev/nvme0n1', '/dev/mmcblk0',
                       '/dev/disk4', 'D:', '', None]:
            self.assertIsNone(self.index(device), device)

    def test_out_of_range_is_rejected(self):
        # An MBR has four entries; a fifth is a logical partition.
        self.assertIsNone(self.index('/dev/sdb5'))


class TestBundledPayloads(unittest.TestCase):
    """The bundled files must be the ones the installer expects."""

    def test_ldlinux_has_a_patch_area(self):
        self.assertGreater(native._find_patch_area(_payload('ldlinux.sys')), 0)

    def test_boot_template_is_one_sector(self):
        bss = _payload('ldlinux.bss')
        self.assertEqual(len(bss), SECTOR_SIZE)
        self.assertEqual(bss[510:512], b'\x55\xaa')

    def test_menu_modules_are_present(self):
        for name in ('ldlinux.c32', 'libcom32.c32', 'libutil.c32',
                     'menu.c32', 'vesamenu.c32', 'mbr.bin'):
            self.assertTrue(bootloader_path(name).exists(), name)

    def test_uefi_payloads_are_present(self):
        for name in ('syslinux.efi', 'ldlinux.e64', 'menu.c32',
                     'libcom32.c32', 'libutil.c32'):
            self.assertTrue(
                bootloader_path(os.path.join('efi64', name)).exists(), name)

    def test_mbr_is_440_bytes(self):
        self.assertEqual(len(_payload('mbr.bin')), 440)


if __name__ == '__main__':
    unittest.main()
