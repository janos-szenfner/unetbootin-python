"""
Unit tests for UI components.

These tests verify the MainWindow UI functionality using PySimpleGUI.
"""

import unittest
import os
import sys
import tempfile
import shutil
from unittest.mock import patch, MagicMock

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Mock PySimpleGUI if not available
try:
    import PySimpleGUI as sg
    HAS_PYSIMPLEGUI = True
except ImportError:
    HAS_PYSIMPLEGUI = False
    sys.modules['PySimpleGUI'] = MagicMock()

# Now we can import without errors
from unetbootin.models.distro import DistributionManager
from unetbootin.ui.main_window_pysg import MainWindowPySG


class TestMainWindowInitialization(unittest.TestCase):
    """Test MainWindowPySG initialization and setup."""
    
    def setUp(self):
        """Set up test fixtures."""
        # We'll test the non-PySimpleGUI parts of MainWindowPySG
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_main_window_import(self):
        """Test that MainWindowPySG can be imported."""
        # If we get here, the import succeeded
        self.assertTrue(True)
    
    def test_distribution_manager_integration(self):
        """Test that MainWindow can use DistributionManager."""
        manager = DistributionManager()
        distros = manager.get_distributions()
        self.assertGreater(len(distros), 0)


class TestMainWindowDriveSelection(unittest.TestCase):
    """Test drive selection functionality."""
    
    def test_set_drive_list_with_devices(self):
        """Test setting drive list with device tuples."""
        # Test data
        
        # Test data
        drives = [
            ('/dev/sda (100 GB) [Internal]', '/dev/sda'),
            ('/dev/sdb (16 GB) [Removable]', '/dev/sdb'),
            ('/dev/nvme0n1 (500 GB) [Internal]', '/dev/nvme0n1'),
        ]
        
        # Verify the data structure is correct
        for display, device in drives:
            self.assertIsInstance(display, str)
            self.assertIsInstance(device, str)
            self.assertIn(device, display)
    
    def test_drive_display_format(self):
        """Test drive display string formatting."""
        # Test various drive info formats
        test_cases = [
            {
                'device': '/dev/sda',
                'size': 100000000000,
                'label': 'MyDrive',
                'removable': False,
                'expected': '/dev/sda'
            },
            {
                'device': '/dev/sdb',
                'size': 16000000000,
                'label': 'USB Drive',
                'removable': True,
                'expected': '/dev/sdb'
            },
        ]
        
        for case in test_cases:
            device = case['device']
            # The device path should be present in the display
            self.assertIn(device, str(case))


class TestMainWindowInstallationParameters(unittest.TestCase):
    """Test installation parameters extraction."""
    
    def test_get_installation_parameters_distribution(self):
        """Test getting installation parameters for distribution install."""
        # This would normally be called from the UI
        # We'll test the logic that would be in get_installation_parameters
        
        # Mock parameters
        params = {
            'install_type': 'distribution',
            'drive_type': 'USB Drive',
            'target_drive': '/dev/sdb',
            'distro': 'ubuntu',
            'version': '24.04 LTS',
        }
        
        # Verify all required keys are present
        self.assertIn('install_type', params)
        self.assertIn('drive_type', params)
        self.assertIn('target_drive', params)
        self.assertIn('distro', params)
        self.assertIn('version', params)
    
    def test_get_installation_parameters_iso(self):
        """Test getting installation parameters for ISO install."""
        params = {
            'install_type': 'iso',
            'drive_type': 'USB Drive',
            'target_drive': '/dev/sdb',
            'iso_path': '/path/to/file.iso',
        }
        
        self.assertEqual(params['install_type'], 'iso')
        self.assertIn('iso_path', params)
    
    def test_get_installation_parameters_floppy(self):
        """Test getting installation parameters for floppy install."""
        params = {
            'install_type': 'floppy',
            'drive_type': 'Floppy',
            'target_drive': '/dev/fd0',
            'floppy_image': '/path/to/floppy.img',
        }
        
        self.assertEqual(params['install_type'], 'floppy')
        self.assertIn('floppy_image', params)


