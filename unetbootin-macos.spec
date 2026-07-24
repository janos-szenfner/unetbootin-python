# PyInstaller spec file for UNetbootin macOS
# Build with: pyinstaller unetbootin-macos.spec --windowed
#
# This creates a Universal 2 binary (Apple Silicon arm64 + Intel x86_64)
# PyInstaller on macOS automatically builds universal binaries

block_cipher = None

_a = Analysis(
    ['src/unetbootin/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Include all resources: icons, logos, bootloader, translations
        ('src/unetbootin/resources/icons/*', 'unetbootin/resources/icons/'),
        ('src/unetbootin/resources/logos/*', 'unetbootin/resources/logos/'),
        ('src/unetbootin/resources/bootloader/*', 'unetbootin/resources/bootloader/'),
        ('src/unetbootin/resources/translations/*', 'unetbootin/resources/translations/'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

_pyi_rth_hooks = (
    ('pyi_rth_hooks.py', 60),
    ('pyi_rth_pkgutil.py', 60),
)

pyz = PYZ(_a.pure, _a.zipped_data, cipher=block_cipher)

# macOS app bundle settings
# PyInstaller on macOS will automatically create a Universal 2 binary
# (supports both Apple Silicon arm64 and Intel x86_64)
_exe = EXE(
    pyz,
    _a,
    [],
    exclude_binaries=True,
    name='unetbootin',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon='src/unetbootin/resources/icons/unetbootin.icns',
)

# macOS-specific: create app bundle with Universal 2 support
coll = COLLECT(
    _exe,
    _a.binaries,
    _a.zipfiles,
    _a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='unetbootin',
    # macOS app bundle identifier
    app=['--osx-bundle-identifier', 'com.unetbootin.UNetbootin'],
)
