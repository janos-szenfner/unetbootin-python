# UNetbootin for macOS - Installation Instructions

## Important: Gatekeeper Bypass Required

Since UNetbootin is **not code-signed** with an Apple Developer certificate (we are an open-source project without paid Apple Developer membership), macOS Gatekeeper will initially block the app from running.

**This is expected and safe.** Apple's Gatekeeper is designed to protect users from potentially malicious software, but it also blocks unsigned apps from trusted developers.

---

## Installation Methods

### Method 1: ZIP File (Recommended)

This is the simplest and most reliable method.

1. **Download** `unetbootin.zip` from the release assets
2. **Extract** the ZIP file by double-clicking it
3. **Drag** the `UNetbootin.app` to your `Applications` folder
4. **First Launch Only**:
   - Open Finder
   - Navigate to your `Applications` folder
   - Find `UNetbootin.app`
   - **Right-click** (or Ctrl-click) on it
   - Select **Open** from the context menu
   - In the dialog that appears, click **Open**
5. **Done!** The app will launch. All future launches can be done by double-clicking normally.

### Method 2: DMG File (Alternative)

1. **Download** `unetbootin.dmg` from the release assets
2. **Open** the DMG by double-clicking it
3. **Drag** the `UNetbootin.app` to your `Applications` folder
4. **First Launch Only**:
   - Open Finder
   - Navigate to your `Applications` folder
   - Find `UNetbootin.app`
   - **Right-click** (or Ctrl-click) on it
   - Select **Open** from the context menu
   - In the dialog that appears, click **Open**
5. **Done!** The app will launch.

---

## Why This Is Necessary

Apple requires all macOS apps to be code-signed by a paid Apple Developer ($99/year) to bypass Gatekeeper automatically. As an open-source project, we choose not to:

1. **Cost**: Require a paid Apple Developer account
2. **Independence**: Maintain full control over our distribution
3. **Transparency**: Our source code is publicly available for review
4. **Community**: Many open-source macOS apps use this same approach

Apple's own documentation confirms that right-click → Open is the proper way to run unsigned apps from trusted sources.

---

## Security Assurance

You can verify that UNetbootin is safe:

- ✅ **Open Source**: Review our complete source code on GitHub
- ✅ **Transparent Builds**: All builds are done on GitHub Actions (public, reproducible)
- ✅ **No Hidden Code**: No obfuscation, no proprietary binaries
- ✅ **Trusted Dependencies**: All dependencies are listed in `requirements.txt`
- ✅ **Community**: Used by thousands of users worldwide

---

## Troubleshooting

### "App is damaged and can't be opened"

This is Gatekeeper. Follow the **right-click → Open** instructions above.

### "App can't be opened because Apple cannot check it for malicious software"

Same as above. Right-click → Open → Open.

### The app doesn't launch after right-click → Open

Try these steps:

1. **Check the app is in Applications**: Make sure you dragged it to `/Applications/`
2. **Try again**: Sometimes it takes two attempts
3. **Check System Preferences**:
   - Open System Preferences → Security & Privacy → General
   - Look for a message about UNetbootin
   - Click "Open Anyway"
4. **Terminal method**:
   ```bash
   # Navigate to Applications
   cd /Applications
   # Run with explicit open
   open -a UNetbootin
   ```

### "App is from an unidentified developer"

This is normal for unsigned apps. The right-click → Open method bypasses this warning.

---

## Alternative: Run from Terminal

If you're comfortable with the command line, you can run UNetbootin directly:

```bash
# Navigate to where you extracted the app
cd ~/Downloads/unetbootin

# Run the Python module directly (bypasses Gatekeeper)
python3 -m unetbootin.main
```

This works without any Gatekeeper warnings since it's running via Python.

---

## System Requirements

- **macOS Version**: 10.15 (Catalina) or later
- **Architecture**: Apple Silicon (arm64) and Intel (x86_64) - Universal 2 binary
- **Python**: Not required (bundled in the app)
- **Disk Space**: ~50 MB

---

## Uninstalling

To remove UNetbootin:

1. Open Finder
2. Go to `Applications`
3. Drag `UNetbootin.app` to Trash
4. Empty Trash

---

## Support

If you have issues:

1. **Check this guide** again for Gatekeeper instructions
2. **Verify the download**: Check the SHA256 checksums (available in release assets)
3. **Open an issue**: https://github.com/your-repo/unetbootin-python/issues
4. **Ask the community**: Join our discussions

---

## Privacy

UNetbootin:
- Does NOT collect any personal data
- Does NOT send telemetry
- Does NOT include tracking
- Does NOT require internet access (except for downloading ISOs)
- Runs entirely on your computer

---

## License

UNetbootin is free software licensed under **GPLv2+**. You are free to use, modify, and distribute it according to the terms of the license.

---

## Building from Source

If you prefer to build from source:

```bash
# Clone the repository
git clone https://github.com/your-repo/unetbootin-python.git
cd unetbootin-python

# Install dependencies
pip3 install -r requirements.txt pyinstaller

# Build (creates dist/ folder)
pyinstaller unetbootin-macos.spec --windowed

# Create ZIP
cd dist
zip -r unetbootin.zip unetbootin.app
```

---

**Thank you for using UNetbootin!**

For more information, visit: https://unetbootin.sourceforge.net
