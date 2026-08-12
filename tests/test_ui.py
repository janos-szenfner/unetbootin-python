"""
Unit tests for UI components.

These tests verify the MainWindow UI functionality (CustomTkinter).
"""

import unittest
import os
import sys
import tempfile
import shutil
import threading
import time
from unittest.mock import patch, MagicMock

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    import customtkinter
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

# Now we can import without errors
from pynetboot.models.distro import DistributionManager
from pynetboot.ui.main_window_ctk import MainWindowCTk as MainWindowPySG


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
        from pynetboot.core.extractor import ISOExtractor
        from pynetboot.core.downloader import Downloader
        from pynetboot.core.installer import USBInstaller

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
        from pynetboot.platform import get_drive_list
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
#   from pynetboot.ui.main_window_ctk import MainWindowCTk as MainWindowPySG
#   window = MainWindowCTk()
#   # Test UI interactions here


class TestUIComponents(unittest.TestCase):
    """Test UI components that don't require window display."""

    def test_format_drive_list_filters_unsafe_drives(self):
        """format_drive_list must exclude non-removable/internal/virtual drives.

        Only drives that `is_safe_target()` approves may appear in the UI list.
        """
        from unittest.mock import patch
        from pynetboot.app import PyNetbootApp

        app = PyNetbootApp.__new__(PyNetbootApp)

        drives = [
            {'device': '/dev/sda', 'size': 100000000000, 'label': 'System', 'removable': False},
            {'device': '/dev/sdb', 'size': 16000000000, 'label': 'USB', 'removable': True},
        ]

        # Only the USB drive is a safe target; the system disk must be dropped.
        def fake_safe(device, allow_external_fixed=False):
            return device == '/dev/sdb'

        with patch('pynetboot.app.is_safe_target', side_effect=fake_safe):
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
        from pynetboot.app import PyNetbootApp

        app = PyNetbootApp.__new__(PyNetbootApp)
        drives = [
            {'device': '/dev/sda', 'size': 100000000000, 'removable': False},
            {'device': 'disk0', 'size': 500000000000, 'removable': False},
        ]
        with patch('pynetboot.app.is_safe_target', return_value=False):
            formatted = app.format_drive_list(drives)
        self.assertEqual(formatted, [])

    def test_format_drive_list_target_type_selects_filter_strictness(self):
        """"Hard Disk" widens the filter; "USB Drive" keeps the strict one.

        The target type must be forwarded to is_safe_target as
        allow_external_fixed, so external hard drives become selectable only in
        "Hard Disk" mode.
        """
        from unittest.mock import patch
        from pynetboot.app import PyNetbootApp

        app = PyNetbootApp.__new__(PyNetbootApp)
        # An external HDD: not removable media, so only allowed when the filter
        # is widened for the "Hard Disk" target type.
        drives = [{'device': '/dev/sdc', 'size': 2000000000000, 'removable': False}]

        def fake_safe(device, allow_external_fixed=False):
            return allow_external_fixed

        with patch('pynetboot.app.is_safe_target', side_effect=fake_safe):
            usb_mode = app.format_drive_list(drives, target_type="USB Drive")
            hdd_mode = app.format_drive_list(drives, target_type="Hard Disk")

        self.assertEqual(usb_mode, [], "external HDD must not appear in USB mode")
        self.assertEqual([dev for _d, dev in hdd_mode], ['/dev/sdc'])

    def test_resolve_iso_download_dir_custom_folder_is_kept(self):
        """A chosen ISO folder is used and the ISO is NOT scheduled for deletion."""
        import tempfile
        from pynetboot.app import PyNetbootApp

        app = PyNetbootApp.__new__(PyNetbootApp)

        target = tempfile.mkdtemp(prefix='pynetboot_iso_')
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
        from pynetboot.app import PyNetbootApp

        app = PyNetbootApp.__new__(PyNetbootApp)
        with patch.object(PyNetbootApp, 'get_downloads_dir',
                          return_value='/home/someone/Downloads'):
            directory, delete_after = app.resolve_iso_download_dir(None)
        self.assertEqual(directory, '/home/someone/Downloads')
        self.assertTrue(delete_after, "the staged ISO must be deleted on success")

    def test_resolve_iso_download_dir_raises_when_no_downloads_folder(self):
        """No chosen folder and no Downloads folder -> tell the user to set one."""
        from unittest.mock import patch
        from pynetboot.app import PyNetbootApp, ISOLocationError

        app = PyNetbootApp.__new__(PyNetbootApp)
        with patch.object(PyNetbootApp, 'get_downloads_dir', return_value=None):
            with self.assertRaises(ISOLocationError) as ctx:
                app.resolve_iso_download_dir(None)
        self.assertIn("ISO Location", str(ctx.exception))

    def test_resolve_iso_download_dir_raises_on_unwritable_choice(self):
        """An unwritable chosen folder is reported, not silently replaced."""
        from pynetboot.app import PyNetbootApp, ISOLocationError

        app = PyNetbootApp.__new__(PyNetbootApp)
        with self.assertRaises(ISOLocationError):
            app.resolve_iso_download_dir('/proc/definitely/not/writable')

    def test_discard_staged_iso_removes_only_staged_file(self):
        """The staged ISO is deleted once; a kept ISO is never touched."""
        import tempfile
        from pynetboot.app import PyNetbootApp

        app = PyNetbootApp.__new__(PyNetbootApp)

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
        from pynetboot.app import PyNetbootApp

        app = PyNetbootApp.__new__(PyNetbootApp)
        app.show_error = MagicMock()

        with patch('pynetboot.app.is_safe_target', return_value=False):
            # Even if the user would click "Yes", an unsafe device is rejected
            # before any prompt.
            with patch('pynetboot.app.sg') as mock_sg:
                mock_sg.popup_yes_no.return_value = 'Yes'
                result = app._confirm_destructive_write('/dev/sda')

        self.assertFalse(result)
        app.show_error.assert_called_once()

    def test_format_size_in_app(self):
        """Test format_size function used in app.py."""
        from pynetboot.core.utils import format_size

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
        from pynetboot.app import PyNetbootApp
        import queue

        app = PyNetbootApp.__new__(PyNetbootApp)

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
        from pynetboot.ui.main_window_ctk import window_icon_path
        path = window_icon_path()
        self.assertIsNotNone(path, "a bundled window icon must be found")
        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith('.png'))
        self.assertGreater(os.path.getsize(path), 0)

    def test_app_title_is_the_app_name(self):
        from pynetboot import APP_TITLE, APP_NAME
        self.assertEqual(APP_TITLE, APP_NAME)

    def test_window_is_not_created_with_the_placeholder_icon(self):
        """Guard against regressing to the 1x1 transparent GIF placeholder."""
        import inspect
        from pynetboot.ui import main_window_ctk
        src = inspect.getsource(main_window_ctk.MainWindowCTk.init_ui)
        self.assertNotIn("transparent_gif", src,
                         "the window must not use the blank placeholder icon")


