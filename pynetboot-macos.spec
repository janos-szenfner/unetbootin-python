# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — macOS (.app bundle).
# Build:  pyinstaller pynetboot-macos.spec --noconfirm --clean --distpath dist/macos
# Produces dist/macos/pynetboot.app. Compatible with PyInstaller 6.x.

from PyInstaller.utils.hooks import collect_data_files

# CustomTkinter ships its themes and fonts as package data; without these the
# app cannot build any widget at runtime.
datas = collect_data_files('customtkinter')

datas += [
    ('src/pynetboot/resources/icons/*', 'pynetboot/resources/icons/'),
    ('src/pynetboot/resources/logos/*', 'pynetboot/resources/logos/'),
    ('src/pynetboot/resources/bootloader/*', 'pynetboot/resources/bootloader/'),
    # The UEFI payloads live in a subdirectory, which the glob above does
    # not reach; without this a build has no BOOTX64.EFI to install.
    ('src/pynetboot/resources/bootloader/efi64/*', 'pynetboot/resources/bootloader/efi64/'),
    ('src/pynetboot/resources/translations/*', 'pynetboot/resources/translations/'),
]

a = Analysis(
    ['src/pynetboot/main.py'],
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

# One-dir layout inside the .app bundle.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='pynetboot',
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
    icon='src/pynetboot/resources/icons/unetbootin.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='pynetboot',
)

app = BUNDLE(
    coll,
    name='pynetboot.app',
    icon='src/pynetboot/resources/icons/unetbootin.icns',
    bundle_identifier='com.pynetboot.PyNetboot',
)
