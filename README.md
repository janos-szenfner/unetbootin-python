# UNetbootin - Python Rewrite

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
python_unetbootin/
├── README.md                          # Project documentation
├── requirements.txt                   # Python dependencies
├── setup.py                           # Setup script for installation
│
├── src/
│   └── unetbootin/
│       ├── __init__.py               # Package init with version info
│       ├── __main__.py               # Allow python -m unetbootin
│       ├── main.py                   # Main entry point (PySimpleGUI)
│       ├── app.py                    # Main application class (PySimpleGUI)
│       │
│       ├── ui/
│       │   ├── __init__.py
│       │   └── main_window_pysg.py   # PySimpleGUI UI implementation
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
    └── test_ui.py                  # PySimpleGUI window handling
```

> Note: `resources/` also contains `icons/`, `logos/`, `bootloader/`, and `translations/` — see the ⚠️ notes in *Current Status* about which of these are actually used by the running app.

## Installation

```bash
# Clone or navigate to the project
cd python_unetbootin

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
python -m src.unetbootin.main

# After installation
python -m unetbootin.main

# Or using the entry point (after pip install -e .)
unetbootin
```

> ⚠️ **Current limitation:** creating a USB writes to raw block devices, which needs elevated privileges. Until the double-click elevation model is implemented (see 🛑 Critical in *Next Steps*), the app must be launched with `sudo` (Linux/macOS) or as Administrator (Windows) — it does **not** yet meet the "just double-click the executable" goal.

## Requirements

### Core Dependencies
- **Python 3.10+**
- **PySimpleGUI==6.2** - Lightweight GUI framework (Tkinter backend)
  > ✅ **Licensing:** pinned to **PySimpleGUI 6.2, which is released under the GPLv3** — a free copyleft license, compatible with this project's GPLv2-or-later and fine to bundle into redistributable executables. (The pin also avoids the withdrawn commercial-license-key 5.x line.)
- **requests>=2.28.0** - HTTP downloads
- **psutil>=5.9.0** - System information

### Optional Dependencies (auto-detected)
- **pywin32>=305** - Windows-specific features
- **pyobjc>=9.0** - macOS-specific features  
- **pyudev>=0.24.0** - Linux hardware detection
- **py7zr>=0.20.0** - 7z archive support
- **beautifulsoup4>=4.12.0** - HTML parsing for directory listings
- **pycdlib** - ISO9660 reading/writing
- **iso9660** - Alternative ISO library

### Development Dependencies
- pytest>=7.0.0
- black>=23.0.0
- mypy>=1.0.0
- pylint>=3.0.0

## Features Implemented

### Application Framework
- Main entry point with PySimpleGUI application setup
- Main window class coordinating all functionality
- Event-based UI interactions
- Root/admin privilege checking on startup
- Progress tracking for operations
- Logging to file and console

### User Interface
- Complete recreation of the original UI using PySimpleGUI + Tkinter
- Distribution selection (radio button + combo boxes)
- Installation type selection (Distribution, Disk Image, Custom/Manual)
- Drive selection with refresh capability
- Advanced options (persistence for live USB)
- File selectors for ISO, kernel, initrd, and config files
- Progress dialogs for long operations

### Distribution Management
- Built-in list of **21 distributions** across Linux (13), BSD (6), and Windows (2) — see the full list under *Next Steps → Distribution Statistics*
- Version management with download URLs, file sizes, and optional dynamic checksums (⚠️ partial — 6 of 28 versions have `sha256_url` wired; see checksum note above)
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
  4. Python libraries (pycdlib, py7zr, iso9660)
- Single file extraction from archives
- Kernel and initrd auto-detection
- Archive contents listing
- Progress reporting

### USB Installation
> ⚠️ **Not yet working end-to-end.** The install pipeline (format → mount → copy → bootloader) still has correctness gaps — see the 🛑 Critical section under *Next Steps*. Key limitations today: it shells out to interactive `sudo` (fails in a no-terminal GUI), requires **system-installed** syslinux/grub (the bundled `resources/bootloader/` binaries are unused), and resolves target disks by fragile text parsing. **Drive safety is handled**, though: only removable USB drives are selectable, and an explicit erase confirmation + installer-level hard guard prevent writing to internal/system/virtual disks. Treat the items below as *implemented code paths*, not verified working features.

- File copying from source to target device
- Bootloader installation support (via **system-installed** tools, not the bundled binaries):
  - Syslinux (MBR + boot files)
  - EXTLinux (for ext filesystems)
  - GRUB/GRUB2 (for BIOS and UEFI)
  - UEFI-only mode (installs GRUB/syslinux EFI files to EFI partition)
  - Secure Boot support (copies signed shim+mmx64.efi when available)
- Platform-specific bootloader installation
- Temporary directory management
- Filesystem syncing
- Configuration file generation (syslinux.cfg, grub.cfg)

### Platform Support
> ⚠️ Drive **listing/info/detection** is solid on all three platforms. The **format / mount / bootloader-install** paths below are implemented but incomplete and not verified on real hardware.

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
- Bootloader installation using `syslinux`, `extlinux`, `grub-install`
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
  - macOS: `~/Library/Application Support/UNetbootin`
  - Linux: `~/.config/unetbootin` or `$XDG_CONFIG_HOME/unetbootin`
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
python -m pytest --cov=src/unetbootin tests/
```

