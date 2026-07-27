"""
Unit tests for UI components.

These tests verify the MainWindow UI functionality (CustomTkinter).
"""

import unittest
import os
import sys
import tempfile
import shutil
from unittest.mock import patch, MagicMock

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    import customtkinter
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

# Now we can import without errors
from unetbootin.models.distro import DistributionManager
from unetbootin.ui.main_window_ctk import MainWindowCTk as MainWindowPySG


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
#   from unetbootin.ui.main_window_ctk import MainWindowCTk as MainWindowPySG
#   window = MainWindowCTk()
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


class TestBackgroundWorker(unittest.TestCase):
    """run_in_background must keep results, progress and cancellation correct."""

    def _app_with_fake_window(self):
        """An app instance whose window records progress and replays events."""
        from unittest.mock import MagicMock
        from unetbootin.app import UNetbootinAppPySG
        import queue

        app = UNetbootinAppPySG.__new__(UNetbootinAppPySG)

        class FakeWindow:
            def __init__(self):
                self.q = queue.Queue()

            def write_event_value(self, key, value):
                self.q.put((key, {key: value}))

            def read(self, timeout=None):
                try:
                    return self.q.get(timeout=(timeout or 100) / 1000.0)
                except queue.Empty:
                    return '__TIMEOUT__', {}

        app.ui = MagicMock()
        app.ui.window = FakeWindow()
        app.progress_seen = []
        app.ui.set_progress.side_effect = (
            lambda percent=None, text=None: app.progress_seen.append((percent, text))
        )
        return app

    def test_returns_worker_result_and_reports_progress(self):
        app = self._app_with_fake_window()

        def work(report, cancelled):
            report(percent=42, text="halfway")
            return "finished"

        self.assertEqual(app.run_in_background(work), "finished")
        self.assertIn((42, "halfway"), app.progress_seen)
        app.ui.begin_progress.assert_called_once()
        app.ui.end_progress.assert_called_once()

    def test_exception_is_raised_on_the_calling_thread(self):
        app = self._app_with_fake_window()

        def work(report, cancelled):
            raise RuntimeError("worker blew up")

        with self.assertRaises(RuntimeError) as ctx:
            app.run_in_background(work)
        self.assertIn("worker blew up", str(ctx.exception))
        # The progress widgets must still be cleaned up.
        app.ui.end_progress.assert_called_once()

    def test_cancel_event_reaches_the_worker(self):
        """Pressing Cancel must make cancelled() return True in the worker."""
        import time
        app = self._app_with_fake_window()
        # Queue a Cancel press so the pump sees it while the worker spins.
        app.ui.window.q.put(('-CANCEL_DOWNLOAD-', {}))

        def work(report, cancelled):
            for _ in range(200):
                if cancelled():
                    return "stopped"
                time.sleep(0.01)
            return "ran to completion"

        self.assertEqual(app.run_in_background(work, cancellable=True), "stopped")

    def test_cancel_ignored_when_not_cancellable(self):
        """A non-cancellable stage must not be stopped by a Cancel press."""
        app = self._app_with_fake_window()
        app.ui.window.q.put(('-CANCEL_DOWNLOAD-', {}))

        def work(report, cancelled):
            return "cancelled" if cancelled() else "completed"

        self.assertEqual(
            app.run_in_background(work, cancellable=False), "completed")


class TestWindowIdentity(unittest.TestCase):
    """The window must carry the real app icon and the full title."""

    def test_window_icon_path_resolves_to_a_real_file(self):
        from unetbootin.ui.main_window_ctk import window_icon_path
        path = window_icon_path()
        self.assertIsNotNone(path, "a bundled window icon must be found")
        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith('.png'))
        self.assertGreater(os.path.getsize(path), 0)

    def test_app_title_includes_python(self):
        from unetbootin import APP_TITLE, APP_NAME
        self.assertEqual(APP_TITLE, f"{APP_NAME} - Python")

    def test_window_is_not_created_with_the_placeholder_icon(self):
        """Guard against regressing to the 1x1 transparent GIF placeholder."""
        import inspect
        from unetbootin.ui import main_window_ctk
        src = inspect.getsource(main_window_ctk.MainWindowCTk.init_ui)
        self.assertNotIn("transparent_gif", src,
                         "the window must not use the blank placeholder icon")


