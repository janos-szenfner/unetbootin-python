"""
Windows-specific functionality for PyNetboot.
"""

import os
import csv
import io
import json
import logging
import subprocess
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# External tools (wmic, vol, fsutil) are driven via subprocess; parsing their
# output can raise value/index errors. Group the common set for reuse.
_SUBPROCESS_PARSE_ERRORS = (subprocess.SubprocessError, OSError,
                            ValueError, IndexError)


def _drive_from_fields(device_id: str, drive_type: str, filesystem: str,
                       label: str, size: str, free: str) -> Optional[Dict[str, Any]]:
    """Build a drive entry from one source's raw string fields."""
    device_id = (device_id or '').strip()
    if not device_id:
        return None

    letter = device_id.rstrip(':')
    type_str = (drive_type or '').strip()
    type_code = int(type_str) if type_str.isdigit() else 0
    size_str = (size or '').strip()
    free_str = (free or '').strip()

    return {
        'device': f"{letter}:\\",
        'letter': letter,
        'type': get_drive_type_name(type_code),
        'filesystem': (filesystem or '').strip(),
        'label': (label or '').strip(),
        'size': int(size_str) if size_str.isdigit() else 0,
        'free': int(free_str) if free_str.isdigit() else 0,
        'removable': type_code == 2,
    }


def _drives_via_win32() -> List[Dict[str, Any]]:
    """List drives through the Win32 API.

    Both other sources start a process -- PowerShell needs about three
    seconds to load .NET, and that cost is paid again on every refresh.
    These calls answer from the kernel in well under a millisecond.
    """
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

    kernel32.GetLogicalDrives.restype = wintypes.DWORD
    kernel32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetDriveTypeW.restype = wintypes.UINT
    kernel32.GetVolumeInformationW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD]
    kernel32.GetVolumeInformationW.restype = wintypes.BOOL
    kernel32.GetDiskFreeSpaceExW.argtypes = [
        wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_ulonglong),
        ctypes.POINTER(ctypes.c_ulonglong), ctypes.POINTER(ctypes.c_ulonglong)]
    kernel32.GetDiskFreeSpaceExW.restype = wintypes.BOOL

    # Probing an empty card reader otherwise raises a "There is no disk in
    # the drive" dialog that the user has to dismiss.
    SEM_FAILCRITICALERRORS = 0x0001
    previous_mode = kernel32.SetErrorMode(SEM_FAILCRITICALERRORS)

    try:
        mask = kernel32.GetLogicalDrives()
        if not mask:
            return []

        drives = []
        for index in range(26):
            if not (mask >> index) & 1:
                continue

            letter = chr(ord('A') + index)
            root = f"{letter}:\\"
            drive_type = kernel32.GetDriveTypeW(root)

            label_buffer = ctypes.create_unicode_buffer(261)
            fs_buffer = ctypes.create_unicode_buffer(261)
            serial = wintypes.DWORD()
            max_component = wintypes.DWORD()
            flags = wintypes.DWORD()

            # Fails for a drive with no media; the entry is still listed so
            # an empty card reader remains visible, just without details.
            # len() of a unicode buffer is its length in characters, which
            # is what the API wants; sizeof would be bytes.
            if not kernel32.GetVolumeInformationW(
                    root, label_buffer, len(label_buffer),
                    ctypes.byref(serial), ctypes.byref(max_component),
                    ctypes.byref(flags),
                    fs_buffer, len(fs_buffer)):
                label_buffer.value = ''
                fs_buffer.value = ''

            total = ctypes.c_ulonglong(0)
            free = ctypes.c_ulonglong(0)
            kernel32.GetDiskFreeSpaceExW(
                root, None, ctypes.byref(total), ctypes.byref(free))

            drive = _drive_from_fields(
                f"{letter}:", str(drive_type), fs_buffer.value,
                label_buffer.value, str(total.value), str(free.value))
            if drive:
                drives.append(drive)

        return drives
    finally:
        kernel32.SetErrorMode(previous_mode)


def _drives_via_powershell() -> List[Dict[str, Any]]:
    """List drives with CIM, the supported replacement for wmic.

    wmic is deprecated and no longer present on current Windows 11, where
    invoking it raises FileNotFoundError and no drives can be listed.
    """
    script = (
        "Get-CimInstance -ClassName Win32_LogicalDisk | "
        "Select-Object DeviceID,VolumeName,FileSystem,Size,FreeSpace,DriveType | "
        "ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ['powershell', '-NoProfile', '-NonInteractive', '-Command', script],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        logger.warning(
            f"PowerShell drive listing failed: {(result.stderr or '').strip()}")
        return []

    payload = (result.stdout or '').strip()
    if not payload:
        return []

    rows = json.loads(payload)
    # ConvertTo-Json emits a bare object, not a list, for a single drive.
    if isinstance(rows, dict):
        rows = [rows]

    drives = []
    for row in rows:
        drive = _drive_from_fields(
            str(row.get('DeviceID') or ''), str(row.get('DriveType') or ''),
            str(row.get('FileSystem') or ''), str(row.get('VolumeName') or ''),
            str(row.get('Size') or ''), str(row.get('FreeSpace') or ''))
        if drive:
            drives.append(drive)
    return drives