## Build & Distribution

### Setup for Development
```bash
pip install -e .
```

### Build Standalone Executables

> ⚠️ **Status: Partially working.** These commands are a starting point only. The GUI dependency is settled (PySimpleGUI 6.2, GPLv3). Packaging metadata is now correct (`setup.py` `package_data` matches the real asset paths), and a `sys._MEIPASS`-aware resource resolver (`unetbootin.resources`) finds bundled icons/bootloader binaries at runtime. See *Next Steps → 🔧 Build & Distribution* for remaining packaging tasks.

Using PyInstaller (illustrative):
```bash
# Install PyInstaller
pip install pyinstaller

# Build using the spec file (recommended - includes all resources)
pyinstaller unetbootin.spec

# Or build directly with command line (icon lives under resources/icons/)
pyinstaller --onefile --windowed --name unetbootin \
    --icon=src/unetbootin/resources/icons/unetbootin.ico \
    src/unetbootin/main.py

# Build for macOS (app bundle)
pyinstaller --windowed --name UNetbootin \
    --icon=src/unetbootin/resources/icons/unetbootin.icns \
    src/unetbootin/main.py
```

> Note: `python setup.py build` does **not** produce an executable — there is no cx_Freeze configuration in `setup.py`. Use PyInstaller (above) plus the per-OS packaging steps in *Next Steps*. The `unetbootin.spec` file bundles all required resources (icons, logos, bootloader, translations) automatically.

## Adding New Distributions

Edit `src/unetbootin/models/distro.py`:

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

### Why PySimpleGUI?
- **Lightweight**: Small dependency footprint, uses the built-in Tkinter backend
- **Compatibility**: Works with Python 3.10+
- **Simplicity**: Simple, declarative layouts that are quick to maintain
- **Cross-platform**: Runs on Linux, macOS and Windows without native Qt builds

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

The application logs to both console and file (`unetbootin.log`):

```
2026-07-23 10:00:00 - unetbootin.app - INFO - Initializing UNetbootinApp
2026-07-23 10:00:01 - unetbootin.core.downloader - INFO - Downloading https://.../ubuntu.iso to /tmp/...
2026-07-23 10:05:01 - unetbootin.core.downloader - INFO - Downloaded 2500000000 bytes
```

## Command Line Arguments

The application supports command line arguments for automation:

```bash
# Specify language
python -m unetbootin.main --lang=en_US

# Skip root check (Linux)
python -m unetbootin.main --rootcheck=no

# Automate installation
python -m unetbootin.main --automate
```

See `src/unetbootin/core/utils.py:parse_command_line_args()` for full list.

## Troubleshooting

### Common Issues

**"No module named 'PySimpleGUI'"**
```bash
# PySimpleGUI 6.2 is GPLv3 (free, no license key):
pip install "PySimpleGUI==6.2"
```

**"Command not found: xorriso"**
```bash
# On Ubuntu/Debian
sudo apt install xorriso

# On macOS
brew install xorriso
```

**"Permission denied" on USB drive**
- Writing to raw devices needs elevated privileges. Today the app relies on `sudo`/admin, so in practice it must currently be started from a terminal with `sudo` (Linux/macOS) or "Run as Administrator" (Windows). *This is a known limitation — a proper double-click elevation model (polkit / Authorization Services / UAC) is tracked under 🛑 Critical in Next Steps.*

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
- **Python Rewrite**: Started in 2026
- **PySimpleGUI**: The PySimpleGUI project (Tkinter backend)
- **All Linux distributions**: Their respective maintainers

## Next Steps

This is a work in progress. Here are the tasks needed to complete the rewrite:

### 🎯 Distribution Statistics
- **Total Distributions**: 21
- **Categories**: Linux (13), BSD (6), Windows (2)

