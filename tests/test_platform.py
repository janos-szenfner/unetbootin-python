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

from unetbootin.platform import base, linux, windows, macos


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
        # Mock lsblk command
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = """
NAME   MAJ:MIN RM   SIZE RO TYPE MOUNTPOINT
sda      8:0    0   100G  0 disk 
├─sda1   8:1    0   512M  0 part /boot/efi
└─sda2   8:2    0  99.5G  0 part /
sdb      8:16   1  14.5G  0 disk 
└─sdb1   8:17   1  14.5G  0 part /media/usb
"""
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            
            drives = linux.get_drive_list()
            self.assertIsInstance(drives, list)
            # Should find at least sda and sdb
            drive_names = [d.get('device', '') for d in drives]
            self.assertIn('/dev/sda', drive_names)
            self.assertIn('/dev/sdb', drive_names)
    
    def test_get_drive_info(self):
        """Test getting drive info on Linux."""
        with patch('subprocess.run') as mock_run:
            # Mock lsblk for parent disk
            mock_lsblk = MagicMock()
            mock_lsblk.stdout = """
NAME   MAJ:MIN RM   SIZE RO TYPE MOUNTPOINT
sda      8:0    0   100G  0 disk 
└─sda1   8:1    0   512M  0 part /boot/efi
"""
            mock_lsblk.returncode = 0
            
            # Mock blockdev for size
            mock_blockdev = MagicMock()
            mock_blockdev.stdout = "100000000"
            mock_blockdev.returncode = 0
            
            mock_run.side_effect = [mock_lsblk, mock_blockdev]
            
            info = linux.get_drive_info('/dev/sda')
            self.assertIsNotNone(info)
            self.assertIn('device', info)
    
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
        with patch('os.access', return_value=True):
            result = linux.check_drive_writable('/dev/sdb')
            self.assertTrue(result)
    
    def test_unmount_drive(self):
        """Test unmounting drive on Linux."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            
            result = linux.unmount_drive('/dev/sdb1')
            self.assertTrue(result)
    
    def test_mount_drive(self):
        """Test mounting drive on Linux."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            
            result = linux.mount_drive('/dev/sdb1', '/mnt/usb')
            self.assertTrue(result)
    
    def test_format_drive_vfat(self):
        """Test formatting drive as FAT32 on Linux."""
        with patch('subprocess.run') as mock_run:
            # First call is unmount, second is mkfs.vfat
            mock_unmount = MagicMock()
            mock_unmount.returncode = 0
            mock_mkfs = MagicMock()
            mock_mkfs.returncode = 0
            mock_run.side_effect = [mock_unmount, mock_mkfs]
            
            result = linux.format_drive('/dev/sdb1', 'vfat', 'UNETBOOTIN')
            self.assertTrue(result)
    
    def test_set_volume_label(self):
        """Test setting volume label on Linux."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            
            result = linux.set_volume_label('/dev/sdb1', 'MYUSB')
            self.assertTrue(result)
    
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
            mock_result = MagicMock()
            mock_result.stdout = "/dev/sdb1 on /media/usb type vfat (rw,nosuid)"
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
            
            result = windows.format_drive('D:\\', 'FAT32', 'UNETBOOTIN')
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
    
    def test_unmount_drive(self):
        """Test unmounting drive on macOS."""
        with patch('subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            
            result = macos.unmount_drive('/dev/disk2')
            self.assertTrue(result)
    
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

            result = macos.format_drive('/dev/disk2', 'vfat', 'UNETBOOTIN')
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


class TestPlatformDetection(unittest.TestCase):
    """Test platform detection and imports."""
    
    def test_get_drive_list_import(self):
        """Test that get_drive_list can be imported from platform."""
        from unetbootin.platform import get_drive_list
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
