# CI/CD Setup for UNetbootin

This document describes the GitHub Actions CI/CD setup for automatically building and releasing UNetbootin for all platforms.

## Overview

The CI/CD pipeline uses GitHub Actions to:
1. Run tests on every push
2. Build packages for Windows, macOS, and Linux when a tag is pushed
3. Create a GitHub Release with all the artifacts

## Triggering a Release

To create a new release:

```bash
# Create and push a new tag
git tag v1.0.0
git push origin v1.0.0
```

Or manually trigger the workflow via GitHub Actions UI.

## Workflow Files

- `.github/workflows/release.yml` - Main release workflow

## Required Secrets

The workflow will work without any secrets, but for full functionality on macOS, you should configure these secrets in your GitHub repository (Settings > Secrets > Actions):

### macOS Code Signing (Optional but Recommended)

| Secret Name | Description | Required |
|-------------|-------------|----------|
| `APPLE_CERTIFICATE` | Base64-encoded .p12 certificate file | No |
| `APPLE_CERTIFICATE_PASSWORD` | Password for the .p12 file | No |
| `APPLE_CERTIFICATE_NAME` | Certificate common name (e.g., "Developer ID Application: Your Name") | No |
| `APPLE_ID` | Apple Developer account email | No |
| `APPLE_ID_PASSWORD` | App-specific password for notarization | No |

**How to create the certificate:**

1. Export your Developer ID certificate from Keychain Access as a .p12 file
2. Encode it in base64: `base64 -i certificate.p12 -o certificate.b64`
3. Copy the content of certificate.b64 into the `APPLE_CERTIFICATE` secret

**Note:** Without code signing, macOS Gatekeeper will block the app by default. Users will need to right-click and select "Open" to bypass Gatekeeper.

## Build Artifacts

### Windows
- **File**: `unetbootin.exe`
- **Features**: 
  - Single-file executable (--onefile)
  - Windowed mode (no console)
  - UAC manifest embedded for admin elevation
  - All resources bundled (icons, bootloaders, etc.)

### macOS
- **File**: `unetbootin.dmg`
- **Features**:
  - .app bundle
  - DMG with volume name "UNetbootin"
  - Optional code signing
  - Optional notarization
  - All resources bundled

### Linux
- **AppImage**: `unetbootin.AppImage`
  - Single-file portable executable
  - Works on most modern Linux distributions
  - Includes all dependencies
  
- **DEB**: `unetbootin.deb`
  - For Debian/Ubuntu-based distributions
  - Dependencies: syslinux, syslinux-common, dosfstools, mtools
  
- **RPM**: `unetbootin.rpm`
  - For Fedora/RHEL-based distributions
  - Dependencies: syslinux, dosfstools, mtools

- **Flatpak**: `unetbootin.flatpak`
  - Sandboxed application
  - Requires Flatpak runtime
  - Has access to all devices (--device=all)

## Platform-Specific Notes

### Windows
- Uses PyInstaller with `--onefile --windowed`
- UAC manifest is embedded using `mt.exe` from Windows SDK
- Admin privileges are required for USB device operations
- diskpart is used for drive formatting (non-interactive)

### macOS
- Uses PyInstaller to create an .app bundle
- DMG is created using `hdiutil`
- Code signing uses `codesign` command
- Notarization uses `altool`
- Without signing, users must right-click -> Open to bypass Gatekeeper

### Linux
- All packages are built on Ubuntu runners
- AppImage uses `linuxdeploy` for bundling
- DEB/RPM packages use `fpm` tool
- Flatpak uses `flatpak-builder`
- All packages include dependencies on syslinux, dosfstools, mtools

## Customization

### Version Number
The version is automatically extracted from `src/unetbootin/__init__.py` or from the git tag.

### Package Names
Set the `APP_NAME` environment variable in the workflow file to change the output filename.

### Python Version
Set the `PYTHON_VERSION` environment variable in the workflow file.

## Testing Locally

You can test the build process locally using the spec files:

### Windows
```bash
pyinstaller unetbootin-windows.spec --onefile --windowed
# Then embed manifest
mt.exe -manifest resources/windows/unetbootin.exe.manifest -outputresource:dist/unetbootin.exe;#1
```

### macOS
```bash
pyinstaller unetbootin-macos.spec --windowed
# Create DMG
hdiutil create -volname "UNetbootin" -srcfolder dist/unetbootin.app -ov -format UDZO unetbootin.dmg
```

### Linux
```bash
pyinstaller unetbootin.spec --onefile
# Then create packages as needed
```

## Troubleshooting

### macOS Code Signing Issues
- Ensure the certificate is in your keychain
- Verify the certificate name matches `APPLE_CERTIFICATE_NAME`
- Check that the certificate has the "Developer ID Application" type

### Notarization Issues
- Ensure your Apple ID has the "App Store Connect" role
- Create an app-specific password: https://appleid.apple.com/
- Notarization can take several minutes

### Windows UAC Issues
- Ensure the manifest file is correctly formatted
- Verify `mt.exe` is available in the Windows SDK path

### Linux Package Issues
- Ensure `fpm` is installed: `sudo gem install fpm`
- Check that all dependencies are available in the runner

## License

This CI/CD setup is provided as-is and is licensed under the same terms as UNetbootin (GPLv2+).

## Contributing

Improvements to the CI/CD workflow are welcome. Please submit pull requests with:
- Clear descriptions of the changes
- Testing instructions
- Updated documentation as needed
