# PyNetboot - Python Rewrite

A Python rewrite of UNetbootin, the cross-platform tool for creating bootable USB drives from ISO files.

Original C++ version by Geza Kovacs <geza0kovacs@gmail.com>
Python rewrite started in 2026

## Disclaimer

This project is a creative endeavour, built for learning and experimentation.
Use it at your own responsibility. It writes directly to storage devices and
can overwrite data, so double-check your target drive before proceeding. The
software is provided "as is", without warranty of any kind, and the authors
accept no liability for any data loss or damage arising from its use.

## Project Structure

```
pynetboot/
├── README.md                          # Project documentation
├── requirements.txt                   # Python dependencies
├── setup.py                           # Setup script for installation
│
├── src/
│   └── pynetboot/
│       ├── __init__.py               # Package init with version info
│       ├── __main__.py               # Allow python -m pynetboot
│       ├── main.py                   # Main entry point (CustomTkinter)
│       ├── app.py                    # Main application class
│       │
│       ├── ui/
│       │   ├── __init__.py
│       │   └── main_window_ctk.py    # CustomTkinter UI implementation
│       │
│       ├── models/
│       │   ├── __init__.py
│       │   ├── distro.py             # Distribution models & manager
│       │   └── config.py             # Configuration management
│       │
│       ├── core/
│       │   ├── __init__.py
│       │   ├── extractor.py          # ISO/Archive extraction
│       │   ├── downloader.py         # Download functionality
│       │   ├── installer.py          # USB installation logic
│       │   └── utils.py              # Utility functions
│       │
│       └── platform/
│           ├── __init__.py
│           ├── base.py               # Base platform functions
│           ├── macos.py               # macOS-specific code
│           ├── linux.py               # Linux-specific code
│           └── windows.py             # Windows-specific code
│
└── tests/
    ├── __init__.py
    ├── test_models.py              # Unit tests for models
    ├── test_core.py                # Downloader / extractor / installer
    ├── test_platform.py            # Platform-specific functions
    ├── test_integration.py         # Cross-module (unit-level, mocked)
    ├── test_new_features.py        # Mirrors, resume, categories, UEFI/SB params
    └── test_ui.py                  # CustomTkinter window handling
```

> Note: `resources/` also contains `icons/`, `logos/`, `bootloader/`, and `translations/` — see the ⚠️ notes in *Current Status* about which of these are actually used by the running app.

## Installation

### From a release (recommended)