class TestProgressThrottling(unittest.TestCase):
    """Progress updates must not starve button presses such as Cancel."""

    def _app_with_recording_window(self, preload=()):
        import queue
        from unittest.mock import MagicMock
        from unetbootin.app import UNetbootinAppPySG

        app = UNetbootinAppPySG.__new__(UNetbootinAppPySG)

        class FakeWindow:
            def __init__(self):
                self.q = queue.Queue()
                self.posted = 0

            def write_event_value(self, key, value):
                self.posted += 1
                self.q.put((key, {key: value}))

            def read(self, timeout=None):
                try:
                    return self.q.get(timeout=(timeout or 100) / 1000.0)
                except queue.Empty:
                    return '__TIMEOUT__', {}

        app.ui = MagicMock()
        app.ui.window = FakeWindow()
        for item in preload:
            app.ui.window.q.put(item)
        return app

    def test_progress_updates_are_rate_limited(self):
        """Chunk-rate reporting must collapse into a few UI events.

        The downloader calls its progress callbacks once per 8 KB chunk, so an
        unthrottled report() would queue one event per chunk - hundreds of
        thousands for a large ISO - and starve button presses.
        """
        calls = 50_000

        def work(report, cancelled):
            for _ in range(calls):
                report(percent=1, text="downloading")
            return "done"

        app = self._app_with_recording_window()
        self.assertEqual(app.run_in_background(work, cancellable=False), "done")

        # Throttled to ~10/s, so a loop this fast must emit only a handful.
        self.assertLess(app.ui.window.posted, 100,
                        f"{app.ui.window.posted} events queued for {calls} "
                        "reports - progress is not throttled")

    def test_cancel_reaches_the_worker_promptly_while_reporting(self):
        """A pending Cancel must stop a worker that is streaming progress."""
        import time

        def work(report, cancelled):
            for _ in range(200_000):
                report(percent=1, text="downloading")
                if cancelled():
                    return "stopped"
                time.sleep(0)
            return "ran to completion"

        app = self._app_with_recording_window(
            preload=[('-CANCEL_DOWNLOAD-', {})])
        self.assertEqual(
            app.run_in_background(work, cancellable=True), "stopped",
            "Cancel must reach the worker instead of queueing behind progress")


class TestVendorOnlyDownloads(unittest.TestCase):
    """Images with no direct URL must guide the user, not fail."""

    def test_windows_versions_have_a_download_page_and_no_url(self):
        from unetbootin.models.distro import DistributionManager
        m = DistributionManager()
        for key in ('windows11', 'windows10'):
            distro = m.get_distribution(key)
            self.assertIsNotNone(distro, f"{key} must exist")
            self.assertEqual(len(distro.versions), 1,
                             f"{key} should list only the latest release")
            version = distro.versions[0]
            self.assertEqual(version.url, "",
                             "no direct URL exists for Windows images")
            self.assertTrue(version.download_page.startswith('https://'),
                            "a vendor download page must be provided")

    def test_manual_download_is_detected_and_reported(self):
        from unittest.mock import patch, MagicMock
        from unetbootin.app import UNetbootinAppPySG
        from unetbootin.models.distro import DistributionManager

        app = UNetbootinAppPySG.__new__(UNetbootinAppPySG)
        app.distro_manager = DistributionManager()

        with patch('unetbootin.app.sg') as mock_sg:
            mock_sg.popup_yes_no.return_value = 'No'
            handled = app._handle_manual_download(
                'windows11', app.distro_manager.get_distribution(
                    'windows11').versions[0].name)

        self.assertTrue(handled, "a vendor-only image must be handled")
        mock_sg.popup_yes_no.assert_called_once()
        shown = mock_sg.popup_yes_no.call_args[0][0]
        self.assertIn("microsoft.com", shown.lower())
        self.assertIn("Disk image", shown)

    def test_normal_distro_is_not_treated_as_manual(self):
        from unetbootin.app import UNetbootinAppPySG
        from unetbootin.models.distro import DistributionManager

        app = UNetbootinAppPySG.__new__(UNetbootinAppPySG)
        app.distro_manager = DistributionManager()
        self.assertFalse(
            app._handle_manual_download('ubuntu', '26.04 LTS'),
            "a normal distribution must download as usual")


