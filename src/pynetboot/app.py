"""
Main application class for PyNetboot using PySimpleGUI.
This replaces the Qt-based app.py with a lightweight PySimpleGUI implementation.
"""

import os
import sys
import platform
import subprocess
import logging
import tempfile
import shutil
import threading
import time
from typing import Optional, List, Dict, Any

from pynetboot.ui import main_window_ctk as sg   # dialog helpers + WIN_CLOSED
from pynetboot.ui.main_window_ctk import MainWindowCTk, HAS_CTK

HAS_PYSIMPLEGUI = HAS_CTK  # kept: the app still guards on a usable toolkit

from pynetboot import APP_NAME
from pynetboot.models.distro import DistributionManager
from pynetboot.core.extractor import ISOExtractor
from pynetboot.core.downloader import (
    Downloader
)
from pynetboot.core.installer import USBInstaller
from pynetboot.core.utils import (
    get_platform_info, format_size, normalize_language_code,
    directory_stats
)
from pynetboot.platform import get_drive_list, is_safe_target

logger = logging.getLogger(__name__)

# Minimum gap between progress updates pushed to the UI thread. The downloader
# reports every 8 KB chunk; forwarding all of them floods the event queue and
# starves button presses such as Cancel.
_PROGRESS_INTERVAL = 0.1


class InstallationCancelled(Exception):
    """Raised when the user cancels the installation."""
    pass


class ISOLocationError(Exception):
    """Raised when no usable folder is available to download the ISO into."""
    pass


