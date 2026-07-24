# PyInstaller spec file for UNetbootin
# Build with: pyinstaller unetbootin.spec
#
# This is a cross-platform spec file that works on Windows, macOS, and Linux.
# For Windows: uses unetbootin.ico
# For macOS: uses unetbootin.icns (PyInstaller auto-selects the right icon)
# For Linux: uses unetbootin.xpm or PNG fallback

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

_pyinstaller_hooks = (
    ('pyi_rth_hooks.py', 60),
    ('pyi_rth_pkgutil.py', 60),
)

pyz = PYZ(_a.pure, _a.zipped_data, cipher=block_cipher)

# PyInstaller automatically selects the appropriate icon format:
# - .ico for Windows
# - .icns for macOS
# - .xpm or .png for Linux
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
    icon='src/unetbootin/resources/icons/unetbootin.ico',
)

coll = COLLECT(
    _exe,
    _a.binaries,
    _a.zipfiles,
    _a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='unetbootin',
)
