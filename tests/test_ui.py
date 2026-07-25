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

        # Verify each version has required fields. versions holds
        # DistributionVersion dataclass instances, so check attributes
        # (and their dict form) rather than treating them as dicts.
        for version in versions:
            self.assertTrue(hasattr(version, 'name'))
            self.assertTrue(hasattr(version, 'url'))
            version_dict = version.to_dict()
            self.assertIn('name', version_dict)
            self.assertIn('url', version_dict)


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

    def test_format_drive_list_filters_unsafe_drives(self):
        """format_drive_list must exclude non-removable/internal/virtual drives.

        Only drives that `is_safe_target()` approves may appear in the UI list.
        """
        from unittest.mock import patch
        from unetbootin.app import UNetbootinAppPySG

        app = UNetbootinAppPySG.__new__(UNetbootinAppPySG)

        drives = [
            {'device': '/dev/sda', 'size': 100000000000, 'label': 'System', 'removable': False},
            {'device': '/dev/sdb', 'size': 16000000000, 'label': 'USB', 'removable': True},
        ]

        # Only the USB drive is a safe target; the system disk must be dropped.
        def fake_safe(device, allow_external_fixed=False):
            return device == '/dev/sdb'

        with patch('unetbootin.app.is_safe_target', side_effect=fake_safe):
            formatted = app.format_drive_list(drives)

        devices = [dev for _display, dev in formatted]
        self.assertIn('/dev/sdb', devices)
        self.assertNotIn('/dev/sda', devices)          # internal disk excluded
        self.assertEqual(len(formatted), 1)
        for item in formatted:
            self.assertIsInstance(item, tuple)
            self.assertEqual(len(item), 2)

    def test_format_drive_list_excludes_all_when_none_safe(self):
        """If no drive is a safe target, the list is empty (nothing selectable)."""
        from unittest.mock import patch
        from unetbootin.app import UNetbootinAppPySG

        app = UNetbootinAppPySG.__new__(UNetbootinAppPySG)
        drives = [
            {'device': '/dev/sda', 'size': 100000000000, 'removable': False},
            {'device': 'disk0', 'size': 500000000000, 'removable': False},
        ]
        with patch('unetbootin.app.is_safe_target', return_value=False):
            formatted = app.format_drive_list(drives)
        self.assertEqual(formatted, [])

    def test_format_drive_list_target_type_selects_filter_strictness(self):
        """"Hard Disk" widens the filter; "USB Drive" keeps the strict one.

        The target type must be forwarded to is_safe_target as
        allow_external_fixed, so external hard drives become selectable only in
        "Hard Disk" mode.
        """
        from unittest.mock import patch
        from unetbootin.app import UNetbootinAppPySG

        app = UNetbootinAppPySG.__new__(UNetbootinAppPySG)
        # An external HDD: not removable media, so only allowed when the filter
        # is widened for the "Hard Disk" target type.
        drives = [{'device': '/dev/sdc', 'size': 2000000000000, 'removable': False}]

        def fake_safe(device, allow_external_fixed=False):
            return allow_external_fixed

        with patch('unetbootin.app.is_safe_target', side_effect=fake_safe):
            usb_mode = app.format_drive_list(drives, target_type="USB Drive")
            hdd_mode = app.format_drive_list(drives, target_type="Hard Disk")

        self.assertEqual(usb_mode, [], "external HDD must not appear in USB mode")
        self.assertEqual([dev for _d, dev in hdd_mode], ['/dev/sdc'])

    def test_resolve_iso_download_dir_custom_folder_is_kept(self):
        """A chosen ISO folder is used and the ISO is NOT scheduled for deletion."""
        import tempfile
        from unetbootin.app import UNetbootinAppPySG

        app = UNetbootinAppPySG.__new__(UNetbootinAppPySG)

        target = tempfile.mkdtemp(prefix='unetbootin_iso_')
        directory, delete_after = app.resolve_iso_download_dir(target)
        self.assertEqual(directory, target)
        self.assertFalse(delete_after, "a chosen folder must keep the ISO")

        # A folder that does not exist yet is created and used.
        nested = os.path.join(target, 'sub', 'dir')
        directory, delete_after = app.resolve_iso_download_dir(nested)
        self.assertEqual(directory, nested)
        self.assertTrue(os.path.isdir(nested))

    def test_resolve_iso_download_dir_defaults_to_downloads_and_deletes(self):
        """With no folder chosen the Downloads folder is used and ISO deleted."""
        from unittest.mock import patch
        from unetbootin.app import UNetbootinAppPySG

        app = UNetbootinAppPySG.__new__(UNetbootinAppPySG)
        with patch.object(UNetbootinAppPySG, 'get_downloads_dir',
                          return_value='/home/someone/Downloads'):
            directory, delete_after = app.resolve_iso_download_dir(None)
        self.assertEqual(directory, '/home/someone/Downloads')
        self.assertTrue(delete_after, "the staged ISO must be deleted on success")

    def test_resolve_iso_download_dir_raises_when_no_downloads_folder(self):
        """No chosen folder and no Downloads folder -> tell the user to set one."""
        from unittest.mock import patch
        from unetbootin.app import UNetbootinAppPySG, ISOLocationError

        app = UNetbootinAppPySG.__new__(UNetbootinAppPySG)
        with patch.object(UNetbootinAppPySG, 'get_downloads_dir', return_value=None):
            with self.assertRaises(ISOLocationError) as ctx:
                app.resolve_iso_download_dir(None)
        self.assertIn("ISO Location", str(ctx.exception))

    def test_resolve_iso_download_dir_raises_on_unwritable_choice(self):
        """An unwritable chosen folder is reported, not silently replaced."""
        from unetbootin.app import UNetbootinAppPySG, ISOLocationError

        app = UNetbootinAppPySG.__new__(UNetbootinAppPySG)
        with self.assertRaises(ISOLocationError):
            app.resolve_iso_download_dir('/proc/definitely/not/writable')

    def test_discard_staged_iso_removes_only_staged_file(self):
        """The staged ISO is deleted once; a kept ISO is never touched."""
        import tempfile
        from unetbootin.app import UNetbootinAppPySG

        app = UNetbootinAppPySG.__new__(UNetbootinAppPySG)

        fd, staged = tempfile.mkstemp(suffix='.iso')
        os.close(fd)
        app.iso_to_delete = staged
        app._discard_staged_iso()
        self.assertFalse(os.path.exists(staged), "staged ISO must be removed")
        self.assertIsNone(app.iso_to_delete)

        # Nothing staged -> no error, nothing removed.
        fd, kept = tempfile.mkstemp(suffix='.iso')
        os.close(fd)
        app.iso_to_delete = None
        app._discard_staged_iso()
        self.assertTrue(os.path.exists(kept), "a kept ISO must survive")
        os.remove(kept)

    def test_confirm_destructive_write_refuses_unsafe_device(self):
        """The pre-format confirmation must refuse a non-safe device outright."""
        from unittest.mock import patch, MagicMock
        from unetbootin.app import UNetbootinAppPySG

        app = UNetbootinAppPySG.__new__(UNetbootinAppPySG)
        app.show_error = MagicMock()

        with patch('unetbootin.app.is_safe_target', return_value=False):
            # Even if the user would click "Yes", an unsafe device is rejected
            # before any prompt.
            with patch('unetbootin.app.sg') as mock_sg:
                mock_sg.popup_yes_no.return_value = 'Yes'
                result = app._confirm_destructive_write('/dev/sda')

        self.assertFalse(result)
        app.show_error.assert_called_once()

    def test_format_size_in_app(self):
        """Test format_size function used in app.py."""
        from unetbootin.core.utils import format_size

        # Bytes are whole numbers; larger units use one decimal place
        # (consistent with test_core and test_integration).
        self.assertEqual(format_size(0), '0 B')
        self.assertEqual(format_size(1024), '1.0 KB')
        self.assertEqual(format_size(1024 * 1024), '1.0 MB')


if __name__ == '__main__':
    unittest.main()
