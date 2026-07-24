"""
Base platform functionality for UNetbootin.

These are fallback stubs used when no platform-specific implementation
exists (unsupported platforms, or functions a platform module does not
provide). Each stub logs a warning so failures are visible instead of
silently returning empty/False values.
"""

import os
import sys
import logging
import subprocess
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


def _unsupported(operation: str):
    """Log that an operation is not supported on this platform."""
    logger.warning(
        f"{operation} is not implemented for platform '{sys.platform}'; "
        f"this operation will report failure"
    )


def get_drive_list() -> List[Dict[str, Any]]:
    """Get list of available drives."""
    _unsupported("Drive listing")
    return []


def get_drive_info(drive: str) -> Optional[Dict[str, Any]]:
    """Get information about a specific drive."""
    _unsupported("Drive information lookup")
    return None


def unmount_drive(drive: str) -> bool:
    """Unmount a drive."""
    _unsupported("Drive unmounting")
    return False


def mount_drive(drive: str, mount_point: str = None) -> bool:
    """Mount a drive."""
    _unsupported("Drive mounting")
    return False


def format_drive(drive: str, filesystem: str = "vfat",
                 label: str = "UNETBOOTIN") -> bool:
    """Format a drive."""
    _unsupported("Drive formatting")
    return False


def install_bootloader(drive: str, bootloader_type: str = "syslinux") -> bool:
    """Install bootloader to a drive."""
    _unsupported("Bootloader installation")
    return False


def get_volume_label(drive: str) -> Optional[str]:
    """Get volume label for a drive."""
    _unsupported("Volume label lookup")
    return None


def set_volume_label(drive: str, label: str) -> bool:
    """Set volume label for a drive."""
    _unsupported("Volume label setting")
    return False


def get_device_size(drive: str) -> Optional[int]:
    """Get size of a device in bytes."""
    _unsupported("Device size lookup")
    return None


def check_drive_writable(drive: str) -> bool:
    """Check if a drive is writable."""
    _unsupported("Drive writability check")
    return False


def is_external_drive(drive: str) -> bool:
    """Check if a drive is external (USB, etc.)."""
    _unsupported("External drive detection")
    return False


def is_safe_target(device: str) -> bool:
    """Whether `device` is a safe target to erase and write a bootable USB to.

    A safe target is an EXTERNAL / REMOVABLE PHYSICAL whole disk that is not
    the system disk and not a virtual device / disk image. On unsupported
    platforms we cannot prove any of that, so we fail closed and return
    False — refusing is always safer than risking an internal disk.
    """
    _unsupported("Safe-target detection")
    return False


def sync_filesystem() -> bool:
    """Sync the filesystem."""
    try:
        if sys.platform != 'win32':
            subprocess.run(['sync'], timeout=10)
            return True
        return True
    except (subprocess.SubprocessError, OSError) as e:
        logger.error(f"Failed to sync filesystem: {e}")
        return False


def get_mount_point(device: str) -> Optional[str]:
    """Get the mount point for a device."""
    _unsupported("Mount point lookup")
    return None
