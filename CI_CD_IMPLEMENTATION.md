# CI/CD Implementation for UNetbootin

## Summary

This implementation provides a complete GitHub Actions CI/CD pipeline that automatically builds and releases UNetbootin for all major platforms (Windows, macOS, Linux) using GitHub's free build services. No local builds are required.

## What Was Implemented

### 1. GitHub Actions Workflow
- **File**: `.github/workflows/release.yml`
- **Trigger**: On tag push (`v*`) or manual workflow dispatch
- **Jobs**:
  - `test`: Runs the test suite on Ubuntu
  - `build-windows`: Builds Windows .exe with UAC manifest
  - `build-macos`: Builds macOS .app → .dmg with optional code signing
  - `build-linux-appimage`: Builds Linux AppImage
  - `build-linux-deb`: Builds Debian .deb package
  - `build-linux-rpm`: Builds Fedora/RHEL .rpm package
  - `build-flatpak`: Builds Flatpak bundle
  - `create-release`: Creates GitHub Release with all artifacts

### 2. Platform-Specific Spec Files
- **`unetbootin-windows.spec`**: Windows PyInstaller spec with manifest support
- **`unetbootin-macos.spec`**: macOS PyInstaller spec with app bundle settings
- **`unetbootin.spec`**: Generic spec for Linux builds

### 3. Resource Files
- **`resources/windows/unetbootin.exe.manifest`**: UAC manifest for Windows elevation
- **`resources/linux/unetbootin.desktop`**: Linux desktop entry file
- **`resources/linux/com.unetbootin.UNetbootin.json`**: Flatpak manifest

### 4. Code Changes

#### Windows Platform (`src/unetbootin/platform/windows.py`)
- **Replaced interactive format command with scripted diskpart**
- Implemented `format_drive()` using diskpart scripting
- Creates temporary script files for non-interactive diskpart operations
- Supports FAT32, NTFS, and exFAT filesystems
- Properly cleans up temporary files

#### Installer (`src/unetbootin/core/installer.py`)
- Updated `_format_device()` to use platform-specific `format_drive()` function
- Consistent formatting across all platforms
- Better error handling

## Build Artifacts

### Windows
- **Output**: `unetbootin.exe`
- **Type**: Single-file executable
- **Features**:
  - Windowed mode (no console)
  - UAC manifest embedded for admin elevation
  - All resources bundled (icons, bootloaders, translations)
  - diskpart-based non-interactive formatting

### macOS
- **Output**: `unetbootin.dmg`
- **Contains**: `unetbootin.app` bundle
- **Features**:
  - Native .app bundle
  - DMG with volume name "UNetbootin"
  - Optional code signing (requires secrets)
  - Optional notarization (requires secrets)
  - All resources bundled

### Linux
1. **AppImage** (`unetbootin.AppImage`)
   - Single-file portable executable
   - Works on most modern distributions
   - Includes all dependencies
   - No installation required

2. **DEB Package** (`unetbootin.deb`)
   - For Debian/Ubuntu-based distributions
   - Declares dependencies: syslinux, syslinux-common, dosfstools, mtools
   - Proper .desktop file integration

3. **RPM Package** (`unetbootin.rpm`)
   - For Fedora/RHEL-based distributions
   - Declares dependencies: syslinux, dosfstools, mtools
   - Proper .desktop file integration

4. **Flatpak** (`unetbootin.flatpak`)
   - Sandboxed application
   - Uses Flatpak runtime 23.08
   - Has access to all devices (`--device=all`)
   - Proper sandboxing with filesystem access

## Required GitHub Secrets (Optional)

The workflow functions without any secrets, but for full macOS functionality:

| Secret | Description | Required |
|--------|-------------|----------|
| `APPLE_CERTIFICATE` | Base64-encoded .p12 certificate | No |
| `APPLE_CERTIFICATE_PASSWORD` | Certificate password | No |
| `APPLE_CERTIFICATE_NAME` | Certificate common name | No |
| `APPLE_ID` | Apple Developer email | No |
| `APPLE_ID_PASSWORD` | App-specific password | No |

