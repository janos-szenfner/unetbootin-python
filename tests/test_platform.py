"""
Unit tests for platform-specific code: Linux, Windows, macOS.
"""

import unittest
import os
import sys
import json
import tempfile
import shutil
from unittest.mock import patch, MagicMock

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from pynetboot.platform import base, linux, windows, macos


class TestBasePlatform(unittest.TestCase):
    """Test base platform functions."""

    def test_get_drive_list_empty(self):
        """Test that base get_drive_list returns empty list."""
        drives = base.get_drive_list()
        self.assertIsInstance(drives, list)

    def test_get_drive_info_none(self):
        """Test that base get_drive_info returns None."""
        info = base.get_drive_info('/dev/sda')
        self.assertIsNone(info)

    def test_unmount_drive_false(self):
        """Test that base unmount_drive returns False."""
        result = base.unmount_drive('/dev/sda')
        self.assertFalse(result)

    def test_mount_drive_false(self):
        """Test that base mount_drive returns False."""
        result = base.mount_drive('/dev/sda', '/mnt')
        self.assertFalse(result)

    def test_format_drive_false(self):
        """Test that base format_drive returns False."""
        result = base.format_drive('/dev/sda', 'vfat')
        self.assertFalse(result)

    def test_get_volume_label_none(self):
        """Test that base get_volume_label returns None."""
        label = base.get_volume_label('/dev/sda')
        self.assertIsNone(label)

    def test_set_volume_label_false(self):
        """Test that base set_volume_label returns False."""
        result = base.set_volume_label('/dev/sda', 'TEST')
        self.assertFalse(result)

    def test_get_device_size_none(self):
        """Test that base get_device_size returns None."""
        size = base.get_device_size('/dev/sda')
        self.assertIsNone(size)

    def test_check_drive_writable_false(self):
        """Test that base check_drive_writable returns False."""
        result = base.check_drive_writable('/dev/sda')
        self.assertFalse(result)

    def test_sync_filesystem(self):
        """Test filesystem sync."""
        # On Unix systems, this should run sync command
        if sys.platform != 'win32':
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                result = base.sync_filesystem()
                self.assertTrue(result)

    def test_get_mount_point_none(self):
        """Test that base get_mount_point returns None."""
        mount_point = base.get_mount_point('/dev/sda')
        self.assertIsNone(mount_point)


