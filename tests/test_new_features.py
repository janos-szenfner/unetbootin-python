"""
Tests for new features: persistence UI, boot options, UEFI/Secure Boot support, download resume, and mirror selection.
"""

import unittest
import os
import sys
import tempfile
import shutil
from unittest.mock import patch, MagicMock

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from unetbootin.models.config import ConfigManager, AppConfig
from unetbootin.models.distro import Distribution, DistributionVersion, DistributionManager
from unetbootin.core.downloader import (
    Downloader, AsyncDownloader, DownloadWorker, 
    MirrorManager, MirrorInfo, DownloadResumeManager
)
from unetbootin.core.installer import USBInstaller, AsyncUSBInstaller
from unetbootin.ui.main_window import MainWindow


class TestNewConfigOptions(unittest.TestCase):
    """Test new configuration options."""
    
    def test_new_config_fields(self):
        """Test that new configuration fields are present."""
        config = AppConfig()
        
        # Boot options
        self.assertEqual(config.boot_options, '')
        self.assertFalse(config.enable_uefi_only)
        self.assertFalse(config.enable_secure_boot)
        
        # Download settings
        self.assertTrue(config.enable_download_resume)
        self.assertEqual(config.preferred_mirror, '')
        self.assertEqual(config.custom_mirrors, [])
    
    def test_config_to_dict_with_new_fields(self):
        """Test that to_dict includes new fields."""
        config = AppConfig(
            boot_options='quiet splash',
            enable_uefi_only=True,
            enable_secure_boot=True,
            enable_download_resume=False,
            preferred_mirror='https://mirror.example.com',
            custom_mirrors=['https://mirror1.com', 'https://mirror2.com']
        )
        
        data = config.to_dict()
        
        self.assertEqual(data['boot_options'], 'quiet splash')
        self.assertTrue(data['enable_uefi_only'])
        self.assertTrue(data['enable_secure_boot'])
        self.assertFalse(data['enable_download_resume'])
        self.assertEqual(data['preferred_mirror'], 'https://mirror.example.com')
        self.assertEqual(data['custom_mirrors'], ['https://mirror1.com', 'https://mirror2.com'])
    
    def test_config_from_dict_with_new_fields(self):
        """Test that from_dict includes new fields."""
        data = {
            'boot_options': 'test options',
            'enable_uefi_only': True,
            'enable_secure_boot': True,
            'enable_download_resume': False,
            'preferred_mirror': 'https://test.com',
            'custom_mirrors': ['https://mirror1.com']
        }
        
        config = AppConfig.from_dict(data)
        
        self.assertEqual(config.boot_options, 'test options')
        self.assertTrue(config.enable_uefi_only)
        self.assertTrue(config.enable_secure_boot)
        self.assertFalse(config.enable_download_resume)
        self.assertEqual(config.preferred_mirror, 'https://test.com')
        self.assertEqual(config.custom_mirrors, ['https://mirror1.com'])
    
    def test_config_manager_save_load_new_fields(self):
        """Test saving and loading new configuration fields."""
        temp_dir = tempfile.mkdtemp()
        config_manager = ConfigManager(config_dir=temp_dir)
        
        try:
            # Set new fields
            config_manager.set('boot_options', 'quiet splash persistent')
            config_manager.set('enable_uefi_only', True)
            config_manager.set('enable_secure_boot', True)
            config_manager.set('enable_download_resume', False)
            config_manager.set('preferred_mirror', 'https://mirror.example.com')
            config_manager.set('custom_mirrors', ['https://mirror1.com', 'https://mirror2.com'])
            
            # Load and verify
            config = config_manager.load()
            
            self.assertEqual(config.boot_options, 'quiet splash persistent')
            self.assertTrue(config.enable_uefi_only)
            self.assertTrue(config.enable_secure_boot)
            self.assertFalse(config.enable_download_resume)
            self.assertEqual(config.preferred_mirror, 'https://mirror.example.com')
            self.assertEqual(config.custom_mirrors, ['https://mirror1.com', 'https://mirror2.com'])
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestDistributionMirrors(unittest.TestCase):
    """Test distribution mirror support."""
    
    def test_distribution_version_with_mirrors(self):
        """Test DistributionVersion with mirrors."""
        version = DistributionVersion(
            name='24.04 LTS',
            url='https://releases.ubuntu.com/24.04/ubuntu-24.04.iso',
            size=4500000000,
            mirrors=['https://mirror1.ubuntu.com', 'https://mirror2.ubuntu.com']
        )
        
        self.assertEqual(version.mirrors, ['https://mirror1.ubuntu.com', 'https://mirror2.ubuntu.com'])
        
        # Test that mirrors are included in to_dict
        data = version.to_dict()
        self.assertIn('mirrors', data)
        self.assertEqual(data['mirrors'], version.mirrors)
    
    def test_distribution_with_mirrors(self):
        """Test Distribution with mirrors."""
        distro = Distribution(
            name='ubuntu',
            display_name='Ubuntu',
            mirrors=['https://mirror1.ubuntu.com', 'https://mirror2.ubuntu.com']
        )
        
        self.assertEqual(distro.mirrors, ['https://mirror1.ubuntu.com', 'https://mirror2.ubuntu.com'])
        
        # Test that mirrors are included in to_dict
        data = distro.to_dict()
        self.assertIn('mirrors', data)
        self.assertEqual(data['mirrors'], distro.mirrors)
    
    def test_distribution_manager_with_mirrors(self):
        """Test DistributionManager with mirrors."""
        manager = DistributionManager()
        distros = manager.get_distributions()
        
        # Check that distributions can have mirrors
        for distro in distros:
            if 'mirrors' in distro:
                self.assertIsInstance(distro['mirrors'], list)