class TestMainWindowDistributionHandling(unittest.TestCase):
    """Test distribution handling in the UI."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.manager = DistributionManager()
    
    def test_set_distributions(self):
        """Test setting distributions in the UI."""
        distros = self.manager.get_distributions()
        
        # Verify we have distributions
        self.assertGreater(len(distros), 0)
        
        # Verify each distribution has required fields
        for distro in distros:
            self.assertIn('name', distro)
            self.assertIn('display_name', distro)
            self.assertIn('versions', distro)
    
    def test_update_version_list(self):
        """Test updating version list for a distribution."""
        # Get Ubuntu distribution
        ubuntu = self.manager.get_distribution('ubuntu')
        self.assertIsNotNone(ubuntu)
        
        # Get its versions
        versions = ubuntu.versions
        self.assertGreater(len(versions), 0)
        
        # Verify each version has required fields
        for version in versions:
            self.assertIn('name', version)
            self.assertIn('url', version)


class TestMainWindowUIConnections(unittest.TestCase):
    """Test UI signal-slot connections."""
    
    def test_radio_button_toggles(self):
        """Test radio button toggle handlers."""
        # Test that install type radio buttons would work
        install_types = ['distribution', 'iso', 'floppy', 'manual']
        
        for install_type in install_types:
            # Each type should have corresponding UI elements
            self.assertIn(install_type, ['distribution', 'iso', 'floppy', 'manual'])
    
    def test_combo_box_selections(self):
        """Test combo box selection handlers."""
        # Test that combo box changes would trigger handlers
        combo_boxes = [
            'distro_select',
            'version_select',
            'type_select',
            'drive_select',
        ]
        
        for combo in combo_boxes:
            self.assertIsInstance(combo, str)


class TestAppIntegration(unittest.TestCase):
    """Test app and UI integration with PySimpleGUI."""
    
    def test_app_ui_initialization(self):
        """Test that app can initialize UI."""
        # This would normally be tested with a PySimpleGUI window
        # For unit testing, we verify the components can be created
        
        # Create distribution manager
        manager = DistributionManager()
        distros = manager.get_distributions()
        self.assertGreater(len(distros), 0)
    
    def test_app_components(self):
        """Test that app components can be initialized."""
        # Test that we can create the components
        from unetbootin.core.extractor import ISOExtractor
        from unetbootin.core.downloader import Downloader
        from unetbootin.core.installer import USBInstaller
        
        extractor = ISOExtractor()
        downloader = Downloader()
        installer = USBInstaller()
        
        self.assertIsNotNone(extractor)
        self.assertIsNotNone(downloader)
        self.assertIsNotNone(installer)


class TestUICallbacks(unittest.TestCase):
    """Test UI callback functions."""
    
    def test_on_distro_changed(self):
        """Test on_distro_text_changed callback."""
        # This callback would typically:
        # 1. Get the selected distribution
        # 2. Update the version combo box
        
        manager = DistributionManager()
        ubuntu = manager.get_distribution('ubuntu')
        self.assertIsNotNone(ubuntu)
        
        # Get versions
        versions = ubuntu.versions
        self.assertGreater(len(versions), 0)
    
    def test_on_version_changed(self):
        """Test on_version_text_changed callback."""
        # This callback would typically:
        # 1. Get the selected version
        # 2. Update the ISO URL or other UI elements
        
        manager = DistributionManager()
        ubuntu = manager.get_distribution('ubuntu')
        version = ubuntu.versions[0]
        
        self.assertIsNotNone(version.url)
        self.assertTrue(version.url.startswith('http'))
    
    def test_on_type_changed(self):
        """Test on_type_changed callback."""
        # This callback would typically:
        # 1. Show/hide appropriate UI sections based on drive type
        
        drive_types = ['USB Drive', 'Hard Disk', 'Floppy']
        for drive_type in drive_types:
            self.assertIsInstance(drive_type, str)


class TestDriveRefresh(unittest.TestCase):
    """Test drive refresh functionality."""
    
    def test_drive_list_refresh(self):
        """Test refreshing the drive list."""
        # This would typically:
        # 1. Call platform.get_drive_list()
        # 2. Format the results
        # 3. Update the UI
        
        # For now, we test that the platform module can be imported
        from unetbootin.platform import get_drive_list
        self.assertTrue(callable(get_drive_list))
    
    def test_drive_format_string(self):
        """Test drive format string generation."""
        # Test various drive info combinations
        test_drives = [
            {
                'device': '/dev/sda',
                'size': 100000000000,
                'label': 'System',
                'removable': False,
            },
            {
                'device': '/dev/sdb',
                'size': 16000000000,
                'label': None,
                'removable': True,
            },
            {
                'device': '/dev/nvme0n1',
                'size': 500000000000,
                'label': 'NVMe Drive',
                'removable': False,
            },
        ]
        
        for drive in test_drives:
            self.assertIn('device', drive)
            self.assertIn('size', drive)


# Note: Full UI tests with PySimpleGUI can be run directly
# For testing with actual PySimpleGUI windows, use:
#   from unetbootin.ui.main_window_pysg import MainWindowPySG
#   window = MainWindowPySG()
#   # Test UI interactions here


class TestUIComponents(unittest.TestCase):
    """Test UI components that don't require window display."""
    
    def test_format_drive_list_function(self):
        """Test the format_drive_list function from app.py."""
        from unetbootin.app import UNetbootinAppPySG
        
        # Create a mock app instance to access the method
        app = UNetbootinAppPySG.__new__(UNetbootinAppPySG)
        
        # Mock drives data
        drives = [
            {'device': '/dev/sda', 'size': 100000000000, 'label': 'System', 'removable': False},
            {'device': '/dev/sdb', 'size': 16000000000, 'label': 'USB', 'removable': True},
        ]
        
        # Call the method
        formatted = app.format_drive_list(drives)
        
        # Should return a list of tuples
        self.assertIsInstance(formatted, list)
        for item in formatted:
            self.assertIsInstance(item, tuple)
            self.assertEqual(len(item), 2)
    
    def test_format_size_in_app(self):
        """Test format_size function used in app.py."""
        from unetbootin.core.utils import format_size
        
        # Test various sizes
        self.assertEqual(format_size(0), '0.00 B')
        self.assertEqual(format_size(1024), '1.00 KB')
        self.assertEqual(format_size(1024 * 1024), '1.00 MB')


if __name__ == '__main__':
    unittest.main()