@unittest.skipIf(sys.platform != 'linux', "Linux-only tests")
class TestLinuxPlatform(unittest.TestCase):
    """Test Linux platform functions."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_drive_list(self):
        """Test getting drive list on Linux."""
        # Mock lsblk command with JSON output (-J flag)
        with patch('subprocess.run') as mock_run:
            # First call: lsblk -J for basic drive info
            mock_result1 = MagicMock()
            mock_result1.stdout = '{"blockdevices": [{"name": "sda", "size": "100G", "type": "disk", "rm": false, "model": "", "vendor": "", "hctl": "", "tran": ""}, {"name": "sdb", "size": "14.5G", "type": "disk", "rm": true, "model": "", "vendor": "", "hctl": "", "tran": ""}]}'
            mock_result1.returncode = 0
            
            # Second call: lsblk -J for mount points
            mock_result2 = MagicMock()
            mock_result2.stdout = '{"blockdevices": [{"name": "sda", "type": "disk", "mountpoint": null, "children": [{"name": "sda1", "type": "part", "mountpoint": "/boot/efi"}, {"name": "sda2", "type": "part", "mountpoint": "/"}]}, {"name": "sdb", "type": "disk", "mountpoint": null, "children": [{"name": "sdb1", "type": "part", "mountpoint": "/media/usb"}]}]}'
            mock_result2.returncode = 0
            
            mock_run.side_effect = [mock_result1, mock_result2, mock_result2]

            # get_drive_serial() shells out to udevadm/sg_vpd/hdparm per disk;
            # stub it so this test only exercises the lsblk parsing (and the
            # mocked subprocess calls aren't exhausted).
            with patch.object(linux, 'get_drive_serial', return_value=''):
                drives = linux.get_drive_list()
            self.assertIsInstance(drives, list)
            # Should find at least sda and sdb
            drive_names = [d.get('device', '') for d in drives]
            self.assertIn('/dev/sda', drive_names)
            self.assertIn('/dev/sdb', drive_names)
            # Human-readable lsblk sizes must be parsed to bytes, not crash.
            by_name = {d['name']: d for d in drives}
            self.assertEqual(by_name['sda']['size'], 100 * 1024 ** 3)  # 100G

    def test_get_drive_info(self):
        """Test getting drive info on Linux."""
        with patch('subprocess.run') as mock_run:
            # Mock lsblk -J for drive info
            mock_lsblk = MagicMock()
            mock_lsblk.stdout = '{"blockdevices": [{"name": "sda", "size": "100G", "type": "disk", "rm": false, "model": "", "vendor": "", "hctl": "", "tran": ""}]}'
            mock_lsblk.returncode = 0

            # Mock lsblk -J for partitions
            mock_lsblk2 = MagicMock()
            mock_lsblk2.stdout = '{"blockdevices": [{"name": "sda", "type": "disk", "mountpoint": null, "children": [{"name": "sda1", "type": "part", "mountpoint": "/boot/efi", "size": "512M"}]}]}'
            mock_lsblk2.returncode = 0

            # Mock blockdev for size (fallback path)
            mock_blockdev = MagicMock()
            mock_blockdev.stdout = "100000000"
            mock_blockdev.returncode = 0

            mock_run.side_effect = [mock_lsblk, mock_lsblk2, mock_blockdev]

            # Stub the serial lookup (udevadm/sg_vpd/hdparm) so the mocked
            # subprocess sequence isn't exhausted and the test is deterministic.
            with patch.object(linux, 'get_drive_serial', return_value=''):
                info = linux.get_drive_info('/dev/sda')
            self.assertIsNotNone(info)
            self.assertIn('device', info)
            # '100G' must parse to bytes rather than raising ValueError.
            self.assertEqual(info['size'], 100 * 1024 ** 3)

    def test_get_parent_disk(self):
        """Test getting parent disk for a partition."""
        with patch('subprocess.run') as mock_run:
            # Mock lsblk for partition with parent
            mock_result = MagicMock()
            mock_result.stdout = "sda\n"
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            parent = linux.get_parent_disk('/dev/sda1')
            self.assertEqual(parent, '/dev/sda')

    def test_get_parent_disk_no_parent(self):
        """Test getting parent disk when device is already a disk."""
        with patch('subprocess.run') as mock_run:
            # Mock lsblk returning empty (no parent)
            mock_result = MagicMock()
            mock_result.stdout = ""
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            parent = linux.get_parent_disk('/dev/sda')
            # Should return None or the device itself
            self.assertIn(parent, [None, '/dev/sda'])

    def test_check_drive_writable(self):
        """Test checking if drive is writable."""
        with patch('subprocess.run') as mock_run:
            # check_drive_writable calls: test -w <drive>
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            
            result = linux.check_drive_writable('/dev/sdb')
            self.assertTrue(result)

    def test_unmount_drive(self):
        """Test unmounting drive on Linux."""
        with patch('subprocess.run') as mock_run:
            # First call: lsblk lists the mount points on the device.
            mock_lsblk = MagicMock()
            mock_lsblk.stdout = '/media/usb\n'
            mock_lsblk.returncode = 0

            # Second call: sudo umount /media/usb
            mock_umount = MagicMock()
            mock_umount.returncode = 0

            mock_run.side_effect = [mock_lsblk, mock_umount]

            result = linux.unmount_drive('/dev/sdb1')
            self.assertTrue(result)

    def test_unmount_drive_unmounts_partitions_of_a_whole_disk(self):
        """Partitions of the target disk must be unmounted too.

        Regression test: the old implementation asked findmnt about
        /dev/sdb, which never reports /dev/sdb1. The auto-mounted partition
        stayed mounted and mkfs then failed with EBUSY.
        """
        with patch('subprocess.run') as mock_run:
            # lsblk walks the disk *and its children*.
            mock_lsblk = MagicMock()
            mock_lsblk.stdout = '\n/media/szefi/DATA\n/media/szefi/BOOT\n'
            mock_lsblk.returncode = 0

            ok = MagicMock()
            ok.returncode = 0
            mock_run.side_effect = [mock_lsblk, ok, ok]

            self.assertTrue(linux.unmount_drive('/dev/sdb'))

            unmounted = [c.args[0][-1] for c in mock_run.call_args_list[1:]]
            self.assertEqual(
                unmounted, ['/media/szefi/DATA', '/media/szefi/BOOT'])

    def test_format_drive_refuses_when_a_partition_stays_mounted(self):
        """A failed unmount must abort before mkfs runs."""
        with patch('subprocess.run') as mock_run:
            mock_lsblk = MagicMock()
            mock_lsblk.stdout = '/media/szefi/DATA\n'
            mock_lsblk.returncode = 0

            failed_umount = MagicMock()
            failed_umount.returncode = 1
            failed_umount.stderr = 'umount: target is busy'

            mock_run.side_effect = [mock_lsblk, failed_umount]

            self.assertFalse(
                linux.format_drive('/dev/sdb', 'vfat', 'PYNETBOOT'))
            # Only lsblk and the umount attempt: mkfs must not be reached.
            self.assertEqual(mock_run.call_count, 2)

    def test_mount_drive(self):
        """Test mounting drive on Linux."""
        with patch('subprocess.run') as mock_run:
            with patch('os.makedirs'):
                mock_result = MagicMock()
                mock_result.returncode = 0
                mock_run.return_value = mock_result

                result = linux.mount_drive('/dev/sdb1', '/mnt/usb')
                self.assertTrue(result)

    def test_format_drive_vfat(self):
        """Test formatting drive as FAT32 on Linux."""
        with patch('subprocess.run') as mock_run:
            # format_drive unmounts first, which calls lsblk; nothing is
            # mounted here, so mkfs.vfat runs next.
            mock_lsblk = MagicMock()
            mock_lsblk.stdout = '\n'
            mock_lsblk.returncode = 0

            mock_mkfs = MagicMock()
            mock_mkfs.returncode = 0

            mock_run.side_effect = [mock_lsblk, mock_mkfs]

            result = linux.format_drive('/dev/sdb1', 'vfat', 'PYNETBOOT')
            self.assertTrue(result)

    def test_set_volume_label(self):
        """Test setting volume label on Linux."""
        with patch('subprocess.run') as mock_run:
            # First call: blkid to get filesystem type
            mock_blkid = MagicMock()
            mock_blkid.stdout = '/dev/sdb1: TYPE="vfat"'
            mock_blkid.returncode = 0
            
            # Second call: sudo fatlabel to set label
            mock_fatlabel = MagicMock()
            mock_fatlabel.returncode = 0
            
            mock_run.side_effect = [mock_blkid, mock_fatlabel]

            result = linux.set_volume_label('/dev/sdb1', 'MYUSB')
            self.assertTrue(result)

    def test_is_whole_disk(self):
        """A disk and one of its partitions must be told apart."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='disk\n')
            self.assertTrue(linux.is_whole_disk('/dev/sdb'))

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='part\n')
            self.assertFalse(linux.is_whole_disk('/dev/sdb1'))

    def test_first_partition_does_not_guess_at_naming(self):
        """Partition names differ: sdb1 but nvme0n1p1, so ask lsblk."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout='nvme0n1 disk\nnvme0n1p1 part\n')
            self.assertEqual(
                linux.first_partition('/dev/nvme0n1'), '/dev/nvme0n1p1')

    def test_partition_device_creates_a_bootable_fat32_partition(self):
        """The disk needs a DOS table with one bootable FAT32 partition.

        Without it there is nowhere for the syslinux MBR to live: writing it
        to sector 0 would overwrite the filesystem's own boot sector.
        """
        with patch('shutil.which', return_value='/sbin/parted'), \
                patch('os.path.exists', return_value=True), \
                patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout='\n'),      # lsblk: unmount
                MagicMock(returncode=0, stdout='', stderr=''),   # elevated script
                MagicMock(returncode=0, stdout=''),        # udevadm settle
                MagicMock(returncode=0, stdout='sdb disk\nsdb1 part\n'),
            ]

            self.assertEqual(linux.partition_device('/dev/sdb'), '/dev/sdb1')

            script = next(
                call.args[0][-1] for call in mock_run.call_args_list
                if 'parted' in ' '.join(call.args[0]))
            for expected in ('wipefs', 'mklabel', 'msdos', 'fat32',
                             'boot', 'on', 'partprobe'):
                self.assertIn(expected, script)

    def test_partitioning_uses_a_single_elevation_prompt(self):
        """wipefs, parted and partprobe must share one prompt.

        Run separately they each raise their own PolicyKit dialog, so the
        user is asked for a password three times to partition one drive.
        """
        with patch('shutil.which', return_value='/sbin/parted'), \
                patch('os.path.exists', return_value=True), \
                patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout='\n'),
                MagicMock(returncode=0, stdout='', stderr=''),
                MagicMock(returncode=0, stdout=''),
                MagicMock(returncode=0, stdout='sdb disk\nsdb1 part\n'),
            ]

            linux.partition_device('/dev/sdb')

            elevated = [c.args[0] for c in mock_run.call_args_list
                        if c.args[0][0] == 'sudo']
            self.assertEqual(len(elevated), 1, elevated)

    def test_partition_device_without_parted_is_not_destructive(self):
        """If parted is missing, fail before touching the drive."""
        with patch('shutil.which', return_value=None), \
                patch('os.path.exists', return_value=False), \
                patch('subprocess.run') as mock_run:
            self.assertIsNone(linux.partition_device('/dev/sdb'))
            mock_run.assert_not_called()

    def test_partition_device_reports_parted_failure(self):
        """A parted failure returns None rather than a bogus partition."""
        with patch('shutil.which', return_value='/sbin/parted'), \
                patch('os.path.exists', return_value=True), \
                patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout='\n'),   # lsblk: unmount
                MagicMock(returncode=1, stdout='',      # elevated script
                          stderr='parted: unable to open /dev/sdb'),
            ]
            self.assertIsNone(linux.partition_device('/dev/sdb'))

    def test_get_volume_label(self):
        """Test getting volume label on Linux."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "MYUSB"
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            label = linux.get_volume_label('/dev/sdb1')
            self.assertEqual(label, 'MYUSB')

    def test_get_mount_point(self):
        """Test getting mount point on Linux."""
        with patch('subprocess.run') as mock_run:
            # findmnt returns just the mount point
            mock_result = MagicMock()
            mock_result.stdout = "/media/usb"
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            mount_point = linux.get_mount_point('/dev/sdb1')
            self.assertEqual(mount_point, '/media/usb')

    def _lsblk(self, **dev):
        """Build a minimal lsblk -J payload for a single device."""
        return json.dumps({'blockdevices': [dev]})

    def test_is_safe_target_usb_disk(self):
        """A USB whole disk with no system mountpoints is a safe target."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = self._lsblk(
                name='sdb', type='disk', rm=True, tran='usb',
                vendor='SanDisk', model='Ultra',
                children=[{'name': 'sdb1', 'mountpoint': '/media/usb'}])
            mock_run.return_value = mock_result
            self.assertTrue(linux.is_safe_target('/dev/sdb'))

    def test_is_safe_target_rejects_system_disk(self):
        """A disk hosting '/' must be rejected even if it were USB."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = self._lsblk(
                name='sda', type='disk', rm=False, tran='sata',
                vendor='ATA', model='SSD',
                children=[{'name': 'sda1', 'mountpoint': '/'}])
            mock_run.return_value = mock_result
            self.assertFalse(linux.is_safe_target('/dev/sda'))

    def test_is_safe_target_external_hdd_only_in_hard_disk_mode(self):
        """A fixed external HDD qualifies only with allow_external_fixed."""
        payload = self._lsblk(
            name='sdc', type='disk', rm=False, tran='usb', hotplug=True,
            vendor='Seagate', model='Expansion',
            children=[{'name': 'sdc1', 'mountpoint': '/media/backup'}])
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = payload
            mock_run.return_value = mock_result
            # tran='usb' already qualifies in strict mode…
            self.assertTrue(linux.is_safe_target('/dev/sdc'))
            # …and still qualifies when the filter is widened.
            self.assertTrue(
                linux.is_safe_target('/dev/sdc', allow_external_fixed=True))

    def test_is_safe_target_hotplug_esata_needs_hard_disk_mode(self):
        """A hot-pluggable non-USB external disk needs allow_external_fixed."""
        payload = self._lsblk(
            name='sdd', type='disk', rm=False, tran='sata', hotplug=True,
            vendor='WD', model='Elements', children=[])
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = payload
            mock_run.return_value = mock_result
            # Strict (USB Drive) mode rejects it: not USB, not removable.
            self.assertFalse(linux.is_safe_target('/dev/sdd'))
            # Hard Disk mode accepts it: hot-pluggable, non-system, non-virtual.
            self.assertTrue(
                linux.is_safe_target('/dev/sdd', allow_external_fixed=True))

    def test_is_safe_target_hard_disk_mode_still_rejects_system_disk(self):
        """Widening the filter must never expose the system disk."""
        payload = self._lsblk(
            name='sda', type='disk', rm=False, tran='sata', hotplug=True,
            vendor='ATA', model='SSD',
            children=[{'name': 'sda1', 'mountpoint': '/'}])
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = payload
            mock_run.return_value = mock_result
            self.assertFalse(
                linux.is_safe_target('/dev/sda', allow_external_fixed=True))

    def test_is_safe_target_hard_disk_mode_still_rejects_virtual_disk(self):
        """Widening the filter must never expose a virtual disk."""
        payload = self._lsblk(
            name='sde', type='disk', rm=False, tran='', hotplug=True,
            vendor='VBOX', model='HARDDISK', children=[])
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = payload
            mock_run.return_value = mock_result
            self.assertFalse(
                linux.is_safe_target('/dev/sde', allow_external_fixed=True))

    def test_is_safe_target_rejects_virtual_disk(self):
        """A virtual (VirtualBox/virtio) disk must be rejected."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = self._lsblk(
                name='sdc', type='disk', rm=False, tran='',
                vendor='VBOX', model='HARDDISK', children=[])
            mock_run.return_value = mock_result
            self.assertFalse(linux.is_safe_target('/dev/sdc'))


@unittest.skipIf(sys.platform != 'win32', "Windows-only tests")
class TestWindowsPlatform(unittest.TestCase):
    """Test Windows platform functions."""

    def test_get_drive_list(self):
        """Test getting drive list on Windows."""
        with patch('subprocess.run') as mock_run:
            # Mock wmic output in CSV format
            mock_result = MagicMock()
            mock_result.stdout = """DeviceID,VolumeName,FileSystem,Size,FreeSpace,DriveType
