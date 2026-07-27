# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — Linux (single-file executable).
# Build:  pyinstaller unetbootin.spec --noconfirm --clean --distpath dist/linux
# Compatible with PyInstaller 6.x (no bytecode-cipher options).

from PyInstaller.utils.hooks import collect_data_files

# CustomTkinter ships its themes and fonts as package data; without these the
# app cannot build any widget at runtime.
datas = collect_data_files('customtkinter')

datas += [
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
    hiddenimports=['customtkinter', 'PIL', 'PIL._tkinter_finder'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

# One-file build: bundle scripts + binaries + datas into a single executable.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='unetbootin-python',
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
    icon=None,  # Linux ignores embedded icons; the .desktop file provides it.
)