Prebuilt packages for every platform are attached to each
[GitHub release](https://github.com/janos-szenfner/unetbootin-python/releases).
Download the one for your system — no Python or extra toolkit required.

| Platform | Asset | Install / run |
|---|---|---|
| Windows | `pynetboot-<version>.exe` | Double-click (prompts for UAC elevation) |
| macOS | `pynetboot-<version>.dmg` | Mount, drag to Applications, then **right-click → Open** (unsigned) |
| macOS | `pynetboot-<version>.zip` | Extract, then right-click → Open |
| Linux | `pynetboot-<version>.AppImage` | `chmod +x pynetboot-*.AppImage && ./pynetboot-*.AppImage` |
| Linux (Debian/Ubuntu) | `pynetboot-<version>.deb` | `sudo apt install ./pynetboot-<version>.deb` |
| Linux (Fedora/RHEL) | `pynetboot-<version>.rpm` | `sudo dnf install ./pynetboot-<version>.rpm` |
| Linux (Flatpak) | `pynetboot-<version>.flatpak` | `flatpak install --user pynetboot-<version>.flatpak` |

After installing the DEB/RPM/Flatpak the app appears in the GNOME and KDE
application menus (under **Utilities**) with its icon, and launches with a
normal double-click — no terminal needed.

> The macOS build is **unsigned** (no Apple Developer certificate), so Gatekeeper
> requires the right-click → Open step on first launch. See `README-macOS.md` in
> the release for details.

### From source

```bash
# Clone or navigate to the project
cd pynetboot

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# For development (optional):
pip install -e .
```

## Running

```bash
# Development mode
python -m src.pynetboot.main

# After installation
python -m pynetboot.main

# Or using the entry point (after pip install -e .)
pynetboot
```

### Privileges

The GUI runs as a **normal user** — just double-click it. Writing to a raw block
device needs root, so only the privileged steps of an install elevate, on demand,
using the mechanism the OS already provides:

| Platform | Mechanism | Extra software needed |
|---|---|---|
| Linux | `pkexec` (PolicyKit), falling back to `sudo` with a graphical askpass | None — the DEB/RPM depend on `sudo` |
| macOS | `osascript` with administrator privileges (Authorization Services) | None |
| Windows | UAC (`ShellExecute` `runas`; the EXE also embeds a `uac_admin` manifest) | None |

You are prompted for your password only when an install actually begins. On Linux
`sudo` caches the credential, so a single install does not re-prompt for every step.

## Requirements

### Core Dependencies
- **Python 3.10+**
- **customtkinter>=5.2.0** - Modern, HiDPI-aware widgets on the Tkinter backend
  > ✅ **Licensing:** CustomTkinter is **MIT licensed**, compatible with this project's GPLv2-or-later and fine to bundle into redistributable executables. It replaced PySimpleGUI, whose licence terms changed across major versions.
- **Pillow>=10.0.0** - Icon rendering (`CTkImage`)
- **requests>=2.28.0** - HTTP downloads
- **psutil>=5.9.0** - System information

### Optional Dependencies (auto-detected)
- **pywin32>=305** - Windows-specific features
- **pyobjc>=9.0** - macOS-specific features  
- **pyudev>=0.24.0** - Linux hardware detection
- **py7zr>=0.20.0** - 7z archive support
- **beautifulsoup4>=4.12.0** - HTML parsing for directory listings
- **pycdlib** - pure-Python ISO9660 fallback, tried last when no external
  extractor is present

> **On extracting ISOs.** In practice this uses `xorriso`, `7z` or **bsdtar**,
> whichever is installed. bsdtar matters most on Windows, which ships it as
> `tar.exe` — so an ISO unpacks there with nothing extra installed.

### Development Dependencies
- pytest>=7.0.0
- black>=23.0.0
- mypy>=1.0.0
- pylint>=3.0.0

## Features Implemented

### Application Framework
- Main entry point with CustomTkinter application setup
- Main window class coordinating all functionality
- Event-based UI interactions
- Root/admin privilege checking on startup
- Progress tracking for operations
- Logging to file and console

### User Interface
- Modern interface built with CustomTkinter: follows the system light/dark theme, HiDPI-aware, resizable
- Distribution selection (radio button + combo boxes)
- Installation type selection (Distribution, Disk Image, Custom/Manual)
- Drive selection with refresh capability
- Advanced options (persistence for live USB)
- File selectors for ISO, kernel, initrd, and config files
- Inline progress bar and Cancel button in the main window (no popups)

### Distribution Management
- Built-in list of **22 distributions** across Linux (14), BSD (6), and Windows (2) — see the full list under *Next Steps → Distribution Statistics*
- Version management with download URLs, file sizes, and optional dynamic checksums (all 40 versions are verified against a published checksum)
- Search and filtering by category
- Easy extensibility to add more distributions
- JSON-based external distribution loading

### Download Functionality
- HTTP/HTTPS file downloads with progress tracking
- Download speed calculation and formatting
- File size verification (minimum size checks)
- FTP directory listing
- HTTP directory listing with HTML parsing
- Checksum verification (SHA256, SHA1, MD5) — mechanism present and active for 6 distros (Ubuntu 24.04/22.04/20.04, Debian current, Fedora 44/43) via dynamic `sha256_url` fetching; other distros skip verification (log "No checksum available… skipping")
- Support for redirects

### Archive Extraction
- Multiple extraction methods with automatic fallback:
  1. xorriso (most reliable for ISO)
  2. 7z (p7zip)
  3. bsdtar
  4. Python libraries (pycdlib, py7zr)
- Single file extraction from archives
- Kernel and initrd auto-detection
- Archive contents listing
- Progress reporting

### USB Installation
> ✅ **Verified on Windows and Linux; macOS not yet.** The install pipeline (format → mount → copy → bootloader) produces bootable drives on Windows and Linux, and elevation no longer needs a terminal. The bootloader half is **self-contained**: nothing has to be installed on the host — Windows uses the bundled `syslinux.exe`, Linux the bundled `ubnsylnx*`, and macOS (or any host the bundled binaries cannot run on, such as ARM Linux) uses the built-in installer in `core/syslinux_native.py`, which writes and patches the syslinux boot sector itself.
>
> The macOS path is the one still unproven on hardware: it is the only platform where the boot sector is written by that Python installer rather than by a syslinux binary. Its output is checked against real FAT32/FAT16 images and a fragmented in-memory volume, which shows the bytes are correct and self-consistent — not that a BIOS has accepted them. **Drive safety** is in place everywhere: only removable USB drives are selectable, and an explicit erase confirmation plus an installer-level hard guard prevent writing to internal/system/virtual disks.

- File copying from source to target device
- Bootloader installation (all payloads bundled — **no host installation required**):
  - Syslinux for BIOS: MBR to sector 0, boot sector + `ldlinux.sys` on the partition,
    installed by the bundled binary or the built-in installer
  - UEFI: `EFI/BOOT/BOOTX64.EFI` from the bundled syslinux.efi, unless the image
    brings its own EFI loader (which is kept)
  - EXTLinux / GRUB kept as fallbacks when they happen to be present
  - Secure Boot support (copies signed shim+mmx64.efi when available)
- Platform-specific bootloader installation
- Temporary directory management
- Filesystem syncing
- Configuration file generation (syslinux.cfg, grub.cfg)

### Platform Support
> Drive **listing/info/detection** is solid on all three platforms. The **format / mount / bootloader-install** paths are confirmed working on Windows and Linux; on macOS they are implemented but not yet exercised on real hardware.

#### macOS
- Drive listing using `diskutil`
- Drive information using `diskutil info`
- Mount/unmount using `diskutil` and `umount`
- Drive formatting using `diskutil eraseVolume`
- Bootloader installation using `bless`
- External drive detection
- Size string parsing (GB, MB, etc.)

#### Linux
- Drive listing using `lsblk`
- Drive information using `lsblk`, `blockdev`
- Serial number detection using `udevadm`, `sg_vpd`, `hdparm`
- Mount/unmount using `mount`, `umount`, `findmnt`
- Drive formatting using `mkfs.*` utilities
- Bootloader installation using the bundled syslinux (falls back to `extlinux`/`grub-install` if present)
- Volume label management using `blkid`, `e2label`, `dosfslabel`
- Filesystem type detection

#### Windows
- Drive listing using `wmic`
- Drive information using `vol`, `fsutil`
- Volume label detection
- Device size detection
- Drive writability checking
- Administrator privilege detection
- Basic bootloader support

### Configuration Management
- JSON-based configuration storage
- Cross-platform config directory handling:
  - Windows: `%APPDATA%\UNetbootin` or `%USERPROFILE%\.unetbootin`
  - macOS: `~/Library/Application Support/PyNetboot`
  - Linux: `~/.config/pynetboot` or `$XDG_CONFIG_HOME/pynetboot`
- User preferences persistence (language, last paths, etc.)

### Utility Functions
- Platform detection and information gathering
- Command line argument parsing
- External command execution with timeout
- Graphical sudo detection (gksu, kdesu, gnomesu, pkexec) — *helper exists but is not yet wired into the install flow, which still calls plain `sudo`*
- Drive listing across platforms
- Size formatting (human-readable)
- Root/admin privilege checking

## Testing

```bash
# Run all tests
python -m pytest tests/

# Run specific test file
python -m pytest tests/test_models.py

# Run with verbose output
python -m pytest -v tests/

# Run with coverage
python -m pytest --cov=src/pynetboot tests/
```

## Build & Distribution

### Setup for Development
```bash
pip install -e .
```

### Build Standalone Executables

> ✅ **Status: working and automated.** Every artifact is built in CI by
> [`.github/workflows/release.yml`](.github/workflows/release.yml) and attached to
> the GitHub release when a `v*` tag is pushed. The commands below are for
> building locally.

### Automated releases

```bash
# Cut a release: builds all artifacts and publishes them
git tag -a v1.2.3 -m "v1.2.3"
git push origin v1.2.3
```

The workflow builds Windows EXE, macOS `.app` (Universal 2, as ZIP **and** DMG),
Linux AppImage, DEB, RPM and Flatpak, then publishes them as **raw, un-zipped
release assets**. Running the workflow manually (`workflow_dispatch`) builds the
artifacts without publishing a release — the release job is tag-only.

Notes on the packaging setup, learned the hard way:

- The `create-release` job needs `permissions: contents: write`, otherwise the
  release API returns `403 Resource not accessible by integration`.
- `fpm` must be invoked as `fpm -C package … usr`, not `fpm … package/` — the
  latter installs everything under `/package/usr/...` and produces a package
  whose binary, icon and metadata are all in the wrong place.
- The DEB/RPM ship AppStream metadata (`com.pynetboot.PyNetboot.appdata.xml`)
  and icons named after the app id, so software centres show the icon, name,
  description and the GPL license once installed.
- The AppImage build pins `ARCH=x86_64` and `OUTPUT`, since `appimagetool`
  cannot infer either on its own here.
- The Flatpak manifest resolves its source paths relative to its **own**
  directory, builds against `org.freedesktop.{Platform,Sdk}//24.08`, needs
  `--share=network` for pip, and must be exported with `--repo=` before
  `flatpak build-bundle` can read it.

### Building locally

Using PyInstaller:
```bash
# Install PyInstaller
pip install pyinstaller

# Build using the spec file (recommended - includes all resources)
pyinstaller pynetboot.spec

# Or build directly with command line (icon lives under resources/icons/)
pyinstaller --onefile --windowed --name pynetboot \
    --icon=src/pynetboot/resources/icons/unetbootin.ico \
    src/pynetboot/main.py

# Build for macOS (app bundle)
pyinstaller --windowed --name PyNetboot \
    --icon=src/pynetboot/resources/icons/unetbootin.icns \
    src/pynetboot/main.py
```

> Note: `python setup.py build` does **not** produce an executable — there is no cx_Freeze configuration in `setup.py`. Use PyInstaller (above) plus the per-OS packaging steps in *Next Steps*. The `pynetboot.spec` file bundles all required resources (icons, logos, bootloader, translations) automatically.

## Adding New Distributions

Edit `src/pynetboot/models/distro.py`:

```python
builtin_distros = [
    {
        'name': 'your_distro',
        'display_name': 'Your Distribution',
        'description': 'Description of your distro',
        'category': 'YourCategory',
        'homepage': 'https://yourdistro.org',
        'versions': [
            {'name': 'Latest', 'url': 'https://download.yourdistro.org/latest.iso', 'size': 1500000000},
            {'name': 'Stable', 'url': 'https://download.yourdistro.org/stable.iso', 'size': 1400000000},
        ],
        'icon': 'yourdistro',
    },
    # ... existing distros
]
```

Or load from external JSON files:
```python
manager = DistributionManager()
manager.load_from_directory('/path/to/distro/definitions')
```

## Architecture Decisions

### Why CustomTkinter?
- **Modern look**: rounded, flat widgets instead of Tkinter's dated defaults,
  and it follows the system light/dark setting
- **HiDPI-aware**: scales correctly on high-resolution displays
- **Lightweight**: builds on the Tkinter backend already in the standard
  library, so bundles stay small — no Qt or bundled browser engine
- **Cross-platform**: the same interface on Linux, macOS and Windows
- **Licensing**: MIT, so it is safe to bundle into redistributable executables.
  This replaced PySimpleGUI, whose licence terms changed across major versions
  and required pinning to a specific release

*Trade-off:* CustomTkinter is consistent rather than *native* — it looks the
same on all three platforms rather than adopting each one's widget style.
wxPython was considered for genuinely native widgets, but it has no Linux
wheels on PyPI and ships separate arm64/x86_64 macOS wheels, which would cost
the Universal 2 macOS build.

### Why This Structure?
- **Separation of Concerns**: UI, business logic, data models, platform code are all separate
- **Testability**: Each component can be tested independently
- **Maintainability**: Clear boundaries between components
- **Extensibility**: Easy to add new features or distributions

### Threading Strategy
- **Long operations** (downloads, extraction, installation) run in worker threads
- **UI remains responsive** during operations
- **Progress reporting** through signals
- **Clean cancellation** support

## Configuration

The application uses a JSON configuration file to store user preferences:

```json
{
    "lang": "en_US",
    "last_iso_path": "/path/to/last/iso.iso",
    "last_target_drive": "/dev/sdX",
    "last_install_type": "distribution",
    "last_distro": "ubuntu",
    "last_version": "24.04 LTS",
    "enable_persistence": false,
    "persistence_size": 1000,
    "check_updates": true,
    "window_geometry": {}
}
```

## Logging

The application logs to both console and file (`pynetboot.log`):

```
2026-07-23 10:00:00 - pynetboot.app - INFO - Initializing PyNetbootApp
2026-07-23 10:00:01 - pynetboot.core.downloader - INFO - Downloading https://.../ubuntu.iso to /tmp/...
2026-07-23 10:05:01 - pynetboot.core.downloader - INFO - Downloaded 2500000000 bytes
```

## Command Line Arguments

The application supports command line arguments for automation:

```bash
# Specify language
python -m pynetboot.main --lang=en_US

# Skip root check (Linux)
python -m pynetboot.main --rootcheck=no

# Automate installation
python -m pynetboot.main --automate
```

See `src/pynetboot/core/utils.py:parse_command_line_args()` for full list.

## Troubleshooting

### Common Issues

**"No module named 'customtkinter'"**
```bash
pip install customtkinter
```

**"Command not found: xorriso"**
```bash
# On Ubuntu/Debian
sudo apt install xorriso

# On macOS
brew install xorriso
```

**"Permission denied" on USB drive**
- Writing to raw devices needs elevated privileges. The app requests them on
  demand when an install starts (pkexec/sudo on Linux, Authorization Services on
  macOS, UAC on Windows) — you do **not** need to launch it from a terminal.
- If no password prompt appears on Linux, the system has neither `pkexec` nor a
  graphical askpass helper. Install polkit (`sudo apt install policykit-1`) or
  start the app from a terminal once so `sudo` can prompt.

**Nothing happens / no icon when opening a `.deb` in a software centre**
- A `.deb` carries no icon or AppStream data in its file header, so the
  *pre-install* preview of any local `.deb` shows a placeholder icon and
  "Unknown License". After installing, the correct icon, description and GPL
  license appear, and the app shows up under **Utilities**. The Flatpak bundle
  is the format that can display this metadata before installing.

**"Drive not found"**
- Make sure the USB drive is inserted
- Click "Refresh" button in the drive selection
- On Linux: Check `lsblk` or `dmesg` after inserting

### Debug Mode

Enable debug logging by modifying `setup_logging()` in `main.py`:

```python
logging.basicConfig(
    level=logging.DEBUG,  # Change from INFO to DEBUG
    format=log_format,
    handlers=[...]
)
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run `python -m pytest` to ensure tests pass
6. Submit a pull request

### Code Style
- Follow PEP 8 guidelines
- Use type hints (Python 3.10+)
- Include docstrings for all public methods
- Keep lines under 88 characters when possible

## License

This project is licensed under the **GNU General Public License version 2 or later (GPLv2+)**.

Same as the original UNetbootin by Geza Kovacs.

See [LICENSE](LICENSE) for the full license text.

## Credits

- **Original UNetbootin**: Geza Kovacs <geza0kovacs@gmail.com>
- **Python Rewrite**: Janos Szenfner <szenfner@outlook.com>, started in 2026
- **CustomTkinter**: The CustomTkinter project (modern widgets on the Tkinter backend)
- **Icon**: derived from the original UNetbootin icon (GPLv2-or-later, as is
  this project) and recoloured in Python's palette to distinguish this
  rewrite. Only Python's colours are used — not the PSF's Python logo, which
  is a trademark with its own usage terms.
- **All Linux distributions**: Their respective maintainers

## Next Steps

This is a work in progress. Here are the tasks needed to complete the rewrite:

### 🎯 Distribution Statistics
- **Total Distributions**: 22 (40 versions, every one checksum-verified)
- **Categories**: Linux (14), BSD (6), Windows (2)

#### Available Distributions by Category:
- **Linux**: Ubuntu (24.04, 22.04, 20.04), Debian 13, Fedora (44, 43), Linux Mint 22.3 (Cinnamon, MATE), Arch Linux, Manjaro 26.0.4 (Xfce, KDE, GNOME), SUSE Tumbleweed, SUSE Leap 16.0, Zorin OS 18.1 (Core, Lite), Kali Linux 2026.2, Slackware 15.0, OpenMandriva ROME (Plasma X11/Wayland, GNOME), 6.0 Rock (Plasma X11/Wayland), Tiny Core 17.0
- **BSD**: FreeBSD 15.1, NetBSD 10.1, MidnightBSD 3.2.3, GhostBSD 26.1, DragonFly BSD 6.4.2, TrueNAS SCALE 25.10.4
- **Windows**: Windows 11 (25H2), Windows 10 (22H2) — **not downloaded by PyNetboot**

> **Note on Windows entries.** Microsoft does not publish direct ISO links, so
> these two cannot be downloaded for you. Selecting one opens Microsoft's own
> download page instead; fetch the ISO from there, then write it with
> **Disk image**, pointing at the file you downloaded. Every Linux and BSD
> entry above *is* downloaded automatically.

### 🚀 High Priority
- [x] Copy resources from original project (`src/unetbootin/*.png`, `*.xpm`) to `python_unetbootin/src/unetbootin/resources/` - ✅ Complete
- [ ] Test the application on all platforms (Linux, macOS, Windows)
- [x] Implement drive refresh functionality in UI - ✅ Complete
- [x] Implement ISO download functionality from distribution URLs - ✅ Complete

### 📦 Medium Priority
- [x] Add translation support - ✅ **Done.** Added `core/i18n.py` which parses the bundled Qt `.ts` catalogs (de/es/fr/it/hu) into a gettext-style `_()` lookup (no Qt dependency). `main.load_translations()` activates the catalog from CLI `--lang` / system locale, and the UI (`main_window_ctk.py`) wraps user-facing strings in `_()`. Supports 5 languages plus English fallback.
- [ ] Implement auto-update checking
- [x] Add ISO verification (checksum comparison) - ✅ **Done (dynamic).** Added `sha256_url` field + `Downloader.fetch_checksum_from_url()` that downloads a distro's published checksum file and matches the ISO by filename (handles both `<hex>  <file>` GNU/coreutils and `SHA256 (file) = <hex>` BSD/Fedora layouts). Currently wired for 6 distro versions (Ubuntu 24.04/22.04/20.04, Debian current, Fedora 44/43) — verified live. This verifies downloads without hardcoding hashes that rot across point releases.
- [x] Add support for more archive formats (zip, tar, etc.) - ✅ Complete

### 🎨 Low Priority / Enhancements
- [ ] Add themes/dark mode support
- [x] Add persistence configuration UI - ✅ UI present (install-side persistence not yet functional)
- [x] Add boot options editor for advanced users - ✅ UI present
- [x] Add support for UEFI-only installations - ✅ **Complete.** UI toggle present; param reaches installer which attempts to mount the EFI partition and install GRUB/syslinux EFI files. Relies on system-installed binaries (`grub-install --target=x86_64-efi`, syslinux EFI modules) or bundled EFI files when available.
- [x] Add support for Secure Boot - ✅ **Complete.** UI toggle present; installer looks for system shim/signed binaries (`/usr/lib/shim/shimx64.efi`, `/usr/share/shim/shimx64.efi`) and copies them to the EFI partition. Project does not ship signed bootloader binaries (licensing). Secure Boot requires signed shim+mmx64.efi which must be provided by the distribution or OS vendor.
- [ ] Add disk partitioning tool integration
- [x] Add progress estimation for downloads - ✅ Complete
- [x] Add download resume support - ✅ Complete
- [x] Add download mirror selection - ✅ Complete

### 🧪 Testing
- [x] Add unit tests for core functionality - ✅ Complete
- [x] Add unit tests for platform-specific code - ✅ Complete
- [x] Add integration tests - ⚠️ **Unit-level only.** All 192 tests mock `subprocess`; **no test actually formats a drive or produces a bootable USB.** A loopback-image integration test is still needed.
- [x] Add UI tests for the window layer - ✅ Complete (ported to CustomTkinter)

### 📝 Documentation
- [ ] Add user documentation
- [ ] Add developer documentation
- [x] Add inline code documentation - ✅ Complete

### 🛑 Critical — Functional & Safety (must be done before the tool is usable/safe)
> These block the core promise ("create a bootable USB by just running the app") and protect users from data loss. They must land before packaging.
- [x] **Filter the drive list to removable/external devices only** - ✅ **Done.** A new authoritative `is_safe_target()` (per-platform: macOS `diskutil info -plist` Internal/Ejectable/BusProtocol; Linux `lsblk` TYPE/RM/TRAN + virtual & system-disk exclusion; Windows `DriveType == 2`) gates `format_drive_list()`. **Internal disks, the system disk, and virtual drives / disk images are never listed — not even as an exception** (fails closed on any uncertainty).
- [x] **Add a destructive-action confirmation dialog** - ✅ **Done.** `on_ok_clicked()` now shows an explicit "This will PERMANENTLY ERASE ALL DATA on `<device>` (`<size>`, `<label>`)" `popup_yes_no` **and** re-verifies `is_safe_target()` before proceeding. A matching **hard guard in the installer** (`_prepare_installation`) refuses to format any non-removable device at the point of destruction, so the UI cannot be bypassed.
- [x] **Replace per-command `sudo` with a single elevation model** per OS (polkit/`pkexec` on Linux, Authorization Services on macOS, a UAC-elevated manifest on Windows). ✅ **Done.** Created `core/elevation.py` with:
  - `run_elevated()` - main entry point using platform-specific elevation (pkexec/osascript/ShellExecute)
  - `install_sudo_interceptor()` - monkey-patches `subprocess.run` to intercept `['sudo', ...]` calls and redirect through `run_elevated()`
  - Platform-specific implementations for Linux (**pkexec, falling back to `sudo` with a graphical askpass** so no extra toolkit is required), macOS (osascript with admin privileges), Windows (ShellExecute with runas)
  - The sudo interceptor is installed in `main()` so existing code automatically uses the new system without modification.
  - **The GUI itself is never relaunched as root.** An earlier version called `ensure_elevated()` at startup; on Linux that `pkexec` relaunch strips `DISPLAY`/`XAUTHORITY` and cannot reopen the window, so it failed with a spurious "Elevation required" dialog. Elevation now happens per privileged command, only once an install actually starts.
- [x] **Remove the terminal-dependent privilege flow.** ✅ **Done.** Replaced `show_root_warning()`, `show_admin_warning()` and `relaunch_with_sudo()` in `app.py`. The startup privilege check was removed entirely: the app no longer blocks or warns on launch, and no longer relies on Terminal.app or command-line sudo instructions.
- [x] **Actually use the bundled bootloader binaries** - ✅ **Done.** Added a frozen-app-aware resolver (`pynetboot/resources/__init__.py`: `resource_path()`/`bootloader_path()` with `sys._MEIPASS` support + `ensure_executable()`). The installer now writes the bundled `mbr.bin`, copies the bundled `menu.c32`/`vesamenu.c32`, and runs the bundled syslinux (`ubnsylnx64`/`ubnsylnx`, Windows `syslinux.exe`), falling back to system tools only if a bundled binary is missing. (Also fixed a latent `result.return_code` typo that would have crashed the Linux path.)
- [x] **Harden device resolution** - ✅ **Done.** macOS `_format_device`/`_mount_device` now resolve the whole disk and data partition via `diskutil info -plist` / `diskutil list -plist` (`_macos_whole_disk`, `_macos_data_partition`) instead of substring-scanning `diskutil list` text and hardcoding `…s1`; Linux uses `lsblk -no pkname` (`_linux_parent_disk`) for the MBR target.
- [x] **Populate distribution checksums** - ✅ **Done (dynamic).** Added a `sha256_url` field + `Downloader.fetch_checksum_from_url()` that downloads a distro's published checksum file and matches the ISO by filename (handles both `<hex>  <file>` and BSD `SHA256 (file) = <hex>` layouts). Wired for Ubuntu, Debian and Fedora — verified live. This verifies downloads without hardcoding hashes that rot across point releases.
- [x] **Wire real translations** - ✅ **Done.** Added `core/i18n.py`, which parses the bundled Qt `.ts` catalogs (de/es/fr/it/hu) into a gettext-style `_()` lookup (no Qt dependency). `main.load_translations()` now activates the catalog from the CLI `--lang` / system locale, and the UI wraps its user-facing labels/buttons in `_()`. (Semantic combo *values* like "USB Drive" are deliberately left untranslated so installer logic still matches.)

### 🔧 Build & Distribution
> **GUI dependency:** ✅ **CustomTkinter** — modern, HiDPI-aware widgets on Tkinter, MIT licensed and free to bundle. Replaced PySimpleGUI, whose licence terms changed across major versions.
- [x] **Fix packaging metadata first:** ✅ **Done.** `setup.py` `package_data` globs now match the real layout (`resources/bootloader/*`, `resources/icons/*`, `resources/logos/*`, `resources/translations/*.ts`), and `MANIFEST.in` was added to ensure resources are included in source distributions. Assets are now properly bundled in wheels, sdists and PyInstaller bundles.
- [x] **Add a frozen-app resource resolver** (`sys._MEIPASS`-aware) so icons and bootloader binaries are found inside a PyInstaller bundle. ✅ **Done.** Added `pynetboot/resources/__init__.py` with `resource_path()`, `bootloader_path()`, `icon_path()`, `translations_dir()` and helper functions that resolve paths both in normal layouts and inside frozen PyInstaller bundles.
- [x] Add a PyInstaller `.spec` (onefile/windowed) and wire the real app icon. ✅ **Done.** Created `pynetboot.spec` with cross-platform support: uses `unetbootin.ico` for Windows, `unetbootin.icns` for macOS, and `unetbootin.xpm` for Linux. Includes all resources (icons, logos, bootloader, translations) in the bundle.
- [x] Create Windows `.exe` (no install) ✅ **Done.** PyInstaller onefile/windowed via `pynetboot-windows.spec`, with the UAC `uac_admin` manifest embedded by the spec (no fragile post-build `mt.exe` step). The app icon is a real multi-resolution `.ico` (16–256 px). *Scripted `diskpart` to replace the interactive `format` command is still open.*
- [x] Create macOS `.app` → `.dmg` (drag-to-Applications) ✅ **Done.** Universal 2 bundle shipped as both a ZIP and a DMG; the DMG carries a volume icon and an Applications symlink. The Terminal-sudo flow is replaced by Authorization Services. *Still unsigned — codesign + notarize remain open.*
- [x] Create Linux packages ✅ **Done.** AppImage, `.deb`/`.rpm` (via `fpm`, declaring `syslinux`, `dosfstools`, `mtools`, `sudo`) and Flatpak (`--device=all`, runtime 24.08). Each ships a `.desktop` file and AppStream metadata so the app appears in the GNOME/KDE menus.
- [x] Set up a CI/CD matrix (windows/macos/ubuntu runners) to build all artifacts on tag. ✅ **Done.** `.github/workflows/release.yml` builds all six artifacts and publishes a GitHub release on any `v*` tag.
- [ ] Set up automatic updates.
- [ ] Codesign + notarize the macOS build so Gatekeeper stops warning.
- [x] Add `build/`, `dist/`, `__pycache__/`, `.pytest_cache/`, `venv/` to `.gitignore`. ✅ **Done.** Updated `.gitignore` with these entries plus additional common patterns (`.egg-info/`, `*.egg`, `.coverage`, `htmlcov/`, etc.). Note: `pynetboot.spec` is tracked in the repo.

### 🏗️ Architecture Improvements
- [x] Keep the interface responsive during I/O - ✅ Complete, using a worker
  thread rather than async/await. `run_in_background` runs the work off the UI
  thread while pumping the event loop, so the window stays live and Cancel and
  Log keep responding. An unreachable async layer was removed in 1.7.0: eleven
  of its thirteen methods wrapped `run_in_executor`, so they were threads with
  a coroutine signature, and the one real async path needed `aiohttp`, which is
  not a dependency. The work here is I/O-bound and the privileged steps block
  on `subprocess` regardless, so threads are the fitting model.
- [ ] Add plugin system for distribution definitions
- [ ] Add plugin system for extraction methods
- [ ] Add plugin system for bootloader installation
- [ ] Implement proper error recovery


---

## Current Status

| Component | Status |
|-----------|--------|
| Project Structure | ✅ Complete |
| Main Application | ✅ Complete |
| UI Framework | ✅ Complete — CustomTkinter (modern widgets, system light/dark, HiDPI) |
| Distribution Models | ✅ Complete |
| Configuration | ✅ Complete |
| Downloader | ✅ Complete (with resume & mirrors) |
| Extractor | ✅ Complete |
| Installer | ✅ Working on Windows and Linux — writes bootable drives with no host tools installed; elevation needs no interactive terminal (pkexec/sudo/UAC). ⚠️ macOS unverified on hardware. *Drive-safety filtering + erase confirmation are in place.* |
| Drive Safety | ✅ Removable-only selection + erase confirmation + installer hard-guard (internal/system/virtual disks can never be targeted) |
| Platform Support | ✅ Windows and Linux verified end-to-end; ⚠️ macOS implemented but untested on hardware. Drive listing/info solid everywhere. UEFI-only mode installs the bundled `syslinux.efi` as `EFI/BOOT/BOOTX64.EFI`; Secure Boot still needs a distribution-supplied signed shim |
| Core Utilities | ✅ Complete |
| Unit Tests | ⚠️ Unit-level only (mocked subprocess; no real bootable-USB test) |
| Documentation | ⚠️ Partial |
| Resources | ✅ Bundled and used — bootloader binaries in `resources/bootloader/` are now referenced via `pynetboot.resources` resolver; icons and logos are also properly bundled |
| Full Distribution List | ✅ Complete (21 distros; checksums dynamically fetched) |
| Translations | ✅ Implemented — `core/i18n.py` parses bundled Qt `.ts` catalogs (de/es/fr/it/hu) into gettext-style `_()`; wired in `main.load_translations()` |
| Checksum Verification | ✅ Dynamic — downloads and verifies distro checksums from published checksum files (wired for Ubuntu, Debian, Fedora) |
| Packaging | ✅ Complete — CI builds Windows EXE, macOS ZIP + DMG, AppImage, DEB, RPM and Flatpak on every `v*` tag and publishes them as raw release assets. DEB/RPM/Flatpak ship `.desktop` + AppStream metadata and icons, so the app appears in the GNOME/KDE menus with its icon and GPL license. *macOS build is not yet codesigned/notarized.* |
| Elevation / "no-terminal" launch | ✅ Implemented — `core/elevation.py` provides a single elevation model with a `sudo` interceptor. The GUI runs as a normal user and each privileged command elevates on demand: pkexec → `sudo` (graphical askpass) on Linux, osascript on macOS, UAC on Windows. No extra toolkit is required; the DEB/RPM depend on `sudo`. Double-click launch works on all three platforms |

---

## Links

- [Releases (prebuilt packages)](https://github.com/janos-szenfner/unetbootin-python/releases)
- [Original UNetbootin](https://unetbootin.sourceforge.net/)
- [SourceForge Project](https://sourceforge.net/projects/pynetboot/)
- [GitHub Mirror](https://github.com/pynetboot/pynetboot)

---

*This is a work in progress. Contributions are welcome!*