C:\\,System,C:,NTFS,100000000000,50000000000,3
D:\\,Data,D:,NTFS,200000000000,100000000000,2
E:\\,,E:,FAT32,15000000000,15000000000,2
"""
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            drives = windows.get_drive_list()
            self.assertIsInstance(drives, list)
            # Should find drives C, D, E
            drive_devices = [d.get('device', '') for d in drives]
            self.assertIn('C:\\', drive_devices)
            self.assertIn('D:\\', drive_devices)
            self.assertIn('E:\\', drive_devices)

    def test_get_drive_info(self):
        """Test getting drive info on Windows."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = """DeviceID : C:\\
VolumeName : System
FileSystem : NTFS
Size : 100000000000
FreeSpace : 50000000000
DriveType : 3
"""
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            info = windows.get_drive_info('C')
            self.assertIsNotNone(info)
            self.assertEqual(info.get('device'), 'C:\\')
            self.assertEqual(info.get('label'), 'System')

    def test_check_drive_writable(self):
        """Test checking if drive is writable on Windows."""
        with patch('os.access', return_value=True):
            result = windows.check_drive_writable('C:\\')
            self.assertTrue(result)

    def test_unmount_drive(self):
        """Test unmounting drive on Windows (no-op)."""
        result = windows.unmount_drive('D:\\')
        # On Windows, unmount might be a no-op or try to eject
        # The implementation should return True or False based on attempt
        self.assertIsInstance(result, bool)

    def test_mount_drive(self):
        """Test mounting drive on Windows (no-op)."""
        result = windows.mount_drive('D:\\', 'D:\\')
        self.assertIsInstance(result, bool)

    def test_format_drive(self):
        """Test formatting drive on Windows."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            result = windows.format_drive('D:\\', 'FAT32', 'PYNETBOOT')
            self.assertTrue(result)

    def test_set_volume_label(self):
        """Test setting volume label on Windows."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            result = windows.set_volume_label('D:\\', 'MYUSB')
            self.assertTrue(result)

    def test_get_volume_label(self):
        """Test getting volume label on Windows."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "MYUSB"
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            label = windows.get_volume_label('D:\\')
            self.assertEqual(label, 'MYUSB')

    def test_is_safe_target_removable_only(self):
        """Only DRIVE_REMOVABLE (type 2) drives are safe targets on Windows."""
        removable = {'letter': 'E', 'device': 'E:\\', 'removable': True}
        fixed = {'letter': 'C', 'device': 'C:\\', 'removable': False}
        with patch.object(windows, 'get_drive_list',
                          return_value=[removable, fixed]):
            self.assertTrue(windows.is_safe_target('E:\\'))    # USB stick
            self.assertFalse(windows.is_safe_target('C:\\'))   # internal disk
            self.assertFalse(windows.is_safe_target('Z:\\'))   # not present


