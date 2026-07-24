"""
macOS-specific functionality for UNetbootin.
"""

import os
import re
import sys
import shutil
import logging
import subprocess
from xml.parsers.expat import ExpatError
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# diskutil is driven via subprocess; parsing its plist/text output can fail
# in a handful of well-defined ways. Group them for reuse.
# (plistlib.InvalidFileException and json/JSON errors are ValueError subclasses.)
_SUBPROCESS_ERRORS = (subprocess.SubprocessError, OSError)
# AttributeError is included because a plist whose top-level type isn't the
# expected dict (e.g. a bare array) makes `.get()` fail — that's an
# unexpected-structure condition the fallback path is meant to handle.
_PLIST_PARSE_ERRORS = (ValueError, KeyError, TypeError, AttributeError,
                       ExpatError)


def get_drive_list() -> List[Dict[str, Any]]:
    """Get list of available drives on macOS."""
    drives = []

    try:
        # Use diskutil to list all disks
        result = subprocess.run(
            ['diskutil', 'list', '-plist'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            # Parse plist output
            import plistlib
            try:
                data = plistlib.loads(result.stdout.encode())

                for disk in data.get('AllDisksAndPartitions', []):
                    if 'DeviceIdentifier' in disk:
                        drive_info = {
                            'device': disk['DeviceIdentifier'],
                            'type': 'removable' if disk.get('RemovableMedia', False) else 'fixed',
                            'size': disk.get('Size', 0),
                            'label': disk.get('VolumeName', ''),
                            'filesystem': disk.get('FilesystemType', ''),
                            'mountpoint': disk.get('MountPoint', ''),
                            'vendor': disk.get('DeviceVendor', ''),
                            'model': disk.get('DeviceModel', ''),
                            'removable': disk.get('RemovableMedia', False),
                        }

                        # Add partitions if available
                        if 'Partitions' in disk:
                            drive_info['partitions'] = []
                            for partition in disk['Partitions']:
                                drive_info['partitions'].append({
                                    'identifier': partition.get('DeviceIdentifier', ''),
                                    'size': partition.get('Size', 0),
                                    'type': partition.get('Content', ''),
                                    'mountpoint': partition.get('MountPoint', ''),
                                })

                        drives.append(drive_info)

            except _PLIST_PARSE_ERRORS as e:
                logger.error(f"Failed to parse diskutil plist output: {e}")
                # Fallback to text output parsing
                result = subprocess.run(
                    ['diskutil', 'list'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    drives = parse_diskutil_text_output(result.stdout)

    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Failed to get drive list: {e}")

    return drives


def parse_diskutil_text_output(output: str) -> List[Dict[str, Any]]:
    """Parse diskutil text output."""
    drives = []
    current_disk = None

    for line in output.split('\n'):
        line = line.strip()
        if not line:
            continue

        # Check for disk identifier
        disk_match = re.match(r'^/dev/(disk\d+):', line)
        if disk_match:
            disk_name = disk_match.group(1)
            current_disk = {
                'device': f'/dev/{disk_name}',
                'type': 'fixed',
                'size': 0,
                'label': '',
                'filesystem': '',
                'mountpoint': '',
                'removable': False,
                'partitions': [],
            }
            drives.append(current_disk)
            continue

        if current_disk:
            # Parse disk information
            if line.startswith('Type: '):
                current_disk['type'] = line[6:].strip()
            elif line.startswith('Name: '):
                current_disk['label'] = line[6:].strip()
            elif line.startswith('Size: '):
                size_str = line[6:].strip().split()[0]
                current_disk['size'] = parse_size_string(size_str)
            elif line.startswith('Identifier: '):
                current_disk['device'] = line[12:].strip()
            elif line.startswith('Mount Point: '):
                current_disk['mountpoint'] = line[13:].strip()
            elif line.startswith('Content: '):
                content = line[9:].strip()
                if 'Apple_' in content or 'EFI' in content:
                    current_disk['filesystem'] = content
            elif line.startswith('Removable Media: '):
                current_disk['removable'] = line[18:].strip().lower() == 'yes'

        # Check for partition information
        partition_match = re.match(r'\s+(\d+):\s+(.+)', line)
        if partition_match and current_disk:
            # This is a partition line
            pass

    return drives


def parse_size_string(size_str: str) -> int:
    """Parse size string like '123.4 GB' to bytes."""
    size_str = size_str.upper().strip()

    if 'TB' in size_str:
        size = float(size_str.replace('TB', '').strip()) * 1024**4
    elif 'GB' in size_str:
        size = float(size_str.replace('GB', '').strip()) * 1024**3
    elif 'MB' in size_str:
        size = float(size_str.replace('MB', '').strip()) * 1024**2
    elif 'KB' in size_str:
        size = float(size_str.replace('KB', '').strip()) * 1024
    elif 'B' in size_str:
        size = int(size_str.replace('B', '').strip())
    else:
        size = 0

    return int(size)


def get_drive_info(drive: str) -> Optional[Dict[str, Any]]:
    """Get detailed information about a specific drive on macOS."""
    try:
        if not drive.startswith('/dev/'):
            drive = f'/dev/{drive}'

        # Use diskutil info
        result = subprocess.run(
            ['diskutil', 'info', '-plist', drive],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            import plistlib
            try:
                data = plistlib.loads(result.stdout.encode())
                return {
                    'device': drive,
                    'size': data.get('TotalSize', 0),
                    'label': data.get('VolumeName', ''),
                    'filesystem': data.get('FilesystemType', ''),
                    'mountpoint': data.get('MountPoint', ''),
                    'removable': data.get('RemovableMedia', False),
                    'vendor': data.get('DeviceVendor', ''),
                    'model': data.get('DeviceModel', ''),
                    'writable': data.get('WritableMedia', False),
                }
            except _PLIST_PARSE_ERRORS as e:
                logger.error(f"Failed to parse diskutil info plist: {e}")

    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Failed to get drive info for {drive}: {e}")

    return None


def unmount_drive(drive: str) -> bool:
    """Unmount a drive on macOS."""
    try:
        if not drive.startswith('/dev/'):
            drive = f'/dev/{drive}'

        # Find mount point first
        result = subprocess.run(
            ['diskutil', 'info', drive],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if line.startswith('Mount Point:') or line.startswith('Mount Points:'):
                    mount_point = line.split(':')[1].strip()
                    if mount_point and mount_point != 'Not mounted':
                        # Unmount using diskutil
                        result = subprocess.run(
                            ['diskutil', 'unmount', mount_point],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if result.returncode == 0:
                            return True

                        # Alternative: use umount
                        result = subprocess.run(
                            ['umount', mount_point],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        return result.returncode == 0

        # Try direct unmount
        result = subprocess.run(
            ['diskutil', 'unmountDisk', drive],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0

    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Failed to unmount {drive}: {e}")
        return False


def mount_drive(drive: str, mount_point: str = None) -> bool:
    """Mount a drive on macOS."""
    try:
        if not drive.startswith('/dev/'):
            drive = f'/dev/{drive}'

        if mount_point is None:
            # Let system choose mount point
            result = subprocess.run(
                ['diskutil', 'mount', drive],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        else:
            # Mount to specific point
            result = subprocess.run(
                ['mount', '-t', 'hfs', drive, mount_point],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0

    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Failed to mount {drive}: {e}")
        return False


def format_drive(drive: str, filesystem: str = "vfat",
                 label: str = "UNETBOOTIN") -> bool:
    """Format a drive on macOS."""
    try:
        if not drive.startswith('/dev/'):
            drive = f'/dev/{drive}'

        # First, unmount the drive
        unmount_drive(drive)

        # Format based on filesystem type
        if filesystem.lower() in ['vfat', 'msdos', 'fat32']:
            # For FAT32, we use diskutil
            result = subprocess.run(
                ['diskutil', 'eraseVolume', 'FAT32', label, drive],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0

        elif filesystem.lower() in ['hfs', 'hfs+']:
            result = subprocess.run(
                ['diskutil', 'eraseVolume', 'HFS+', label, drive],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0

        elif filesystem.lower() == 'exfat':
            result = subprocess.run(
                ['diskutil', 'eraseVolume', 'ExFAT', label, drive],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0

        logger.error(f"Unsupported filesystem type: {filesystem}")
        return False

    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Failed to format {drive} as {filesystem}: {e}")
        return False


def install_bootloader(drive: str, bootloader_type: str = "syslinux") -> bool:
    """Install bootloader to a drive on macOS."""
    try:
        if not drive.startswith('/dev/'):
            drive = f'/dev/{drive}'

        if bootloader_type.lower() == 'syslinux':
            # For macOS, syslinux is typically used for FAT32 formatted USB
            # We need to install syslinux bootloader files

            # First, ensure syslinux is installed
            syslinux_dir = '/usr/local/share/syslinux'
            if not os.path.exists(syslinux_dir):
                syslinux_dir = '/usr/share/syslinux'

            if not os.path.exists(syslinux_dir):
                logger.error("syslinux files not found")
                return False

            # Copy syslinux files
            mount_point = get_mount_point(drive)
            if not mount_point:
                logger.error(f"Cannot find mount point for {drive}")
                return False

            # Copy bootloader files
            boot_files = ['ldlinux.sys', 'libcom32.c32', 'libutil.c32', 'mboot.c32',
                         'menu.c32', 'vesamenu.c32', 'hdt.c32', 'poweroff.com', 'reboot.com']

            for file in boot_files:
                src = os.path.join(syslinux_dir, file)
                if os.path.exists(src):
                    dst = os.path.join(mount_point, file)
                    shutil.copy2(src, dst)

            # Install MBR
            mbr_file = os.path.join(syslinux_dir, 'mbr.bin')
            if os.path.exists(mbr_file):
                result = subprocess.run(
                    ['dd', f'if={mbr_file}', f'of={drive}', 'bs=440', 'count=1'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                return result.returncode == 0

        elif bootloader_type.lower() == 'grub':
            # For GRUB on macOS, we typically use bless
            mount_point = get_mount_point(drive)
            if not mount_point:
                logger.error(f"Cannot find mount point for {drive}")
                return False

            # Check for EFI boot
            efi_dir = os.path.join(mount_point, 'EFI', 'BOOT')
            if os.path.exists(efi_dir):
                bootx64_path = os.path.join(efi_dir, 'BOOTX64.EFI')
                if os.path.exists(bootx64_path):
                    result = subprocess.run(
                        ['bless', '--mount', mount_point, '--setBoot',
                         '--folder', efi_dir, '--file', bootx64_path],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    return result.returncode == 0

            # For BIOS boot
            grub_cfg_path = os.path.join(mount_point, 'grub.cfg')
            if os.path.exists(grub_cfg_path):
                result = subprocess.run(
                    ['bless', '--mount', mount_point, '--setBoot', '--folder', mount_point],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                return result.returncode == 0

        logger.error(f"Unsupported bootloader type: {bootloader_type}")
        return False

    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Failed to install bootloader to {drive}: {e}")
        return False


def get_volume_label(drive: str) -> Optional[str]:
    """Get volume label for a drive on macOS."""
    try:
        if not drive.startswith('/dev/'):
            drive = f'/dev/{drive}'

        result = subprocess.run(
            ['diskutil', 'info', drive],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            for raw_line in result.stdout.split('\n'):
                # `diskutil info` indents every field, so strip before matching
                line = raw_line.strip()
                if line.startswith('Volume Name:') or line.startswith('Name:'):
                    return line.split(':', 1)[1].strip()

    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Failed to get volume label for {drive}: {e}")

    return None


def set_volume_label(drive: str, label: str) -> bool:
    """Set volume label for a drive on macOS."""
    try:
        if not drive.startswith('/dev/'):
            drive = f'/dev/{drive}'

        result = subprocess.run(
            ['diskutil', 'rename', drive, label],
            capture_output=True,
            text=True,
            timeout=10
        )

        # NOTE: never fall back to reformatting here - renaming a volume must
        # not erase it. If rename fails, report failure.
        return result.returncode == 0

    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Failed to set volume label for {drive}: {e}")
        return False


def get_device_size(drive: str) -> Optional[int]:
    """Get size of a device in bytes on macOS."""
    info = get_drive_info(drive)
    if info:
        return info.get('size')
    return None


def get_parent_disk(device: str) -> Optional[str]:
    """Resolve the whole-disk device for a partition on macOS.

    Uses ``diskutil info`` and its "Part of Whole" field. For a partition
    like ``/dev/disk2s1`` this returns ``/dev/disk2``; for a whole disk it
    returns the disk itself. Mirrors the Linux ``get_parent_disk`` so the
    installer can find the correct device before writing boot records.
    """
    try:
        if not device.startswith('/dev/'):
            device = f'/dev/{device}'

        result = subprocess.run(
            ['diskutil', 'info', device],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'Part of Whole' in line:
                    whole = line.split(':', 1)[1].strip()
                    if whole:
                        return f'/dev/{whole}'
    except (subprocess.SubprocessError, OSError) as e:
        logger.error(f"Failed to resolve parent disk for {device}: {e}")

    return None


def check_drive_writable(drive: str) -> bool:
    """Check if a drive is writable on macOS."""
    try:
        info = get_drive_info(drive)
        if info:
            return info.get('writable', False)
        return False
    except (AttributeError, TypeError, KeyError):
        return False


def sync_filesystem() -> bool:
    """Sync the filesystem on macOS."""
    try:
        result = subprocess.run(['sync'], timeout=10)
        return result.returncode == 0
    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Failed to sync filesystem: {e}")
        return False


def get_mount_point(device: str) -> Optional[str]:
    """Get the mount point for a device on macOS."""
    try:
        if not device.startswith('/dev/'):
            device = f'/dev/{device}'

        result = subprocess.run(
            ['diskutil', 'info', device],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if line.startswith('Mount Point:') or line.startswith('Mount Points:'):
                    mount_point = line.split(':')[1].strip()
                    if (mount_point and mount_point != 'Not mounted'
                            and mount_point != 'None'):
                        return mount_point

        # Try mount command
        result = subprocess.run(['mount'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if device in line:
                    parts = line.split()
                    for part in parts:
                        if part.startswith('/Volumes/'):
                            return part

    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Failed to get mount point for {device}: {e}")

    return None


def is_external_drive(drive: str) -> bool:
    """Check if a drive is external (USB, etc.) on macOS."""
    try:
        info = get_drive_info(drive)
        if info:
            return info.get('removable', False)

        # Alternative: check if it's a disk that's not the system disk
        if 'disk0' not in drive and 'disk1' in drive:
            return True

        return False
    except (AttributeError, TypeError, KeyError):
        return False


def is_safe_target(device: str) -> bool:
    """Whether `device` is a safe external/removable target on macOS.

    Reads ``diskutil info -plist`` and requires ALL of:
      * ``Internal`` is False (external bus), so the built-in disk is excluded;
      * the device is physical, not a disk image
        (``VirtualOrPhysical`` != 'Virtual', ``BusProtocol`` != 'Disk Image');
      * it is ``Ejectable`` or ``RemovableMedia`` (real removable media).

    Fails closed (returns False) on any uncertainty, so an internal disk or a
    mounted .dmg can never be selected — not even as an exception.
    """
    try:
        if not device.startswith('/dev/'):
            device = f'/dev/{device}'

        result = subprocess.run(
            ['diskutil', 'info', '-plist', device],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return False

        import plistlib
        data = plistlib.loads(result.stdout.encode())

        internal = bool(data.get('Internal', True))       # default True → unsafe
        ejectable = bool(data.get('Ejectable', False))
        removable = bool(data.get('RemovableMedia', False))
        bus = (data.get('BusProtocol') or '').strip()
        virt = (data.get('VirtualOrPhysical') or '').strip()

        if internal:
            return False
        if virt == 'Virtual' or bus == 'Disk Image':
            return False
        if not (ejectable or removable):
            return False
        return True

    except _SUBPROCESS_ERRORS:
        return False
    except _PLIST_PARSE_ERRORS:
        return False
