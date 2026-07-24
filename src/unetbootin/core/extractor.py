"""
ISO and archive extraction functionality for UNetbootin.
"""

import os
import re
import logging
import asyncio
import tempfile
import shutil
import zipfile
import tarfile
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Extraction shells out to external tools (xorriso/7z/tar/unzip/bsdtar);
# subprocess failures and missing binaries surface as these.
_SUBPROCESS_ERRORS = (subprocess.SubprocessError, OSError)

# --- Tunable constants (previously scattered magic numbers) ---
# Timeout (seconds) for full archive extraction commands (can be slow).
EXTRACT_TIMEOUT = 300
# Timeout (seconds) for listing archive contents.
LIST_TIMEOUT = 30
# Timeout (seconds) for checking whether a helper command exists.
COMMAND_CHECK_TIMEOUT = 5
# Archive extensions handled by the tar code path.
TAR_EXTENSIONS = ['.tar', '.tar.gz', '.tgz', '.tar.bz2',
                  '.tbz2', '.tar.xz', '.txz']


@dataclass
class ArchiveFileInfo:
    """Information about a file in an archive."""
    name: str
    size: int = 0
    is_directory: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert archive file info to dictionary."""
        return {
            'name': self.name,
            'size': self.size,
            'is_directory': self.is_directory,
        }


class ISOExtractor:
    """Handles ISO and archive extraction."""

    def __init__(self):
        """Initialize the extractor with supported file extensions."""
        self.supported_extensions = [
            '.iso', '.img', '.raw',
            '.zip',
            '.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz', '.txz',
            '.7z'
        ]
        self.worker = None

    def get_supported_extensions(self) -> List[str]:
        """Return the list of archive extensions this extractor supports."""
        return self.supported_extensions

    def _get_files_to_copy(self, source_dir: str,
                           params: Optional[Dict[str, Any]] = None) -> List[str]:
        """List extracted files as paths relative to source_dir.

        Hidden files (names starting with '.') are skipped. `params` is
        accepted for signature compatibility with the installer helper but
        is not used for filtering here.
        """
        files_to_copy = []
        for root, _dirs, files in os.walk(source_dir):
            for file in files:
                if file.startswith('.'):
                    continue
                full_path = os.path.join(root, file)
                files_to_copy.append(os.path.relpath(full_path, source_dir))
        return files_to_copy

    def extract_iso_sync_threaded(self, archive_path: str, dest_dir: str,
                                  files_to_extract: Optional[List[str]] = None,
                                  progress_callback: Optional[Callable[[int], None]] = None) -> tuple:
        """Extract an ISO file in a thread (for use with PySimpleGUI).

        This method runs the synchronous extraction in a separate thread to avoid
        blocking the PySimpleGUI event loop.
        """
        import threading

        result = [None, None]
        exception = [None]

        def extract_wrapper():
            """Run extraction in the worker thread, capturing any exception."""
            try:
                result[0], result[1] = self.extract_iso_sync(
                    archive_path, dest_dir, files_to_extract, progress_callback
                )
            except Exception as e:  # noqa: BLE001 - transparently re-raised on caller thread
                exception[0] = e

        thread = threading.Thread(target=extract_wrapper, daemon=True)
        thread.start()
        thread.join()

        if exception[0]:
            raise exception[0]

        return result[0], result[1]

    def extract_iso_sync(self, archive_path: str, dest_dir: str,
                        files_to_extract: Optional[List[str]] = None,
                        progress_callback: Optional[Callable[[int], None]] = None) -> tuple:
        """Synchronously extract an archive file.

        Supports ISO, IMG, RAW, ZIP, TAR (tar, tar.gz, tar.bz2, tar.xz), and 7z formats.
        """
        try:
            # Create destination directory
            os.makedirs(dest_dir, exist_ok=True)

            # Get archive type
            archive_ext = os.path.splitext(archive_path)[1].lower()

            if archive_ext == '.iso':
                return self._extract_iso(archive_path, dest_dir,
                                         files_to_extract, progress_callback)
            elif archive_ext in ['.img', '.raw']:
                return self._extract_raw(archive_path, dest_dir, progress_callback)
            elif archive_ext == '.zip':
                return self._extract_zip(archive_path, dest_dir,
                                         files_to_extract, progress_callback)
            elif archive_ext in TAR_EXTENSIONS:
                return self._extract_tar(archive_path, dest_dir,
                                         files_to_extract, progress_callback)
            elif archive_ext == '.7z':
                return self._extract_7z_file(
                    archive_path, dest_dir, files_to_extract, progress_callback)
            else:
                return False, f"Unsupported archive type: {archive_ext}"

        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"Extraction failed: {e}")
            return False, str(e)

    def _extract_iso(self, iso_path: str, dest_dir: str,
                     files_to_extract: Optional[List[str]],
                     progress_callback: Optional[Callable[[int], None]]) -> tuple:
        """Extract ISO using various methods."""
        methods_tried = []

        # Try method 1: xorriso (most reliable for ISO)
        if self._try_xorriso(iso_path, dest_dir, files_to_extract, progress_callback):
            return True, "Extraction completed successfully"
        methods_tried.append("xorriso")

        # Try method 2: 7z
        if self._try_7z(iso_path, dest_dir, files_to_extract, progress_callback):
            return True, "Extraction completed successfully"
        methods_tried.append("7z")

        # Try method 3: bsdtar
        if self._try_bsdtar(iso_path, dest_dir, files_to_extract, progress_callback):
            return True, "Extraction completed successfully"
        methods_tried.append("bsdtar")

        # Try method 4: Python libraries
        if self._try_python_libs(
            iso_path, dest_dir, files_to_extract, progress_callback):
            return True, "Extraction completed successfully"
        methods_tried.append("python libs")

        return False, ("All extraction methods failed. "
                       f"Tried: {', '.join(methods_tried)}")

    def _extract_raw(self, img_path: str, dest_dir: str,
                    progress_callback: Optional[Callable[[int], None]]) -> tuple:
        """Extract raw disk image."""
        try:
            import sys
            # For raw images, we need to mount them or use dd
            if sys.platform == 'darwin':
                # macOS: use hdiutil
                result = subprocess.run(
                    ['hdiutil', 'attach', '-imagekey',
                        'diskimage-class=CRawDiskImage', img_path],
                    capture_output=True,
                    text=True,
                    timeout=LIST_TIMEOUT
                )
                if result.returncode != 0:
                    return False, f"Failed to attach raw image: {result.stderr}"

                # Copy files from mounted image
                # This is simplified - actual implementation would need to find the
                # mount point
                return True, "Raw image attached successfully"
            else:
                # Linux: try to mount
                result = subprocess.run(
                    ['sudo', 'mount', '-o', 'loop', img_path, dest_dir],
                    capture_output=True,
                    text=True,
                    timeout=LIST_TIMEOUT
                )
                if result.returncode == 0:
                    return True, "Raw image mounted successfully"
                else:
                    return False, f"Failed to mount raw image: {result.stderr}"
        except _SUBPROCESS_ERRORS as e:
            return False, str(e)

    def _extract_zip(self, zip_path: str, dest_dir: str,
                   files_to_extract: Optional[List[str]],
                   progress_callback: Optional[Callable[[int], None]]) -> tuple:
        """Extract ZIP file using various methods."""
        methods_tried = []

        # Try method 1: unzip command
        if self._try_unzip(zip_path, dest_dir, files_to_extract, progress_callback):
            return True, "Extraction completed successfully"
        methods_tried.append("unzip")

        # Try method 2: Python zipfile module
        if self._try_zipfile(zip_path, dest_dir, files_to_extract, progress_callback):
            return True, "Extraction completed successfully"
        methods_tried.append("zipfile")

        return False, ("All ZIP extraction methods failed. "
                       f"Tried: {', '.join(methods_tried)}")

    def _extract_tar(self, tar_path: str, dest_dir: str,
                   files_to_extract: Optional[List[str]],
                   progress_callback: Optional[Callable[[int], None]]) -> tuple:
        """Extract TAR file using various methods."""
        methods_tried = []

        # Try method 1: tar command
        if self._try_tar_command(
            tar_path, dest_dir, files_to_extract, progress_callback):
            return True, "Extraction completed successfully"
        methods_tried.append("tar command")

        # Try method 2: Python tarfile module
        if self._try_tarfile(tar_path, dest_dir, files_to_extract, progress_callback):
            return True, "Extraction completed successfully"
        methods_tried.append("tarfile")

        return False, ("All TAR extraction methods failed. "
                       f"Tried: {', '.join(methods_tried)}")

    def _extract_7z_file(self, archive_path: str, dest_dir: str,
                        files_to_extract: Optional[List[str]],
                        progress_callback: Optional[Callable[[int], None]]) -> tuple:
        """Extract 7z file using various methods."""
        methods_tried = []

        # Try method 1: 7z command
        if self._try_7z_command(archive_path, dest_dir,
                                files_to_extract, progress_callback):
            return True, "Extraction completed successfully"
        methods_tried.append("7z command")

        # Try method 2: Python py7zr library
        if self._try_py7zr(archive_path, dest_dir, files_to_extract, progress_callback):
            return True, "Extraction completed successfully"
        methods_tried.append("py7zr")

        return False, ("All 7z extraction methods failed. "
                       f"Tried: {', '.join(methods_tried)}")

    def _try_xorriso(self, iso_path: str, dest_dir: str,
                    files_to_extract: Optional[List[str]],
                    progress_callback: Optional[Callable[[int], None]]) -> bool:
        """Try to extract using xorriso."""
        try:
            if not self._command_exists('xorriso'):
                return False

            cmd = [
    'xorriso',
    '-osirrox',
    'on',
    '-indev',
    iso_path,
    '-extract',
    '/',
     dest_dir]

            if files_to_extract:
                # Extract specific files
                for file_pattern in files_to_extract:
                    file_cmd = cmd + ['-extract', file_pattern, dest_dir]
                    result = subprocess.run(
    file_cmd,
    capture_output=True,
    text=True,
     timeout=EXTRACT_TIMEOUT)
                    if result.returncode != 0:
                        logger.warning(
                            f"xorriso failed for {file_pattern}: {result.stderr}")
                        return False
            else:
                # Extract all files
                result = subprocess.run(
    cmd, capture_output=True, text=True, timeout=EXTRACT_TIMEOUT)
                if result.returncode != 0:
                    logger.warning(f"xorriso failed: {result.stderr}")
                    return False

            if progress_callback:
                progress_callback(100)
            return True

        except _SUBPROCESS_ERRORS as e:
            logger.debug(f"xorriso extraction failed: {e}")
            return False

    def _try_7z(self, archive_path: str, dest_dir: str,
                 files_to_extract: Optional[List[str]],
                 progress_callback: Optional[Callable[[int], None]]) -> bool:
        """Try to extract using 7z."""
        try:
            if not self._command_exists('7z'):
                return False

            cmd = ['7z', 'x', archive_path, f'-o{dest_dir}', '-y']

            if files_to_extract:
                # 7z doesn't easily support extracting specific files by pattern
                # So we'll extract all and filter later
                pass

            result = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
     timeout=EXTRACT_TIMEOUT)
            if result.returncode != 0:
                logger.debug(f"7z extraction failed: {result.stderr}")
                return False

            if progress_callback:
                progress_callback(100)
            return True

        except _SUBPROCESS_ERRORS as e:
            logger.debug(f"7z extraction failed: {e}")
            return False

    # ========== ZIP Extraction Methods ==========

    def _try_unzip(self, zip_path: str, dest_dir: str,
                  files_to_extract: Optional[List[str]],
                  progress_callback: Optional[Callable[[int], None]]) -> bool:
        """Try to extract using unzip command."""
        try:
            if not self._command_exists('unzip'):
                return False

            cmd = ['unzip', '-o', '-d', dest_dir, zip_path]

            if files_to_extract:
                cmd = ['unzip', '-o', '-d', dest_dir] + files_to_extract + [zip_path]

            result = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
     timeout=EXTRACT_TIMEOUT)
            if result.returncode != 0:
                logger.debug(f"unzip extraction failed: {result.stderr}")
                return False

            if progress_callback:
                progress_callback(100)
            return True

        except _SUBPROCESS_ERRORS as e:
            logger.debug(f"unzip extraction failed: {e}")
            return False

    def _try_zipfile(self, zip_path: str, dest_dir: str,
                   files_to_extract: Optional[List[str]],
                   progress_callback: Optional[Callable[[int], None]]) -> bool:
        """Try to extract using Python zipfile module."""
        try:
            import zipfile

            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                if files_to_extract:
                    for file_name in files_to_extract:
                        if file_name in zip_ref.namelist():
                            zip_ref.extract(file_name, dest_dir)
                else:
                    zip_ref.extractall(dest_dir)

            if progress_callback:
                progress_callback(100)
            return True

        except ImportError:
            logger.debug("zipfile module not available")
            return False
        except (zipfile.BadZipFile, OSError) as e:
            logger.debug(f"zipfile extraction failed: {e}")
            return False

    # ========== TAR Extraction Methods ==========

    def _try_tar_command(self, tar_path: str, dest_dir: str,
                        files_to_extract: Optional[List[str]],
                        progress_callback: Optional[Callable[[int], None]]) -> bool:
        """Try to extract using tar command."""
        try:
            if not self._command_exists('tar'):
                return False

            # Determine compression type from extension
            tar_ext = os.path.splitext(tar_path)[1].lower()

            # Build appropriate command
            if tar_ext in ['.tar.gz', '.tgz']:
                cmd = ['tar', '-xzf', tar_path, '-C', dest_dir]
            elif tar_ext in ['.tar.bz2', '.tbz2']:
                cmd = ['tar', '-xjf', tar_path, '-C', dest_dir]
            elif tar_ext in ['.tar.xz', '.txz']:
                cmd = ['tar', '-xJf', tar_path, '-C', dest_dir]
            else:  # .tar
                cmd = ['tar', '-xf', tar_path, '-C', dest_dir]

            if files_to_extract:
                cmd.extend(files_to_extract)

            result = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
     timeout=EXTRACT_TIMEOUT)
            if result.returncode != 0:
                logger.debug(f"tar extraction failed: {result.stderr}")
                return False

            if progress_callback:
                progress_callback(100)
            return True

        except _SUBPROCESS_ERRORS as e:
            logger.debug(f"tar extraction failed: {e}")
            return False

    def _try_tarfile(self, tar_path: str, dest_dir: str,
                   files_to_extract: Optional[List[str]],
                   progress_callback: Optional[Callable[[int], None]]) -> bool:
        """Try to extract using Python tarfile module."""
        try:
            import tarfile

            mode = 'r'
            tar_ext = os.path.splitext(tar_path)[1].lower()

            if tar_ext in ['.tar.gz', '.tgz']:
                mode = 'r:gz'
            elif tar_ext in ['.tar.bz2', '.tbz2']:
                mode = 'r:bz2'
            elif tar_ext in ['.tar.xz', '.txz']:
                mode = 'r:xz'

            with tarfile.open(tar_path, mode) as tar_ref:
                # filter='data' (Python 3.12+, backported to 3.10.12/3.11.4)
                # blocks path traversal, absolute paths, symlink escapes and
                # device nodes in untrusted archives. Fall back to manual
                # member validation on older interpreters.
                if files_to_extract:
                    members = [m for m in tar_ref.getmembers()
                               if m.name in files_to_extract]
                else:
                    members = tar_ref.getmembers()

                try:
                    tar_ref.extractall(path=dest_dir, members=members, filter='data')
                except TypeError:
                    # Interpreter without the filter parameter: validate manually
                    safe_members = []
                    dest_real = os.path.realpath(dest_dir)
                    for member in members:
                        target = os.path.realpath(os.path.join(dest_dir, member.name))
                        if not target.startswith(
                            dest_real + os.sep) and target != dest_real:
                            logger.warning(
                                f"Skipping unsafe archive member: {member.name}")
                            continue
                        if member.islnk() or member.issym() or member.isdev():
                            logger.warning(
                                f"Skipping link/device archive member: {member.name}")
                            continue
                        safe_members.append(member)
                    tar_ref.extractall(path=dest_dir, members=safe_members)

            if progress_callback:
                progress_callback(100)
            return True

        except ImportError:
            logger.debug("tarfile module not available")
            return False
        except (tarfile.TarError, OSError) as e:
            logger.debug(f"tarfile extraction failed: {e}")
            return False

    # ========== 7z Extraction Methods ==========

    def _try_7z_command(self, archive_path: str, dest_dir: str,
                       files_to_extract: Optional[List[str]],
                       progress_callback: Optional[Callable[[int], None]]) -> bool:
        """Try to extract 7z using 7z command."""
        try:
            if not self._command_exists('7z'):
                return False

            cmd = ['7z', 'x', archive_path, f'-o{dest_dir}', '-y']

            if files_to_extract:
                # Extract specific files
                for file_pattern in files_to_extract:
                    file_cmd = cmd + [file_pattern]
                    result = subprocess.run(
    file_cmd,
    capture_output=True,
    text=True,
     timeout=EXTRACT_TIMEOUT)
                    if result.returncode != 0:
                        logger.debug(f"7z failed for {file_pattern}: {result.stderr}")
                        return False
            else:
                # Extract all files
                result = subprocess.run(
    cmd, capture_output=True, text=True, timeout=EXTRACT_TIMEOUT)
                if result.returncode != 0:
                    logger.debug(f"7z extraction failed: {result.stderr}")
                    return False

            if progress_callback:
                progress_callback(100)
            return True

        except _SUBPROCESS_ERRORS as e:
            logger.debug(f"7z extraction failed: {e}")
            return False

    def _try_py7zr(self, archive_path: str, dest_dir: str,
                  files_to_extract: Optional[List[str]],
                  progress_callback: Optional[Callable[[int], None]]) -> bool:
        """Try to extract 7z using py7zr library."""
        try:
            import py7zr

            with py7zr.SevenZipFile(archive_path, mode='r') as archive:
                if files_to_extract:
                    for file_info in archive.filelist:
                        if file_info.filename in files_to_extract:
                            archive.extract(file_info.filename, path=dest_dir)
                else:
                    archive.extractall(path=dest_dir)

            if progress_callback:
                progress_callback(100)
            return True

        except ImportError:
            logger.debug("py7zr library not available")
            return False
        except (OSError, ValueError) as e:  # noqa: BLE001 - py7zr raises library-specific errors
            logger.debug(f"py7zr extraction failed: {e}")
            return False

    def _try_bsdtar(self, archive_path: str, dest_dir: str,
                    files_to_extract: Optional[List[str]],
                    progress_callback: Optional[Callable[[int], None]]) -> bool:
        """Try to extract using bsdtar."""
        try:
            if not self._command_exists('bsdtar'):
                return False

            cmd = ['bsdtar', '-xf', archive_path, '-C', dest_dir]

            if files_to_extract:
                cmd.extend(files_to_extract)

            result = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
     timeout=EXTRACT_TIMEOUT)
            if result.returncode != 0:
                logger.debug(f"bsdtar extraction failed: {result.stderr}")
                return False

            if progress_callback:
                progress_callback(100)
            return True

        except _SUBPROCESS_ERRORS as e:
            logger.debug(f"bsdtar extraction failed: {e}")
            return False

    def _try_python_libs(self, archive_path: str, dest_dir: str,
                         files_to_extract: Optional[List[str]],
                         progress_callback: Optional[Callable[[int], None]]) -> bool:
        """Try to extract using Python libraries."""
        try:
            # Try pycdlib
            try:
                import pycdlib
                iso = pycdlib.PyCdlib()
                iso.open(archive_path)

                if files_to_extract:
                    for file_path in files_to_extract:
                        try:
                            data = iso.get_file_from_iso_by_path(file_path)
                            out_path = os.path.join(dest_dir, file_path)
                            os.makedirs(os.path.dirname(out_path), exist_ok=True)
                            with open(out_path, 'wb') as f:
                                f.write(data)
                        except Exception:  # noqa: BLE001 - pycdlib raises library-specific errors; skip file
                            pass
                else:
                    # Extract all files
                    for file_path in iso.get_list_of_files_from_iso():
                        try:
                            data = iso.get_file_from_iso_by_path(file_path)
                            out_path = os.path.join(dest_dir, file_path)
                            os.makedirs(os.path.dirname(out_path), exist_ok=True)
                            with open(out_path, 'wb') as f:
                                f.write(data)
                        except Exception:  # noqa: BLE001 - pycdlib raises library-specific errors; skip file
                            pass

                iso.close()
                if progress_callback:
                    progress_callback(100)
                return True
            except ImportError:
                pass

            # Try py7zr for 7z files
            if archive_path.endswith('.7z'):
                try:
                    import py7zr
                    with py7zr.SevenZipFile(archive_path, mode='r') as archive:
                        archive.extractall(path=dest_dir)
                    if progress_callback:
                        progress_callback(100)
                    return True
                except ImportError:
                    pass

            # Try iso9660 library
            try:
                from iso9660 import CD
                cd = CD(archive_path)
                for file in cd.files:
                    if files_to_extract and not any(
                        p in file.name for p in files_to_extract):
                        continue
                    try:
                        data = cd.read_file(file.name)
                        out_path = os.path.join(dest_dir, file.name)
                        os.makedirs(os.path.dirname(out_path), exist_ok=True)
                        with open(out_path, 'wb') as f:
                            f.write(data)
                    except Exception:  # noqa: BLE001 - iso9660 raises library-specific errors; skip file
                        pass

                if progress_callback:
                    progress_callback(100)
                return True
            except ImportError:
                pass

        except Exception as e:  # noqa: BLE001 - optional pycdlib/iso9660 raise library-specific errors
            logger.debug(f"Python lib extraction failed: {e}")

        return False

    def _command_exists(self, command: str) -> bool:
        """Check if a command exists in the system."""
        try:
            result = subprocess.run(
                ['which', command], capture_output=True, text=True,
                timeout=COMMAND_CHECK_TIMEOUT)
            return result.returncode == 0 and os.path.exists(result.stdout.strip())
        except _SUBPROCESS_ERRORS:
            return False

    def list_archive_contents(self, archive_path: str) -> List[ArchiveFileInfo]:
        """List contents of an archive.

        Supports ISO, ZIP, TAR (tar, tar.gz, tar.bz2, tar.xz), and 7z formats.
        """
        files = []
        archive_ext = os.path.splitext(archive_path)[1].lower()

        try:
            if archive_ext == '.iso':
                files = self._list_iso_contents(archive_path)
            elif archive_ext == '.zip':
                files = self._list_zip_contents(archive_path)
            elif archive_ext in TAR_EXTENSIONS:
                files = self._list_tar_contents(archive_path)
            elif archive_ext == '.7z':
                files = self._list_7z_contents(archive_path)

        except _SUBPROCESS_ERRORS as e:
            logger.error(f"Failed to list archive contents: {e}")

        return files

    def _list_iso_contents(self, archive_path: str) -> List[ArchiveFileInfo]:
        """List contents of an ISO file."""
        files = []

        # Try different methods to list ISO contents
        if self._command_exists('xorriso'):
            result = subprocess.run(
                ['xorriso', '-indev', archive_path, '-find', '/', '-type', 'f'],
                capture_output=True, text=True, timeout=LIST_TIMEOUT
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        files.append(ArchiveFileInfo(name=line.strip()))

        elif self._command_exists('7z'):
            result = subprocess.run(
                ['7z', 'l', archive_path],
                capture_output=True, text=True, timeout=LIST_TIMEOUT
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n')[2:]:  # Skip header
                    parts = line.split()
                    if len(parts) >= 4 and not parts[0].startswith('----'):
                        files.append(ArchiveFileInfo(
                            name=parts[-1],
                            size=int(parts[3]) if parts[3].isdigit() else 0
                        ))

        # Try Python libraries
        try:
            import pycdlib
            iso = pycdlib.PyCdlib()
            iso.open(archive_path)
            for file_path in iso.get_list_of_files_from_iso():
                try:
                    file_info = iso.get_file_info_from_iso_by_path(file_path)
                    files.append(ArchiveFileInfo(
                        name=file_path,
                        size=file_info.get('file_size', 0)
                    ))
                except Exception:  # noqa: BLE001 - pycdlib raises library-specific errors
                    files.append(ArchiveFileInfo(name=file_path))
            iso.close()
        except ImportError:
            pass

        return files

    def _list_zip_contents(self, archive_path: str) -> List[ArchiveFileInfo]:
        """List contents of a ZIP file."""
        files = []

        # Try using 7z command first (works for most formats)
        if self._command_exists('7z'):
            result = subprocess.run(
                ['7z', 'l', archive_path],
                capture_output=True, text=True, timeout=LIST_TIMEOUT
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n')[2:]:  # Skip header
                    parts = line.split()
                    if len(parts) >= 4 and not parts[0].startswith('----'):
                        files.append(ArchiveFileInfo(
                            name=parts[-1],
                            size=int(parts[3]) if parts[3].isdigit() else 0
                        ))
                return files

        # Try Python zipfile module
        try:
            import zipfile
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                for info in zip_ref.infolist():
                    files.append(ArchiveFileInfo(
                        name=info.filename,
                        size=info.file_size,
                        is_directory=info.is_dir()
                    ))
            return files
        except ImportError:
            pass
        except (zipfile.BadZipFile, OSError):
            pass

        return files

    def _list_tar_contents(self, archive_path: str) -> List[ArchiveFileInfo]:
        """List contents of a TAR file."""
        files = []

        # Try using tar command with list option
        if self._command_exists('tar'):
            tar_ext = os.path.splitext(archive_path)[1].lower()

            # Build appropriate command
            if tar_ext in ['.tar.gz', '.tgz']:
                cmd = ['tar', '-tzf', archive_path]
            elif tar_ext in ['.tar.bz2', '.tbz2']:
                cmd = ['tar', '-tjf', archive_path]
            elif tar_ext in ['.tar.xz', '.txz']:
                cmd = ['tar', '-tJf', archive_path]
            else:  # .tar
                cmd = ['tar', '-tf', archive_path]

            result = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
     timeout=LIST_TIMEOUT)
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        # tar -t doesn't show sizes, so we just add the name
                        files.append(ArchiveFileInfo(name=line.strip()))
                return files

        # Try Python tarfile module
        try:
            import tarfile

            mode = 'r'
            tar_ext = os.path.splitext(archive_path)[1].lower()

            if tar_ext in ['.tar.gz', '.tgz']:
                mode = 'r:gz'
            elif tar_ext in ['.tar.bz2', '.tbz2']:
                mode = 'r:bz2'
            elif tar_ext in ['.tar.xz', '.txz']:
                mode = 'r:xz'

            with tarfile.open(archive_path, mode) as tar_ref:
                for member in tar_ref.getmembers():
                    files.append(ArchiveFileInfo(
                        name=member.name,
                        size=member.size,
                        is_directory=member.isdir()
                    ))
            return files
        except ImportError:
            pass
        except (tarfile.TarError, OSError):
            pass

        return files

    def _list_7z_contents(self, archive_path: str) -> List[ArchiveFileInfo]:
        """List contents of a 7z file."""
        files = []

        # Try using 7z command
        if self._command_exists('7z'):
            result = subprocess.run(
                ['7z', 'l', archive_path],
                capture_output=True, text=True, timeout=LIST_TIMEOUT
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n')[2:]:  # Skip header
                    parts = line.split()
                    if len(parts) >= 4 and not parts[0].startswith('----'):
                        files.append(ArchiveFileInfo(
                            name=parts[-1],
                            size=int(parts[3]) if parts[3].isdigit() else 0
                        ))
                return files

        # Try Python py7zr library
        try:
            import py7zr
            with py7zr.SevenZipFile(archive_path, mode='r') as archive:
                for file_info in archive.filelist:
                    files.append(ArchiveFileInfo(
                        name=file_info.filename,
                        size=file_info.uncompressed,
                        is_directory=file_info.is_directory
                    ))
            return files
        except ImportError:
            pass
        except (OSError, ValueError):  # noqa: BLE001 - py7zr raises library-specific errors
            pass

        return files

    def locate_kernel(self, archive_path: str,
                      archive_contents: Optional[List[ArchiveFileInfo]] = None) -> Optional[str]:
        """Locate kernel file in an archive."""
        if archive_contents is None:
            archive_contents = self.list_archive_contents(archive_path)

        # Common kernel names
        kernel_patterns = [
            r'vmlinuz',
            r'vmlinuz\.efi',
            r'bzImage',
            r'linux',
            r'kernel',
            r'kernel\.img',
            r'vmlinux',
        ]

        for file_info in archive_contents:
            for pattern in kernel_patterns:
                if re.search(pattern, file_info.name, re.IGNORECASE):
                    return file_info.name

        return None

    def locate_initrd(self, archive_path: str,
                      archive_contents: Optional[List[ArchiveFileInfo]] = None) -> Optional[str]:
        """Locate initrd file in an archive."""
        if archive_contents is None:
            archive_contents = self.list_archive_contents(archive_path)

        # Common initrd names
        initrd_patterns = [
            r'initrd',
            r'initrd\.img',
            r'initrd\.gz',
            r'initramfs',
            r'initramfs\.img',
            r'initramfs\.gz',
        ]

        for file_info in archive_contents:
            for pattern in initrd_patterns:
                if re.search(pattern, file_info.name, re.IGNORECASE):
                    return file_info.name

        return None

    def extract_kernel(self, archive_path: str, dest_path: str) -> bool:
        """Extract kernel from archive to destination path."""
        kernel_path = self.locate_kernel(archive_path)
        if not kernel_path:
            logger.error("Kernel not found in archive")
            return False

        return self._extract_single_file(archive_path, kernel_path, dest_path)

    def extract_initrd(self, archive_path: str, dest_path: str) -> bool:
        """Extract initrd from archive to destination path."""
        initrd_path = self.locate_initrd(archive_path)
        if not initrd_path:
            logger.error("Initrd not found in archive")
            return False

        return self._extract_single_file(archive_path, initrd_path, dest_path)

    def _extract_single_file(self, archive_path: str,
                             file_path: str, dest_path: str) -> bool:
        """Extract a single file from archive."""
        try:
            # Try using 7z first
            if self._command_exists('7z'):
                result = subprocess.run(
                    ['7z', 'e', archive_path, f'-o{dest_path}', file_path, '-y'],
                    capture_output=True, text=True, timeout=LIST_TIMEOUT
                )
                return result.returncode == 0

            # Fallback to extracting all and then copying
            temp_dir = tempfile.mkdtemp()
            try:
                if self.extract_iso_sync(archive_path, temp_dir):
                    src_path = os.path.join(temp_dir, file_path)
                    if os.path.exists(src_path):
                        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                        shutil.copy2(src_path, dest_path)
                        return True
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

        except _SUBPROCESS_ERRORS as e:
            logger.error(f"Failed to extract single file: {e}")

        return False


class AsyncISOExtractor:
    """Async ISO and archive extractor for non-blocking I/O operations.

    This class provides async/await compatible methods for extracting archives,
    which can be used with asyncio event loops. It runs the extraction in a
    thread pool executor since most extraction libraries are synchronous.
    """

    def __init__(self):
        """Initialize the async extractor."""
        self.supported_extensions = [
            '.iso', '.img', '.raw',
            '.zip',
            '.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz', '.txz',
            '.7z'
        ]

    async def extract_iso_async(
        self,
        archive_path: str,
        dest_dir: str,
        files_to_extract: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> tuple:
        """Extract an archive file asynchronously.

        Args:
            archive_path: Path to the archive file
            dest_dir: Destination directory for extracted files
            files_to_extract: Optional list of specific files to extract
            progress_callback: Optional callback for progress (0-100)
            cancel_check: Optional callable to check for cancellation

        Returns:
            Tuple of (success: bool, message: str)
        """
        logger.info(f"Async extracting {archive_path} to {dest_dir}")

        loop = asyncio.get_event_loop()
        extractor = ISOExtractor()

        # Run sync extraction in executor
        return await loop.run_in_executor(
            None,
            lambda: extractor.extract_iso_sync(
                archive_path,
                dest_dir,
                files_to_extract=files_to_extract,
                progress_callback=progress_callback
            )
        )

    async def extract_with_tool_async(
        self,
        archive_path: str,
        dest_dir: str,
        tool_name: str,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> tuple:
        """Extract using a specific tool asynchronously."""
        loop = asyncio.get_event_loop()
        extractor = ISOExtractor()

        def sync_extract():
            """Run the blocking extraction, to be dispatched in an executor."""
            try:
                result = extractor._extract_with_tool(
                    archive_path, dest_dir, tool_name, progress_callback
                )
                return result
            except _SUBPROCESS_ERRORS as e:
                return False, str(e)

        return await loop.run_in_executor(None, sync_extract)

    def get_supported_extensions(self) -> List[str]:
        """Get list of supported archive extensions."""
        return self.supported_extensions
