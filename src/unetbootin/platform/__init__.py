"""
Platform-specific functionality for UNetbootin.
"""

import sys

# Import platform-specific modules based on current platform
if sys.platform == 'darwin':
    from .macos import *
elif sys.platform == 'win32':
    from .windows import *
elif sys.platform.startswith('linux'):
    from .linux import *
else:
    # Default implementations for unsupported platforms
    from .base import *

# Always import base for fallback
from .base import *
