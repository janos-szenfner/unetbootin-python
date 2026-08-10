# Resources

This directory contains static resources for PyNetboot.

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
├── bootloader/              # Bootloader files (syslinux 6.03)
│   ├── mbr.bin              # Master Boot Record, written to sector 0
│   ├── ldlinux.bss          # Boot sector template (BIOS)
│   ├── ldlinux.sys          # Stage 2, patched with its own sector map
│   ├── ldlinux.c32          # Loaded by ldlinux.sys at boot
│   ├── libcom32.c32         # Required by the 6.x menu modules
│   ├── libutil.c32          # Required by the 6.x menu modules
│   ├── menu.c32             # Syslinux menu module
│   ├── vesamenu.c32         # Syslinux vesamenu module
│   ├── syslinux.exe         # Windows installer binary
│   ├── ubnldr               # PyNetboot Linux loader
│   ├── ubnldr.mbr           # PyNetboot MBR
│   ├── ubnldr.exe           # Windows loader
│   ├── ubnsylnx             # Syslinux loader (32-bit)
│   ├── ubnsylnx64           # Syslinux loader (64-bit)
│   ├── ubnexlnx             # EXTLinux loader (32-bit)
│   ├── ubnexlnx64           # EXTLinux loader (64-bit)
│   └── efi64/               # UEFI payloads, copied to EFI/BOOT on the drive
│       ├── syslinux.efi     # Installed as BOOTX64.EFI
│       ├── ldlinux.e64      # Loaded by syslinux.efi
│       ├── libcom32.c32     # UEFI builds of the menu modules
│       ├── libutil.c32
│       ├── menu.c32
│       └── vesamenu.c32
│
└── translations/            # Translation files
    └── unetbootin_*.ts      # Translation files for various languages
```

## Usage

### Accessing Resources in Python

Resources can be accessed using the `importlib.resources` module (Python 3.7+) or by constructing paths relative to the package.

```python
import importlib.resources
import os

# Get path to a resource file
with importlib.resources.path('pynetboot.resources.icons', 'unetbootin_48.png') as path:
    icon_path = str(path)

# Or using pathlib
from pathlib import Path
import pynetboot

resources_dir = Path(pynetboot.__file__).parent / 'resources'
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

## Bootloader provenance

The syslinux payloads (`ldlinux.bss`, `ldlinux.sys`, `ldlinux.c32`,
`libcom32.c32`, `libutil.c32`, `menu.c32`, `vesamenu.c32`, `mbr.bin` and
everything under `efi64/`) are the prebuilt files from the official
**syslinux 6.03** release:

```
https://mirrors.edge.kernel.org/pub/linux/utils/boot/syslinux/syslinux-6.03.tar.gz
sha256  250b9bd90945d361596a7a69943d0bdc5fc0c0917aa562609f8d3058a2c36b3a
```

`menu.c32`, `vesamenu.c32`, `mbr.bin` and `syslinux.exe` were already in this
repository (from UNetbootin) and are **byte-identical** to that tarball, which
is how the rest were matched to it.

They must all stay on the same syslinux version: `ldlinux.sys` carries a
patch-area layout that `core/syslinux_native.py` writes to by offset, and the
6.x `.c32` modules are dynamically linked against `libcom32`/`libutil` from
the same build. Mixing versions produces a drive that fails at boot with
"Failed to load COM32 file".

The app ships these so that **no syslinux installation is needed on the
host** on any platform: Windows runs the bundled `syslinux.exe`, Linux the
bundled `ubnsylnx*`, and macOS (or any host whose bundled binary cannot run)
uses the built-in installer in `core/syslinux_native.py`.

## Security

Everything under *Bootloader provenance* is traced to the official syslinux
6.03 release by the tarball checksum, and four files that predate this
project — `menu.c32`, `vesamenu.c32`, `mbr.bin` and the Windows installer
`syslinux.exe` — were confirmed **byte-identical** to it. `syslinux.exe` is
therefore the only executable that runs during an install whose origin is
established.

⚠️ The remaining binaries are UNetbootin's and carry no such record:
`ubnsylnx`, `ubnsylnx64`, `ubnexlnx`, `ubnexlnx64` (`ubnsylnx64` reports
syslinux 4.03), plus `ubnldr`, `ubnldr.exe` and `ubnldr.mbr`, which no code
path references at all.

Running a bundled binary is the part worth removing, and most of it already
is: `core/syslinux_native.py` performs the whole BIOS install in Python, so
nothing has to be executed on macOS, or on a Linux host whose architecture the
x86 ELF binaries do not match. What still executes one is the Windows install
(`syslinux.exe`, verified above) and the Linux fast path (`ubnsylnx*`, with
the Python installer as the fallback when it fails).

### Official sources

- **Syslinux**: https://www.syslinux.org/ — release tarballs at
  https://mirrors.edge.kernel.org/pub/linux/utils/boot/syslinux/

### Worth doing

- [ ] Delete `ubnldr`, `ubnldr.exe` and `ubnldr.mbr` — nothing loads them
- [ ] Drop `ubnsylnx*`/`ubnexlnx*` in favour of the built-in installer on
      Linux too, once that path has been exercised on hardware there, which
      would leave no unverified binary in the tree
- [ ] Verify the bundled files at runtime before use