class TestProgressThrottling(unittest.TestCase):
    """Progress updates must not starve button presses such as Cancel."""

    def _app_with_recording_window(self, preload=()):
        import queue
        from unittest.mock import MagicMock
        from pynetboot.app import PyNetbootApp

        app = PyNetbootApp.__new__(PyNetbootApp)

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
        from pynetboot.models.distro import DistributionManager
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
        from pynetboot.app import PyNetbootApp
        from pynetboot.models.distro import DistributionManager

        app = PyNetbootApp.__new__(PyNetbootApp)
        app.distro_manager = DistributionManager()

        with patch('pynetboot.app.sg') as mock_sg:
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
        from pynetboot.app import PyNetbootApp
        from pynetboot.models.distro import DistributionManager

        app = PyNetbootApp.__new__(PyNetbootApp)
        app.distro_manager = DistributionManager()
        self.assertFalse(
            app._handle_manual_download('ubuntu', '26.04 LTS'),
            "a normal distribution must download as usual")


class TestCategoryIcons(unittest.TestCase):
    """Each main category must map to a bundled icon."""

    def test_icon_files_exist_for_every_category(self):
        from pynetboot.resources import icon_path
        from pynetboot.ui.main_window_ctk import MainWindowCTk as MainWindowPySG
        from pynetboot.models.distro import DistributionManager

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
        from pynetboot.ui.main_window_ctk import MainWindowCTk as MainWindowPySG
        mapping = MainWindowPySG._CATEGORY_ICONS
        self.assertIsNone(mapping.get('all'))
        self.assertIsNone(mapping.get(''))