**Without these secrets:**
- macOS builds will still be created but unsigned
- Users will need to right-click → Open to bypass Gatekeeper

## Usage

### Triggering a Release

```bash
# Create a new version tag
git tag v1.0.0
git push origin v1.0.0
```

The workflow will automatically:
1. Run all tests
2. Build packages for all platforms in parallel
3. Create a GitHub Release with all artifacts
4. Upload all build artifacts

### Manual Trigger
You can also manually trigger the workflow via:
1. GitHub Actions tab
2. Select "Release" workflow
3. Click "Run workflow"
4. Optionally specify a version

## File Structure

```
.github/
├── workflows/
│   └── release.yml          # Main CI/CD workflow
└── CI_CD_SETUP.md          # Setup documentation

resources/
├── windows/
│   └── unetbootin.exe.manifest  # UAC manifest
└── linux/
    ├── unetbootin.desktop       # Desktop entry
    └── com.unetbootin.UNetbootin.json  # Flatpak manifest

*.spec                     # PyInstaller spec files
```

## Key Features

### 1. Cross-Platform Support
- Windows EXE with UAC elevation
- macOS .app bundle in DMG
- Linux: AppImage, DEB, RPM, Flatpak

### 2. No Local Builds Required
- Everything builds on GitHub's runners
- Uses GitHub's free build minutes
- No need for local development environment

### 3. Automatic Testing
- Full test suite runs before any builds
- Prevents releasing broken code

### 4. Parallel Builds
- All platform builds run in parallel
- Faster release process

### 5. Professional Packaging
- Proper platform-specific packaging
- Native installers for each platform
- Proper metadata and icons

### 6. Scripted Diskpart for Windows
- Replaced interactive format command
- Non-interactive diskpart scripting
- Supports FAT32, NTFS, exFAT
- Proper error handling

## Testing the Implementation

### Local Testing
You can test individual components locally:

```bash
# Test Windows build (requires Windows)
pyinstaller unetbootin-windows.spec --onefile --windowed

# Test macOS build (requires macOS)
pyinstaller unetbootin-macos.spec --windowed

# Test Linux build
pyinstaller unetbootin.spec --onefile
```

### Verifying the Setup

1. **Check workflow syntax**:
   ```bash
   # Install act (GitHub Actions local runner)
   # Then test the workflow locally
   ```

2. **Verify files exist**:
   ```bash
   ls -la .github/workflows/
   ls -la resources/windows/
   ls -la resources/linux/
   ls -la *.spec
   ```

3. **Run tests**:
   ```bash
   python -m pytest tests/ -v
   ```

## Limitations

### macOS Code Signing
- Requires Apple Developer account ($99/year)
- Without signing, users see Gatekeeper warnings
- Notarization adds ~2-5 minutes to build time

### Windows UAC
- UAC manifest embedding requires Windows SDK
- GitHub Actions windows-latest has this pre-installed
- Local builds may need to install Windows SDK

### Flatpak
- Build time is longer (~10-15 minutes)
- Flatpak runtime must be installed on user systems
- Requires --device=all for USB access

## Future Improvements

1. **Code Signing for Windows**
   - Add support for Authenticode signing
   - Requires Windows Developer certificate

2. **Automated Notarization Polling**
   - Currently uses `sleep 60`
   - Could poll for actual completion

3. **Matrix Testing**
   - Test on multiple Python versions
   - Test on multiple OS versions

4. **Nightly Builds**
   - Automated builds from main branch
   - For testing latest changes

5. **Artifact Retention**
   - Keep old releases for historical purposes
   - Clean up old artifacts automatically

## Documentation

- `.github/CI_CD_SETUP.md` - Detailed setup instructions
- This file - Implementation overview
- Workflow file comments - Specific build steps

## Support

For issues with the CI/CD setup:
1. Check the workflow run logs in GitHub Actions
2. Review the documentation in `.github/CI_CD_SETUP.md`
3. Verify all required files are in place
4. Check that secrets are properly configured (if using code signing)

## License

This CI/CD implementation is provided under the same license as UNetbootin (GPLv2+).
