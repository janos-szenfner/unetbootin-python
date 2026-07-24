"""Resources package for UNetbootin.

Contains icons, logos, bootloader files, translations and other static
resources, plus a small resolver that finds them both in a normal
(source/installed) layout and inside a frozen PyInstaller bundle.
"""

import os
import sys
import stat
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _base_dirs():
    """Candidate directories that may contain the bundled resources.

    Order matters: a frozen bundle's extraction dir (``sys._MEIPASS``) is
    checked first, then the package directory (this file's folder) for normal
    source / ``pip install`` layouts.
    """
    candidates = []
    if getattr(sys, 'frozen', False):
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            meipass = Path(meipass)
            # One-file / one-dir: datas live under _MEIPASS.
            candidates.append(meipass / 'unetbootin' / 'resources')
            candidates.append(meipass / 'resources')
            candidates.append(meipass)
            # macOS .app: _MEIPASS is Contents/Frameworks while datas are
            # placed in the sibling Contents/Resources directory.
            resources_dir = meipass.parent / 'Resources'
            candidates.append(resources_dir / 'unetbootin' / 'resources')
            candidates.append(resources_dir / 'resources')
        # As a last frozen-app resort, look next to the executable and its
        # macOS .app Contents/Resources sibling.
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / 'unetbootin' / 'resources')
        candidates.append(exe_dir.parent / 'Resources' / 'unetbootin' / 'resources')
    # Normal layout: this file lives at <pkg>/unetbootin/resources/__init__.py
    candidates.append(Path(__file__).resolve().parent)
    return candidates


def resource_path(*parts: str) -> Path:
    """Return an absolute path to a bundled resource.

    Works in a source checkout, an installed package and a frozen PyInstaller
    app. If the resource is not found in any known location, the package-local
    path is returned anyway so callers can report a clear "missing file" error.
    """
    for base in _base_dirs():
        candidate = base.joinpath(*parts)
        if candidate.exists():
            return candidate
    return Path(__file__).resolve().parent.joinpath(*parts)


def bootloader_path(name: str) -> Path:
    """Path to a bundled bootloader binary/module (e.g. ``mbr.bin``)."""
    return resource_path('bootloader', name)


def icon_path(name: str) -> Path:
    """Path to a bundled icon (e.g. ``unetbootin.ico``)."""
    return resource_path('icons', name)


def translations_dir() -> Path:
    """Directory holding translation catalogs."""
    return resource_path('translations')


def ensure_executable(path) -> bool:
    """Best-effort ``chmod +x`` for a bundled binary.

    Frozen bundles and wheels often drop the executable bit, so we restore it
    before running a bundled syslinux/extlinux binary. Returns True if the
    file exists (and is now executable), False otherwise.
    """
    try:
        p = Path(path)
        if not p.exists():
            return False
        st = os.stat(p)
        os.chmod(p, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return True
    except OSError as e:
        logger.debug(f"Could not mark {path} executable: {e}")
        return Path(path).exists()


def find_bundled_syslinux(prefer_64bit: bool = True) -> Optional[Path]:
    """Return the bundled Linux syslinux binary, made executable, or None.

    UNetbootin ships ``ubnsylnx`` (32-bit) and ``ubnsylnx64`` (64-bit).
    """
    names = ['ubnsylnx64', 'ubnsylnx'] if prefer_64bit else ['ubnsylnx', 'ubnsylnx64']
    for name in names:
        p = bootloader_path(name)
        if p.exists():
            ensure_executable(p)
            return p
    return None


def find_bundled_extlinux(prefer_64bit: bool = True) -> Optional[Path]:
    """Return the bundled Linux extlinux binary, made executable, or None.

    UNetbootin ships ``ubnexlnx`` (32-bit) and ``ubnexlnx64`` (64-bit).
    """
    names = ['ubnexlnx64', 'ubnexlnx'] if prefer_64bit else ['ubnexlnx', 'ubnexlnx64']
    for name in names:
        p = bootloader_path(name)
        if p.exists():
            ensure_executable(p)
            return p
    return None
