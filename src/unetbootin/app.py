"""
Main application class for UNetbootin.
"""

import os
import sys
import platform
import subprocess
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QMainWindow, QMessageBox, QFileDialog,
    QProgressDialog, QApplication
)
from PySide6.QtCore import (
    Qt, QThread, Signal, Slot, QObject,
    QProcess, QUrl, QSettings, QLocale
)
from PySide6.QtGui import QIcon

from unetbootin import APP_NAME, APP_VERSION
from unetbootin.ui.main_window import MainWindow
from unetbootin.models.distro import DistributionManager
from unetbootin.core.extractor import ISOExtractor
from unetbootin.core.downloader import Downloader
from unetbootin.core.installer import USBInstaller
from unetbootin.core.utils import (
    check_root, check_admin, get_platform_info,
    format_size, parse_command_line_args
)
from unetbootin.platform import get_drive_list

logger = logging.getLogger(__name__)


class InstallationCancelled(Exception):
    """Raised when the user cancels the installation via the progress dialog."""
    pass


class UNetbootinApp(QMainWindow):
    """Main application class that coordinates all functionality."""
    
    def __init__(self, parent: Optional[QMainWindow] = None,
                 cli_args: Optional[Dict[str, Any]] = None):
        """Initialize the UNetbootin application."""
        super().__init__(parent)
        logger.info("Initializing UNetbootinApp")

        # Application state
        self.cli_args = cli_args or {}
        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.app_loc = sys.argv[0]
        self.app_lang = self.cli_args.get('lang') or QLocale.system().name()
        self.tmp_dir = None
        self.exit_on_completion = False
        self.testing_download = False
        
        # Platform-specific setup
        self.platform = platform.system().lower()
        self.setup_platform()
        
        # Initialize components
        self.distro_manager = DistributionManager()
        self.extractor = ISOExtractor()
        self.downloader = Downloader()
        self.installer = USBInstaller()
        
        # Initialize UI
        self.init_ui()
        self.setup_connections()
        
        # Check for root/admin privileges on Unix systems
        # (skippable via --rootcheck=no, as documented in the README)
        rootcheck = str(self.cli_args.get('rootcheck', True)).lower() not in ('no', 'false', '0')
        if rootcheck and self.platform in ['linux', 'darwin']:
            self.check_privileges()
    
    def setup_platform(self):
        """Setup platform-specific configurations."""
        self.platform_info = get_platform_info()
        logger.info(f"Platform: {self.platform}, Info: {self.platform_info}")
    
    def init_ui(self):
        """Initialize the user interface."""
        logger.info("Initializing UI")
        self.ui = MainWindow(self)
        self.setCentralWidget(self.ui)
        
        # Set window properties
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(524, 360)
        self.resize(524, 360)
        
        # Load distribution list
        self.load_distributions()
        
        # Load drive list
        self.load_drive_list()
    
    def setup_connections(self):
        """Setup signal-slot connections."""
        logger.info("Setting up signal-slot connections")
        
        # Connect UI signals
        self.ui.distro_selected.connect(self.on_distro_selected)
        self.ui.version_selected.connect(self.on_version_selected)
        self.ui.install_type_changed.connect(self.on_install_type_changed)
        self.ui.ok_button_clicked.connect(self.on_ok_clicked)
        self.ui.cancel_button_clicked.connect(self.on_cancel_clicked)
        self.ui.exit_button_clicked.connect(self.on_exit_clicked)
        
        # Connect downloader progress
        self.downloader.progress_updated.connect(self.on_download_progress)
        self.downloader.progress_estimated.connect(self.on_download_progress_estimated)
        self.downloader.download_failed.connect(self.on_download_failed)
        
        # Connect extractor progress
        self.extractor.progress_updated.connect(self.on_extraction_progress)
        
        # Connect installer progress
        self.installer.progress_updated.connect(self.on_install_progress)
        self.installer.installation_complete.connect(self.on_installation_complete)
        
        # Connect drive refresh
        self.ui.refresh_drive_list.connect(self.on_refresh_drive_list)
    
    def load_distributions(self):
        """Load the list of supported distributions."""
        logger.info("Loading distributions")
        try:
            distros = self.distro_manager.get_distributions()
            self.ui.set_distributions(distros)
        except Exception as e:
            logger.error(f"Failed to load distributions: {e}")
            self.show_error("Failed to load distribution list")
    
    def load_drive_list(self):
        """Load the list of available drives."""
        logger.info("Loading drive list")
        try:
            drives = get_drive_list()
            drive_display_list = self.format_drive_list(drives)
            self.ui.set_drive_list(drive_display_list)
            return True
        except Exception as e:
            logger.error(f"Failed to load drive list: {e}")
            self.show_error("Failed to load drive list")
            return False
    
    def format_drive_list(self, drives: List[Dict[str, Any]]) -> List[tuple]:
        """Format drive list for display in UI.

        Converts drive dictionaries to (display_string, device_path) tuples so
        the UI can show a friendly label while keeping the real device path.
        """
        display_list = []

        for drive in drives:
            # Basic information
            device = drive.get('device', '')
            if not device:
                continue

            # Build display string with useful information
            parts = [device]
            
            # Add size if available
            size = drive.get('size')
            if size:
                try:
                    size_str = format_size(size)
                    parts.append(f"({size_str})")
                except Exception:
                    pass
            
            # Add label if available
            label = drive.get('label', '')
            if label:
                parts.append(f"'{label}'")
            
            # Add removable indicator
            if drive.get('removable', False):
                parts.append("[Removable]")
            
            # Add filesystem type if available
            filesystem = drive.get('filesystem', '')
            if filesystem:
                parts.append(f"({filesystem})")
            
            display_str = " ".join(parts)
            display_list.append((display_str, device))

        # Sort drives - put removable drives first, then by device name
        display_list.sort(key=lambda x: ("[Removable]" not in x[0], x[0]))

        return display_list
    
    def check_privileges(self):
        """Check if running with sufficient privileges."""
        if self.platform == 'linux':
            if not check_root():
                logger.warning("Not running as root on Linux")
                self.show_root_warning()
        elif self.platform == 'darwin':
            if not check_admin():
                logger.warning("Not running as admin on macOS")
                self.show_admin_warning()
    
    def show_root_warning(self):
        """Show warning that root privileges are required."""
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("Must run as root")
        msg_box.setText(
            f"{APP_NAME} must be run as root. "
            f"Run it from the command line using:<br/>"
            f"<b>sudo QT_X11_NO_MITSHM=1 {sys.argv[0]}</b>"
        )
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec()
        sys.exit(1)
    
    def show_admin_warning(self):
        """Show warning that admin privileges are required on macOS."""
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("Administrator privileges required")
        msg_box.setText(
            f"{APP_NAME} requires administrator privileges to install "
            f"bootloaders. Please run using sudo or with administrator rights."
        )
        msg_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        result = msg_box.exec()
        if result == QMessageBox.Ok:
            # Try to re-launch with sudo
            self.relaunch_with_sudo()
        else:
            sys.exit(1)
    
    def relaunch_with_sudo(self):
        """Re-launch the application with sudo on macOS."""
        logger.info("Attempting to re-launch with sudo")
        try:
            # For macOS, we use osascript for sudo. Quote the executable path
            # so paths with spaces/quotes cannot break out of the command.
            import shlex
            quoted = shlex.quote(sys.argv[0])
            script = f'tell application "Terminal" to do script "sudo {quoted}"'
            subprocess.run(['osascript', '-e', script], check=True)
            sys.exit(0)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to re-launch with sudo: {e}")
            self.show_error("Failed to elevate privileges")
    
    def on_distro_selected(self, distro_name: str):
        """Handle distribution selection."""
        logger.info(f"Distribution selected: {distro_name}")
        self.ui.update_version_list(distro_name)
    
    def on_version_selected(self, version: str):
        """Handle version selection."""
        logger.info(f"Version selected: {version}")
        # Update UI with version-specific info
        pass
    
    def on_install_type_changed(self, install_type: str):
        """Handle installation type change."""
        logger.info(f"Installation type changed to: {install_type}")
        self.ui.update_install_type(install_type)
    
    def on_ok_clicked(self):
        """Handle OK button click - start the installation process."""
        logger.info("OK button clicked - starting installation")
        
        try:
            # Get parameters from UI
            params = self.ui.get_installation_parameters()
            logger.info(f"Installation parameters: {params}")
            
            # Validate parameters
            if not self.validate_parameters(params):
                return
            
            # Create temporary directory
            self.create_temp_directory()
            
            # Start installation process
            self.start_installation(params)
            
        except Exception as e:
            logger.error(f"Error in installation process: {e}")
            self.show_error(f"Installation error: {str(e)}")
    
    def validate_parameters(self, params: Dict[str, Any]) -> bool:
        """Validate installation parameters."""
        # Basic validation
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
    
    def create_temp_directory(self):
        """Create a temporary directory for extraction."""
        import tempfile
        self.tmp_dir = tempfile.mkdtemp(prefix='unetbootin_')
        logger.info(f"Created temporary directory: {self.tmp_dir}")
    
    def _update_progress(self, progress_dialog, value: int):
        """Update the progress dialog, keep the UI responsive, honor Cancel."""
        progress_dialog.setValue(value)
        QApplication.processEvents()
        if progress_dialog.wasCanceled():
            raise InstallationCancelled("Cancelled by user")

    def start_installation(self, params: Dict[str, Any]):
        """Start the installation process.

        Runs the pipeline stages synchronously (download -> extract -> install)
        so each stage only starts after the previous one succeeded, failures
        are reported honestly, and cleanup happens after all work is done.
        """
        logger.info("Starting installation process")

        # Show progress dialog
        progress_dialog = QProgressDialog(
            "Installing...",
            "Cancel",
            0,
            100,
            self
        )
        progress_dialog.setWindowTitle("Installation in Progress")
        progress_dialog.setModal(True)
        progress_dialog.show()

        try:
            install_type = params.get('install_type')

            if install_type in ('iso', 'floppy'):
                source_image = params.get('iso_path') or params.get('floppy_image')

                # Extract image (0-50%)
                progress_dialog.setLabelText("Extracting image...")
                success, message = self.extractor.extract_iso_sync(
                    source_image,
                    self.tmp_dir,
                    progress_callback=lambda p: self._update_progress(progress_dialog, int(p * 0.5))
                )
                if not success:
                    raise RuntimeError(f"Extraction failed: {message}")

                # Install to USB (50-100%)
                progress_dialog.setLabelText("Installing to drive...")
                success, message = self.installer.install_sync(
                    self.tmp_dir,
                    params['target_drive'],
                    params,
                    progress_callback=lambda p: self._update_progress(progress_dialog, 50 + int(p * 0.5))
                )
                if not success:
                    raise RuntimeError(f"Installation failed: {message}")

            elif install_type == 'distribution':
                # Download ISO from distribution URL, then extract and install
                self.download_and_install_distribution(params, progress_dialog)
            else:
                raise RuntimeError(f"Unsupported install type: {install_type}")

            progress_dialog.setValue(100)
            self.show_completion_message()

        except InstallationCancelled:
            logger.info("Installation cancelled by user")
        except Exception as e:
            logger.error(f"Installation failed: {e}")
            self.show_error(f"Installation failed: {str(e)}")
        finally:
            progress_dialog.close()
            self.cleanup()
    
    def download_and_install_distribution(self, params: Dict[str, Any], progress_dialog):
        """Download ISO from distribution URL and install.
        
        Args:
            params: Installation parameters
            progress_dialog: Progress dialog to update
        """
        logger.info(f"Downloading distribution: {params.get('distro')}, version: {params.get('version')}")
        
        # Get the ISO URL for the selected distribution and version
        iso_url = self.get_distribution_iso_url(params.get('distro'), params.get('version'))
        if not iso_url:
            raise ValueError(f"Could not find ISO URL for distribution {params.get('distro')} version {params.get('version')}")
        
        # Determine the ISO filename from the URL
        import os
        iso_filename = os.path.basename(iso_url)
        iso_path = os.path.join(self.tmp_dir, iso_filename)
        
        logger.info(f"Downloading ISO from {iso_url} to {iso_path}")
        progress_dialog.setLabelText(f"Downloading {iso_filename}...")
        
        # Download the ISO file
        def download_progress_callback(bytes_received: int, bytes_total: int):
            """Update progress for download phase (0-30%)."""
            if bytes_total > 0:
                download_percent = int((bytes_received / bytes_total) * 30)
            else:
                # No total size known, show indeterminate progress
                download_percent = int(30 * bytes_received / (bytes_received + 1024 * 1024))
            progress_dialog.setValue(download_percent)
            QApplication.processEvents()  # keep dialog responsive; cancel handled via cancel_check

        def download_estimated_callback(percentage: int, bytes_received: int, eta_or_speed: int):
            """Handle estimated progress updates."""
            if percentage >= 0:
                # We have percentage, show it in the label
                progress_dialog.setLabelText(f"Downloading {iso_filename}... {percentage}% ({format_size(bytes_received)})")
            else:
                # Show speed
                speed_str = self.downloader.format_download_speed(eta_or_speed)
                progress_dialog.setLabelText(f"Downloading {iso_filename}... {format_size(bytes_received)} at {speed_str}")

        # Perform the download
        success, message = self.downloader.download_file_sync(
            iso_url,
            iso_path,
            min_size=1024 * 1024,  # At least 1MB
            progress_callback=download_progress_callback,
            progress_estimated_callback=download_estimated_callback,
            cancel_check=progress_dialog.wasCanceled
        )

        if not success:
            if progress_dialog.wasCanceled():
                raise InstallationCancelled("Cancelled by user")
            raise ValueError(f"Failed to download ISO: {message}")

        logger.info(f"ISO downloaded successfully: {iso_path}")

        # Extract ISO (30-80%)
        progress_dialog.setLabelText("Extracting ISO...")
        success, message = self.extractor.extract_iso_sync(
            iso_path,
            self.tmp_dir,
            progress_callback=lambda p: self._update_progress(progress_dialog, 30 + int(p * 0.5))
        )
        if not success:
            raise RuntimeError(f"Extraction failed: {message}")

        logger.info("ISO extracted successfully")

        # Install to USB (80-100%)
        progress_dialog.setLabelText("Installing to USB...")
        success, message = self.installer.install_sync(
            self.tmp_dir,
            params['target_drive'],
            params,
            progress_callback=lambda p: self._update_progress(progress_dialog, 80 + int(p * 0.2))
        )
        if not success:
            raise RuntimeError(f"Installation failed: {message}")
    
    def get_distribution_iso_url(self, distro_name: str, version_name: str) -> Optional[str]:
        """Get the ISO URL for a specific distribution and version.
        
        Args:
            distro_name: Name of the distribution
            version_name: Name of the version
            
        Returns:
            URL string or None if not found
        """
        distro = self.distro_manager.get_distribution(distro_name)
        if not distro:
            logger.error(f"Distribution not found: {distro_name}")
            return None
        
        # Find the version with matching name
        for version in distro.versions:
            if version.name == version_name:
                if version.url:
                    logger.info(f"Found ISO URL for {distro_name} {version_name}: {version.url}")
                    return version.url
                else:
                    logger.error(f"Version {version_name} has no URL")
                    return None
        
        # If version not found by name, try to find by pattern
        if distro.versions:
            # Return the first version's URL as fallback
            logger.warning(f"Version {version_name} not found, using first available version")
            return distro.versions[0].url
        
        logger.error(f"No versions available for distribution {distro_name}")
        return None
    
    def on_cancel_clicked(self):
        """Handle cancel button click."""
        logger.info("Cancel button clicked")
        self.close()
    
    def on_exit_clicked(self):
        """Handle exit button click."""
        logger.info("Exit button clicked")
        self.close()
    
    def on_refresh_drive_list(self):
        """Handle refresh drive list request."""
        logger.info("Refreshing drive list")
        self.load_drive_list()
    
    def on_download_progress(self, bytes_received: int, bytes_total: int):
        """Handle download progress updates."""
        progress = int((bytes_received / bytes_total) * 100) if bytes_total > 0 else 0
        logger.debug(f"Download progress: {progress}%")
    
    def on_download_progress_estimated(self, percentage: int, bytes_received: int, 
                                        eta_or_speed: int):
        """Handle download progress estimation updates.
        
        Args:
            percentage: Completion percentage (-1 if unknown)
            bytes_received: Number of bytes downloaded so far
            eta_or_speed: ETA in seconds (if percentage >= 0) or speed in bytes/sec (if percentage < 0)
        """
        if percentage >= 0:
            # We have a percentage, eta_or_speed is ETA in seconds
            eta_str = self.downloader.format_eta(eta_or_speed)
            logger.debug(f"Estimated download progress: {percentage}%, ETA: {eta_str}")
        else:
            # We don't have a percentage, eta_or_speed is speed in bytes/sec
            speed_str = self.downloader.format_download_speed(eta_or_speed)
            logger.debug(f"Download progress: {bytes_received} bytes, Speed: {speed_str}")
    
    def on_extraction_progress(self, percent: int):
        """Handle extraction progress updates."""
        logger.debug(f"Extraction progress: {percent}%")
    
    def on_install_progress(self, percent: int):
        """Handle installation progress updates."""
        logger.debug(f"Installation progress: {percent}%")
    
    def on_download_failed(self, url: str, error: str):
        """Handle download failure."""
        logger.error(f"Download failed for {url}: {error}")
        self.show_error(f"Download failed: {error}")
    
    def on_installation_complete(self, success: bool, message: str):
        """Handle installation completion."""
        if success:
            logger.info("Installation completed successfully")
            self.show_completion_message(message)
        else:
            logger.error(f"Installation failed: {message}")
            self.show_error(message)
    
    def show_completion_message(self, message: str = None):
        """Show installation completion message."""
        if message is None:
            message = f"{APP_NAME} has completed successfully!"
        
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Information)
        msg_box.setWindowTitle("Installation Complete")
        msg_box.setText(message)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec()
        
        if self.exit_on_completion:
            self.close()
    
    def show_error(self, message: str):
        """Show error message to user."""
        logger.error(f"Showing error to user: {message}")
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setWindowTitle("Error")
        msg_box.setText(message)
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec()
    
    def cleanup(self):
        """Clean up temporary files."""
        import shutil
        if self.tmp_dir and os.path.exists(self.tmp_dir):
            try:
                shutil.rmtree(self.tmp_dir)
                logger.info(f"Cleaned up temporary directory: {self.tmp_dir}")
            except Exception as e:
                logger.error(f"Failed to clean up temporary directory: {e}")
        self.tmp_dir = None
    
    def closeEvent(self, event):
        """Handle close event."""
        logger.info("Application closing")
        self.cleanup()
        event.accept()