class TestDownloadResumeManager(unittest.TestCase):
    """Test DownloadResumeManager."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, 'test.iso')
        self.resume_manager = DownloadResumeManager(self.test_file)
    
    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_resume_manager_initialization(self):
        """Test DownloadResumeManager initialization."""
        self.assertEqual(self.resume_manager.dest_path, self.test_file)
        self.assertEqual(self.resume_manager.temp_path, f"{self.test_file}.part")
        self.assertEqual(self.resume_manager.checksum_path, f"{self.test_file}.checksum")
        self.assertEqual(self.resume_manager.resume_info_path, f"{self.test_file}.resume")
    
    def test_partial_file_size(self):
        """Test getting partial file size."""
        # Initially, no partial file
        self.assertEqual(self.resume_manager.get_partial_file_size(), 0)
        
        # Create a partial file
        with open(self.resume_manager.temp_path, 'wb') as f:
            f.write(b'test data')
        
        self.assertEqual(self.resume_manager.get_partial_file_size(), 9)
    
    def test_save_and_get_resume_info(self):
        """Test saving and getting resume info."""
        info = {'url': 'https://example.com/file.iso', 'bytes_downloaded': 1024}
        self.resume_manager.save_resume_info(info)
        
        loaded_info = self.resume_manager.get_resume_info()
        self.assertEqual(loaded_info['url'], info['url'])
        self.assertEqual(loaded_info['bytes_downloaded'], info['bytes_downloaded'])
    
    def test_cleanup(self):
        """Test cleanup of temporary files."""
        # Create temporary files
        with open(self.resume_manager.temp_path, 'wb') as f:
            f.write(b'temp data')
        with open(self.resume_manager.checksum_path, 'w') as f:
            f.write('checksum')
        with open(self.resume_manager.resume_info_path, 'w') as f:
            f.write('{}')
        
        # Clean up
        self.resume_manager.cleanup()
        
        # Verify files are removed
        self.assertFalse(os.path.exists(self.resume_manager.temp_path))
        self.assertFalse(os.path.exists(self.resume_manager.checksum_path))
        self.assertFalse(os.path.exists(self.resume_manager.resume_info_path))
    
    def test_rename_partial_to_final(self):
        """Test renaming partial file to final destination."""
        # Create a partial file
        with open(self.resume_manager.temp_path, 'wb') as f:
            f.write(b'test data')
        
        # Rename
        result = self.resume_manager.rename_partial_to_final()
        
        # Verify
        self.assertTrue(result)
        self.assertTrue(os.path.exists(self.test_file))
        self.assertFalse(os.path.exists(self.resume_manager.temp_path))
        
        with open(self.test_file, 'rb') as f:
            self.assertEqual(f.read(), b'test data')


class TestMirrorManager(unittest.TestCase):
    """Test MirrorManager."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mirror_manager = MirrorManager()
    
    def test_add_mirror(self):
        """Test adding a mirror."""
        mirror = MirrorInfo(
            url='mirror.example.com',
            name='Example Mirror',
            country='US',
            priority=1,
            protocol='https'
        )
        
        self.mirror_manager.add_mirror(mirror)
        
        self.assertEqual(len(self.mirror_manager.mirrors), 1)
        self.assertEqual(self.mirror_manager.mirrors[0].url, 'mirror.example.com')
    
    def test_add_mirrors(self):
        """Test adding multiple mirrors."""
        mirrors = [
            MirrorInfo(url='mirror1.com', priority=2),
            MirrorInfo(url='mirror2.com', priority=1),
            MirrorInfo(url='mirror3.com', priority=3),
        ]
        
        self.mirror_manager.add_mirrors(mirrors)
        
        self.assertEqual(len(self.mirror_manager.mirrors), 3)
        # Should be sorted by priority (highest first)
        self.assertEqual(self.mirror_manager.mirrors[0].url, 'mirror3.com')
        self.assertEqual(self.mirror_manager.mirrors[1].url, 'mirror1.com')
        self.assertEqual(self.mirror_manager.mirrors[2].url, 'mirror2.com')
    
    def test_set_custom_mirrors(self):
        """Test setting custom mirrors."""
        custom_mirrors = ['https://custom1.com', 'https://custom2.com']
        self.mirror_manager.set_custom_mirrors(custom_mirrors)
        
        self.assertEqual(self.mirror_manager.custom_mirrors, custom_mirrors)
    
    def test_get_all_mirrors(self):
        """Test getting all mirror URLs."""
        mirror = MirrorInfo(url='mirror.example.com', protocol='https')
        self.mirror_manager.add_mirror(mirror)
        self.mirror_manager.set_custom_mirrors(['https://custom.com'])
        
        all_mirrors = self.mirror_manager.get_all_mirrors()
        
        self.assertIn('https://mirror.example.com', all_mirrors)
        self.assertIn('https://custom.com', all_mirrors)
    
    def test_get_best_mirror(self):
        """Test getting the best mirror."""
        # Test with custom mirrors
        self.mirror_manager.set_custom_mirrors(['https://custom.com'])
        best = self.mirror_manager.get_best_mirror('https://original.com')
        self.assertEqual(best, 'https://custom.com')
        
        # Test with built-in mirrors
        self.mirror_manager.custom_mirrors = []
        mirror = MirrorInfo(url='mirror.example.com', protocol='https')
        self.mirror_manager.add_mirror(mirror)
        best = self.mirror_manager.get_best_mirror('https://original.com')
        self.assertEqual(best, 'https://mirror.example.com')
        
        # Test with no mirrors
        self.mirror_manager.mirrors = []
        self.mirror_manager.custom_mirrors = []
        best = self.mirror_manager.get_best_mirror('https://original.com')
        self.assertEqual(best, 'https://original.com')
    
    def test_replace_url_base(self):
        """Test replacing URL base."""
        new_base = 'https://mirror.example.com'
        original_url = 'https://original.com/path/to/file.iso'
        
        replaced = self.mirror_manager.replace_url_base(original_url, new_base)
        self.assertEqual(replaced, 'https://mirror.example.com/path/to/file.iso')