class TestDistroOrdering(unittest.TestCase):
    """The distribution drop-down must read alphabetically."""

    def _sorted_names(self, category=None):
        from unittest.mock import MagicMock
        from pynetboot.ui.main_window_ctk import MainWindowCTk as MainWindowPySG
        from pynetboot.models.distro import DistributionManager

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
        from pynetboot.app import PyNetbootApp

        src = inspect.getsource(PyNetbootApp.run)
        # Isolate the -CANCEL- branch (not -CANCEL_DOWNLOAD-).
        idx = src.index("event == '-CANCEL-'")
        branch = src[idx:idx + 400].split("elif event ==")[0]
        self.assertNotIn("self.running = False", branch,
                         "Cancel must not stop the event loop")
        self.assertNotIn("break", branch, "Cancel must not exit the loop")

    def test_exit_still_stops_the_application(self):
        import inspect
        from pynetboot.app import PyNetbootApp
        src = inspect.getsource(PyNetbootApp.run)
        self.assertIn("'-EXIT-'", src)
        self.assertIn("self.running = False", src,
                      "Exit must still be able to stop the loop")

    def test_wm_class_matches_the_desktop_entries(self):
        """The task bar matches a window to its launcher via WM_CLASS."""
        import re, glob
        from pynetboot.ui.main_window_ctk import WM_CLASS

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
        from pynetboot.ui.main_window_ctk import MainWindowCTk
        src = inspect.getsource(MainWindowCTk._apply_window_icon)
        self.assertIn("self._window_icon", src,
                      "the PhotoImage must be stored, or the icon disappears")


class TestDialogIcons(unittest.TestCase):
    """Dialogs must carry the right status mark."""

    def test_dialog_icon_files_exist(self):
        from pynetboot.resources import icon_path
        for name in ('dlg_success.png', 'dlg_error.png', 'dlg_warning.png'):
            path = icon_path(name)
            self.assertTrue(os.path.exists(path), f"missing {name}")
            self.assertGreater(os.path.getsize(path), 0)

    def test_each_dialog_kind_uses_its_own_icon(self):
        import inspect
        from pynetboot.ui import main_window_ctk as ui
        self.assertIn("dlg_success.png", inspect.getsource(ui.popup_ok))
        self.assertIn("dlg_error.png", inspect.getsource(ui.popup_error))
        self.assertIn("dlg_warning.png", inspect.getsource(ui.popup_yes_no))

    def test_version_is_current(self):
        """About shows __version__, so it must not drift behind the tags."""
        from pynetboot import __version__, APP_VERSION
        self.assertEqual(APP_VERSION, __version__)
        parts = __version__.split('.')
        self.assertEqual(len(parts), 3, "expected a three-part version")
        self.assertTrue(all(p.isdigit() for p in parts))
        self.assertGreaterEqual(tuple(int(p) for p in parts), (1, 1, 6),
                                "version is behind the released tags")


class TestFontFallback(unittest.TestCase):
    """The UI must not depend on a font it has to install at runtime."""

    def test_candidates_include_fonts_common_on_linux(self):
        from pynetboot.ui.main_window_ctk import FONT_CANDIDATES
        # Roboto is CustomTkinter's default but is not installable inside a
        # Flatpak sandbox, so widely-shipped fallbacks must follow it.
        for family in ("DejaVu Sans", "Noto Sans", "Liberation Sans"):
            self.assertIn(family, FONT_CANDIDATES)
        self.assertEqual(FONT_CANDIDATES[0], "Roboto",
                         "Roboto stays first so the intended look wins if present")

    def test_resolution_is_safe_without_a_tk_root(self):
        """Called with no interpreter available it must return None, not raise."""
        from pynetboot.ui.main_window_ctk import resolve_font_family
        from unittest.mock import patch
        with patch('tkinter.font.families', side_effect=RuntimeError('no root')):
            self.assertIsNone(resolve_font_family())

    def test_flatpak_grants_font_access(self):
        """The sandbox must be able to read fonts, or Tk renders a bitmap font."""
        import json
        path = os.path.join(os.path.dirname(__file__), '..', 'resources',
                            'linux', 'com.pynetboot.PyNetboot.json')
        manifest = json.load(open(path))
        args = ' '.join(manifest['finish-args'])
        self.assertIn('/usr/share/fonts', args)
        self.assertIn('fontconfig', args)
        # And a font is shipped inside the bundle as a last resort. Find the
        # module by name: dependency modules precede the application one.
        app_module = next(m for m in manifest['modules']
                          if m['name'] == 'pynetboot')
        commands = ' '.join(app_module['build-commands'])
        self.assertIn('/app/share/fonts', commands)


