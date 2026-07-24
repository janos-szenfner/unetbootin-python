"""
Main application class for UNetbootin using PySimpleGUI.
This replaces the Qt-based app.py with a lightweight PySimpleGUI implementation.
"""

import os
import sys
import platform
import subprocess
import logging
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any

try:
    import PySimpleGUI as sg
    HAS_PYSIMPLEGUI = True
except ImportError:
    HAS_PYSIMPLEGUI = False
    sg = None

from unetbootin import APP_NAME, APP_VERSION
from unetbootin.ui.main_window_pysg import MainWindowPySG
from unetbootin.models.distro import DistributionManager
from unetbootin.core.extractor import ISOExtractor
from unetbootin.core.downloader import (
    Downloader, AsyncDownloader, DownloadResumeManager
)
from unetbootin.core.installer import USBInstaller
from unetbootin.core.utils import (
    check_root, check_admin, get_platform_info,
    format_size, normalize_language_code
)
from unetbootin.platform import get_drive_list, is_safe_target

logger = logging.getLogger(__name__)


class InstallationCancelled(Exception):
    """Raised when the user cancels the installation."""
    pass


class UNetbootinAppPySG:
    """Main application class that coordinates all functionality using PySimpleGUI."""
    
    def __init__(self, parent=None, cli_args: Optional[Dict[str, Any]] = None):
        """Initialize the UNetbootin application."""
        if not HAS_PYSIMPLEGUI:
            raise ImportError(
                "PySimpleGUI is required. "
                "Please install it with: pip install PySimpleGUI"
            )
        
        logger.info("Initializing UNetbootinApp with PySimpleGUI")
        
        # Application state
        self.cli_args = cli_args or {}
        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.app_loc = sys.argv[0]
        # Normalize language code
        lang = self.cli_args.get('lang')
        self.app_lang = normalize_language_code(lang) or \
            normalize_language_code('en')
        self.tmp_dir = None
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
        self.async_downloader = AsyncDownloader()
        
        # Initialize UI (window is finalized in __init__)
        self.ui = MainWindowPySG(self)
        
        # Hide the window while we load data
        self.ui.window.hide()
        
        # Load distribution list
        self.load_distributions()
        
        # Load drive list
        self.load_drive_list()
        
        # Check for root/admin privileges on Unix systems
        rootcheck = str(
            self.cli_args.get('rootcheck', True)
        ).lower() not in ('no', 'false', '0')
        if rootcheck and self.platform in ['linux', 'darwin']:
            self.check_privileges()
    
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
            drive_display_list = self.format_drive_list(drives)
            return self.ui.set_drive_list(drive_display_list)
        except (OSError, ValueError, KeyError, RuntimeError) as e:
            logger.error(f"Failed to load drive list: {e}")
            self.show_error("Failed to load drive list")
            return False
    
    def format_drive_list(self, drives: List[Dict[str, Any]]) -> List[tuple]:
        """Format drive list for display in UI.

        SAFETY: only genuinely removable/external USB drives are shown. Internal
        disks, the system disk and virtual drives / disk images are filtered out
        via the platform `is_safe_target()` check and can never be selected —
        not even as an exception. If nothing qualifies, the list is empty.
        """
        display_list = []

        for drive in drives:
            device = drive.get('device', '')
            if not device:
                continue

            # Hard safety gate: skip anything that is not a proven-safe
            # removable target. Fails closed on any uncertainty.
            if not is_safe_target(device):
                logger.debug(f"Excluding non-removable/unsafe drive: {device}")
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
    
    def check_privileges(self):
        """Check if running with sufficient privileges.
        
        Uses the new elevation system instead of terminal-dependent flows.
        If not elevated, will attempt to relaunch with elevation automatically.
        """
        from unetbootin.core.elevation import (
            is_elevated, ensure_elevated, check_elevation_availability,
            ElevationError
        )
        
        if is_elevated():
            return
        
        # Not elevated - try to elevate
        if not check_elevation_availability():
            # Fallback: show platform-specific message
            self._show_elevation_not_available()
            return
        
        try:
            ensure_elevated()
        except ElevationError as e:
            logger.warning(f"Elevation attempt failed: {e}")
            self._show_elevation_not_available()
    
    def _show_elevation_not_available(self):
        """Show message when elevation is not available."""
        if self.platform == 'linux':
            sg.popup_error(
                f"{APP_NAME} requires elevated privileges.\n\n"
                "Please ensure polkit/pkexec is installed, or run from a terminal with sudo.",
                title="Elevation Required"
            )
        elif self.platform == 'darwin':
            sg.popup_error(
                f"{APP_NAME} requires administrator privileges.\n\n"
                "Please run with elevated privileges (pkexec, sudo, or as admin).",
                title="Elevation Required"
            )
        elif self.platform == 'win32':
            sg.popup_error(
                f"{APP_NAME} requires Administrator privileges.\n\n"
                "Please right-click and select 'Run as administrator'.",
                title="Elevation Required"
            )
        else:
            sg.popup_error(
                f"{APP_NAME} requires elevated privileges on {self.platform}.\n\n"
                "Please run with appropriate elevated permissions.",
                title="Elevation Required"
            )
    
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
    
    def create_temp_directory(self) -> None:
        """Create a temporary directory for extraction."""
        self.tmp_dir = tempfile.mkdtemp(prefix='unetbootin_')
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
            if version.name == version_name:
                static = version.get_checksum("sha256")
                if static:
                    return static
                url = getattr(version, 'sha256_url', None)
                if url and iso_filename:
                    return self.downloader.fetch_checksum_from_url(
                        url, iso_filename)
                return None

        return None
    
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
            
            # Show progress in a popup with a progress bar
            progress_layout = [
                [sg.Text("Extracting image...")],
                [sg.ProgressBar(100, orientation='h', size=(
                    40, 20), key='-PROGRESS-BAR-')],
                [sg.Button('Cancel', key='-CANCEL-INSTALL-')]
            ]
            progress_window = sg.Window(
    'Installation in Progress',
    progress_layout,
     finalize=True)
            
            try:
                # Extract image
                progress_text = progress_window['-PROGRESS-BAR-']
                
                def extract_progress(percent: int):
                    """Forward extraction progress to the event loop."""
                    progress_window.write_event_value('-PROGRESS-', percent)
                
                success, message = self.extractor.extract_iso_sync(
                    source_image,
                    self.tmp_dir,
                    progress_callback=extract_progress
                )
                if not success:
                    raise RuntimeError(f"Extraction failed: {message}")
                
                # Install to USB
                progress_window['-PROGRESS-BAR-'].update(50)
                
                def install_progress(percent: int):
                    """Forward install progress (mapped to 50-100%) to the loop."""
                    progress_window.write_event_value(
                        '-PROGRESS-', 50 + int(percent * 0.5))
                
                success, message = self.installer.install_sync(
                    self.tmp_dir,
                    params['target_drive'],
                    params,
                    progress_callback=install_progress
                )
                if not success:
                    raise RuntimeError(f"Installation failed: {message}")
                
                progress_window['-PROGRESS-BAR-'].update(100)
                self.show_completion_message()
                
            except InstallationCancelled:
                logger.info("Installation cancelled by user")
            except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as e:
                logger.error(f"Installation failed: {e}")
                self.show_error(f"Installation failed: {str(e)}")
            finally:
                progress_window.close()
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

        # Get the ISO URL
        iso_url = self.get_distribution_iso_url(
            params.get('distro'), params.get('version'))
        if not iso_url:
            raise ValueError(
                f"Could not find ISO URL for distribution "
                f"{params.get('distro')} version {params.get('version')}")
        
        iso_filename = os.path.basename(iso_url)
        iso_path = os.path.join(self.tmp_dir, iso_filename)
        
        logger.info(f"Downloading ISO from {iso_url} to {iso_path}")
        
        # Create progress window
        progress_layout = [
            [sg.Text(f"Downloading {iso_filename}...")],
            [sg.ProgressBar(100, orientation='h', size=(40, 20), key='-PROGRESS-BAR-')],
            [sg.Text("", size=(40, 1), key='-PROGRESS-TEXT-')],
            [sg.Button('Cancel', key='-CANCEL-DOWNLOAD-')]
        ]
        progress_window = sg.Window(
    'Download in Progress',
    progress_layout,
     finalize=True)
        
        cancel_download = False
        
        def download_progress(bytes_received: int, bytes_total: int):
            """Map download byte progress onto the 0-30% bar range."""
            if cancel_download:
                return
            if bytes_total > 0:
                percent = min(int((bytes_received / bytes_total) * 30), 30)
                progress_window['-PROGRESS-BAR-'].update(percent)
            else:
                # No total size known
                progress_window['-PROGRESS-BAR-'].update(
                    30 * bytes_received // (bytes_received + 1024 * 1024))
        
        def download_estimated(percentage: int, bytes_received: int, eta_or_speed: int):
            """Update the progress text with percentage or transfer speed."""
            if cancel_download:
                return
            if percentage >= 0:
                progress_window['-PROGRESS-TEXT-'].update(
                    f"{percentage}% - {format_size(bytes_received)}")
            else:
                speed_str = self.downloader.format_download_speed(eta_or_speed)
                progress_window['-PROGRESS-TEXT-'].update(
                    f"{format_size(bytes_received)} at {speed_str}")
        
        try:
            # Download the ISO file
            success, message = self.downloader.download_file_sync(
                iso_url,
                iso_path,
                min_size=1024 * 1024,
                progress_callback=download_progress,
                progress_estimated_callback=download_estimated,
                cancel_check=lambda: cancel_download
            )
            
            if not success:
                if cancel_download:
                    raise InstallationCancelled("Cancelled by user")
                raise ValueError(f"Failed to download ISO: {message}")
            
            logger.info(f"ISO downloaded successfully: {iso_path}")
            
            # Verify checksum
            progress_window['-PROGRESS-BAR-'].update(30)
            progress_window['-PROGRESS-TEXT-'].update("Verifying ISO checksum...")
            
            checksum = self.get_distribution_checksum(
                params.get('distro'), params.get('version'),
                iso_filename=iso_filename)
            if checksum:
                if not self.downloader.verify_checksum(iso_path, checksum, "sha256"):
                    try:
                        os.remove(iso_path)
                    except OSError:
                        pass
                    raise RuntimeError(
                        f"ISO checksum verification failed for {iso_filename}")
                logger.info(f"ISO checksum verified successfully")
            else:
                logger.warning(
                    f"No checksum available for {params.get('distro')} "
                    f"{params.get('version')}, skipping verification")
            
            progress_window['-PROGRESS-BAR-'].update(35)
            
            # Extract ISO
            progress_window['-PROGRESS-TEXT-'].update("Extracting ISO...")
            
            def extract_progress(percent: int):
                """Map extraction progress onto the 35-80% bar range."""
                progress_window['-PROGRESS-BAR-'].update(35 + int(percent * 0.45))
            
            success, message = self.extractor.extract_iso_sync(
                iso_path,
                self.tmp_dir,
                progress_callback=extract_progress
            )
            if not success:
                raise RuntimeError(f"Extraction failed: {message}")
            
            logger.info("ISO extracted successfully")
            
            # Install to USB
            progress_window['-PROGRESS-TEXT-'].update("Installing to USB...")
            
            def install_progress(percent: int):
                """Map install progress onto the 80-100% bar range."""
                progress_window['-PROGRESS-BAR-'].update(80 + int(percent * 0.2))
            
            success, message = self.installer.install_sync(
                self.tmp_dir,
                params['target_drive'],
                params,
                progress_callback=install_progress
            )
            if not success:
                raise RuntimeError(f"Installation failed: {message}")
            
            progress_window['-PROGRESS-BAR-'].update(100)
            progress_window['-PROGRESS-TEXT-'].update("Installation complete!")
            self.show_completion_message()
            
        except InstallationCancelled:
            logger.info("Installation cancelled by user")
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as e:
            logger.error(f"Installation failed: {e}")
            self.show_error(f"Installation failed: {str(e)}")
        finally:
            progress_window.close()
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
                logger.info("Cancel requested")
                self.running = False
                break
            
            elif event == '-OK-':
                self.on_ok_clicked()
            
            elif event == '-REFRESH_DRIVES-':
                self.on_refresh_drive_list()
            
            elif event == '-RADIO_DISTRO-':
                self.on_install_type_changed('distribution')
            
            elif event == '-RADIO_FLOPPY-':
                self.on_install_type_changed('floppy')
            
            elif event == '-RADIO_MANUAL-':
                self.on_install_type_changed('manual')
            
            elif event == '-CATEGORY_SELECT-':
                category = values.get('-CATEGORY_SELECT-')
                self.ui.update_distro_list(category)
            
            elif event == '-DISTRO_SELECT-':
                distro_name = self.ui.get_current_distro_name()
                if distro_name:
                    self.ui.update_version_list(distro_name)
            
            elif event == '-ADVANCED_TOGGLE-':
                visible = values.get('-ADVANCED_TOGGLE-', False)
                self.ui.update_advanced_visibility(visible)
            
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

        # Hard re-check against the live device table (fails closed).
        if not is_safe_target(device):
            logger.error(f"Refusing destructive write to unsafe device: {device}")
            self.show_error(
                f"Refusing to write to {device}.\n\n"
                "Only removable USB drives can be used as a target. Internal "
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

    Delegates to unetbootin.main.main so `python -m unetbootin.app` and the
    canonical launcher share identical startup (logging, CLI parsing, etc.).
    """
    from unetbootin.main import main as _main
    _main()


if __name__ == "__main__":
    main()