#### Available Distributions by Category:
- **Linux**: Ubuntu (24.04, 22.04, 20.04), Debian 13, Fedora (44, 43), Linux Mint (22.3, 22.2), Arch Linux, SUSE Tumbleweed, SUSE Leap 16.0, Zorin OS 18.1, Kali Linux 2026.2, Slackware 15.0, OpenMandriva (ROME, 6.0), Tiny Core 17.0
- **BSD**: FreeBSD 15.1, NetBSD 10.1, MidnightBSD 3.2.3, GhostBSD 26.1, DragonFly BSD 6.4.2, TrueNAS SCALE 25.10.4
- **Windows**: Windows 11 (24H2, 23H2, 22H2), Windows 10 (22H2, 21H2)

### 🚀 High Priority
- [x] Copy resources from original project (`src/unetbootin/*.png`, `*.xpm`) to `python_unetbootin/src/unetbootin/resources/` - ✅ Complete
- [ ] Test the application on all platforms (Linux, macOS, Windows)
- [x] Implement drive refresh functionality in UI - ✅ Complete
- [x] Implement ISO download functionality from distribution URLs - ✅ Complete

### 📦 Medium Priority
- [x] Add translation support - ✅ **Done.** Added `core/i18n.py` which parses the bundled Qt `.ts` catalogs (de/es/fr/it/hu) into a gettext-style `_()` lookup (no Qt dependency). `main.load_translations()` activates the catalog from CLI `--lang` / system locale, and the UI (`main_window_pysg.py`) wraps user-facing strings in `_()`. Supports 5 languages plus English fallback.
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
- [x] Add integration tests - ⚠️ **Unit-level only.** All 166 tests mock `subprocess`; **no test actually formats a drive or produces a bootable USB.** A loopback-image integration test is still needed.
- [x] Add UI tests for PySimpleGUI - ✅ Complete

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
  - `ensure_elevated()` - checks elevation at startup and attempts to relaunch if needed
  - Platform-specific implementations for Linux (pkexec), macOS (osascript with admin privileges), Windows (ShellExecute with runas)
  - The sudo interceptor is installed in `main()` so existing code automatically uses the new system without modification.
- [x] **Remove the terminal-dependent privilege flow.** ✅ **Done.** Replaced `show_root_warning()`, `show_admin_warning()`, and `relaunch_with_sudo()` in `app.py` with `check_privileges()` that uses the new `ensure_elevated()` function. No longer relies on Terminal.app or command-line sudo instructions.
- [x] **Actually use the bundled bootloader binaries** - ✅ **Done.** Added a frozen-app-aware resolver (`unetbootin/resources/__init__.py`: `resource_path()`/`bootloader_path()` with `sys._MEIPASS` support + `ensure_executable()`). The installer now writes the bundled `mbr.bin`, copies the bundled `menu.c32`/`vesamenu.c32`, and runs the bundled syslinux (`ubnsylnx64`/`ubnsylnx`, Windows `syslinux.exe`), falling back to system tools only if a bundled binary is missing. (Also fixed a latent `result.return_code` typo that would have crashed the Linux path.)
- [x] **Harden device resolution** - ✅ **Done.** macOS `_format_device`/`_mount_device` now resolve the whole disk and data partition via `diskutil info -plist` / `diskutil list -plist` (`_macos_whole_disk`, `_macos_data_partition`) instead of substring-scanning `diskutil list` text and hardcoding `…s1`; Linux uses `lsblk -no pkname` (`_linux_parent_disk`) for the MBR target.
- [x] **Populate distribution checksums** - ✅ **Done (dynamic).** Added a `sha256_url` field + `Downloader.fetch_checksum_from_url()` that downloads a distro's published checksum file and matches the ISO by filename (handles both `<hex>  <file>` and BSD `SHA256 (file) = <hex>` layouts). Wired for Ubuntu, Debian and Fedora — verified live. This verifies downloads without hardcoding hashes that rot across point releases.
- [x] **Wire real translations** - ✅ **Done.** Added `core/i18n.py`, which parses the bundled Qt `.ts` catalogs (de/es/fr/it/hu) into a gettext-style `_()` lookup (no Qt dependency). `main.load_translations()` now activates the catalog from the CLI `--lang` / system locale, and the UI wraps its user-facing labels/buttons in `_()`. (Semantic combo *values* like "USB Drive" are deliberately left untranslated so installer logic still matches.)