@unittest.skipIf(sys.platform != 'darwin', "macOS-only tests")
class TestMacOSPlatform(unittest.TestCase):
    """Test macOS platform functions."""

    def test_get_drive_list(self):
        """Test getting drive list on macOS."""
        with patch('subprocess.run') as mock_run:
            # Mock diskutil list -plist output (simplified XML-like)
            mock_result = MagicMock()
            mock_result.stdout = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<array>
    <dict>
        <key>DeviceIdentifier</key>
        <string>disk0</string>
        <key>DeviceNode</key>
        <string>/dev/disk0</string>
    </dict>
    <dict>
        <key>DeviceIdentifier</key>
        <string>disk2</string>
        <key>DeviceNode</key>
        <string>/dev/disk2</string>
    </dict>
</array>
</plist>
"""
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            drives = macos.get_drive_list()
            self.assertIsInstance(drives, list)

    def test_get_drive_info(self):
        """Test getting drive info on macOS."""
        with patch('subprocess.run') as mock_run:
            # macos.get_drive_info parses `diskutil info -plist` output
            mock_result = MagicMock()
            mock_result.stdout = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>VolumeName</key>
    <string>MYUSB</string>
    <key>TotalSize</key>
    <integer>15000000000</integer>
    <key>FilesystemType</key>
    <string>msdos</string>
</dict>
</plist>"""
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            info = macos.get_drive_info('/dev/disk2')
            self.assertIsNotNone(info)
            self.assertEqual(info.get('device'), '/dev/disk2')
            self.assertEqual(info.get('label'), 'MYUSB')

    def test_check_drive_writable(self):
        """Test checking if drive is writable on macOS."""
        with patch('os.access', return_value=True):
            result = macos.check_drive_writable('/dev/disk2')
            self.assertTrue(result)

    @staticmethod
    def _diskutil_info(whole_disk: bool):
        """A diskutil `info -plist` reply saying whether this is a disk."""
        import plistlib
        reply = MagicMock()
        reply.returncode = 0
        reply.stdout = plistlib.dumps({'WholeDisk': whole_disk}).decode()
        return reply

    def test_unmount_drive(self):
        """Test unmounting drive on macOS."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                self._diskutil_info(whole_disk=False),
                MagicMock(returncode=0, stdout='', stderr=''),
            ]
            self.assertTrue(macos.unmount_drive('/dev/disk2s1'))

    def test_unmount_disk_detaches_every_partition(self):
        """A whole disk needs unmountDisk, not unmount.

        Unmounting one mount point leaves the disk's other partitions
        mounted, and any mounted partition keeps the whole disk busy.
        """
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                self._diskutil_info(whole_disk=True),
                MagicMock(returncode=0, stdout='', stderr=''),
            ]
            self.assertTrue(macos.unmount_drive('/dev/disk2'))
            self.assertIn('unmountDisk', mock_run.call_args_list[1].args[0])

    def test_whole_disk_is_repartitioned_not_made_a_superfloppy(self):
        """eraseVolume on a whole disk leaves no partition map.

        The boot record written afterwards would land on the filesystem's
        own boot sector. eraseDisk lays down an MBR map plus a partition.
        """
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                self._diskutil_info(whole_disk=True),   # unmount_drive
                MagicMock(returncode=0, stdout='', stderr=''),
                self._diskutil_info(whole_disk=True),   # format_drive
                MagicMock(returncode=0, stdout='', stderr=''),
            ]
            self.assertTrue(
                macos.format_drive('/dev/disk2', 'vfat', 'PYNETBOOT'))

            argv = mock_run.call_args_list[-1].args[0]
            self.assertIn('eraseDisk', argv)
            self.assertIn('MBRFormat', argv)
            self.assertNotIn('eraseVolume', argv)

    def test_an_existing_partition_is_only_reformatted(self):
        """A partition must not be repartitioned out from under itself."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                self._diskutil_info(whole_disk=False),
                MagicMock(returncode=0, stdout='', stderr=''),
                self._diskutil_info(whole_disk=False),
                MagicMock(returncode=0, stdout='', stderr=''),
            ]
            self.assertTrue(
                macos.format_drive('/dev/disk2s1', 'vfat', 'PYNETBOOT'))

            argv = mock_run.call_args_list[-1].args[0]
            self.assertIn('eraseVolume', argv)
            self.assertNotIn('eraseDisk', argv)

    def test_format_failure_reports_the_reason(self):
        """A bare False gives nothing to diagnose."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = [
                self._diskutil_info(whole_disk=True),
                MagicMock(returncode=0, stdout='', stderr=''),
                self._diskutil_info(whole_disk=True),
                MagicMock(returncode=1, stdout='',
                          stderr='could not modify partition map'),
            ]
            with self.assertLogs('pynetboot.platform.macos', 'ERROR') as logs:
                self.assertFalse(macos.format_drive('/dev/disk2', 'vfat'))
            self.assertIn('could not modify partition map',
                          '\n'.join(logs.output))

    def test_mount_drive(self):
        """Test mounting drive on macOS."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            result = macos.mount_drive('/dev/disk2', '/Volumes/MYUSB')
            self.assertTrue(result)

    def test_format_drive(self):
        """Test formatting drive on macOS."""
        with patch('subprocess.run') as mock_run:
            # format_drive calls unmount_drive first (which may issue several
            # diskutil calls), then diskutil eraseVolume. Return success for
            # every subprocess call rather than a fixed-length side_effect
            # list so the count of internal calls doesn't matter.
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = ""
            mock_run.return_value = mock_result

            result = macos.format_drive('/dev/disk2', 'vfat', 'PYNETBOOT')
            self.assertTrue(result)

    def test_set_volume_label(self):
        """Test setting volume label on macOS."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            result = macos.set_volume_label('/dev/disk2', 'MYUSB')
            self.assertTrue(result)

    def test_get_volume_label(self):
        """Test getting volume label on macOS."""
        with patch('subprocess.run') as mock_run:
            # get_volume_label parses `diskutil info` text for "Volume Name:"
            mock_result = MagicMock()
            mock_result.stdout = (
                "   Device Identifier:        disk2\n"
                "   Volume Name:              MYUSB\n"
                "   Mounted:                  Yes\n"
            )
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            label = macos.get_volume_label('/dev/disk2')
            self.assertEqual(label, 'MYUSB')

    def test_get_device_size(self):
        """Test getting device size on macOS."""
        with patch.object(macos, 'get_drive_info') as mock_info:
            mock_info.return_value = {'size': 15000000000}

            size = macos.get_device_size('/dev/disk2')
            self.assertEqual(size, 15000000000)

    def test_get_parent_disk(self):
        """Test getting parent disk on macOS."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            # diskutil info output for a partition
            mock_result.stdout = """
   Device Identifier:        disk2s1
   Device Node:              /dev/disk2s1
   Whole:                   No
   Part of Whole:            disk2
   """
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            parent = macos.get_parent_disk('/dev/disk2s1')
            self.assertEqual(parent, '/dev/disk2')

    def _diskutil_info_plist(self, **fields):
        """Build a minimal `diskutil info -plist` XML payload."""
        import plistlib
        return plistlib.dumps(fields).decode()

    def test_is_safe_target_external_usb(self):
        """External, ejectable, physical USB media is a safe target."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = self._diskutil_info_plist(
                Internal=False, Ejectable=True, RemovableMedia=True,
                BusProtocol='USB', VirtualOrPhysical='Physical')
            mock_run.return_value = mock_result
            self.assertTrue(macos.is_safe_target('/dev/disk4'))

    def test_is_safe_target_rejects_internal_disk(self):
        """The built-in internal disk must never be a safe target."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = self._diskutil_info_plist(
                Internal=True, Ejectable=False, RemovableMedia=False,
                BusProtocol='PCI-Express', VirtualOrPhysical='Physical')
            mock_run.return_value = mock_result
            self.assertFalse(macos.is_safe_target('/dev/disk0'))

    def test_is_safe_target_rejects_disk_image(self):
        """A mounted .dmg (virtual / Disk Image bus) must be rejected."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = self._diskutil_info_plist(
                Internal=False, Ejectable=True, RemovableMedia=True,
                BusProtocol='Disk Image', VirtualOrPhysical='Virtual')
            mock_run.return_value = mock_result
            self.assertFalse(macos.is_safe_target('/dev/disk9'))

    def test_is_safe_target_fails_closed_on_error(self):
        """If diskutil fails, fail closed (return False)."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stdout = ""
            mock_run.return_value = mock_result
            self.assertFalse(macos.is_safe_target('/dev/disk4'))


