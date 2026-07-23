"""
Base platform functionality for UNetbootin.
"""

import os
import sys
import logging
import subprocess
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


def get_drive_list() -> List[str]:
    """Get list of available drives."""
    return []


def get_drive_info(drive: str) -> Optional[Dict[str, Any]]:
    """Get information about a specific drive."""
    return None


def unmount_drive(drive: str) -> bool:
    """Unmount a drive."""
    return False


def mount_drive(drive: str, mount_point: str) -> bool:
    """Mount a drive."""
    return False


def format_drive(drive: str, filesystem: str = "vfat") -> bool:
    """Format a drive."""
    return False


def install_bootloader(drive: str, bootloader_type: str = "syslinux") -> bool:
    """Install bootloader to a drive."""
    return False


def get_volume_label(drive: str) -> Optional[str]:
    """Get volume label for a drive."""
    return None


def set_volume_label(drive: str, label: str) -> bool:
    """Set volume label for a drive."""
    return False


def get_device_size(drive: str) -> Optional[int]:
    """Get size of a device in bytes."""
    return None


def check_drive_writable(drive: str) -> bool:
    """Check if a drive is writable."""
    return False


def sync_filesystem() -> bool:
    """Sync the filesystem."""
    try:
        if sys.platform != 'win32':
            subprocess.run(['sync'], timeout=10)
            return True
        return True
    except Exception as e:
        logger.error(f"Failed to sync filesystem: {e}")
        return False


def get_mount_point(device: str) -> Optional[str]:
    """Get the mount point for a device."""
    return None
