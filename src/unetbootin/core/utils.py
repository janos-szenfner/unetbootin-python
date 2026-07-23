"""
Utility functions for UNetbootin.
"""

import os
import sys
import platform
import subprocess
import logging
import shlex
import psutil
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

# Supported languages (language codes for translation files)
# English (en_US/en_GB) is the default and doesn't need a translation file
SUPPORTED_LANGUAGES = {'de', 'es', 'fr', 'it', 'hu'}

# Full language code to short code mapping for Qt locale names
LANGUAGE_CODE_MAP = {
    'en_US': 'en',
    'en_GB': 'en',
    'de_DE': 'de',
    'de_AT': 'de',
    'de_CH': 'de',
    'es_ES': 'es',
    'es_MX': 'es',
    'fr_FR': 'fr',
    'fr_CA': 'fr',
    'it_IT': 'it',
    'hu_HU': 'hu',
}


def get_supported_languages() -> List[str]:
    """Get list of supported language codes.
    
    Returns:
        List of 2-letter language codes (de, es, fr, it, hu)
    """
    return sorted(SUPPORTED_LANGUAGES)


def normalize_language_code(locale_str: str) -> Optional[str]:
    """Normalize a locale string to a supported language code.
    
    Args:
        locale_str: Locale string (e.g., 'en_US', 'de_DE', 'es_ES')
        
    Returns:
        Normalized 2-letter language code if supported, None otherwise
    """
    if not locale_str:
        return None
    
    # Try direct match first
    if locale_str in SUPPORTED_LANGUAGES:
        return locale_str
    
    # Try mapping from full locale name
    if locale_str in LANGUAGE_CODE_MAP:
        return LANGUAGE_CODE_MAP[locale_str]
    
    # Try extracting language code from locale (e.g., 'de_DE' -> 'de')
    if '_' in locale_str:
        lang_code = locale_str.split('_')[0]
        if lang_code in SUPPORTED_LANGUAGES:
            return lang_code
    
    # If it's already a 2-letter code, check if supported
    if len(locale_str) == 2 and locale_str.lower() in SUPPORTED_LANGUAGES:
        return locale_str.lower()
    
    return None


def is_language_supported(locale_str: str) -> bool:
    """Check if a language/locale is supported.
    
    Args:
        locale_str: Locale string to check
        
    Returns:
        True if the language is supported, False otherwise
    """
    return normalize_language_code(locale_str) is not None


def check_root() -> bool:
    """Check if running as root (Linux/Unix)."""
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def check_admin() -> bool:
    """Check if running as administrator."""
    if sys.platform == 'win32':
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False
    elif sys.platform == 'darwin':
        # Writing boot sectors and using diskutil/bless on raw devices
        # requires root. (Do NOT test writability of /usr/local: Homebrew
        # makes it user-writable, giving false positives.)
        return check_root()
    else:
        return check_root()


def get_platform_info() -> Dict[str, Any]:
    """Get detailed platform information."""
    info = {
        'system': platform.system(),
        'node_name': platform.node(),
        'release': platform.release(),
        'version': platform.version(),
        'machine': platform.machine(),
        'processor': platform.processor(),
        'architecture': platform.architecture(),
        'python_version': platform.python_version(),
        'python_implementation': platform.python_implementation(),
    }
    
    # Add system-specific info
    if sys.platform == 'linux':
        info['linux_distro'] = get_linux_distro()
    elif sys.platform == 'darwin':
        info['mac_ver'] = platform.mac_ver()
    elif sys.platform == 'win32':
        info['windows_version'] = platform.win32_ver()
    
    # Add memory info
    try:
        mem = psutil.virtual_memory()
        info['memory_total'] = mem.total
        info['memory_available'] = mem.available
    except Exception:
        info['memory_total'] = 0
        info['memory_available'] = 0
    
    # Add disk info
    try:
        partitions = psutil.disk_partitions()
        info['partitions'] = [
            {'device': p.device, 'mountpoint': p.mountpoint, 'fstype': p.fstype}
            for p in partitions
        ]
    except Exception:
        info['partitions'] = []
    
    return info


def get_linux_distro() -> Optional[Dict[str, str]]:
    """Get Linux distribution information."""
    try:
        if os.path.exists('/etc/os-release'):
            with open('/etc/os-release', 'r') as f:
                lines = f.readlines()
            
            distro_info = {}
            for line in lines:
                if '=' in line:
                    key, value = line.strip().split('=', 1)
                    distro_info[key] = value.strip('"')
            return distro_info
    except Exception as e:
        logger.error(f"Failed to get Linux distro info: {e}")
    
    return None


