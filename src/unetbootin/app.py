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
from typing import Optional, List, Dict, Any, Tuple

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
from unetbootin.core.downloader import Downloader, AsyncDownloader, DownloadResumeManager
from unetbootin.core.installer import USBInstaller
from unetbootin.core.utils import (
    check_root, check_admin, get_platform_info,
    format_size, normalize_language_code
)
from unetbootin.platform import get_drive_list

logger = logging.getLogger(__name__)


class InstallationCancelled(Exception):
    """Raised when the user cancels the installation."""
    pass


class UNetbootinAppPySG:
    """Main application class that coordinates all functionality using PySimpleGUI."""
    
    def __init__(self, parent=None, cli_args: Optional[Dict[str, Any]] = None):
        """Initialize the UNetbootin application."""
        if not HAS_PYSIMPLEGUI:
            raise ImportError("PySimpleGUI is required. Please install it with: pip install PySimpleGUI")
        
        logger.info("Initializing UNetbootinApp with PySimpleGUI")
        
        # Application state
        self.cli_args = cli_args or {}
        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.app_loc = sys.argv[0]
        # Normalize language code
        self.app_lang = normalize_language_code(self.cli_args.get('lang')) or normalize_language_code('en')
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
        rootcheck = str(self.cli_args.get('rootcheck', True)).lower() not in ('no', 'false', '0')
        if rootcheck and self.platform in ['linux', 'darwin']:
            self.check_privileges()
    
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
            return self.ui.set_drive_list(drive_display_list)
        except Exception as e:
            logger.error(f"Failed to load drive list: {e}")
            self.show_error("Failed to load drive list")
            return False
    
    def format_drive_list(self, drives: List[Dict[str, Any]]) -> List[tuple]:
        """Format drive list for display in UI."""
        display_list = []
        
        for drive in drives:
            device = drive.get('device', '')
            if not device:
                continue
            
            parts = [device]
            
            size = drive.get('size')
            if size:
                try:
                    size_str = format_size(size)
                    parts.append(f"({size_str})")
                except Exception:
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
        sg.popup_error(
            f"{APP_NAME} must be run as root.\n\n"
            f"Run it from the command line using:\n"
            f"sudo {sys.argv[0]}",
            title="Must run as root"
        )
        sys.exit(1)
    
    def show_admin_warning(self):
        """Show warning that admin privileges are required on macOS."""
        result = sg.popup_yes_no(
            f"{APP_NAME} requires administrator privileges to install bootloaders. "
            "Please run using sudo or with administrator rights.\n\n"
            "Would you like to try running with sudo?",
            title="Administrator privileges required"
        )
        if result == 'Yes':
            self.relaunch_with_sudo()
        else:
            sys.exit(1)
    
    def relaunch_with_sudo(self):
        """Re-launch the application with sudo on macOS."""
        logger.info("Attempting to re-launch with sudo")
        try:
            import shlex
            quoted = shlex.quote(sys.argv[0])
            script = f'tell application "Terminal" to do script "sudo {quoted}"'
            subprocess.run(['osascript', '-e', script], check=True)
            sys.exit(0)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to re-launch with sudo: {e}")
            self.show_error("Failed to elevate privileges")
    
    def get_installation_parameters(self) -> Dict[str, Any]:
        """Get installation parameters from UI."""
        return self.ui.get_installation_parameters()
    
    def validate_parameters(self, params: Dict[str, Any]) -> bool:
        """Validate installation parameters."""
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
        self.tmp_dir = tempfile.mkdtemp(prefix='unetbootin_')
        logger.info(f"Created temporary directory: {self.tmp_dir}")
    
    def cleanup(self):
        """Clean up temporary files."""
        if self.tmp_dir and os.path.exists(self.tmp_dir):
            try:
                shutil.rmtree(self.tmp_dir)
                logger.info(f"Cleaned up temporary directory: {self.tmp_dir}")
            except Exception as e:
                logger.error(f"Failed to clean up temporary directory: {e}")
        self.tmp_dir = None
    
    def show_error(self, message: str):
        """Show error message to user."""
        logger.error(f"Showing error to user: {message}")
        sg.popup_error(message, title="Error")
    
    def show_info(self, message: str, title: str = "Information"):
        """Show information message to user."""
        sg.popup_ok(message, title=title)
    
    def show_completion_message(self, message: str = None):
        """Show installation completion message."""
        if message is None:
            message = f"{APP_NAME} has completed successfully!"
        sg.popup_ok(message, title="Installation Complete")
        
        if self.exit_on_completion:
            self.stop()
    
    def get_distribution_checksum(self, distro_name: str, version_name: str) -> Optional[str]:
        """Get the checksum for a specific distribution and version."""
        distro = self.distro_manager.get_distribution(distro_name)
        if not distro:
            logger.error(f"Distribution not found: {distro_name}")
            return None
        
        for version in distro.versions:
            if version.name == version_name:
                return version.get_checksum("sha256")
        
        return None
    
    def get_distribution_iso_url(self, distro_name: str, version_name: str) -> Optional[str]:
        """Get the ISO URL for a specific distribution and version."""
        distro = self.distro_manager.get_distribution(distro_name)
        if not distro:
            logger.error(f"Distribution not found: {distro_name}")
            return None
        
        for version in distro.versions:
            if version.name == version_name:
                if version.url:
                    logger.info(f"Found ISO URL for {distro_name} {version_name}: {version.url}")
                    return version.url
                else:
                    logger.error(f"Version {version_name} has no URL")
                    return None
        
        if distro.versions:
            logger.warning(f"Version {version_name} not found, using first available version")
            return distro.versions[0].url
        
        logger.error(f"No versions available for distribution {distro_name}")
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
                [sg.ProgressBar(100, orientation='h', size=(40, 20), key='-PROGRESS-BAR-')],
                [sg.Button('Cancel', key='-CANCEL-INSTALL-')]
            ]
            progress_window = sg.Window('Installation in Progress', progress_layout, finalize=True)
            
            try:
                # Extract image
                progress_text = progress_window['-PROGRESS-BAR-']
                
                def extract_progress(percent: int):
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
                    progress_window.write_event_value('-PROGRESS-', 50 + int(percent * 0.5))
                
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
            except Exception as e:
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
        logger.info(f"Downloading distribution: {params.get('distro')}, version: {params.get('version')}")
        
        # Get the ISO URL
        iso_url = self.get_distribution_iso_url(params.get('distro'), params.get('version'))
        if not iso_url:
            raise ValueError(f"Could not find ISO URL for distribution {params.get('distro')} version {params.get('version')}")
        
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
        progress_window = sg.Window('Download in Progress', progress_layout, finalize=True)
        
        cancel_download = False
        
        def download_progress(bytes_received: int, bytes_total: int):
            if cancel_download:
                return
            if bytes_total > 0:
                percent = min(int((bytes_received / bytes_total) * 30), 30)
                progress_window['-PROGRESS-BAR-'].update(percent)
            else:
                # No total size known
                progress_window['-PROGRESS-BAR-'].update(30 * bytes_received // (bytes_received + 1024 * 1024))
        
        def download_estimated(percentage: int, bytes_received: int, eta_or_speed: int):
            if cancel_download:
                return
            if percentage >= 0:
                progress_window['-PROGRESS-TEXT-'].update(f"{percentage}% - {format_size(bytes_received)}")
            else:
                speed_str = self.downloader.format_download_speed(eta_or_speed)
                progress_window['-PROGRESS-TEXT-'].update(f"{format_size(bytes_received)} at {speed_str}")
        
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
            
            checksum = self.get_distribution_checksum(params.get('distro'), params.get('version'))
            if checksum:
                if not self.downloader.verify_checksum(iso_path, checksum, "sha256"):
                    try:
                        os.remove(iso_path)
                    except Exception:
                        pass
                    raise RuntimeError(f"ISO checksum verification failed for {iso_filename}")
                logger.info(f"ISO checksum verified successfully")
            else:
                logger.warning(f"No checksum available for {params.get('distro')} {params.get('version')}, skipping verification")
            
            progress_window['-PROGRESS-BAR-'].update(35)
            
            # Extract ISO
            progress_window['-PROGRESS-TEXT-'].update("Extracting ISO...")
            
            def extract_progress(percent: int):
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
        except Exception as e:
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
                    file_types=(("All files", "*.*"), ("ISO files", "*.iso"), ("IMG files", "*.img"))
                )
                if file_path:
                    self.ui.elements['floppy_file'].update(file_path)
            
            elif event == '-KERNEL_BROWSE-':
                file_path = sg.popup_get_file("Select Kernel File", default_path="", file_types=(("All files", "*.*"),))
                if file_path:
                    self.ui.elements['kernel_file'].update(file_path)
            
            elif event == '-INITRD_BROWSE-':
                file_path = sg.popup_get_file("Select Initrd File", default_path="", file_types=(("All files", "*.*"),))
                if file_path:
                    self.ui.elements['initrd_file'].update(file_path)
            
            elif event == '-CFG_BROWSE-':
                file_path = sg.popup_get_file("Select Config File", default_path="", file_types=(("All files", "*.*"), ("CFG files", "*.cfg")))
                if file_path:
                    self.ui.elements['cfg_file'].update(file_path)
            
            # Handle progress events
            elif event == '-PROGRESS-':
                # This is handled internally
                pass
        
        self.cleanup()
    
    def on_ok_clicked(self):
        """Handle OK button click - start the installation process."""
        logger.info("OK button clicked - starting installation")
        
        try:
            params = self.get_installation_parameters()
            logger.info(f"Installation parameters: {params}")
            
            if not self.validate_parameters(params):
                return
            
            self.create_temp_directory()
            self.start_installation(params)
            
        except Exception as e:
            logger.error(f"Error in installation process: {e}")
            self.show_error(f"Installation error: {str(e)}")
    
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