class TestMirrorInfo(unittest.TestCase):
    """Test MirrorInfo dataclass."""
    
    def test_mirror_info_creation(self):
        """Test creating MirrorInfo."""
        mirror = MirrorInfo(
            url='mirror.example.com',
            name='Example Mirror',
            country='US',
            priority=1,
            protocol='https'
        )
        
        self.assertEqual(mirror.url, 'mirror.example.com')
        self.assertEqual(mirror.name, 'Example Mirror')
        self.assertEqual(mirror.country, 'US')
        self.assertEqual(mirror.priority, 1)
        self.assertEqual(mirror.protocol, 'https')
    
    def test_get_base_url(self):
        """Test getting base URL."""
        mirror = MirrorInfo(url='mirror.example.com', protocol='https')
        self.assertEqual(mirror.get_base_url(), 'https://mirror.example.com')
        
        mirror = MirrorInfo(url='mirror.example.com', protocol='http')
        self.assertEqual(mirror.get_base_url(), 'http://mirror.example.com')


class TestDownloaderResume(unittest.TestCase):
    """Test downloader resume functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.downloader = Downloader()
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.downloader.cleanup()
    
    def test_download_with_resume_enabled(self):
        """Test download with resume enabled."""
        dest_path = os.path.join(self.temp_dir, 'test.iso')
        
        # Mock the session.get to simulate a download
        with patch('requests.Session.get') as mock_get:
            mock_response = MagicMock()
            mock_response.headers = {'content-length': '1024'}
            mock_response.iter_content.return_value = [b'test data']
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value.__enter__.return_value = mock_response
            
            # Test with resume enabled
            success, message = self.downloader.download_file_sync(
                'https://example.com/test.iso',
                dest_path,
                enable_resume=True
            )
            
            # The download should work (though we're mocking it)
            self.assertIn('Downloaded', message)
    
    def test_download_with_custom_mirror(self):
        """Test download with custom mirror replacement."""
        # Create a DownloadWorker with custom mirror
        worker = DownloadWorker(
            'https://original.com/file.iso',
            '/tmp/file.iso',
            custom_mirrors=['https://mirror.com']
        )
        
        # The worker should be initialized with the mirror
        self.assertEqual(worker.custom_mirrors, ['https://mirror.com'])
        self.assertTrue(worker.enable_resume)


class TestUSBInstallerNewFeatures(unittest.TestCase):
    """Test USB installer new features."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.installer = USBInstaller()
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_installer_handles_uefi_only(self):
        """Test that installer handles UEFI-only parameter."""
        # Test that the installer accepts the new parameters without crashing
        params = {
            'install_type': 'distribution',
            'enable_uefi_only': True,
            'enable_secure_boot': True,
            'boot_options': 'quiet splash'
        }
        
        # This should not crash
        source_dir = os.path.join(self.temp_dir, 'source')
        os.makedirs(source_dir)
        
        # We're not actually testing the full installation, just parameter handling
        with patch.object(self.installer, '_prepare_installation', return_value=True):
            with patch.object(self.installer, '_copy_files_to_device', return_value=True):
                with patch.object(self.installer, '_install_bootloader', return_value=True):
                    with patch.object(self.installer, '_cleanup_installation'):
                        success, message = self.installer.install_sync(
                            source_dir, '/dev/sdb1', params
                        )
                        # Should succeed with parameter handling
                        self.assertTrue(success or 'failed' not in message.lower())
    
    def test_bootloader_methods_accept_new_params(self):
        """Test that bootloader methods accept new parameters."""
        params = {'boot_options': 'test', 'install_type': 'distribution'}
        
        # Test that methods accept the new parameters
        try:
            # These should not crash due to parameter errors
            self.installer._install_bootloader_windows('/dev/sda', params, True, True)
        except Exception as e:
            # Should not be a parameter error
            self.assertNotIn('unexpected keyword argument', str(e))
        
        try:
            self.installer._install_bootloader_macos('/dev/disk2', params, True, True)
        except Exception as e:
            self.assertNotIn('unexpected keyword argument', str(e))
        
        try:
            self.installer._install_bootloader_linux('/dev/sdb', params, True, True)
        except Exception as e:
            self.assertNotIn('unexpected keyword argument', str(e))


