# Resources

This directory contains static resources for UNetbootin.

## Directory Structure

```
resources/
├── __init__.py              # Package initialization
├── README.md                # This file
│
├── icons/                   # Application icons
│   ├── unetbootin_*.png     # Various icon sizes (14, 16, 22, 24, 32, 48, 64, 128, 192, 256, 512)
│   ├── unetbootin.icns      # macOS icon
│   ├── unetbootin.ico       # Windows icon
│   ├── unetbootin.xpm       # XPM icon
│   └── unetbootin_icons.svg # SVG source
│
├── logos/                   # Distribution logos
│   ├── asgd*.png            # Alternative System Graduated Distribution logos
│   ├── eeepclos.png         # eeepclos logo
│   ├── eeeubuntu.png        # eeeubuntu logo
│   ├── elive.png            # Elive logo
│   ├── gnewsense.png        # gNewSense logo
│   ├── kiwi_logo_ro.png     # Kiwi Linux logo
│   ├── nimblex.png          # NimbleX logo
│   ├── slitaz.png           # SliTaz logo
│   └── xpud.png             # XPUD logo
│
├── bootloader/              # Bootloader files
│   ├── mbr.bin              # Master Boot Record
│   ├── menu.c32             # Syslinux menu module
│   ├── vesamenu.c32         # Syslinux vesamenu module
│   ├── ubnldr               # UNetbootin Linux loader
│   ├── ubnldr.mbr           # UNetbootin MBR
│   ├── ubnldr.exe           # Windows loader
│   ├── ubnsylnx             # Syslinux loader (32-bit)
│   ├── ubnsylnx64           # Syslinux loader (64-bit)
│   ├── ubnexlnx             # EXTLinux loader (32-bit)
│   └── ubnexlnx64           # EXTLinux loader (64-bit)
│
├── translations/            # Qt translation files
│   └── unetbootin_*.ts      # Translation files for various languages
│
├── misc/                   # Miscellaneous resources
│   ├── 7zS.sfx              # 7-Zip self-extracting module
│   ├── gpxe                 # gPXE network boot image
│   ├── sevnz.dll            # 7-Zip DLL for Windows
│   ├── sevnz.exe            # 7-Zip executable for Windows
│   ├── asgd_en.htm          # ASGD English help
│   └── asgd_es.htm          # ASGD Spanish help
│
└── qt/                     # Qt resource files (for reference)
    ├── *.qrc                # Qt resource collection files
    └── *.pro                # Qt project files
```

## Usage

### Accessing Resources in Python

Resources can be accessed using the `importlib.resources` module (Python 3.7+) or by constructing paths relative to the package.

```python
import importlib.resources
import os

# Get path to a resource file
with importlib.resources.path('unetbootin.resources.icons', 'unetbootin_48.png') as path:
    icon_path = str(path)

# Or using pathlib
from pathlib import Path
import unetbootin

resources_dir = Path(unetbootin.__file__).parent / 'resources'
icon_path = resources_dir / 'icons' / 'unetbootin_48.png'
```

### Adding New Resources

1. **Icons**: Add PNG files to the `icons/` directory with the naming convention `unetbootin_<size>.png`
2. **Logos**: Add distribution logos to the `logos/` directory
3. **Bootloader files**: Add to the `bootloader/` directory
4. **Translations**: Add Qt `.ts` files to the `translations/` directory

## Notes

- All resources are copied from the original UNetbootin C++ project
- The SVG source file (`unetbootin_icons.svg`) is the master source for icons
- PNG icons were generated from the SVG at various sizes
- Bootloader files are platform-specific and used during USB installation
- Translation files are Qt Linguist files that need to be compiled to `.qm` files for use

## Security

⚠️ **IMPORTANT**: Binary files in `bootloader/` and `misc/` (sevnz.exe, sevnz.dll, 7zS.sfx, ubnldr.exe, syslinux.exe) are committed to the repository without cryptographic verification.

### Verification Recommended

Before using these binaries in production:
1. Verify their SHA256 checksums against trusted sources
2. Replace them with binaries from official distributions
3. Consider using Python-based alternatives (py7zr, pycdlib) instead

### Official Sources

- **Syslinux**: https://www.syslinux.org/ (bootloader files)
- **7-Zip**: https://www.7-zip.org/ (misc/7z*.* files)

### Future Improvements

- [ ] Add verified checksums for all binary files
- [ ] Implement runtime verification of resource files
- [ ] Fetch binaries dynamically from official sources with verification