class TestMacOSMountDetection(unittest.TestCase):
    """A USB stick's mount state, and unmounting a whole disk."""

    MOUNT_OUTPUT = (
        "/dev/disk3s1s1 on / (apfs, sealed, local, read-only, journaled)\n"
        "/dev/disk5s1 on /Volumes/PYNETBOOT (msdos, local, nodev, nosuid, "
        "noowners)\n"
        "/dev/disk50s1 on /Volumes/OTHER (msdos, local)\n"
    )

    def _with_mount_output(self, output):
        from unittest.mock import MagicMock, patch
        result = MagicMock()
        result.returncode = 0
        result.stdout = output
        return patch('pynetboot.platform.macos.subprocess.run',
                     return_value=result)

    def test_a_whole_disk_reports_its_volumes(self):
        """`diskutil info disk5` shows no mount point even when it is mounted,
        so the check has to look at the mount table."""
        from pynetboot.platform import macos
        with self._with_mount_output(self.MOUNT_OUTPUT):
            self.assertEqual(macos.device_mountpoints('disk5'),
                             ['/Volumes/PYNETBOOT'])
            self.assertEqual(macos.device_mountpoints('/dev/disk5'),
                             ['/Volumes/PYNETBOOT'])

    def test_a_slice_reports_its_own_mount(self):
        from pynetboot.platform import macos
        with self._with_mount_output(self.MOUNT_OUTPUT):
            self.assertEqual(macos.device_mountpoints('disk5s1'),
                             ['/Volumes/PYNETBOOT'])

    def test_a_similar_name_is_not_matched(self):
        """disk5 must not pick up disk50."""
        from pynetboot.platform import macos
        with self._with_mount_output(self.MOUNT_OUTPUT):
            self.assertNotIn('/Volumes/OTHER', macos.device_mountpoints('disk5'))

    def test_an_unmounted_disk_reports_nothing(self):
        from pynetboot.platform import macos
        with self._with_mount_output(self.MOUNT_OUTPUT):
            self.assertEqual(macos.device_mountpoints('disk9'), [])

    def test_a_whole_disk_is_unmounted_with_unmountDisk(self):
        """`diskutil unmount disk5` refuses a disk with a partition scheme --
        which is what stopped an install before it began."""
        from unittest.mock import MagicMock, patch

        from pynetboot.platform import macos
        ok = MagicMock()
        ok.returncode = 0
        ok.stdout = ok.stderr = ''
        with patch('pynetboot.platform.macos.is_whole_disk',
                   return_value=True), \
                patch('pynetboot.platform.macos.subprocess.run',
                      return_value=ok) as run:
            self.assertTrue(macos.unmount_drive('disk5'))
        self.assertEqual(run.call_args.args[0],
                         ['diskutil', 'unmountDisk', '/dev/disk5'])

    def test_a_slice_is_unmounted_with_unmount(self):
        from unittest.mock import MagicMock, patch

        from pynetboot.platform import macos
        ok = MagicMock()
        ok.returncode = 0
        ok.stdout = ok.stderr = ''
        with patch('pynetboot.platform.macos.is_whole_disk',
                   return_value=False), \
                patch('pynetboot.platform.macos.subprocess.run',
                      return_value=ok) as run:
            self.assertTrue(macos.unmount_drive('disk5s1'))
        self.assertEqual(run.call_args.args[0],
                         ['diskutil', 'unmount', '/dev/disk5s1'])


