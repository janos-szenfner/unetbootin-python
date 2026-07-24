"""
Windows-specific functionality for UNetbootin.
"""

import os
import sys
import csv
import logging
import subprocess
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# External tools (wmic, vol, fsutil) are driven via subprocess; parsing their
# output can raise value/index errors. Group the common set for reuse.
_SUBPROCESS_PARSE_ERRORS = (subprocess.SubprocessError, OSError,
                            ValueError, IndexError)


def get_drive_list() -> List[Dict[str, Any]]:
    """Get list of available drives on Windows."""
    drives = []
    
    try:
        # Use wmic CSV output and parse by column NAME. Plain `wmic get`
        # prints columns in ALPHABETICAL order (not the requested order) and
        # whitespace-splitting breaks on volume labels containing spaces.
        result = subprocess.run(
            ['wmic', 'logicaldisk', 'get',
             'DeviceID,VolumeName,FileSystem,Size,FreeSpace,DriveType',
             '/format:csv'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            import csv
            import io
            # wmic CSV output starts with a blank line; strip empty lines
            lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
            reader = csv.DictReader(io.StringIO('\n'.join(lines)))
            for row in reader:
                device_id = (row.get('DeviceID') or '').strip()
                if not device_id:
                    continue
                letter = device_id.rstrip(':')
                drive_type_str = (row.get('DriveType') or '').strip()
                drive_type = int(drive_type_str) if drive_type_str.isdigit() else 0
                size_str = (row.get('Size') or '').strip()
                free_str = (row.get('FreeSpace') or '').strip()
                drive_info = {
                    'device': f"{letter}:\\",
                    'letter': letter,
                    'type': get_drive_type_name(drive_type),
                    'filesystem': (row.get('FileSystem') or '').strip(),
                    'label': (row.get('VolumeName') or '').strip(),
                    'size': int(size_str) if size_str.isdigit() else 0,
                    'free': int(free_str) if free_str.isdigit() else 0,
                    'removable': drive_type == 2,
                }
                drives.append(drive_info)
    except (subprocess.SubprocessError, OSError, ValueError, csv.Error) as e:
        logger.error(f"Failed to get drive list: {e}")

    return drives


def get_drive_type_name(drive_type: int) -> str:
    """Get drive type name from Windows API constant."""
    drive_types = {
        0: 'Unknown',
        1: 'No Root Directory',
        2: 'Removable',
        3: 'Fixed',
        4: 'Remote',
        5: 'CD-ROM',
        6: 'RAM Disk',
    }
    return drive_types.get(drive_type, f'Unknown ({drive_type})')


def get_drive_info(drive: str) -> Optional[Dict[str, Any]]:
    """Get detailed information about a specific drive on Windows."""
    try:
        if not drive.endswith(':\\') and len(drive) == 1 and drive.isalpha():
            drive = f"{drive}:\\"
        
        return {
            'device': drive,
            'letter': drive[0] if drive.endswith(':\\') else drive,
            'type': 'removable' if is_external_drive(drive) else 'fixed',
            'removable': is_external_drive(drive),
        }
    except (AttributeError, IndexError, TypeError) as e:
        logger.error(f"Failed to get drive info for {drive}: {e}")
    
    return None


def unmount_drive(drive: str) -> bool:
    """Unmount a drive on Windows."""
    # On Windows, unmounting is typically not needed for this use case
    return True


def mount_drive(drive: str, mount_point: str = None) -> bool:
    """Mount a drive on Windows."""
    # On Windows, drives are automatically mounted
    return True


def format_drive(drive: str, filesystem: str = "FAT32",
                 label: str = "UNETBOOTIN") -> bool:
    """Format a drive on Windows.

    Not implemented: automated formatting of arbitrary drives is too
    destructive to run non-interactively. Reports failure so callers do
    not assume the drive was formatted.
    """
    logger.warning(
        f"Drive formatting is not implemented on Windows; format {drive} "
        f"as {filesystem} manually (Explorer or diskpart) and retry"
    )
    return False


def install_bootloader(drive: str, bootloader_type: str = "syslinux") -> bool:
    """Install bootloader to a drive on Windows.

    Not implemented at the platform layer. The installer module handles
    Windows bootloader installation via syslinux.exe when available; this
    stub reports failure so callers never assume a bootable result.
    """
    logger.warning(
        f"Platform-level bootloader installation ({bootloader_type}) is not "
        f"implemented on Windows; install syslinux.exe and use the installer "
        f"module instead"
    )
    return False


def get_volume_label(drive: str) -> Optional[str]:
    """Get volume label for a drive on Windows."""
    try:
        if not drive.endswith(':\\') and len(drive) == 1 and drive.isalpha():
            drive = f"{drive}:\\"
        
        # Try using vol command
        result = subprocess.run(
            ['vol', drive],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'Volume in drive' in line and 'has no label' not in line:
                    return line.split()[-1]
    except _SUBPROCESS_PARSE_ERRORS as e:
        logger.error(f"Failed to get volume label for {drive}: {e}")
    
    return None


def set_volume_label(drive: str, label: str) -> bool:
    """Set volume label for a drive on Windows.

    Not implemented: reports failure so callers do not assume the label
    was changed. Users can set the label manually with the `label` command.
    """
    logger.warning(
        f"Setting the volume label is not implemented on Windows; "
        f"run 'label {drive} {label}' in an elevated prompt instead"
    )
    return False


def get_device_size(drive: str) -> Optional[int]:
    """Get size of a device in bytes on Windows."""
    try:
        if not drive.endswith(':\\') and len(drive) == 1 and drive.isalpha():
            drive = f"{drive}:\\"
        
        # Use fsutil or chkdsk
        result = subprocess.run(
            ['fsutil', 'volume', 'query', drive],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Parse output to find size
            for line in result.stdout.split('\n'):
                if 'Total # of bytes' in line or 'Capacity' in line:
                    size_str = line.split(':')[1].strip()
                    return int(size_str)
    except _SUBPROCESS_PARSE_ERRORS as e:
        logger.error(f"Failed to get size for {drive}: {e}")
    
    return None


def check_drive_writable(drive: str) -> bool:
    """Check if a drive is writable on Windows."""
    try:
        if not drive.endswith(':\\') and len(drive) == 1 and drive.isalpha():
            drive = f"{drive}:\\"
        
        # Try to create a temporary file
        test_file = os.path.join(drive, f'.unetbootin_test_{os.getpid()}.tmp')
        try:
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            return True
        except OSError:
            return False
    except OSError:
        return False


def sync_filesystem() -> bool:
    """Sync the filesystem on Windows."""
    # Windows doesn't need explicit sync
    return True


def get_mount_point(device: str) -> Optional[str]:
    """Get the mount point for a device on Windows."""
    try:
        if not device.endswith(':\\') and len(device) == 1 and device.isalpha():
            return f"{device}:\\"
        return device if device.endswith(':\\') else None
    except (AttributeError, TypeError):
        return None


def is_external_drive(drive: str) -> bool:
    """Check if a drive is external (USB, etc.) on Windows."""
    try:
        info = get_drive_info(drive)
        if info:
            return info.get('removable', False)
        return False
    except (AttributeError, TypeError, KeyError):
        return False


def check_admin_privileges() -> bool:
    """Check if running with administrator privileges on Windows."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except (AttributeError, OSError):
        return False
