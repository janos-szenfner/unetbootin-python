# UNetbootin - Python Rewrite

A Python rewrite of UNetbootin, the cross-platform tool for creating bootable USB drives from ISO files.

Original C++ version by Geza Kovacs <geza0kovacs@gmail.com>
Python rewrite started in 2026

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
│       ├── main.py                   # Main entry point
│       ├── app.py                    # Main application class
│       │
│       ├── ui/
│       │   ├── __init__.py
│       │   └── main_window.py        # Qt UI implementation
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
    └── test_models.py               # Unit tests for models
```

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

## Requirements

### Core Dependencies
- **Python 3.10+**
- **PySide6>=6.4.0** - Qt for Python (GUI framework)
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
- Main entry point with Qt application setup
- Main window class coordinating all functionality
- Signal-slot connections between components
- Root/admin privilege checking on startup
- Progress tracking for operations
- Logging to file and console

### User Interface
- Complete recreation of the original Qt UI using PySide6
- Distribution selection (radio button + combo boxes)
- Installation type selection (Distribution, Disk Image, Custom/Manual)
- Drive selection with refresh capability
- Advanced options (persistence for live USB)
- File selectors for ISO, kernel, initrd, and config files
- Progress dialogs for long operations

### Distribution Management
- Built-in list of 6 popular distributions:
  - Ubuntu (24.04 LTS, 22.04 LTS, 20.04 LTS)
  - Debian (12 Bookworm, 11 Bullseye)
  - Fedora (40, 39)
  - Linux Mint (21.3 Virginia, 21.2 Victoria)
  - Arch Linux (Latest)
  - openSUSE (Tumbleweed, Leap 15.5)
- Version management with download URLs and file sizes
- Search and filtering by category
- Easy extensibility to add more distributions
- JSON-based external distribution loading

### Download Functionality
- HTTP/HTTPS file downloads with progress tracking
- Download speed calculation and formatting
- File size verification (minimum size checks)
- FTP directory listing
- HTTP directory listing with HTML parsing
- Checksum verification (SHA256, SHA1, MD5)
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
- File copying from source to target device
- Bootloader installation support:
  - Syslinux (MBR + boot files)
  - EXTLinux (for ext filesystems)
  - GRUB/GRUB2 (for BIOS and UEFI)
- Platform-specific bootloader installation
- Temporary directory management
- Filesystem syncing
- Configuration file generation (syslinux.cfg, grub.cfg)

### Platform Support

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
- Graphical sudo detection (gksu, kdesu, gnomesu, pkexec)
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

Using PyInstaller:
```bash
# Install PyInstaller
pip install pyinstaller

# Build for current platform
pyinstaller --onefile --windowed --name unetbootin src/unetbootin/main.py

# Build for macOS (app bundle)
pyinstaller --windowed --name UNetbootin --icon=resources/unetbootin.icns src/unetbootin/main.py
```

Using cx_Freeze:
```bash
pip install cx_Freeze
python setup.py build
```

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

### Why PySide6?
- **License**: LGPL (commercial-friendly vs Qt's GPL)
- **Compatibility**: Works with Python 3.6+
- **Maintenance**: Actively maintained by Qt company
- **Features**: Full Qt feature set

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

**"No module named 'PySide6'"**
```bash
pip install PySide6
```

**"Command not found: xorriso"**
```bash
# On Ubuntu/Debian
sudo apt install xorriso

# On macOS
brew install xorriso
```

**"Permission denied" on USB drive**
- On Linux/macOS: Run with sudo
- On Windows: Run as Administrator

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
- **Qt/PySide6**: The Qt Company
- **All Linux distributions**: Their respective maintainers

## Next Steps

This is a work in progress. Here are the tasks needed to complete the rewrite:

### 🚀 High Priority
- [x] Copy resources from original project (`src/unetbootin/*.png`, `*.xpm`) to `python_unetbootin/src/unetbootin/resources/` - Done
- [ ] Test the application on all platforms (Linux, macOS, Windows)
- [x] Implement drive refresh functionality in UI - Done
- [ ] Add more distributions to the built-in list (100+ from original)
- [x] Implement ISO download functionality from distribution URLs - Done
- [ ] Test ISO extraction with actual ISO files
- [ ] Test USB installation with actual USB drives (carefully!)

### 📦 Medium Priority
- [ ] Add translation support (port `.ts` files to `.qm`)
- [ ] Implement auto-update checking
- [x] Add ISO verification (checksum comparison) - Done
- [x] Add support for more archive formats (zip, tar, etc.) - Done

### 🎨 Low Priority / Enhancements
- [ ] Add themes/dark mode support
- [ ] Add persistence configuration UI
- [ ] Add boot options editor for advanced users
- [ ] Add support for UEFI-only installations
- [ ] Add support for Secure Boot
- [ ] Add disk partitioning tool integration
- [x] Add progress estimation for downloads - Done
- [ ] Add download resume support
- [ ] Add download mirror selection

### 🧪 Testing
- [ ] Add unit tests for core functionality
- [ ] Add unit tests for platform-specific code
- [ ] Add integration tests
- [ ] Add UI tests (consider pytest-qt)
- [ ] Create test ISO files for testing

### 📝 Documentation
- [ ] Add user documentation
- [ ] Add developer documentation
- [ ] Create man page
- [ ] Add inline code documentation

### 🔧 Build & Distribution
- [ ] Create macOS .app bundle
- [ ] Create Windows installer
- [ ] Create Linux packages (.deb, .rpm, AppImage, Flatpak)
- [ ] Set up CI/CD pipeline for builds
- [ ] Set up automatic updates

### 🏗️ Architecture Improvements
- [x] Consider using async/await for I/O operations - Done
- [ ] Add plugin system for distribution definitions
- [ ] Add plugin system for extraction methods
- [ ] Add plugin system for bootloader installation
- [ ] Implement proper error recovery
- [ ] Add crash reporting
- [ ] Add telemetry (opt-in, anonymous)

### 🌐 Web Integration
- [ ] Add download progress reporting to server
- [ ] Add usage statistics (opt-in, anonymous)
- [ ] Add error reporting to help improve the software

---

## Current Status

| Component | Status |
|-----------|--------|
| Project Structure | ✅ Complete |
| Main Application | ✅ Complete |
| UI Framework | ✅ Complete |
| Distribution Models | ✅ Complete |
| Configuration | ✅ Complete |
| Downloader | ✅ Complete |
| Extractor | ✅ Complete |
| Installer | ✅ Complete |
| Platform Support | ✅ Complete (all 3 platforms) |
| Core Utilities | ✅ Complete |
| Unit Tests | ⚠️ Partial |
| Documentation | ⚠️ Partial |
| Resources | ❌ Not Started |
| Full Distribution List | ❌ Not Started |
| Translations | ❌ Not Started |
| Packaging | ❌ Not Started |

---

## Links

- [Original UNetbootin](https://unetbootin.sourceforge.net/)
- [SourceForge Project](https://sourceforge.net/projects/unetbootin/)
- [GitHub Mirror](https://github.com/unetbootin/unetbootin)

---

*This is a work in progress. Contributions are welcome!*
