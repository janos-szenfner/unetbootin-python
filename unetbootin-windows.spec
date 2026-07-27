# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — Windows (single-file windowed executable).
# Build:  pyinstaller unetbootin-windows.spec --noconfirm --clean --distpath dist/windows
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
    # setuptools/pkg_resources are build-time only - nothing in this app
    # imports them at runtime. Bundling them makes PyInstaller add its
    # pkg_resources runtime hook, which imports setuptools' vendored jaraco
    # modules; those are not collected, so the frozen app died at startup with
    # "No module named 'jaraco'" before showing a window.
    excludes=['setuptools', 'pkg_resources', 'pip', 'wheel'],
    noarchive=False,
)

pyz = PYZ(a.pure)

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
    console=False,             # windowed (no console) GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='src/unetbootin/resources/icons/unetbootin.ico',
    # Embed a UAC "requireAdministrator" manifest directly, so the app
    # elevates on launch. This replaces the fragile post-build mt.exe step
    # (which grabbed the wrong-arch mt.exe on the runner).
    uac_admin=True,
)