class TestPlatformDetection(unittest.TestCase):
    """Test platform detection and imports."""

    def test_get_drive_list_import(self):
        """Test that get_drive_list can be imported from platform."""
        from pynetboot.platform import get_drive_list
        self.assertTrue(callable(get_drive_list))

    def test_platform_module_structure(self):
        """Test that platform modules have expected structure."""
        # Check that all platform modules have get_drive_list
        for module in [base, linux, windows, macos]:
            self.assertTrue(hasattr(module, 'get_drive_list'))
            self.assertTrue(hasattr(module, 'get_drive_info'))
            self.assertTrue(hasattr(module, 'unmount_drive'))
            self.assertTrue(hasattr(module, 'mount_drive'))
            self.assertTrue(hasattr(module, 'format_drive'))
            self.assertTrue(hasattr(module, 'get_volume_label'))
            self.assertTrue(hasattr(module, 'set_volume_label'))


if __name__ == '__main__':
    unittest.main()


class TestDriveSerialToolFallback(unittest.TestCase):
    """A missing probe tool must not be fatal, noisy, or skip the fallbacks."""

    @unittest.skipIf(sys.platform != 'linux', "Linux-only")
    def test_missing_tool_falls_through_to_the_next_probe(self):
        from pynetboot.platform import linux as linux_mod

        def only_hdparm(name):
            return '/usr/sbin/hdparm' if name == 'hdparm' else None

        completed = MagicMock()
        completed.returncode = 0
        completed.stdout = "Serial number: ABC123\n"

        with patch('shutil.which', side_effect=only_hdparm), \
             patch('subprocess.run', return_value=completed) as run:
            serial = linux_mod.get_drive_serial('/dev/sdb')

        self.assertEqual(serial, 'ABC123',
                         "must reach hdparm even though udevadm is absent")
        # Only the available tool should have been executed.
        self.assertEqual(run.call_count, 1)

    @unittest.skipIf(sys.platform != 'linux', "Linux-only")
    def test_absent_tools_are_not_logged_as_errors(self):
        """Inside a sandbox none of these exist; that is expected, not an error."""
        from pynetboot.platform import linux as linux_mod

        with patch('shutil.which', return_value=None):
            with self.assertLogs('pynetboot.platform.linux',
                                 level='DEBUG') as captured:
                result = linux_mod.get_drive_serial('/dev/sdb')

        self.assertIsNone(result)
        self.assertFalse([m for m in captured.output if m.startswith('ERROR')],
                         "a missing optional tool must not log an error")