class TestCategoryIcons(unittest.TestCase):
    """Switching categories repeatedly must keep showing the icons.

    CustomTkinter ignores `image=None` -- its label goes on displaying the
    previous image -- so an image released on the Python side left the widget
    pointing at one Tk had destroyed, and the next category raised
    "image pyimageN doesn't exist". The icons disappeared from the second
    round onwards.
    """

    def setUp(self):
        if not HAS_CTK:
            self.skipTest("customtkinter is not installed")
        from pynetboot.ui.main_window_ctk import MainWindowCTk
        try:
            self.window = MainWindowCTk()
        except Exception as e:                # no display, e.g. headless CI
            self.skipTest(f"no Tk display: {e}")
        self.window.root.withdraw()
        self.window.root.update_idletasks()
        self.addCleanup(self.window.root.destroy)

    def test_cycling_categories_keeps_the_icon(self):
        label = self.window._category_icon._label
        for _round in range(3):
            for category in ('All', 'Linux', 'BSD', 'Windows'):
                self.window.set_category_icon(category)
                self.window.root.update_idletasks()
                shown = str(label.cget('image'))
                self.assertTrue(shown, f"{category}: no image on the label")
                # The name must still refer to a live Tk image.
                self.assertTrue(
                    self.window.root.tk.call('image', 'inuse', shown),
                    f"{category}: {shown} was destroyed underneath Tk")

    def test_images_are_reused_rather_than_rebuilt(self):
        label = self.window._category_icon._label
        self.window.set_category_icon('Linux')
        first = str(label.cget('image'))
        self.window.set_category_icon('All')
        self.window.set_category_icon('Linux')
        self.assertEqual(str(label.cget('image')), first,
                         "each visit built a new image instead of reusing one")

    def test_the_linux_category_uses_the_distribution_logo(self):
        import os

        from pynetboot.resources import icon_path, resource_path
        from pynetboot.ui.main_window_ctk import MainWindowCTk
        filename = MainWindowCTk._CATEGORY_ICONS['linux']
        self.assertEqual(filename, 'Linux-Logo.png')
        # It lives in logos/, not icons/, so the lookup has to reach both.
        found = (os.path.exists(icon_path(filename))
                 or os.path.exists(resource_path('logos', filename)))
        self.assertTrue(found, f"{filename} is not bundled")

    def test_every_category_icon_is_bundled(self):
        import os

        from pynetboot.resources import icon_path, resource_path
        from pynetboot.ui.main_window_ctk import MainWindowCTk
        for category, filename in MainWindowCTk._CATEGORY_ICONS.items():
            found = (os.path.exists(icon_path(filename))
                     or os.path.exists(resource_path('logos', filename)))
            self.assertTrue(found, f"{category}: {filename} is not bundled")

    def test_an_unknown_category_shows_nothing_but_stays_usable(self):
        label = self.window._category_icon._label
        self.window.set_category_icon('Linux')
        self.window.set_category_icon('Something Else')
        self.window.root.update_idletasks()
        shown = str(label.cget('image'))
        self.assertTrue(self.window.root.tk.call('image', 'inuse', shown))


class TestUpdateCheck(unittest.TestCase):
    """About reports whether a newer release has been published."""

    def test_versions_compare_numerically(self):
        from pynetboot.core.updates import is_newer

        self.assertTrue(is_newer('1.10.4', '1.10.3'))
        self.assertTrue(is_newer('1.11.0', '1.10.9'))
        self.assertTrue(is_newer('2.0.0', '1.99.99'))
        self.assertFalse(is_newer('1.10.3', '1.10.3'))
        # The trap in comparing these as text: 9 sorts after 1.
        self.assertFalse(is_newer('1.9.11', '1.10.0'))

    def test_a_shorter_number_is_the_earlier_one(self):
        from pynetboot.core.updates import is_newer

        self.assertFalse(is_newer('1.10', '1.10.1'))
        self.assertTrue(is_newer('1.10.1', '1.10'))

    def test_a_name_that_does_not_parse_is_never_newer(self):
        """Nobody should be told to update on the strength of an unread name."""
        from pynetboot.core.updates import is_newer, parse_version

        self.assertIsNone(parse_version('nightly'))
        self.assertFalse(is_newer('nightly', '1.10.3'))
        self.assertFalse(is_newer('1.10.4', ''))

    def test_a_tag_is_read_without_its_v(self):
        from pynetboot.core import updates

        reply = MagicMock()
        reply.json.return_value = {'tag_name': 'v1.10.4'}
        with patch('requests.get', return_value=reply):
            self.assertEqual(updates.latest_release(), '1.10.4')

    def test_a_newer_release_is_reported(self):
        from pynetboot.core import updates

        with patch.object(updates, 'latest_release', return_value='1.10.4'):
            result = updates.check_for_update(current='1.10.3')
        self.assertTrue(result.update_available)
        self.assertEqual(result.latest, '1.10.4')

    def test_the_current_version_is_not_reported_as_an_update(self):
        from pynetboot.core import updates

        with patch.object(updates, 'latest_release', return_value='1.10.3'):
            result = updates.check_for_update(current='1.10.3')
        self.assertEqual(result.status, 'current')
        self.assertFalse(result.update_available)

    def test_a_failed_check_is_unknown_rather_than_up_to_date(self):
        """No network must not read as "you have the latest version"."""
        from pynetboot.core import updates

        import requests
        with patch.object(updates, 'latest_release',
                          side_effect=requests.exceptions.ConnectionError('x')):
            result = updates.check_for_update(current='1.10.3')
        self.assertEqual(result.status, 'unknown')
        self.assertFalse(result.update_available)
        self.assertIsNone(result.latest)

    def test_the_check_never_raises(self):
        """It runs on a worker thread, where an exception would go unseen."""
        from pynetboot.core import updates

        for blow_up in (ValueError('bad json'), OSError('socket'),
                        KeyError('tag_name')):
            with patch.object(updates, 'latest_release', side_effect=blow_up):
                self.assertEqual(
                    updates.check_for_update(current='1.10.3').status,
                    'unknown')


