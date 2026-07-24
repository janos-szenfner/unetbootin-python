# PyInstaller spec file for UNetbootin Windows
# Build with: pyinstaller unetbootin-windows.spec --onefile --windowed

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
        # Include manifest for UAC elevation
        ('resources/windows/unetbootin.exe.manifest', '.'),
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