class TestMainWindowNewFeatures(unittest.TestCase):
    """Test main window new features."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create main window without showing it
        self.window = MainWindow()
    
    def test_new_ui_elements_exist(self):
        """Test that new UI elements exist."""
        # Check that new UI elements are present
        self.assertIsNotNone(self.window.advanced_tabs)
        self.assertIsNotNone(self.window.boot_options_edit)
        self.assertIsNotNone(self.window.uefi_only_check)
        self.assertIsNotNone(self.window.secure_boot_check)
    
    def test_tab_count(self):
        """Test that advanced tabs are present."""
        self.assertEqual(self.window.advanced_tabs.count(), 3)
        tab_texts = [self.window.advanced_tabs.tabText(i) for i in range(self.window.advanced_tabs.count())]
        self.assertIn('Persistence', tab_texts)
        self.assertIn('Boot Options', tab_texts)
        self.assertIn('Firmware', tab_texts)
    
    def test_get_installation_parameters_includes_new_fields(self):
        """Test that get_installation_parameters includes new fields."""
        # Enable advanced options
        self.window.advanced_group.setChecked(True)
        
        # Set some values
        self.window.boot_options_edit.setPlainText('quiet splash')
        self.window.uefi_only_check.setChecked(True)
        self.window.secure_boot_check.setChecked(True)
        
        params = self.window.get_installation_parameters()
        
        self.assertIn('boot_options', params)
        self.assertEqual(params['boot_options'], 'quiet splash')
        self.assertIn('enable_uefi_only', params)
        self.assertTrue(params['enable_uefi_only'])
        self.assertIn('enable_secure_boot', params)
        self.assertTrue(params['enable_secure_boot'])
    
    def test_persistence_still_works(self):
        """Test that persistence functionality still works."""
        self.window.advanced_group.setChecked(True)
        self.window.persistence_check.setChecked(True)
        self.window.persistence_size_spin.setValue(2000)
        
        params = self.window.get_installation_parameters()
        
        self.assertIn('persistence_enabled', params)
        self.assertTrue(params['persistence_enabled'])
        self.assertIn('persistence_size', params)
        self.assertEqual(params['persistence_size'], 2000)


class TestAsyncNewFeatures(unittest.IsolatedAsyncioTestCase):
    """Test async functionality for new features."""
    
    async def asyncSetUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
    
    async def asyncTearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    async def test_async_downloader_with_resume(self):
        """Test async downloader with resume support."""
        async_downloader = AsyncDownloader()
        
        # Test that it can be initialized (actual download testing would require networking)
        self.assertIsNotNone(async_downloader)


if __name__ == '__main__':
    unittest.main()