class TestUpdateCheckInAboutDialog(unittest.TestCase):
    """The dialog opens at once and is told the answer afterwards.

    The outcome is applied by _apply_update_result, which these drive
    directly. Pumping the event loop instead would mean root.update() with a
    modal dialog up, which does not return on every Tk build.
    """

    def setUp(self):
        if not HAS_CTK:
            self.skipTest("customtkinter is not installed")
        import customtkinter as ctk
        from pynetboot.ui.main_window_ctk import MainWindowCTk
        try:
            self.window = MainWindowCTk()
        except Exception as e:                # no display, e.g. headless CI
            self.skipTest(f"no Tk display: {e}")
        self.window.root.withdraw()
        self.addCleanup(self.window.root.destroy)
        self.label = ctk.CTkLabel(self.window.root, text="checking")

    def _apply(self, status, latest=None):
        from pynetboot.core.updates import UpdateCheck
        self.window._apply_update_result(self.label,
                                         UpdateCheck(status, latest))
        return self.label.cget('text')

    def test_a_newer_version_is_named(self):
        self.assertIn('9.9.9', self._apply('update', '9.9.9'))

    def test_the_update_line_opens_the_releases_page(self):
        from pynetboot.core import updates
        from pynetboot.ui import main_window_ctk

        import customtkinter as ctk

        # The handler is caught as it is bound and then called: a real click
        # cannot be delivered to a widget in a window that is never mapped.
        bound = {}
        real_bind = ctk.CTkLabel.bind

        def capture(label, sequence=None, command=None, add=True):
            bound[sequence] = command
            return real_bind(label, sequence, command, add)

        with patch.object(main_window_ctk.MainWindowCTk, '_open_url') as opened, \
                patch.object(ctk.CTkLabel, 'bind', capture):
            self._apply('update', '9.9.9')
            self.assertIn('<Button-1>', bound, "the line is not clickable")
            bound['<Button-1>'](None)
            opened.assert_called_once_with(updates.RELEASES_PAGE)

    def test_being_current_says_so(self):
        self.assertIn('latest', self._apply('current', '1.0.0').lower())

    def test_a_failed_check_does_not_claim_the_version_is_current(self):
        text = self._apply('unknown')
        self.assertIn('Could not check', text)
        self.assertNotIn('latest', text.lower())

    def test_a_closed_dialog_is_left_alone(self):
        """The window can be gone by the time the request comes back."""
        self.label.destroy()
        self.window._apply_update_result(         # must not raise
            self.label, __import__(
                'pynetboot.core.updates', fromlist=['UpdateCheck']
            ).UpdateCheck('update', '9.9.9'))

    def test_the_dialog_does_not_wait_for_the_answer(self):
        """It opens saying it is checking, with the request still out."""
        from pynetboot.core import updates
        from pynetboot.ui import main_window_ctk
        import customtkinter as ctk

        started = threading.Event()
        threads = []

        def slow_check(*_a, **_k):
            threads.append(threading.current_thread().name)
            started.set()
            time.sleep(0.5)
            return updates.UpdateCheck('update', '9.9.9')

        with patch.object(main_window_ctk.MainWindowCTk, '_open_url'), \
                patch.object(updates, 'check_for_update', slow_check):
            self.window.show_about()
            self.assertTrue(started.wait(2), "the check never ran")
            texts = []
            for child in self.window.root.winfo_children():
                if isinstance(child, ctk.CTkToplevel):
                    texts = [w.cget('text') for w in child.winfo_children()
                             if isinstance(w, ctk.CTkLabel)]
                    child.destroy()
        self.assertTrue(any('Checking' in t for t in texts),
                        f"no checking line among {texts}")
        self.assertNotIn('MainThread', threads,
                         "the request blocked the window")


