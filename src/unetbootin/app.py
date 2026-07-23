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


class UNetbootinApp(QMainWindow):
    """Main application class that coordinates all functionality."""
    
    def __init__(self, parent: Optional[QMainWindow] = None):
        """Initialize the UNetbootin application."""
        super().__init__(parent)
        logger.info("Initializing UNetbootinApp")
        
        # Application state
        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.app_loc = sys.argv[0]
        self.app_lang = QLocale.system().name()
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
        if self.platform in ['linux', 'darwin']:
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
    
    def format_drive_list(self, drives: List[Dict[str, Any]]) -> List[str]:
        """Format drive list for display in UI.
        
        Converts drive dictionaries to display strings with relevant information.
        """
        display_list = []
        
        for drive in drives:
            # Basic information
            device = drive.get('device', '')
            
            # Build display string with useful information
            parts = []
            
            # Add device name
            if device:
                parts.append(device)
            
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
            display_list.append(display_str)
        
        # Sort drives - put removable drives first, then by device name
        display_list.sort(key=lambda x: ("[Removable]" not in x, x))
        
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
            # For macOS, we use osascript for sudo
            script = f'tell application "Terminal" to do script "sudo {sys.argv[0]}"'
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
    
    def start_installation(self, params: Dict[str, Any]):
        """Start the installation process."""
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
            if params.get('install_type') == 'iso':
                # Extract ISO
                self.extractor.extract_iso(
                    params['iso_path'],
                    self.tmp_dir,
                    progress_callback=lambda p: progress_dialog.setValue(p)
                )
                
                # Install to USB
                self.installer.install(
                    self.tmp_dir,
                    params['target_drive'],
                    progress_callback=lambda p: progress_dialog.setValue(50 + p // 2)
                )
            
            progress_dialog.setValue(100)
            self.show_completion_message()
            
        except Exception as e:
            logger.error(f"Installation failed: {e}")
            self.show_error(f"Installation failed: {str(e)}")
        finally:
            progress_dialog.close()
            self.cleanup()
    
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
        from unetbootin.core.downloader import Downloader
        downloader = Downloader()
        
        if percentage >= 0:
            # We have a percentage, eta_or_speed is ETA in seconds
            eta_str = downloader.format_eta(eta_or_speed)
            logger.debug(f"Estimated download progress: {percentage}%, ETA: {eta_str}")
        else:
            # We don't have a percentage, eta_or_speed is speed in bytes/sec
            speed_str = downloader.format_download_speed(eta_or_speed)
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