### 🔧 Build & Distribution
> **GUI dependency:** ✅ resolved — pinned to **`PySimpleGUI==6.2` (GPLv3)**, which is free to bundle into redistributable executables.
- [x] **Fix packaging metadata first:** ✅ **Done.** `setup.py` `package_data` globs now match the real layout (`resources/bootloader/*`, `resources/icons/*`, `resources/logos/*`, `resources/translations/*.ts`), and `MANIFEST.in` was added to ensure resources are included in source distributions. Assets are now properly bundled in wheels, sdists and PyInstaller bundles.
- [x] **Add a frozen-app resource resolver** (`sys._MEIPASS`-aware) so icons and bootloader binaries are found inside a PyInstaller bundle. ✅ **Done.** Added `unetbootin/resources/__init__.py` with `resource_path()`, `bootloader_path()`, `icon_path()`, `translations_dir()` and helper functions that resolve paths both in normal layouts and inside frozen PyInstaller bundles.
- [x] Add a PyInstaller `.spec` (onefile/windowed) and wire the real app icon. ✅ **Done.** Created `unetbootin.spec` with cross-platform support: uses `unetbootin.ico` for Windows, `unetbootin.icns` for macOS, and `unetbootin.xpm` for Linux. Includes all resources (icons, logos, bootloader, translations) in the bundle.
- [ ] Create Windows `.exe` (no install) — PyInstaller `--onefile --windowed` **+ a UAC `uac_admin` manifest**; replace the interactive `format` command with scripted `diskpart`.
- [ ] Create macOS `.app` → `.dmg` (drag-to-Applications) — **codesign + notarize** (Gatekeeper blocks unsigned apps); replace the Terminal-sudo flow with Authorization Services.
- [ ] Create Linux packages: **AppImage** first (simplest single-file), then `.deb`/`.rpm` via `fpm`, then **Flatpak** last (sandbox makes raw block-device writes hard — needs `--device=all` + host tools); ship a `.desktop` file and declare runtime deps (syslinux, dosfstools).
- [ ] Set up a CI/CD matrix (windows/macos/ubuntu runners) to build all artifacts on tag.
- [ ] Set up automatic updates.
- [x] Add `build/`, `dist/`, `__pycache__/`, `.pytest_cache/`, `venv/` to `.gitignore`. ✅ **Done.** Updated `.gitignore` with these entries plus additional common patterns (`.egg-info/`, `*.egg`, `.coverage`, `htmlcov/`, etc.). Note: `unetbootin.spec` is tracked in the repo.

### 🏗️ Architecture Improvements
- [x] Consider using async/await for I/O operations - ✅ Complete
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
| UI Framework | ✅ Complete |
| Distribution Models | ✅ Complete |
| Configuration | ✅ Complete |
| Downloader | ✅ Complete (with resume & mirrors) |
| Extractor | ✅ Complete |
| Installer | ⚠️ **Not working end-to-end** — depends on interactive `sudo`, needs system-installed syslinux, fragile device detection (see 🛑 Critical). *Drive-safety filtering + erase confirmation are now in place.* |
| Drive Safety | ✅ Removable-only selection + erase confirmation + installer hard-guard (internal/system/virtual disks can never be targeted) |
| Platform Support | ⚠️ Partial — drive listing/info solid; format/mount/bootloader paths implemented (including UEFI-only mode via system-installed `grub-install --target=x86_64-efi`, syslinux EFI modules, and Secure Boot via shim+mmx64.efi) but not verified end-to-end on all 3 platforms |
| Core Utilities | ✅ Complete |
| Unit Tests | ⚠️ Unit-level only (mocked subprocess; no real bootable-USB test) |
| Documentation | ⚠️ Partial |
| Resources | ✅ Bundled and used — bootloader binaries in `resources/bootloader/` are now referenced via `unetbootin.resources` resolver; icons and logos are also properly bundled |
| Full Distribution List | ✅ Complete (21 distros; checksums dynamically fetched) |
| Translations | ✅ Implemented — `core/i18n.py` parses bundled Qt `.ts` catalogs (de/es/fr/it/hu) into gettext-style `_()`; wired in `main.load_translations()` |
| Checksum Verification | ✅ Dynamic — downloads and verifies distro checksums from published checksum files (wired for Ubuntu, Debian, Fedora) |
| Packaging | ⚠️ Partially complete — `setup.py` metadata and `package_data` are correct; frozen-app resolver works; PyInstaller `.spec` added (cross-platform, uses platform-appropriate icons). Remaining: platform-specific packaging, CI/CD |
| Elevation / "no-terminal" launch | ✅ Implemented — `core/elevation.py` provides single elevation model with sudo interceptor; `main()` installs interceptor and attempts elevation at startup; `app.py` no longer uses terminal-dependent flows. Uses pkexec on Linux, osascript on macOS, and ShellExecute on Windows. Automatic relaunch with UAC requires a manifest for packaged Windows builds |

---

## Links

- [Original UNetbootin](https://unetbootin.sourceforge.net/)
- [SourceForge Project](https://sourceforge.net/projects/unetbootin/)
- [GitHub Mirror](https://github.com/unetbootin/unetbootin)

---

*This is a work in progress. Contributions are welcome!*