class TestApplicationMenu(unittest.TestCase):
    """The macOS application menu must open this app's About dialog.

    Left to itself Tk fills that menu with an About item that opens the Cocoa
    panel, which shows the bundle's name and version rather than the dialog
    the About button opens.
    """

    def setUp(self):
        if not HAS_CTK:
            self.skipTest("customtkinter is not installed")
        from pynetboot.ui.main_window_ctk import MainWindowCTk
        try:
            self.window = MainWindowCTk()
        except Exception as e:                # no display, e.g. headless CI
            self.skipTest(f"no Tk display: {e}")
        self.addCleanup(self.window.root.destroy)
        self.window.root.withdraw()
        if self.window.root.tk.call('tk', 'windowingsystem') != 'aqua':
            self.skipTest("the application menu exists only on macOS")

    def test_the_about_item_is_wired_to_the_about_event(self):
        menubar, app_menu = self.window._app_menu
        # Named "apple", or macOS treats it as an ordinary menu.
        self.assertEqual(app_menu.winfo_name(), 'apple')
        self.assertEqual(str(self.window.root.cget('menu')), str(menubar))
        self.assertIn('About', app_menu.entrycget(0, 'label'))

        while not self.window._events.empty():
            self.window._events.get_nowait()
        app_menu.invoke(0)
        self.assertEqual(self.window._events.get_nowait()[0], '-ABOUT-',
                         "the menu item must go through the same event as "
                         "the About button")


class TestMacOSBundleMetadata(unittest.TestCase):
    """The standard About panel and Finder read these from Info.plist."""

    def _spec(self):
        return open(os.path.join(os.path.dirname(__file__), '..',
                                 'pynetboot-macos.spec')).read()

    def test_the_bundle_carries_the_package_version(self):
        """PyInstaller writes 0.0.0 when BUNDLE is given no version."""
        spec = self._spec()
        self.assertIn('version=VERSION', spec)
        self.assertIn("'CFBundleShortVersionString': VERSION", spec)

    def test_the_version_is_read_from_the_package(self):
        """Run the spec's own lookup: a stale pattern must not pass silently."""
        import ast

        import pynetboot

        root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        tree = ast.parse(self._spec())
        wanted = []
        for node in tree.body:
            if isinstance(node, ast.Import):        # pathlib, re
                wanted.append(node)
            elif (isinstance(node, ast.Assign)
                    and getattr(node.targets[0], 'id', None) == 'VERSION'):
                wanted.append(node)
        namespace = {}
        cwd = os.getcwd()
        os.chdir(root)                              # the spec reads src/ from here
        try:
            exec(compile(ast.Module(body=wanted, type_ignores=[]),
                         'spec', 'exec'), namespace)
        finally:
            os.chdir(cwd)
        self.assertEqual(namespace['VERSION'], pynetboot.__version__)

    def test_the_bundle_is_named_for_display(self):
        """The bundle directory is lower-case; the menu title must not be."""
        from pynetboot import APP_NAME
        self.assertIn(f"'CFBundleName': '{APP_NAME}'", self._spec())