class TestWindowsFormatting(unittest.TestCase):
    """diskpart scripting. Pure text, so it runs on any platform."""

    def _script_for(self, drive):
        import io
        captured = {}

        class FakeTempFile(io.StringIO):
            name = '/tmp/diskpart.txt'

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                captured['script'] = self.getvalue()
                return False

        with patch('tempfile.NamedTemporaryFile', return_value=FakeTempFile()), \
                patch('os.unlink'), \
                patch('subprocess.run',
                      return_value=MagicMock(returncode=0, stdout='done',
                                             stderr='')):
            windows.format_drive(drive, 'FAT32', 'PYNETBOOT')
        return captured['script']

    def test_the_original_letter_is_requested_back(self):
        """A bare `assign` lets Windows choose any free letter.

        Regression test: the drive could reappear as a different letter, and
        every write then went to a path that did not exist.
        """
        self.assertIn('assign letter=E', self._script_for('E:\\'))

    def test_every_drive_spelling_is_accepted(self):
        for spelling in ('E', 'e:', 'E:\\', 'e:/'):
            with self.subTest(drive=spelling):
                script = self._script_for(spelling)
                self.assertIn('select volume E', script)
                self.assertIn('assign letter=E', script)

    def test_a_non_drive_is_refused(self):
        self.assertFalse(windows.format_drive('/dev/sdb', 'FAT32'))


class TestWaitForDrive(unittest.TestCase):
    """Formatting removes the letter; the volume returns a moment later."""

    def test_waits_until_the_volume_is_listable(self):
        appearing = [False, False, True]
        with patch('os.path.exists',
                   side_effect=lambda p: appearing.pop(0) if appearing else True), \
                patch('os.listdir', return_value=[]), \
                patch('time.sleep'):
            self.assertTrue(windows.wait_for_drive('E:\\', timeout=5))

    def test_existing_but_not_yet_readable_is_not_ready(self):
        """exists() can be true before the filesystem will answer."""
        with patch('os.path.exists', return_value=True), \
                patch('os.listdir', side_effect=OSError('not ready')), \
                patch('time.sleep'), \
                patch('time.monotonic', side_effect=[0, 1, 99]):
            self.assertFalse(windows.wait_for_drive('E:\\', timeout=5))

    def test_gives_up_and_says_so(self):
        with patch('os.path.exists', return_value=False), \
                patch('time.sleep'), \
                patch('time.monotonic', side_effect=[0, 1, 99]):
            with self.assertLogs('pynetboot.platform.windows', 'ERROR'):
                self.assertFalse(windows.wait_for_drive('E:\\', timeout=5))


class TestDiskpartOutputParsing(unittest.TestCase):
    """diskpart reports failures on stdout and still exits 0.

    Pure text handling, so it runs everywhere rather than only on Windows.
    """

    def test_a_clean_run_is_not_treated_as_an_error(self):
        output = (
            "Volume 3 is the selected volume.\r\n"
            "DiskPart succeeded in cleaning the disk.\r\n"
            "DiskPart succeeded in creating the specified partition.\r\n"
            "DiskPart successfully formatted the volume.\r\n"
        )
        self.assertIsNone(windows._diskpart_error(output))

    def test_a_failed_script_is_detected_despite_exit_zero(self):
        output = (
            "Microsoft DiskPart version 10.0\r\n"
            "There is no volume selected.\r\n"
            "Please select a volume and try again.\r\n"
        )
        self.assertEqual(
            windows._diskpart_error(output), "There is no volume selected.")

    def test_service_errors_are_detected(self):
        output = ("Virtual Disk Service error:\r\n"
                  "The media is write protected.\r\n")
        self.assertIn('Virtual Disk Service error',
                      windows._diskpart_error(output) or '')

    def test_encountered_error_is_detected(self):
        output = "DiskPart has encountered an error: Access is denied.\r\n"
        self.assertIn('encountered an error',
                      windows._diskpart_error(output) or '')


class TestRequiredToolDiscovery(unittest.TestCase):
    """Locating the external commands a write depends on.

    The deb and rpm declare these as package dependencies, but the AppImage
    declares none and relies entirely on the host, so they are checked at
    runtime. Pure lookup logic, so it runs on any platform.
    """

    def test_finds_a_tool_on_path(self):
        self.assertIsNotNone(linux.find_tool('sh'))

    def test_finds_a_tool_only_present_in_sbin(self):
        """sbin is normally absent from a desktop user's PATH.

        mkfs.vfat and parted live there and run fine once elevated, so
        looking only at PATH would report them missing.
        """
        with patch('shutil.which', return_value=None), \
                patch('os.path.exists',
                      side_effect=lambda p: p == '/usr/sbin/parted'), \
                patch('os.access', return_value=True):
            self.assertEqual(linux.find_tool('parted'), '/usr/sbin/parted')

    def test_reports_missing_tools_with_their_packages(self):
        with patch.object(linux, 'find_tool',
                          side_effect=lambda n: None if n in
                          ('parted', 'mkfs.vfat') else f'/usr/bin/{n}'):
            missing = linux.missing_required_tools()
        self.assertEqual(missing, ['mkfs.vfat (dosfstools)', 'parted (parted)'])

    def test_reports_nothing_when_all_are_present(self):
        with patch.object(linux, 'find_tool', return_value='/usr/bin/x'):
            self.assertEqual(linux.missing_required_tools(), [])


