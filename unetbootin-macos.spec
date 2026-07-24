# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — macOS (.app bundle).
# Build:  pyinstaller unetbootin-macos.spec --noconfirm --clean --distpath dist/macos
# Produces dist/macos/unetbootin.app. Compatible with PyInstaller 6.x.

datas = [
    ('src/unetbootin/resources/icons/*', 'unetbootin/resources/icons/'),
    ('src/unetbootin/resources/logos/*', 'unetbootin/resources/logos/'),
    ('src/unetbootin/resources/bootloader/*', 'unetbootin/resources/bootloader/'),
    ('src/unetbootin/resources/translations/*', 'unetbootin/resources/translations/'),
]

a = Analysis(
    ['src/unetbootin/main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['PySimpleGUI'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

# One-dir layout inside the .app bundle.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='unetbootin',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='src/unetbootin/resources/icons/unetbootin.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='unetbootin',
)

app = BUNDLE(
    coll,
    name='unetbootin.app',
    icon='src/unetbootin/resources/icons/unetbootin.icns',
    bundle_identifier='com.unetbootin.UNetbootin',
)