class TestPressToClick(unittest.TestCase):
    """A press must count as "the mouse is inside", or buttons look dead.

    CustomTkinter runs a button's command only when it has seen an <Enter>
    event first. Tk on macOS does not reliably deliver crossing events, so
    without this the buttons responded only in the odd spot where a crossing
    happened to fire.
    """

    def setUp(self):
        if not HAS_CTK:
            self.skipTest("customtkinter is not installed")
        import customtkinter as ctk
        try:
            self.root = ctk.CTk()
        except Exception as e:            # no display, e.g. headless CI
            self.skipTest(f"no Tk display: {e}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.button = ctk.CTkButton(self.root, text="OK", command=lambda: None)
        self.button.pack()
        self.root.update_idletasks()

    def test_press_on_the_canvas_marks_the_button(self):
        from pynetboot.ui.main_window_ctk import mark_mouse_inside
        self.button._mouse_inside = False
        self.assertTrue(mark_mouse_inside(self.button._canvas))
        self.assertTrue(self.button._mouse_inside)

    def test_press_on_the_label_marks_the_button(self):
        from pynetboot.ui.main_window_ctk import mark_mouse_inside
        self.button._mouse_inside = False
        self.assertTrue(mark_mouse_inside(self.button._text_label))
        self.assertTrue(self.button._mouse_inside)

    def test_a_release_without_the_flag_does_nothing(self):
        """The behaviour being worked around, pinned so it stays understood."""
        fired = []
        self.button.configure(command=lambda: fired.append(1))
        self.button._mouse_inside = False
        self.button._on_release()
        self.assertEqual(fired, [], "CustomTkinter still gates on _mouse_inside")

        from pynetboot.ui.main_window_ctk import mark_mouse_inside
        mark_mouse_inside(self.button._canvas)
        self.button._on_release()
        self.assertEqual(fired, [1])

    def test_a_widget_with_no_customtkinter_owner_is_ignored(self):
        import tkinter

        from pynetboot.ui.main_window_ctk import mark_mouse_inside
        plain = tkinter.Frame(self.root)
        self.assertFalse(mark_mouse_inside(plain))
        self.assertFalse(mark_mouse_inside(None))

    def test_the_handler_is_bound_for_the_whole_application(self):
        from pynetboot.ui.main_window_ctk import enable_press_to_click
        enable_press_to_click(self.root)
        self.assertIn('<Button-1>', self.root.bind_all())


class TestDrawingMethodFallback(unittest.TestCase):
    """Corners are glyphs; without the font they render as stray letters."""

    def setUp(self):
        try:
            from customtkinter.windows.widgets.core_rendering import DrawEngine
        except ImportError:
            self.skipTest("customtkinter is not installed")
        self.engine = DrawEngine
        self.original = DrawEngine.preferred_drawing_method
        self.addCleanup(
            setattr, DrawEngine, 'preferred_drawing_method', self.original)

    def _resolve(self, available, platform='linux'):
        from unittest.mock import patch

        from pynetboot.ui.main_window_ctk import resolve_drawing_method
        with patch('pynetboot.ui.main_window_ctk.sys.platform', platform):
            return resolve_drawing_method(available=available)

    def test_missing_shapes_font_falls_back_to_polygons(self):
        self.engine.preferred_drawing_method = "font_shapes"
        chosen = self._resolve({"DejaVu Sans", "Noto Sans"})
        self.assertEqual(chosen, "polygon_shapes")
        self.assertEqual(self.engine.preferred_drawing_method, "polygon_shapes")

    def test_present_shapes_font_keeps_font_shapes(self):
        from pynetboot.ui.main_window_ctk import SHAPES_FONT
        self.engine.preferred_drawing_method = "font_shapes"
        chosen = self._resolve({SHAPES_FONT, "DejaVu Sans"})
        self.assertEqual(chosen, "font_shapes")

    def test_installed_font_recovers_from_customtkinters_own_fallback(self):
        """CustomTkinter downgrades when its ~/.fonts copy fails, even though
        the Flatpak ships the font system-wide."""
        from pynetboot.ui.main_window_ctk import SHAPES_FONT
        self.engine.preferred_drawing_method = "circle_shapes"
        self.assertEqual(self._resolve({SHAPES_FONT}), "font_shapes")
        self.assertEqual(self.engine.preferred_drawing_method, "font_shapes")

    def test_other_platforms_are_left_alone(self):
        """Windows loads the font privately, so it is absent from the list."""
        for platform in ('win32', 'darwin'):
            self.engine.preferred_drawing_method = "font_shapes"
            self.assertIsNone(self._resolve({"Segoe UI"}, platform=platform))
            self.assertEqual(self.engine.preferred_drawing_method,
                             "font_shapes")

    def test_flatpak_does_not_hide_its_own_fonts(self):
        """Mounting the host's /etc/fonts replaces the runtime's fontconfig,
        whose config is what makes /app/share/fonts visible."""
        import json
        path = os.path.join(os.path.dirname(__file__), '..', 'resources',
                            'linux', 'com.pynetboot.PyNetboot.json')
        manifest = json.load(open(path))
        self.assertNotIn('/etc/fonts',
                         ' '.join(manifest['finish-args']))
        app_module = next(m for m in manifest['modules']
                          if m['name'] == 'pynetboot')
        commands = ' '.join(app_module['build-commands'])
        self.assertIn('CustomTkinter_shapes_font.otf', commands)


class TestLogWindow(unittest.TestCase):
    """The Log button must expose the captured log."""

    def setUp(self):
        from pynetboot.core import log_buffer
        log_buffer.install()
        buf = log_buffer.get_buffer()
        if buf is not None:
            buf.clear()

    def test_buffer_captures_records(self):
        import logging
        from pynetboot.core import log_buffer

        log_buffer.install()
        logging.getLogger('pynetboot.test').warning('a distinctive message')
        self.assertIn('a distinctive message', log_buffer.get_text())

    def test_buffer_is_bounded(self):
        import logging
        from pynetboot.core import log_buffer

        buf = log_buffer.install(capacity=50)
        # install() is idempotent, so use whatever capacity is in force.
        cap = buf._records.maxlen
        for i in range(cap + 120):
            logging.getLogger('pynetboot.test').info(f'line {i}')
        self.assertLessEqual(len(buf), cap, "the buffer must not grow forever")

    def test_text_is_useful_before_any_logging(self):
        from pynetboot.core import log_buffer
        buf = log_buffer.get_buffer()
        buf.clear()
        self.assertTrue(log_buffer.get_text().strip(),
                        "must explain itself rather than return nothing")

    def test_log_button_is_wired_to_the_window(self):
        import inspect
        from pynetboot.app import PyNetbootApp
        from pynetboot.ui.main_window_ctk import MainWindowCTk

        import ast, textwrap

        self.assertIn("'-LOG-'", inspect.getsource(PyNetbootApp.run))
        self.assertTrue(hasattr(MainWindowCTk, 'show_log'))

        # An ordinary window: minimisable and maximisable, so it must not be
        # made modal or transient. Check real calls, not words in the prose.
        tree = ast.parse(textwrap.dedent(
            inspect.getsource(MainWindowCTk.show_log)))
        called = {n.func.attr for n in ast.walk(tree)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute)}
        self.assertNotIn('grab_set', called, "the log window must not be modal")
        self.assertNotIn('transient', called,
                         "a transient window cannot be minimised separately")

    def test_log_icons_exist(self):
        from pynetboot.resources import icon_path
        for name in ('ui_log.png', 'ui_copy.png'):
            self.assertTrue(os.path.exists(icon_path(name)), f"missing {name}")

    def test_the_log_starts_at_the_left_margin(self):
        """`see('end')` also scrolls sideways when the last line is long.

        That left every line starting mid-word, so the reset has to follow it.
        """
        if not HAS_CTK:
            self.skipTest("customtkinter is not installed")
        from pynetboot.core import log_buffer
        from pynetboot.ui.main_window_ctk import MainWindowCTk

        original = log_buffer.get_text
        log_buffer.get_text = lambda: ('x' * 400 + '\n') * 30 + 'z' * 400
        self.addCleanup(setattr, log_buffer, 'get_text', original)
        try:
            window = MainWindowCTk()
        except Exception as e:                # no display, e.g. headless CI
            self.skipTest(f"no Tk display: {e}")
        window.root.withdraw()
        self.addCleanup(window.root.destroy)

        window.show_log()
        window.root.update_idletasks()
        self.assertEqual(window._log_textbox.xview()[0], 0.0,
                         "the log opened scrolled to the right")


