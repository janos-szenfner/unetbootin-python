"""
Platform-specific functionality for UNetbootin.

Selects the implementation module for the current platform and re-exports
its public API explicitly (no wildcard imports). Functions missing from a
platform module fall back to the stubs in `base`.

NOTE: the previous wildcard version imported `base` *last*, which silently
replaced every platform implementation with the base stubs (drive listing
always returned an empty list). Keep base as fallback only.
"""

import sys

from . import base

if sys.platform == 'darwin':
    from . import macos as _impl
elif sys.platform == 'win32':
    from . import windows as _impl
elif sys.platform.startswith('linux'):
    from . import linux as _impl
else:
    # Default implementations for unsupported platforms
    _impl = base

# Public platform API. Each name resolves to the platform implementation,
# with the base stub as fallback for names a platform module doesn't define.
_PUBLIC_API = (
    'get_drive_list',
    'get_drive_info',
    'unmount_drive',
    'mount_drive',
    'format_drive',
    'install_bootloader',
    'get_volume_label',
    'set_volume_label',
    'get_device_size',
    'check_drive_writable',
    'sync_filesystem',
    'get_mount_point',
    'is_external_drive',
    'is_safe_target',
)

for _name in _PUBLIC_API:
    globals()[_name] = getattr(_impl, _name, getattr(base, _name))

__all__ = list(_PUBLIC_API)
