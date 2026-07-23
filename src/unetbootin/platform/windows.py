"""
Windows-specific functionality for UNetbootin.
"""

import os
import sys
import logging
import subprocess
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


def get_drive_list() -> List[Dict[str, Any]]:
    """Get list of available drives on Windows."""
    drives = []
    
    try:
        # Use wmic to get drive list
        result = subprocess.run(
            ['wmic', 'logicaldisk', 'get', 'DeviceID,VolumeName,FileSystem,Size,FreeSpace,DriveType'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for line in lines[1:]:  # Skip header
                parts = line.strip().split()
                if len(parts) >= 5:
                    drive_info = {
                        'device': f"{parts[0]}:\\",
                        'letter': parts[0],
                        'type': get_drive_type_name(int(parts[5]) if len(parts) > 5 and parts[5].isdigit() else 0),
                        'filesystem': parts[2] if len(parts) > 2 else '',
                        'label': parts[1] if len(parts) > 1 else '',
                        'size': int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0,
                        'free': int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0,
                        'removable': int(parts[5]) == 2 if len(parts) > 5 and parts[5].isdigit() else False,
                    }
                    drives.append(drive_info)
    except Exception as e:
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
    except Exception as e:
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


def format_drive(drive: str, filesystem: str = "FAT32", label: str = "UNETBOOTIN") -> bool:
    """Format a drive on Windows."""
    logger.warning("Drive formatting not implemented on Windows")
    return False


def install_bootloader(drive: str, bootloader_type: str = "syslinux") -> bool:
    """Install bootloader to a drive on Windows."""
    logger.warning("Bootloader installation not implemented on Windows")
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
    except Exception as e:
        logger.error(f"Failed to get volume label for {drive}: {e}")
    
    return None


def set_volume_label(drive: str, label: str) -> bool:
    """Set volume label for a drive on Windows."""
    logger.warning("Setting volume label not implemented on Windows")
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
    except Exception as e:
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
        except Exception:
            return False
    except Exception:
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
    except Exception:
        return None


def is_external_drive(drive: str) -> bool:
    """Check if a drive is external (USB, etc.) on Windows."""
    try:
        info = get_drive_info(drive)
        if info:
            return info.get('removable', False)
        return False
    except Exception:
        return False


def check_admin_privileges() -> bool:
    """Check if running with administrator privileges on Windows."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False