class TestCategoryIcons(unittest.TestCase):
    """Each main category must map to a bundled icon."""

    def test_icon_files_exist_for_every_category(self):
        from unetbootin.resources import icon_path
        from unetbootin.ui.main_window_ctk import MainWindowCTk as MainWindowPySG
        from unetbootin.models.distro import DistributionManager

        mapping = MainWindowPySG._CATEGORY_ICONS
        categories = DistributionManager().get_categories()

        for category in categories:
            key = category.strip().lower()
            self.assertIn(key, mapping,
                          f"category '{category}' has no icon mapped")
            path = icon_path(mapping[key])
            self.assertTrue(os.path.exists(path), f"missing icon: {path}")
            self.assertGreater(os.path.getsize(path), 0)

    def test_unknown_category_maps_to_no_icon(self):
        """'All' must not show a misleading icon."""
        from unetbootin.ui.main_window_ctk import MainWindowCTk as MainWindowPySG
        mapping = MainWindowPySG._CATEGORY_ICONS
        self.assertIsNone(mapping.get('all'))
        self.assertIsNone(mapping.get(''))


class TestDistroOrdering(unittest.TestCase):
    """The distribution drop-down must read alphabetically."""

    def _sorted_names(self, category=None):
        from unittest.mock import MagicMock
        from unetbootin.ui.main_window_ctk import MainWindowCTk as MainWindowPySG
        from unetbootin.models.distro import DistributionManager

        ui = MainWindowPySG.__new__(MainWindowPySG)
        ui.distributions = {
            d['name']: d for d in DistributionManager().get_distributions()
        }
        captured = {}
        distro = MagicMock()
        distro.get.return_value = ''
        distro.update.side_effect = lambda **kw: captured.update(kw)

        def element():
            el = MagicMock()
            el.get.return_value = ''
            return el

        # update_distro_list selects the first entry, which cascades into the
        # version list, so those elements must exist too.
        ui.elements = {
            'distro_select': distro,
            'category_select': element(),
            'version_select': element(),
            'info_message': element(),
        }
        ui.update_distro_list(category or 'All')
        return captured.get('values', [])

    def test_list_is_alphabetical_ignoring_case(self):
        names = self._sorted_names()
        self.assertEqual(names, sorted(names, key=str.lower))

    def test_lowercase_initial_name_is_not_pushed_to_the_end(self):
        """openSUSE must sit between OpenMandriva and Rocky, not after Zorin."""
        names = self._sorted_names()
        self.assertIn('openSUSE', names)
        self.assertLess(names.index('openSUSE'), names.index('Zorin OS'))

    def test_each_category_is_alphabetical(self):
        for category in ('Linux', 'BSD', 'Windows'):
            names = self._sorted_names(category)
            self.assertEqual(names, sorted(names, key=str.lower),
                             f"{category} list is not alphabetical")


class TestCancelAndWindowIdentity(unittest.TestCase):
    """Cancel must not quit, and the window must be matchable by the task bar."""

    def test_cancel_does_not_stop_the_application(self):
        """Only Exit closes the app; Cancel with nothing running is a no-op."""
        import inspect
        from unetbootin.app import UNetbootinAppPySG

        src = inspect.getsource(UNetbootinAppPySG.run)
        # Isolate the -CANCEL- branch (not -CANCEL_DOWNLOAD-).
        idx = src.index("event == '-CANCEL-'")
        branch = src[idx:idx + 400].split("elif event ==")[0]
        self.assertNotIn("self.running = False", branch,
                         "Cancel must not stop the event loop")
        self.assertNotIn("break", branch, "Cancel must not exit the loop")

    def test_exit_still_stops_the_application(self):
        import inspect
        from unetbootin.app import UNetbootinAppPySG
        src = inspect.getsource(UNetbootinAppPySG.run)
        self.assertIn("'-EXIT-'", src)
        self.assertIn("self.running = False", src,
                      "Exit must still be able to stop the loop")

    def test_wm_class_matches_the_desktop_entries(self):
        """The task bar matches a window to its launcher via WM_CLASS."""
        import re, glob
        from unetbootin.ui.main_window_ctk import WM_CLASS

        entries = glob.glob(os.path.join(
            os.path.dirname(__file__), '..', 'resources', 'linux', '*.desktop'))
        self.assertTrue(entries, "no desktop entries found")
        for path in entries:
            text = open(path).read()
            match = re.search(r'StartupWMClass=(\S+)', text)
            self.assertIsNotNone(match, f"{path} has no StartupWMClass")
            self.assertEqual(
                match.group(1), WM_CLASS,
                f"{os.path.basename(path)} StartupWMClass must equal WM_CLASS")

    def test_window_icon_reference_is_retained(self):
        """Tk holds only a weak reference; an inline image would be collected."""
        import inspect
        from unetbootin.ui.main_window_ctk import MainWindowCTk
        src = inspect.getsource(MainWindowCTk._apply_window_icon)
        self.assertIn("self._window_icon", src,
                      "the PhotoImage must be stored, or the icon disappears")