def _drives_via_wmic() -> List[Dict[str, Any]]:
    """List drives with wmic, for Windows versions that still ship it.

    Parses CSV by column NAME: plain `wmic get` prints columns in
    ALPHABETICAL order rather than the requested order, and
    whitespace-splitting breaks on volume labels containing spaces.
    """
    result = subprocess.run(
        ['wmic', 'logicaldisk', 'get',
         'DeviceID,VolumeName,FileSystem,Size,FreeSpace,DriveType',
         '/format:csv'],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode != 0:
        logger.warning(
            f"wmic drive listing failed: {(result.stderr or '').strip()}")
        return []

    # wmic CSV output starts with a blank line; strip empty lines
    lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
    reader = csv.DictReader(io.StringIO('\n'.join(lines)))

    drives = []
    for row in reader:
        drive = _drive_from_fields(
            row.get('DeviceID'), row.get('DriveType'), row.get('FileSystem'),
            row.get('VolumeName'), row.get('Size'), row.get('FreeSpace'))
        if drive:
            drives.append(drive)
    return drives


def get_drive_list() -> List[Dict[str, Any]]:
    """Get list of available drives on Windows.

    Asks the Win32 API first, which answers immediately; PowerShell and
    wmic are kept as fallbacks, covering both current Windows 11 (where
    wmic is gone) and older releases.
    """
    errors = []

    for describe, source in (('Win32 API', _drives_via_win32),
                             ('PowerShell/CIM', _drives_via_powershell),
                             ('wmic', _drives_via_wmic)):
        try:
            drives = source()
        except FileNotFoundError:
            # The tool is not installed on this version of Windows.
            errors.append(f"{describe}: not available")
            continue
        except (subprocess.SubprocessError, OSError, ValueError,
                AttributeError, csv.Error, json.JSONDecodeError) as e:
            # AttributeError covers a missing ctypes symbol on an unexpected
            # Windows build, so the fallbacks still get their turn.
            errors.append(f"{describe}: {e}")
            continue

        if drives:
            return drives
        errors.append(f"{describe}: no drives reported")

    logger.error("Failed to get drive list -- " + "; ".join(errors))
    return []


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


# diskpart announces failures in prose on stdout and still exits 0, so a
# script that selected nothing and formatted nothing looks like a success.
# These are its failure phrasings.
_DISKPART_ERRORS = (
    'DiskPart has encountered an error',
    'Virtual Disk Service error',
    'The arguments specified for this command are not valid',
    'There is no volume selected',
    'There is no disk selected',
    'The specified volume is not valid',
    'access is denied',
)


def _diskpart_error(output: str) -> Optional[str]:
    """Return the first failure line diskpart printed, if any."""
    lowered = output.lower()
    for marker in _DISKPART_ERRORS:
        position = lowered.find(marker.lower())
        if position == -1:
            continue
        line_start = output.rfind('\n', 0, position) + 1
        line_end = output.find('\n', position)
        return output[line_start:line_end if line_end != -1 else None].strip()
    return None


# Windows removes the drive letter during `clean` and re-creates the volume
# a moment after `assign`; writing before it reappears fails with "The system
# cannot find the path specified".
_VOLUME_SETTLE_SECONDS = 30


def drive_root(device: str) -> Optional[str]:
    """Normalise a Windows target to its drive root: 'D', 'D:', 'D:\\' -> 'D:\\'.

    Callers pass the drive in every one of those shapes, and each place that
    re-derived it got the edge cases slightly differently -- one produced
    'D:\\:' and printed it in the log.
    """
    letter = (device or '').strip().rstrip('\\/').rstrip(':')[:1].upper()
    return f"{letter}:\\" if letter.isalpha() else None


def wait_for_drive(drive: str, timeout: int = _VOLUME_SETTLE_SECONDS) -> bool:
    """Wait for a freshly formatted drive letter to become usable."""
    import time

    root = drive_root(drive)
    if root is None:
        return False

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        # exists() alone can be true before the filesystem is ready, so the
        # directory is actually listed.
        try:
            if os.path.exists(root):
                os.listdir(root)
                logger.info(f"{root} is ready")
                return True
        except OSError:
            pass
        time.sleep(0.5)

    logger.error(
        f"{root} did not become available within {timeout}s after formatting")
    return False


def format_drive(drive: str, filesystem: str = "FAT32",
                 label: str = "PYNETBOOT") -> bool:
    """Format a drive on Windows using diskpart scripting.

    Uses diskpart with a script file to non-interactively format the drive.
    This is safer than the format command as it allows better control and
    works reliably in automated scripts.

    Args:
        drive: Drive letter (e.g., 'E:' or 'E')
        filesystem: Filesystem type (FAT32, NTFS, exFAT)
        label: Volume label to set

    Returns:
        True if formatting succeeded, False otherwise
    """
    try:
        # Callers pass 'E', 'E:' or 'E:\'. Appending ':' unconditionally
        # turned the last of those into 'E:\:', which then appeared in the
        # log as a nonsense path.
        root = drive_root(drive)
        if root is None:
            logger.error(f"Not a drive letter: {drive!r}")
            return False
        drive_letter = root[0]
        drive = f"{drive_letter}:"

        # Create a temporary diskpart script
        import tempfile
        import os

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            # Diskpart script to format the drive
            f.write(f"select volume {drive_letter}\r\n")
            f.write("clean\r\n")
            if filesystem.upper() == "FAT32":
                f.write("create partition primary\r\n")
                f.write(f"format fs=fat32 label={label} quick\r\n")
            elif filesystem.upper() == "NTFS":
                f.write("create partition primary\r\n")
                f.write(f"format fs=ntfs label={label} quick\r\n")
            elif filesystem.upper() == "EXFAT":
                f.write("create partition primary\r\n")
                f.write(f"format fs=exfat label={label} quick\r\n")
            else:
                f.write("create partition primary\r\n")
                f.write(f"format fs=fat32 label={label} quick\r\n")
            # Ask for the letter back explicitly. A bare `assign` lets
            # Windows pick any free letter, so the drive could reappear as
            # something else and every later write would go nowhere.
            f.write(f"assign letter={drive_letter}\r\n")
            f.write("exit\r\n")
            script_path = f.name

        try:
            # Run diskpart with the script
            result = subprocess.run(
                ['diskpart', '/s', script_path],
                capture_output=True,
                text=True,
                timeout=120
            )

            # diskpart reports failures on stdout and still exits 0, so the
            # exit code alone would accept a script that formatted nothing.
            output = ((result.stdout or '') + (result.stderr or '')).strip()
            failure = _diskpart_error(output)

            if result.returncode == 0 and not failure:
                logger.info(f"Successfully formatted {drive} as {filesystem}")
                return True

            logger.error(
                f"diskpart failed to format {drive} "
                f"(exit {result.returncode}): {failure or output or 'no output'}")
            return False
        finally:
            # Clean up the script file
            try:
                os.unlink(script_path)
            except OSError:
                pass

    except (subprocess.SubprocessError, OSError, ValueError, TypeError) as e:
        logger.error(f"Failed to format drive {drive}: {e}")
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
        test_file = os.path.join(drive, f'.pynetboot_test_{os.getpid()}.tmp')
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


def is_safe_target(device: str, allow_external_fixed: bool = False) -> bool:
    """Whether `device` is a safe (removable) USB target on Windows.

    Uses the Win32 DriveType: only ``2`` (DRIVE_REMOVABLE) qualifies. This
    excludes fixed/internal disks (3), network drives (4), CD-ROM (5) and RAM
    disks (6) — and mounted VHDs, which report as fixed. Fails closed if the
    drive can't be found in the current enumeration.

    With ``allow_external_fixed=True`` (the "Hard Disk" target type) fixed
    drives are also accepted, since an external USB hard drive reports as
    fixed — except the system drive (normally ``C:``), which is never a valid
    target. Network, CD-ROM and RAM drives remain excluded.
    """
    try:
        letter = device.rstrip('\\').rstrip(':').upper()
        if not letter:
            return False

        system_drive = (os.environ.get('SystemDrive', 'C:')
                        .rstrip('\\').rstrip(':').upper())

        for drv in get_drive_list():
            if str(drv.get('letter', '')).upper() != letter:
                continue
            # get_drive_list sets removable = (DriveType == 2)
            if bool(drv.get('removable', False)):
                return True
            if allow_external_fixed:
                # Accept a fixed drive only if it is not the system drive.
                if letter == system_drive:
                    return False
                return str(drv.get('type', '')).lower() != 'network'
            return False
        return False
    except (AttributeError, TypeError, OSError):
        return False


def check_admin_privileges() -> bool:
    """Check if running with administrator privileges on Windows."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except (AttributeError, OSError):
        return False