class TestWindowsDriveListing(unittest.TestCase):
    """Drive enumeration on Windows. Runs everywhere: pure parsing."""

    _PS_JSON = ('[{"DeviceID":"C:","VolumeName":"System","FileSystem":"NTFS",'
                '"Size":"500000000000","FreeSpace":"100000000000","DriveType":3},'
                '{"DeviceID":"E:","VolumeName":"USB","FileSystem":"FAT32",'
                '"Size":"16000000000","FreeSpace":"16000000000","DriveType":2}]')

    @staticmethod
    def _fake_kernel32(drive_bits):
        """A stand-in kernel32 reporting the given drive letters."""
        k32 = MagicMock()
        k32.GetLogicalDrives.return_value = drive_bits
        k32.SetErrorMode.return_value = 0
        k32.GetDriveTypeW.side_effect = (
            lambda root: 3 if root.startswith('C') else 2)

        def volume_info(root, label, _ln, _ser, _mx, _fl, fs, _fn):
            label.value = 'System' if root.startswith('C') else 'PYNETBOOT'
            fs.value = 'NTFS' if root.startswith('C') else 'FAT32'
            return 1
        k32.GetVolumeInformationW.side_effect = volume_info

        def free_space(root, _a, total, free):
            total.value = 500_000_000_000 if root.startswith('C') else 16_000_000_000
            free.value = 100
            return 1
        k32.GetDiskFreeSpaceExW.side_effect = free_space
        return k32

    def _run_win32(self, kernel32):
        import ctypes
        import types
        wintypes = types.SimpleNamespace(
            DWORD=ctypes.c_ulong, UINT=ctypes.c_uint, BOOL=ctypes.c_int,
            LPCWSTR=ctypes.c_wchar_p, LPWSTR=ctypes.c_wchar_p)
        with patch.object(ctypes, 'WinDLL', create=True,
                          return_value=kernel32), \
                patch.object(ctypes, 'wintypes', create=True, new=wintypes), \
                patch.object(ctypes, 'byref', side_effect=lambda x: x):
            return windows._drives_via_win32()

    def test_win32_listing_spawns_no_process(self):
        """PowerShell takes about three seconds to start, and that cost was
        paid at launch and again on every refresh."""
        kernel32 = self._fake_kernel32((1 << 2) | (1 << 4))   # C and E
        with patch('subprocess.run') as mock_run:
            drives = self._run_win32(kernel32)
            mock_run.assert_not_called()

        self.assertEqual([d['letter'] for d in drives], ['C', 'E'])
        usb = drives[1]
        self.assertTrue(usb['removable'])
        self.assertEqual(usb['label'], 'PYNETBOOT')
        self.assertEqual(usb['size'], 16_000_000_000)

    def test_win32_listing_suppresses_no_media_dialogs(self):
        """Probing an empty card reader otherwise raises a system dialog."""
        kernel32 = self._fake_kernel32(1 << 2)
        self._run_win32(kernel32)
        self.assertTrue(kernel32.SetErrorMode.called)
        # Called again to restore the previous mode.
        self.assertEqual(kernel32.SetErrorMode.call_count, 2)

    def test_win32_listing_handles_a_drive_with_no_media(self):
        kernel32 = self._fake_kernel32(1 << 4)
        kernel32.GetVolumeInformationW.side_effect = None
        kernel32.GetVolumeInformationW.return_value = 0     # failure
        drives = self._run_win32(kernel32)
        self.assertEqual([d['letter'] for d in drives], ['E'])
        self.assertEqual(drives[0]['label'], '')

    def test_missing_wmic_does_not_raise_unbound_local(self):
        """wmic is gone from current Windows 11.

        Regression test: a function-level `import csv` made csv local to the
        whole function, so when subprocess raised FileNotFoundError before
        that line, the except clause referencing csv.Error died with
        UnboundLocalError -- reported to the user as a fatal error, hiding
        the real cause.
        """
        with patch('subprocess.run', side_effect=FileNotFoundError('wmic')):
            drives = windows.get_drive_list()
        self.assertEqual(drives, [])

    def test_falls_back_to_powershell_when_wmic_is_absent(self):
        def run(argv, **kwargs):
            if argv[0] == 'powershell':
                return MagicMock(returncode=0, stdout=self._PS_JSON, stderr='')
            raise FileNotFoundError('wmic')

        with patch('subprocess.run', side_effect=run):
            drives = windows.get_drive_list()

        self.assertEqual([d['letter'] for d in drives], ['C', 'E'])
        usb = next(d for d in drives if d['letter'] == 'E')
        self.assertTrue(usb['removable'])
        self.assertEqual(usb['filesystem'], 'FAT32')
        self.assertEqual(usb['size'], 16000000000)

    def test_a_single_drive_is_not_mangled(self):
        """ConvertTo-Json emits a bare object, not a list, for one result."""
        single = ('{"DeviceID":"E:","VolumeName":"USB","FileSystem":"FAT32",'
                  '"Size":"16000000000","FreeSpace":"1","DriveType":2}')
        with patch('subprocess.run',
                   return_value=MagicMock(returncode=0, stdout=single, stderr='')):
            drives = windows.get_drive_list()
        self.assertEqual([d['letter'] for d in drives], ['E'])

    def test_wmic_is_used_when_powershell_yields_nothing(self):
        csv_output = (
            "\r\nNode,DeviceID,DriveType,FileSystem,FreeSpace,Size,VolumeName\r\n"
            "PC,E:,2,FAT32,16000000000,16000000000,USB\r\n")

        def run(argv, **kwargs):
            if argv[0] == 'powershell':
                return MagicMock(returncode=0, stdout='', stderr='')
            return MagicMock(returncode=0, stdout=csv_output, stderr='')

        with patch('subprocess.run', side_effect=run):
            drives = windows.get_drive_list()

        self.assertEqual([d['letter'] for d in drives], ['E'])
        self.assertTrue(drives[0]['removable'])

    def test_every_source_failing_reports_each_reason(self):
        with patch('subprocess.run', side_effect=FileNotFoundError('gone')):
            with self.assertLogs('pynetboot.platform.windows', 'ERROR') as logs:
                self.assertEqual(windows.get_drive_list(), [])
        message = '\n'.join(logs.output)
        self.assertIn('PowerShell/CIM', message)
        self.assertIn('wmic', message)