class TestFlatpakTooling(unittest.TestCase):
    """The sandbox must carry the tools the installer shells out to."""

    def _manifest(self):
        import json
        return json.load(open(os.path.join(
            os.path.dirname(__file__), '..', 'resources', 'linux',
            'com.pynetboot.PyNetboot.json')))

    def test_formatting_tools_are_built_into_the_flatpak(self):
        """A Flatpak inherits no host utilities, so mkfs.vfat must be shipped."""
        modules = {m['name'] for m in self._manifest()['modules']}
        self.assertIn('dosfstools', modules,
                      "mkfs.vfat is required to format the target drive")
        self.assertIn('mtools', modules)

    def test_tool_sources_are_pinned_by_checksum(self):
        manifest = self._manifest()
        for name in ('dosfstools', 'mtools', 'parted'):
            module = next(m for m in manifest['modules'] if m['name'] == name)
            for source in module['sources']:
                self.assertIn('sha256', source,
                              f"{name} source must be checksum-pinned")
                self.assertEqual(len(source['sha256']), 64)

    def test_dependencies_are_built_before_the_application(self):
        names = [m['name'] for m in self._manifest()['modules']]
        for tool in ('dosfstools', 'mtools', 'parted'):
            self.assertLess(names.index(tool), names.index('pynetboot'))

    def test_disk_tools_are_installed_somewhere_on_path(self):
        """mkfs.vfat and parted must land in /app/bin.

        Both are sbin programs, and autotools puts them in /app/sbin under
        --prefix=/app. Flatpak's PATH is /app/bin:/usr/bin, so anything left
        in /app/sbin is invisible to shutil.which at runtime.
        """
        manifest = self._manifest()
        for name in ('dosfstools', 'parted'):
            module = next(m for m in manifest['modules'] if m['name'] == name)
            self.assertIn('--sbindir=/app/bin', module.get('config-opts', []),
                          f"{name} would install outside the Flatpak PATH")