def format_size(size_bytes: int) -> str:
    """Format size in bytes to human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def parse_command_line_args(args: Optional[List[str]] = None) -> Dict[str, Any]:
    """Parse command line arguments.
    
    Only the following languages are supported: en (default), de, es, fr, it, hu
    Any other language specified via --lang will be ignored and system locale will be used.
    """
    if args is None:
        args = sys.argv[1:]
    
    parsed = {
        'lang': None,
        'rootcheck': True,
        'automate': False,
        'iso': None,
        'target': None,
    }
    
    i = 0
    while i < len(args):
        arg = args[i]
        
        if arg.startswith('--'):
            # Long option
            if '=' in arg:
                key, value = arg[2:].split('=', 1)
                if key.lower() == 'lang':
                    # Validate language
                    if is_language_supported(value) or normalize_language_code(value) is not None:
                        parsed[key.lower()] = normalize_language_code(value)
                    else:
                        logger.warning(f"Language '{value}' is not supported. Supported languages: {get_supported_languages()}")
                        # Don't set unsupported language, will use system default
                else:
                    parsed[key.lower()] = value
            else:
                key = arg[2:]
                if i + 1 < len(args) and not args[i + 1].startswith('-'):
                    value = args[i + 1]
                    if key.lower() == 'lang':
                        # Validate language
                        if is_language_supported(value) or normalize_language_code(value) is not None:
                            parsed[key.lower()] = normalize_language_code(value)
                        else:
                            logger.warning(f"Language '{value}' is not supported. Supported languages: {get_supported_languages()}")
                            # Don't set unsupported language
                    else:
                        parsed[key.lower()] = value
                    i += 1
                else:
                    parsed[key.lower()] = True
        elif arg.startswith('-'):
            # Short option
            for j, char in enumerate(arg[1:]):
                if j + 1 < len(arg[1:]):
                    # Combined short options
                    parsed[char] = True
                elif i + 1 < len(args) and not args[i + 1].startswith('-'):
                    parsed[char] = args[i + 1]
                    i += 1
                else:
                    parsed[char] = True
        else:
            # Positional argument
            if not parsed.get('iso'):
                parsed['iso'] = arg
            elif not parsed.get('target'):
                parsed['target'] = arg
        
        i += 1
    
    return parsed


def locate_command(command: str, required_for: str = "", package_name: str = "") -> Optional[str]:
    """Locate a command in the system PATH."""
    try:
        result = subprocess.run(
            ['which', command],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode == 0:
            path = result.stdout.strip()
            if os.path.exists(path):
                return path
    except Exception:
        pass
    
    # Try alternative methods
    for path in os.environ.get('PATH', '').split(':'):
        full_path = os.path.join(path, command)
        if os.path.exists(full_path) and os.access(full_path, os.X_OK):
            return full_path
    
    logger.warning(f"Command not found: {command} (required for: {required_for}, package: {package_name})")
    return None


def call_external_app(exec_file: str, exec_param: str = "", write_to_stdin: Optional[str] = None) -> Tuple[int, str, str]:
    """Call an external application and return exit code, stdout, stderr."""
    logger.info(f"Calling external app: {exec_file} {exec_param}")
    
    process = None
    try:
        # Build an argument list on every platform - never shell=True, which
        # would allow command injection through exec_param.
        if sys.platform == 'win32':
            args = shlex.split(exec_param, posix=False) if exec_param else []
            process = subprocess.Popen(
                [exec_file] + args,
                stdin=subprocess.PIPE if write_to_stdin else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
        else:
            args = shlex.split(exec_param) if exec_param else []
            process = subprocess.Popen(
                [exec_file] + args,
                stdin=subprocess.PIPE if write_to_stdin else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

        stdout, stderr = process.communicate(
            input=write_to_stdin, timeout=300  # 5 minute timeout
        )
        return (process.returncode, stdout, stderr)

    except subprocess.TimeoutExpired:
        if process is not None:
            process.kill()
        logger.error(f"External app timeout: {exec_file} {exec_param}")
        return (-1, "", "Timeout")
    except Exception as e:
        logger.error(f"Failed to call external app: {exec_file} {exec_param} - {e}")
        return (-1, "", str(e))


def check_for_graphical_su(su_command: str) -> Optional[str]:
    """Check if a graphical sudo alternative is available."""
    graphical_su_commands = {
        'gksu': ['gksu', 'gksudo'],
        'kdesu': ['kdesu', 'kdesudo'],
        'gnomesu': ['gnomesu'],
        'pkexec': ['pkexec'],
    }
    
    # If specific command requested
    if su_command in graphical_su_commands:
        for cmd in graphical_su_commands[su_command]:
            if locate_command(cmd):
                return cmd
    
    # Check for any available graphical su
    for su_type, commands in graphical_su_commands.items():
        if su_type == su_command:
            continue
        for cmd in commands:
            if locate_command(cmd):
                return cmd
    
    return None


def list_available_drives() -> List[Dict[str, Any]]:
    """List all available drives/disks."""
    drives = []
    
    try:
        if sys.platform == 'win32':
            # Windows: use wmic or win32api
            try:
                import win32api
                import win32file
                
                # List all drives
                drive_bitmask = win32api.GetLogicalDrives()
                for i in range(26):
                    if drive_bitmask & (1 << i):
                        drive_letter = chr(ord('A') + i)
                        drive_path = f"{drive_letter}:\\"
                        try:
                            drive_type = win32file.GetDriveType(drive_path)
                            if drive_type in (win32file.DRIVE_REMOVABLE, win32file.DRIVE_FIXED):
                                drives.append({
                                    'device': drive_path,
                                    'type': 'removable' if drive_type == win32file.DRIVE_REMOVABLE else 'fixed',
                                    'size': 0,
                                    'label': '',
                                })
                        except Exception:
                            pass
            except ImportError:
                pass
        
        elif sys.platform == 'darwin':
            # macOS: use diskutil
            try:
                result = subprocess.run(
                    ['diskutil', 'list', '-plist'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    # Parse plist output (simplified)
                    import plistlib
                    try:
                        data = plistlib.loads(result.stdout.encode())
                        for disk in data.get('AllDisksAndPartitions', []):
                            if 'DeviceIdentifier' in disk:
                                drives.append({
                                    'device': disk['DeviceIdentifier'],
                                    'type': 'removable' if disk.get('RemovableMedia', False) else 'fixed',
                                    'size': disk.get('Size', 0),
                                    'label': disk.get('VolumeName', ''),
                                })
                    except Exception:
                        pass
            except Exception:
                pass
            
            # Fallback for macOS
            try:
                result = subprocess.run(
                    ['diskutil', 'list'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    # Simple parsing
                    lines = result.stdout.split('\n')
                    current_disk = None
                    for line in lines:
                        if '/dev/disk' in line and 'external' in line.lower():
                            parts = line.strip().split()
                            if parts:
                                current_disk = parts[0]
                                drives.append({
                                    'device': current_disk,
                                    'type': 'removable',
                                    'size': 0,
                                    'label': '',
                                })
            except Exception:
                pass
        
        else:  # Linux and other Unix
            try:
                # Use lsblk
                result = subprocess.run(
                    ['lsblk', '-J'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    import json
                    try:
                        data = json.loads(result.stdout)
                        for device in data.get('blockdevices', []):
                            if device.get('type') == 'disk':
                                drives.append({
                                    'device': device.get('name', ''),
                                    'type': 'removable' if device.get('rm', False) else 'fixed',
                                    'size': device.get('size', 0),
                                    'label': '',
                                    'children': [
                                        {'name': c.get('name'), 'size': c.get('size'), 'mountpoint': c.get('mountpoint')}
                                        for c in device.get('children', [])
                                    ]
                                })
                    except Exception:
                        pass
            except Exception:
                pass
            
            # Fallback: use /dev/disk/by-id
            try:
                if os.path.exists('/dev/disk/by-id'):
                    for entry in os.listdir('/dev/disk/by-id'):
                        if 'usb' in entry.lower() or 'ata' in entry.lower():
                            device_path = os.path.join('/dev/disk/by-id', entry)
                            drives.append({
                                'device': device_path,
                                'type': 'removable',
                                'size': 0,
                                'label': '',
                            })
            except Exception:
                pass
        
    except Exception as e:
        logger.error(f"Error listing drives: {e}")
    
    # Remove duplicates and sort
    unique_drives = []
    seen_devices = set()
    for drive in drives:
        device = drive.get('device', '')
        if device and device not in seen_devices:
            seen_devices.add(device)
            unique_drives.append(drive)
    
    return sorted(unique_drives, key=lambda x: x.get('device', ''))


def get_drive_info(device: str) -> Optional[Dict[str, Any]]:
    """Get detailed information about a specific drive."""
    try:
        if sys.platform == 'win32':
            # Windows implementation
            pass
        elif sys.platform == 'darwin':
            # macOS: use diskutil info
            result = subprocess.run(
                ['diskutil', 'info', '-plist', device],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                import plistlib
                try:
                    data = plistlib.loads(result.stdout.encode())
                    return {
                        'device': device,
                        'size': data.get('TotalSize', 0),
                        'label': data.get('VolumeName', ''),
                        'filesystem': data.get('FilesystemType', ''),
                        'mountpoint': data.get('MountPoint', ''),
                        'removable': data.get('RemovableMedia', False),
                        'vendor': data.get('DeviceVendor', ''),
                        'model': data.get('DeviceModel', ''),
                    }
                except Exception:
                    pass
        else:
            # Linux: use lsblk or blkid
            result = subprocess.run(
                ['lsblk', '-J', '-d', '-o', 'NAME,SIZE,TYPE,RM,MODEL,VENDOR'],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                import json
                try:
                    data = json.loads(result.stdout)
                    for device_info in data.get('blockdevices', []):
                        if device_info.get('name') == os.path.basename(device):
                            return {
                                'device': device,
                                'size': int(device_info.get('size', 0)),
                                'type': device_info.get('type', ''),
                                'removable': device_info.get('rm', False),
                                'model': device_info.get('model', ''),
                                'vendor': device_info.get('vendor', ''),
                            }
                except Exception:
                    pass
    
    except Exception as e:
        logger.error(f"Error getting drive info for {device}: {e}")
    
    return None