class PyNetbootApp:
    """Main application class that coordinates all functionality using PySimpleGUI."""

    def __init__(self, parent=None, cli_args: Optional[Dict[str, Any]] = None):
        """Initialize the PyNetboot application."""
        if not HAS_CTK:
            raise ImportError(
                "customtkinter is required. "
                "Please install it with: pip install customtkinter"
            )

        logger.info("Initializing PyNetbootApp with PySimpleGUI")

        # Application state
        self.cli_args = cli_args or {}
        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.app_loc = sys.argv[0]
        # Normalize language code
        lang = self.cli_args.get('lang')
        self.app_lang = normalize_language_code(lang) or \
            normalize_language_code('en')
        self.tmp_dir = None
        # ISO downloaded to the Downloads folder as staging; removed on success.
        self.iso_to_delete = None
        # Set when the user presses the inline Cancel button during a transfer.
        self._cancel_download = False
        self.exit_on_completion = False
        self.testing_download = False
        self.running = False

        # Platform-specific setup
        self.platform = platform.system().lower()
        self.platform_info = get_platform_info()
        logger.info(f"Platform: {self.platform}, Info: {self.platform_info}")

        # Initialize components
        self.distro_manager = DistributionManager()
        self.extractor = ISOExtractor()
        self.downloader = Downloader()
        self.installer = USBInstaller()

        # Initialize async components

        # Initialize UI (window is finalized in __init__)
        self.ui = MainWindowCTk(self)

        # Hide the window while we load data
        self.ui.window.hide()

        # Load distribution list
        self.load_distributions()

        # Load drive list
        self.load_drive_list()

        # Data is loaded — reveal the window again. Without this the process
        # runs with a permanently hidden window and the user sees nothing.
        self.ui.show()

        # No startup privilege check: the GUI runs as a normal user and each
        # privileged device operation elevates on demand (pkexec/PolicyKit).
        # Forcing elevation here produced a spurious "Elevation required" dialog
        # on launch even though the actual install path elevates per-command.

    def load_distributions(self) -> None:
        """Load the list of supported distributions."""
        logger.info("Loading distributions")
        try:
            distros = self.distro_manager.get_distributions()
            self.ui.set_distributions(distros)
        except (OSError, ValueError, KeyError, RuntimeError) as e:
            logger.error(f"Failed to load distributions: {e}")
            self.show_error("Failed to load distribution list")

    def load_drive_list(self) -> bool:
        """Load the list of available drives.

        Returns:
            bool: True if successful, False on error
        """
        logger.info("Loading drive list")
        try:
            drives = get_drive_list()
            drive_display_list = self.format_drive_list(
                drives, target_type=self.get_target_type()
            )
            return self.ui.set_drive_list(drive_display_list)
        except (OSError, ValueError, KeyError, RuntimeError) as e:
            logger.error(f"Failed to load drive list: {e}")
            self.show_error("Failed to load drive list")
            return False

    def get_target_type(self) -> str:
        """Current target type from the UI ("USB Drive" or "Hard Disk")."""
        try:
            return self.ui.elements['type_select'].get() or "USB Drive"
        except (AttributeError, KeyError):
            return "USB Drive"

    def format_drive_list(
        self,
        drives: List[Dict[str, Any]],
        target_type: str = "USB Drive"
    ) -> List[tuple]:
        """Format drive list for display in UI.

        SAFETY: only genuinely external drives are shown. The system disk,
        internal disks and virtual drives / disk images are filtered out via the
        platform `is_safe_target()` check and can never be selected — not even
        as an exception. If nothing qualifies, the list is empty.

        With target_type "Hard Disk" the filter widens to include external
        drives that are not flagged as removable media (external HDDs/SSDs);
        the system and internal disks stay excluded.
        """
        display_list = []
        allow_external_fixed = (target_type == "Hard Disk")

        for drive in drives:
            device = drive.get('device', '')
            if not device:
                continue

            # Hard safety gate: skip anything that is not a proven-safe
            # external target. Fails closed on any uncertainty.
            if not is_safe_target(device, allow_external_fixed=allow_external_fixed):
                logger.debug(f"Excluding internal/unsafe drive: {device}")
                continue

            parts = [device]

            size = drive.get('size')
            if size:
                try:
                    size_str = format_size(size)
                    parts.append(f"({size_str})")
                except (ValueError, TypeError):
                    pass

            label = drive.get('label', '')
            if label:
                parts.append(f"'{label}'")

            if drive.get('removable', False):
                parts.append("[Removable]")

            filesystem = drive.get('filesystem', '')
            if filesystem:
                parts.append(f"({filesystem})")

            display_str = " ".join(parts)
            display_list.append((display_str, device))

        # Sort drives - put removable drives first, then by device name
        display_list.sort(key=lambda x: ("[Removable]" not in x[0], x[0]))

        return display_list



    def get_installation_parameters(self) -> Dict[str, Any]:
        """Get installation parameters from UI.

        Returns:
            Dict[str, Any]: Dictionary of installation parameters
        """
        return self.ui.get_installation_parameters()

    def validate_parameters(self, params: Dict[str, Any]) -> bool:
        """Validate installation parameters.

        Args:
            params: Dictionary of installation parameters to validate

        Returns:
            bool: True if all parameters are valid, False otherwise
        """
        if params.get('install_type') == 'distribution':
            if not params.get('distro'):
                self.show_error("Please select a distribution")
                return False
        elif params.get('install_type') == 'iso':
            if not params.get('iso_path'):
                self.show_error("Please select an ISO file")
                return False
        elif params.get('install_type') == 'floppy':
            if not params.get('floppy_image'):
                self.show_error("Please select a disk image")
                return False

        if not params.get('target_drive'):
            self.show_error("Please select a target drive")
            return False

        return True

    @staticmethod
    def _usable_dir(path: str) -> bool:
        """True if `path` exists (or can be created) and is writable."""
        try:
            os.makedirs(path, exist_ok=True)
            return os.access(path, os.W_OK)
        except OSError:
            return False

    def get_downloads_dir(self) -> Optional[str]:
        """The user's Downloads folder, or None if it is unusable.

        Honours the XDG user-dirs setting on Linux (so localised folder names
        work) and falls back to ~/Downloads.
        """
        candidates = []
        try:
            result = subprocess.run(['xdg-user-dir', 'DOWNLOAD'],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                candidates.append(result.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            pass
        candidates.append(os.path.join(os.path.expanduser('~'), 'Downloads'))

        for path in candidates:
            # A bare home directory means xdg-user-dir found nothing useful.
            if path and path != os.path.expanduser('~') and self._usable_dir(path):
                return path
        return None

    def resolve_iso_download_dir(self, iso_dir: Optional[str]) -> tuple:
        """Where to download the ISO, and whether to delete it afterwards.

        Returns (directory, delete_after_success):
          * a folder set in Advanced Options → ISO Location is used and the ISO
            is KEPT there;
          * otherwise the user's Downloads folder is used and the ISO is
            deleted once the drive has been created successfully.

        Raises ISOLocationError if the chosen folder is not writable, or if no
        folder was chosen and the Downloads folder is unavailable — in that
        case the user is told to set the location in Advanced Options.
        """
        if iso_dir and iso_dir.strip():
            path = os.path.expanduser(iso_dir.strip())
            if self._usable_dir(path):
                logger.info(f"Using ISO Location folder (kept): {path}")
                return path, False
            raise ISOLocationError(
                f"Cannot write to the ISO folder:\n{path}\n\n"
                "Choose a different folder in Advanced Options > ISO Location."
            )

        downloads = self.get_downloads_dir()
        if downloads:
            logger.info(f"Using Downloads folder (temporary): {downloads}")
            return downloads, True

        raise ISOLocationError(
            "Your Downloads folder is not available or not accessible.\n\n"
            "Please select the ISO Location from the advanced option."
        )

    def run_in_background(self, work, status: str = "",
                          cancellable: bool = True):
        """Run blocking `work` off the UI thread while the window stays live.

        `work(report, cancelled)` is executed in a worker thread, where
        `report(percent=, text=)` updates the inline progress and `cancelled()`
        returns True once the user asks to stop. Meanwhile this method runs the
        real event loop, so the window redraws, moves and responds normally
        instead of freezing for the duration.

        A thread rather than a process: the work is I/O-bound (socket reads,
        file writes, subprocess waits) so the GIL is released throughout, while
        a child process would have to re-exec this PyInstaller onefile binary,
        would not inherit the subprocess elevation patch, and could only be
        stopped by killing it mid-write.

        Returns whatever `work` returns; re-raises its exception on this thread.
        """
        window = self.ui.window
        cancel_event = threading.Event()
        outcome = {}

        last_report = [0.0]

        def report(percent: Optional[int] = None, text: Optional[str] = None):
            """Hand a progress update to the UI thread (thread-safe).

            Rate-limited on purpose. The downloader invokes its progress
            callbacks once per 8 KB chunk, so an unthrottled report() queues
            hundreds of thousands of events for a large ISO; the Cancel press
            then sits behind that backlog and appears to do nothing. Dropping
            intermediate frames costs nothing visually — the bar is only
            redrawn a few times a second anyway.
            """
            now = time.monotonic()
            if now - last_report[0] < _PROGRESS_INTERVAL:
                return
            last_report[0] = now
            try:
                window.write_event_value('-WORK_PROGRESS-', (percent, text))
            except (AttributeError, RuntimeError):
                pass

        def runner():
            try:
                outcome['value'] = work(report, cancel_event.is_set)
            except BaseException as exc:  # noqa: BLE001 - re-raised on the UI thread
                outcome['error'] = exc
            finally:
                try:
                    window.write_event_value('-WORK_DONE-', True)
                except (AttributeError, RuntimeError):
                    pass

        self.ui.begin_progress(status, cancellable=cancellable)
        thread = threading.Thread(target=runner, daemon=True)
        thread.start()

        try:
            while True:
                event, values = window.read(timeout=100)

                if event == '-WORK_DONE-':
                    break

                if event == '-WORK_PROGRESS-':
                    percent, text = values['-WORK_PROGRESS-']
                    self.ui.set_progress(percent=percent, text=text)

                elif event == '-LOG-':
                    # The log button stays enabled while work runs (it is not
                    # in _BUSY_ELEMENTS), but this loop used to drop the
                    # event, so nothing happened when it was pressed. The log
                    # is most wanted precisely while something is going on.
                    self.ui.show_log()

                elif event in ('-CANCEL_DOWNLOAD-', '-CANCEL-') and cancellable:
                    if not cancel_event.is_set():
                        logger.info("Cancel requested by user")
                        cancel_event.set()
                        self.ui.set_progress(text="Cancelling...")

                elif event in (sg.WIN_CLOSED, '-EXIT-'):
                    if cancellable:
                        logger.info("Window closed during work - cancelling")
                        cancel_event.set()
                        self.ui.set_progress(text="Cancelling...")
                    else:
                        # Writing to the device cannot be safely interrupted.
                        logger.info("Close ignored: operation cannot be stopped")

            thread.join()
        finally:
            self.ui.end_progress()

        if 'error' in outcome:
            raise outcome['error']
        return outcome.get('value')

    def download_iso(self, iso_url: str, iso_path: str,
                     distro: str, version: str) -> None:
        """Download an ISO to `iso_path` and verify its checksum.

        Progress is shown inline in the main window (bar, status text and
        Cancel button next to the advanced options), not in a popup. Raises on
        failure; InstallationCancelled if cancelled.
        """
        iso_filename = os.path.basename(iso_path)
        logger.info(f"Downloading ISO from {iso_url} to {iso_path}")

        def do_download(report, cancelled):
            """Download on the worker thread, reporting progress to the UI."""
            def on_progress(bytes_received: int, bytes_total: int):
                if bytes_total > 0:
                    report(percent=int(bytes_received / bytes_total * 100))

            def on_estimated(percentage: int, bytes_received: int,
                             eta_or_speed: int):
                if percentage >= 0:
                    report(text=f"{percentage}% - {format_size(bytes_received)}")
                else:
                    speed = self.downloader.format_download_speed(eta_or_speed)
                    report(text=f"{format_size(bytes_received)} at {speed}")

            return self.downloader.download_file_sync(
                iso_url,
                iso_path,
                min_size=1024 * 1024,
                progress_callback=on_progress,
                progress_estimated_callback=on_estimated,
                cancel_check=cancelled
            )

        success, message = self.run_in_background(
            do_download, status=f"Downloading {iso_filename}...",
            cancellable=True)

        if not success:
            if message and 'cancel' in str(message).lower():
                raise InstallationCancelled("Cancelled by user")
            raise ValueError(f"Failed to download ISO: {message}")

        # Hashing a multi-GB ISO also blocks, so verify off the UI thread too.
        verification = self.get_distribution_checksum(
            distro, version, iso_filename=iso_filename)
        if verification:
            checksum, algorithm = verification

            def do_verify(report, cancelled):
                report(percent=100,
                       text=f"Verifying ISO {algorithm.upper()}...")
                return self.downloader.verify_checksum(
                    iso_path, checksum, algorithm)

            if not self.run_in_background(
                    do_verify, status="Verifying ISO checksum...",
                    cancellable=False):
                try:
                    os.remove(iso_path)
                except OSError:
                    pass
                raise RuntimeError(
                    f"ISO checksum verification failed for {iso_filename}")
            logger.info("ISO checksum verified successfully")
        else:
            logger.warning(
                f"No checksum available for {distro} {version}, "
                "skipping verification")

    def _discard_staged_iso(self) -> None:
        """Delete an ISO that was staged in the Downloads folder."""
        path, self.iso_to_delete = self.iso_to_delete, None
        if not path:
            return
        try:
            if os.path.isfile(path):
                os.remove(path)
                logger.info(f"Removed staged ISO: {path}")
        except OSError as e:
            logger.warning(f"Could not remove staged ISO {path}: {e}")

    def on_iso_download_clicked(self):
        """Download the selected ISO into the ISO Location folder only."""
        logger.info("ISO Download clicked")
        try:
            params = self.get_installation_parameters()

            iso_dir = (params.get('iso_download_dir') or '').strip()
            if not iso_dir:
                self.show_error(
                    "No ISO Location selected.\n\n"
                    "For this feature you need to select a location in "
                    "Advanced Options > ISO Location."
                )
                return

            if params.get('install_type') != 'distribution':
                self.show_error(
                    "Select a distribution to download."
                )
                return

            distro, version = params.get('distro'), params.get('version')
            if not distro or not version:
                self.show_error("Please select a distribution and version.")
                return

            if self._handle_manual_download(distro, version):
                return

            iso_url = self.get_distribution_iso_url(distro, version)
            if not iso_url:
                self.show_error(
                    f"Could not find an ISO URL for {distro} {version}."
                )
                return

            target_dir, _delete_after = self.resolve_iso_download_dir(iso_dir)
            iso_path = os.path.join(target_dir, os.path.basename(iso_url))

            # A plain download: never scheduled for deletion.
            self.iso_to_delete = None
            self.download_iso(iso_url, iso_path, distro, version)
            self.show_info(f"ISO downloaded to:\n{iso_path}",
                           title="Download Complete")

        except ISOLocationError as e:
            self.show_error(str(e))
        except InstallationCancelled:
            logger.info("ISO download cancelled by user")
        except (OSError, RuntimeError, ValueError,
                subprocess.SubprocessError) as e:
            logger.error(f"ISO download failed: {e}")
            self.show_error(f"ISO download failed: {str(e)}")

    def create_temp_directory(self) -> None:
        """Create a temporary directory for extraction."""
        self.tmp_dir = tempfile.mkdtemp(prefix='pynetboot_')
        logger.info(f"Created temporary directory: {self.tmp_dir}")

    def cleanup(self) -> None:
        """Clean up temporary files."""
        if self.tmp_dir and os.path.exists(self.tmp_dir):
            try:
                shutil.rmtree(self.tmp_dir)
                logger.info(f"Cleaned up temporary directory: {self.tmp_dir}")
            except (OSError, shutil.Error) as e:
                logger.error(f"Failed to clean up temporary directory: {e}")
        self.tmp_dir = None

    def show_error(self, message: str) -> None:
        """Show error message to user.

        Args:
            message: Error message to display
        """
        logger.error(f"Showing error to user: {message}")
        sg.popup_error(message, title="Error")

    def show_info(
        self,
        message: str,
        title: str = "Information"
    ) -> None:
        """Show information message to user.

        Args:
            message: Information message to display
            title: Window title (default: "Information")
        """
        sg.popup_ok(message, title=title)

    def show_completion_message(self, message: str = None) -> None:
        """Show installation completion message.

        Args:
            message: Completion message to display (default: generic message)
        """
        if message is None:
            message = f"{APP_NAME} has completed successfully!"

        # The drive was created, so drop the ISO staged in the Downloads
        # folder. An ISO in a user-chosen ISO Location folder is never removed.
        self._discard_staged_iso()

        sg.popup_ok(message, title="Installation Complete")

        if self.exit_on_completion:
            self.stop()

    def get_distribution_checksum(self, distro_name: str,
                                  version_name: str,
                                  iso_filename: Optional[str] = None) -> Optional[str]:
        """Get the SHA256 checksum for a distribution version.

        Prefers a static `sha256`; if none is set but the version provides a
        `sha256_url` (a published SHA256SUMS file) and `iso_filename` is known,
        the hash is fetched live and matched by filename. This makes checksum
        verification work across point releases without hardcoding hashes.
        """
        distro = self.distro_manager.get_distribution(distro_name)
        if not distro:
            logger.error(f"Distribution not found: {distro_name}")
            return None

        for version in distro.versions:
            if version.name != version_name:
                continue

            # Strongest first. A weaker digest is worth far more than
            # skipping verification entirely, which is what happened
            # before: it still catches a truncated download, a corrupt
            # mirror or a substituted file.
            for algorithm in ("sha256", "sha512", "sha1", "md5"):
                static = getattr(version, algorithm, None)
                if static:
                    return static, algorithm

                url = getattr(version, f"{algorithm}_url", None)
                if url and iso_filename:
                    fetched = self.downloader.fetch_checksum_from_url(
                        url, iso_filename, algorithm)
                    if fetched:
                        return fetched, algorithm

            return None

        return None

    def get_download_page(self, distro_name: str,
                          version_name: str) -> Optional[str]:
        """Official page for versions that have no direct download URL.

        Windows ISOs are served through session-based pages, so there is no
        stable link to fetch. Such versions carry a `download_page` instead.
        """
        distro = self.distro_manager.get_distribution(distro_name)
        if not distro:
            return None
        for version in distro.versions:
            if version.name == version_name:
                return getattr(version, 'download_page', None)
        return None

    def _handle_manual_download(self, distro: str, version: str) -> bool:
        """Explain how to obtain an image that cannot be downloaded directly.

        Returns True when the version is vendor-only and has been handled.
        """
        page = self.get_download_page(distro, version)
        if not page:
            return False

        message = (
            f"{distro} {version} cannot be downloaded automatically.\n\n"
            "Microsoft provides these images through its own download page, "
            "so there is no direct link to fetch.\n\n"
            f"Download the ISO from:\n{page}\n\n"
            "Then select \"Disk image\" in this window and choose the "
            "downloaded file to write it to your drive."
        )
        if sg.popup_yes_no(message + "\n\nOpen that page now?",
                           title="Download from the vendor") == 'Yes':
            try:
                import webbrowser
                webbrowser.open(page)
            except (ImportError, OSError) as e:
                logger.warning(f"Could not open {page}: {e}")
        return True

    def get_distribution_iso_url(self, distro_name: str,
                                 version_name: str) -> Optional[str]:
        """Get the ISO URL for a specific distribution and version."""
        distro = self.distro_manager.get_distribution(distro_name)
        if not distro:
            logger.error(f"Distribution not found: {distro_name}")
            return None

        for version in distro.versions:
            if version.name == version_name:
                if version.url:
                    logger.info(
                        f"Found ISO URL for {distro_name} {version_name}: "
                        f"{version.url}"
                    )
                    return version.url
                else:
                    logger.error(f"Version {version_name} has no URL")
                    return None

        if distro.versions:
            logger.warning(
                f"Version {version_name} not found, "
                f"using first available version"
            )
            return distro.versions[0].url

        logger.error(
            f"No versions available for distribution {distro_name}"
        )
        return None

    def start_installation(self, params: Dict[str, Any]):
        """Start the installation process."""
        logger.info("Starting installation process")

        install_type = params.get('install_type')

        if install_type in ('iso', 'floppy'):
            source_image = params.get('iso_path') or params.get('floppy_image')

            try:
                # Extraction (0-50%) off the UI thread.
                def do_extract(report, cancelled):
                    def extract_progress(percent: int):
                        report(percent=int(percent * 0.5))

                    return self.extractor.extract_iso_sync(
                        source_image,
                        self.tmp_dir,
                        progress_callback=extract_progress
                    )

                success, message = self.run_in_background(
                    do_extract, status="Extracting image...", cancellable=False)
                if not success:
                    raise RuntimeError(f"Extraction failed: {message}")

                # Write to the device (50-100%). Never cancellable.
                def do_install(report, cancelled):
                    def install_progress(percent: int):
                        report(percent=50 + int(percent * 0.5))

                    return self.installer.install_sync(
                        self.tmp_dir,
                        params['target_drive'],
                        params,
                        progress_callback=install_progress
                    )

                success, message = self.run_in_background(
                    do_install, status="Installing to USB...", cancellable=False)
                if not success:
                    raise RuntimeError(f"Installation failed: {message}")

                self.show_completion_message()

            except InstallationCancelled:
                logger.info("Installation cancelled by user")
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as e:
                logger.error(f"Installation failed: {e}")
                self.show_error(f"Installation failed: {str(e)}")
            finally:
                self.cleanup()

        elif install_type == 'distribution':
            self.download_and_install_distribution(params)
        else:
            raise RuntimeError(f"Unsupported install type: {install_type}")

    def download_and_install_distribution(self, params: Dict[str, Any]):
        """Download ISO from distribution URL and install."""
        logger.info(
            f"Downloading distribution: {params.get('distro')}, "
            f"version: {params.get('version')}")

        # Some images (Windows) are only offered through a vendor page.
        if self._handle_manual_download(params.get('distro'),
                                        params.get('version')):
            raise InstallationCancelled("Image must be downloaded manually")

        # Get the ISO URL
        iso_url = self.get_distribution_iso_url(
            params.get('distro'), params.get('version'))
        if not iso_url:
            raise ValueError(
                f"Could not find ISO URL for distribution "
                f"{params.get('distro')} version {params.get('version')}")

        iso_filename = os.path.basename(iso_url)
        download_dir, delete_after = self.resolve_iso_download_dir(
            params.get('iso_download_dir'))
        iso_path = os.path.join(download_dir, iso_filename)
        # Downloaded into the Downloads folder only as a staging area: remove
        # it once the drive has been created. A user-chosen folder is kept.
        self.iso_to_delete = iso_path if delete_after else None

        logger.info(f"Downloading ISO from {iso_url} to {iso_path}")

        try:
            # Each stage runs off the UI thread so the window stays responsive.
            def do_download(report, cancelled):
                """Download, mapped onto the 0-30% band of the overall job."""
                def on_progress(bytes_received: int, bytes_total: int):
                    if bytes_total > 0:
                        report(percent=min(
                            int(bytes_received / bytes_total * 30), 30))
                    else:
                        report(percent=30 * bytes_received //
                               (bytes_received + 1024 * 1024))

                def on_estimated(percentage: int, bytes_received: int,
                                 eta_or_speed: int):
                    if percentage >= 0:
                        report(text=f"{percentage}% - "
                                    f"{format_size(bytes_received)}")
                    else:
                        speed = self.downloader.format_download_speed(eta_or_speed)
                        report(text=f"{format_size(bytes_received)} at {speed}")

                return self.downloader.download_file_sync(
                    iso_url,
                    iso_path,
                    min_size=1024 * 1024,
                    progress_callback=on_progress,
                    progress_estimated_callback=on_estimated,
                    cancel_check=cancelled
                )

            download_started = time.monotonic()
            success, message = self.run_in_background(
                do_download, status=f"Downloading {iso_filename}...",
                cancellable=True)

            if not success:
                if message and 'cancel' in str(message).lower():
                    raise InstallationCancelled("Cancelled by user")
                raise ValueError(f"Failed to download ISO: {message}")

            download_seconds = time.monotonic() - download_started
            try:
                iso_size = os.path.getsize(iso_path)
            except OSError as e:
                logger.warning(f"Could not stat downloaded ISO: {e}")
                iso_size = 0
            rate = iso_size / download_seconds if download_seconds > 0 else 0
            logger.info(
                f"ISO downloaded successfully: {iso_path} "
                f"({format_size(iso_size)} in {download_seconds:.1f}s, "
                f"{format_size(int(rate))}/s)")

            # Verify checksum (hashing a large ISO blocks too).
            verification = self.get_distribution_checksum(
                params.get('distro'), params.get('version'),
                iso_filename=iso_filename)
            if verification:
                checksum, algorithm = verification

                def do_verify(report, cancelled):
                    report(percent=30,
                           text=f"Verifying ISO {algorithm.upper()}...")
                    return self.downloader.verify_checksum(
                        iso_path, checksum, algorithm)

                if not self.run_in_background(
                        do_verify, status="Verifying ISO checksum...",
                        cancellable=False):
                    try:
                        os.remove(iso_path)
                    except OSError:
                        pass
                    raise RuntimeError(
                        f"ISO checksum verification failed for {iso_filename}")
                logger.info("ISO checksum verified successfully")
            else:
                logger.warning(
                    f"No checksum available for {params.get('distro')} "
                    f"{params.get('version')}, skipping verification")

            # Extract ISO (35-80%).
            def do_extract(report, cancelled):
                def extract_progress(percent: int):
                    report(percent=35 + int(percent * 0.45))

                return self.extractor.extract_iso_sync(
                    iso_path,
                    self.tmp_dir,
                    progress_callback=extract_progress
                )

            logger.info(f"Extracting {iso_path} to {self.tmp_dir}")
            extract_started = time.monotonic()
            success, message = self.run_in_background(
                do_extract, status="Extracting ISO...", cancellable=False)
            if not success:
                raise RuntimeError(f"Extraction failed: {message}")

            extract_seconds = time.monotonic() - extract_started
            extracted_files, extracted_bytes = directory_stats(self.tmp_dir)
            logger.info(
                f"ISO extracted successfully: {extracted_files} files, "
                f"{format_size(extracted_bytes)} in {extract_seconds:.1f}s")
            # A quick extraction is normal when the ISO is still in the page
            # cache, so the counts above are what tell you it did real work.
            if extracted_bytes < iso_size // 2:
                logger.warning(
                    f"Extracted data ({format_size(extracted_bytes)}) is far "
                    f"smaller than the ISO ({format_size(iso_size)}); the "
                    f"image may not have unpacked completely")
            top_level = sorted(os.listdir(self.tmp_dir))[:20]
            logger.info(f"Extracted top-level entries: {top_level}")

            # Write to the device (80-100%). Never cancellable.
            def do_install(report, cancelled):
                def install_progress(percent: int):
                    report(percent=80 + int(percent * 0.2))

                return self.installer.install_sync(
                    self.tmp_dir,
                    params['target_drive'],
                    params,
                    progress_callback=install_progress
                )

            logger.info(
                f"Writing {self.tmp_dir} to {params['target_drive']} "
                f"({format_size(extracted_bytes)} across "
                f"{extracted_files} files)")
            install_started = time.monotonic()
            success, message = self.run_in_background(
                do_install, status="Installing to USB...", cancellable=False)
            if not success:
                raise RuntimeError(f"Installation failed: {message}")

            logger.info(
                f"Installation completed in "
                f"{time.monotonic() - install_started:.1f}s")
            self.show_completion_message()

        except InstallationCancelled:
            logger.info("Installation cancelled by user")
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as e:
            logger.error(f"Installation failed: {e}")
            self.show_error(f"Installation failed: {str(e)}")
        finally:
            self.cleanup()

    def run(self):
        """Run the main application event loop."""
        self.running = True

        while self.running and self.ui.is_visible():
            # Process UI events
            event, values = self.ui.read_event(timeout=100)

            if event in (sg.WIN_CLOSED, '-EXIT-', None):
                logger.info("Exit requested")
                self.running = False
                break

            elif event == '-CANCEL-':
                # Cancel stops an operation in progress; it must never close
                # the application - that is Exit's job. Reaching the main loop
                # means nothing is running, so there is nothing to cancel.
                logger.debug("Cancel pressed with no operation in progress")

            elif event == '-OK-':
                self.on_ok_clicked()

            elif event == '-CANCEL_DOWNLOAD-':
                # Only meaningful while a transfer is running (it is polled by
                # cancel_requested()); ignore a stray press otherwise.
                logger.debug("Cancel pressed with no transfer in progress")

            elif event == '-ABOUT-':
                self.ui.show_about()

            elif event == '-LOG-':
                self.ui.show_log()

            elif event == '-REFRESH_DRIVES-':
                self.on_refresh_drive_list()

            elif event == '-TYPE_SELECT-':
                # Switching between "USB Drive" and "Hard Disk" changes which
                # devices qualify, so re-filter the list against the new type.
                self.on_refresh_drive_list()

            elif event == '-RADIO_DISTRO-':
                self.on_install_type_changed('distribution')

            elif event == '-RADIO_FLOPPY-':
                self.on_install_type_changed('floppy')

            elif event == '-RADIO_MANUAL-':
                self.on_install_type_changed('manual')

            elif event == '-CATEGORY_SELECT-':
                category = values.get('-CATEGORY_SELECT-')
                self.ui.set_category_icon(category)
                self.ui.update_distro_list(category)

            elif event == '-DISTRO_SELECT-':
                distro_name = self.ui.get_current_distro_name()
                if distro_name:
                    self.ui.update_version_list(distro_name)

            elif event == '-ADVANCED_TOGGLE-':
                self.ui.toggle_advanced()

            elif event == '-ISO_DOWNLOAD-':
                self.on_iso_download_clicked()

            elif event == '-PERSISTENCE_CHECK-':
                enabled = values.get('-PERSISTENCE_CHECK-', False)
                self.ui.elements['persistence_size'].update(disabled=not enabled)

            # Handle file browser buttons
            elif event == '-FLOPPY_BROWSE-':
                file_path = sg.popup_get_file(
                    "Select Disk Image",
                    default_path="",
                    file_types=(
    ("All files", "*.*"), ("ISO files", "*.iso"), ("IMG files", "*.img"))
                )
                if file_path:
                    self.ui.elements['floppy_file'].update(file_path)

            elif event == '-KERNEL_BROWSE-':
                file_path = sg.popup_get_file(
    "Select Kernel File", default_path="", file_types=(
        ("All files", "*.*"),))
                if file_path:
                    self.ui.elements['kernel_file'].update(file_path)

            elif event == '-INITRD_BROWSE-':
                file_path = sg.popup_get_file(
    "Select Initrd File", default_path="", file_types=(
        ("All files", "*.*"),))
                if file_path:
                    self.ui.elements['initrd_file'].update(file_path)

            elif event == '-CFG_BROWSE-':
                file_path = sg.popup_get_file(
    "Select Config File", default_path="", file_types=(
        ("All files", "*.*"), ("CFG files", "*.cfg")))
                if file_path:
                    self.ui.elements['cfg_file'].update(file_path)

            # Handle progress events
            elif event == '-PROGRESS-':
                # This is handled internally
                pass

        self.cleanup()

    def _confirm_destructive_write(self, device: str) -> bool:
        """Re-verify the target is a safe USB drive and confirm the erase.

        Returns True only if the device is a proven removable target AND the
        user explicitly confirms. This is defense-in-depth: even though the UI
        only lists safe targets, we re-check here so a stale/hand-edited device
        can never be formatted.
        """
        if not device:
            self.show_error("Please select a target drive.")
            return False

        # Hard re-check against the live device table (fails closed). Uses the
        # same target type as the list the user picked from, so an external
        # hard drive stays valid while internal/system disks never are.
        allow_external_fixed = (self.get_target_type() == "Hard Disk")
        if not is_safe_target(device, allow_external_fixed=allow_external_fixed):
            logger.error(f"Refusing destructive write to unsafe device: {device}")
            self.show_error(
                f"Refusing to write to {device}.\n\n"
                "Only external drives can be used as a target. Internal "
                "disks, the system disk and virtual drives are never allowed."
            )
            return False

        # Look up size/label for a clear warning message.
        size_str, label = "", ""
        try:
            for drv in get_drive_list():
                if drv.get('device') == device:
                    if drv.get('size'):
                        size_str = format_size(drv['size'])
                    label = drv.get('label', '') or ''
                    break
        except (OSError, ValueError, KeyError):
            pass

        detail = device
        if size_str:
            detail += f"  ({size_str})"
        if label:
            detail += f"  '{label}'"

        response = sg.popup_yes_no(
            "WARNING: This will PERMANENTLY ERASE ALL DATA on the drive "
            "below and cannot be undone:\n\n"
            f"    {detail}\n\n"
            "Make sure you have selected the correct USB drive.\n\n"
            "Continue?",
            title="Confirm - all data on this drive will be erased",
        )
        if response != 'Yes':
            logger.info("User cancelled destructive write at confirmation")
            return False
        return True

    def on_ok_clicked(self):
        """Handle OK button click - start the installation process."""
        logger.info("OK button clicked - starting installation")

        try:
            params = self.get_installation_parameters()
            logger.info(f"Installation parameters: {params}")

            if not self.validate_parameters(params):
                return

            # Final safety gate before anything destructive happens: re-verify
            # the target is a removable USB drive and get explicit confirmation
            # that its data will be erased.
            if not self._confirm_destructive_write(params.get('target_drive')):
                return

            self.create_temp_directory()
            self.start_installation(params)

        except ISOLocationError as e:
            logger.error(f"No usable ISO download location: {e}")
            self.show_error(str(e))
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as e:
            logger.error(f"Error in installation process: {e}")
            self.show_error(f"Installation error: {str(e)}")
        finally:
            # Safety net: some error paths raise before start_installation's
            # own finally-cleanup is reached (e.g. unsupported install type,
            # missing ISO URL). cleanup() is idempotent, so calling it again
            # after a successful run is harmless.
            self.cleanup()

    def on_refresh_drive_list(self):
        """Handle refresh drive list request."""
        logger.info("Refreshing drive list")
        self.load_drive_list()

    def on_install_type_changed(self, install_type: str):
        """Handle installation type change."""
        logger.info(f"Installation type changed to: {install_type}")
        self.ui.update_install_type(install_type)

    def stop(self):
        """Stop the application."""
        self.running = False
        self.ui.close()
        self.cleanup()


def main():
    """Entry point for running the application directly.

    Delegates to pynetboot.main.main so `python -m pynetboot.app` and the
    canonical launcher share identical startup (logging, CLI parsing, etc.).
    """
    from pynetboot.main import main as _main
    _main()


if __name__ == "__main__":
    main()
