"""
Unit tests for core functionality: downloader, extractor, installer.
"""

import unittest
import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from unetbootin.core.downloader import Downloader, AsyncDownloader
from unetbootin.core.extractor import ISOExtractor, AsyncISOExtractor
from unetbootin.core.installer import USBInstaller, AsyncUSBInstaller


class TestDownloader(unittest.TestCase):
    """Test Downloader class."""

    def setUp(self):
        """Set up test fixtures."""
        self.downloader = Downloader()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.downloader.cleanup()

    def test_downloader_initialization(self):
        """Test downloader initialization."""
        self.assertIsNotNone(self.downloader.session)
        self.assertEqual(self.downloader.session.headers['User-Agent'], 'UNetbootin/0.1.0')

    def test_get_version(self):
        """Test version retrieval."""
        version = self.downloader.get_version()
        self.assertIsInstance(version, str)

    def test_get_remote_file_size_success(self):
        """Test getting remote file size for a valid URL."""
        # Mock requests to avoid actual network calls
        with patch('requests.Session.head') as mock_head:
            mock_response = MagicMock()
            mock_response.headers = {'content-length': '1024'}
            mock_response.status_code = 200
            mock_head.return_value = mock_response

            size = self.downloader.get_remote_file_size('https://example.com/file.iso')
            self.assertEqual(size, 1024)

    def test_get_remote_file_size_failure(self):
        """Test getting remote file size for an invalid URL."""
        import requests
        with patch('requests.Session.head') as mock_head:
            # requests raises RequestException subclasses on failure
            mock_head.side_effect = requests.exceptions.ConnectionError(
                "Connection failed")

            size = self.downloader.get_remote_file_size('https://example.com/invalid.iso')
            self.assertIsNone(size)

    def test_verify_checksum_sha256(self):
        """Test SHA256 checksum verification."""
        # Create a test file
        test_file = os.path.join(self.temp_dir, 'test.txt')
        with open(test_file, 'w') as f:
            f.write('test content')

        # Calculate expected checksum
        import hashlib
        expected_sha256 = hashlib.sha256(b'test content').hexdigest()

        # Verify checksum
        result = self.downloader.verify_checksum(test_file, expected_sha256, 'sha256')
        self.assertTrue(result)

    def test_verify_checksum_sha1(self):
        """Test SHA1 checksum verification."""
        test_file = os.path.join(self.temp_dir, 'test.txt')
        with open(test_file, 'w') as f:
            f.write('test content')

        import hashlib
        expected_sha1 = hashlib.sha1(b'test content').hexdigest()

        result = self.downloader.verify_checksum(test_file, expected_sha1, 'sha1')
        self.assertTrue(result)

    def test_verify_checksum_md5(self):
        """Test MD5 checksum verification."""
        test_file = os.path.join(self.temp_dir, 'test.txt')
        with open(test_file, 'w') as f:
            f.write('test content')

        import hashlib
        expected_md5 = hashlib.md5(b'test content').hexdigest()

        result = self.downloader.verify_checksum(test_file, expected_md5, 'md5')
        self.assertTrue(result)

    def test_verify_checksum_failure(self):
        """Test checksum verification with wrong checksum."""
        test_file = os.path.join(self.temp_dir, 'test.txt')
        with open(test_file, 'w') as f:
            f.write('test content')

        result = self.downloader.verify_checksum(test_file, 'wrong_checksum', 'sha256')
        self.assertFalse(result)

    def test_format_size(self):
        """Test size formatting."""
        # Test various sizes
        self.assertEqual(self.downloader.format_size(0), '0 B')
        self.assertEqual(self.downloader.format_size(512), '512 B')
        self.assertEqual(self.downloader.format_size(1024), '1.0 KB')
        self.assertEqual(self.downloader.format_size(1024 * 1024), '1.0 MB')
        self.assertEqual(self.downloader.format_size(1024 * 1024 * 1024), '1.0 GB')


class TestAsyncDownloader(unittest.IsolatedAsyncioTestCase):
    """Test AsyncDownloader class."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        self.async_downloader = AsyncDownloader()
        self.temp_dir = tempfile.mkdtemp()

    async def asyncTearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_async_downloader_initialization(self):
        """Test async downloader initialization."""
        self.assertIsNotNone(self.async_downloader.user_agent)

    async def test_get_remote_file_size_async(self):
        """Test async remote file size retrieval."""
        # Mock the sync method
        with patch.object(Downloader, 'get_remote_file_size', return_value=1024):
            size = await self.async_downloader.get_remote_file_size_async('https://example.com/file.iso')
            self.assertEqual(size, 1024)

    async def test_verify_checksum_async(self):
        """Test async checksum verification."""
        # Create a test file
        test_file = os.path.join(self.temp_dir, 'test.txt')
        with open(test_file, 'w') as f:
            f.write('test content')

        import hashlib
        expected_sha256 = hashlib.sha256(b'test content').hexdigest()

        with patch.object(Downloader, 'verify_checksum', return_value=True):
            result = await self.async_downloader.verify_checksum_async(
                test_file, expected_sha256, 'sha256'
            )
            self.assertTrue(result)


class TestExtractor(unittest.TestCase):
    """Test ISOExtractor class."""

    def setUp(self):
        """Set up test fixtures."""
        self.extractor = ISOExtractor()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_extractor_initialization(self):
        """Test extractor initialization."""
        self.assertIn('.iso', self.extractor.supported_extensions)
        self.assertIn('.zip', self.extractor.supported_extensions)
        self.assertIn('.7z', self.extractor.supported_extensions)

    def test_get_supported_extensions(self):
        """Test getting supported extensions."""
        extensions = self.extractor.get_supported_extensions()
        self.assertIsInstance(extensions, list)
        self.assertIn('.iso', extensions)

    def test_extract_iso_sync_nonexistent_file(self):
        """Test extraction with non-existent file."""
        result = self.extractor.extract_iso_sync(
            '/nonexistent/file.iso',
            self.temp_dir
        )
        self.assertFalse(result[0])  # success should be False

    def test_get_files_to_copy(self):
        """Test getting list of files to copy."""
        # Create a test directory structure
        test_dir = os.path.join(self.temp_dir, 'test_extract')
        os.makedirs(test_dir)

        # Create some test files
        with open(os.path.join(test_dir, 'file1.txt'), 'w') as f:
            f.write('content1')
        os.makedirs(os.path.join(test_dir, 'subdir'))
        with open(os.path.join(test_dir, 'subdir', 'file2.txt'), 'w') as f:
            f.write('content2')

        files = self.extractor._get_files_to_copy(test_dir, {})
        self.assertIn('file1.txt', files)
        self.assertIn('subdir/file2.txt', files)

    def test_get_files_to_copy_excludes_hidden(self):
        """Test that hidden files are excluded."""
        test_dir = os.path.join(self.temp_dir, 'test_hidden')
        os.makedirs(test_dir)

        with open(os.path.join(test_dir, '.hidden'), 'w') as f:
            f.write('hidden content')
        with open(os.path.join(test_dir, 'visible.txt'), 'w') as f:
            f.write('visible content')

        files = self.extractor._get_files_to_copy(test_dir, {})
        self.assertNotIn('.hidden', files)
        self.assertIn('visible.txt', files)


class TestAsyncExtractor(unittest.IsolatedAsyncioTestCase):
    """Test AsyncISOExtractor class."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        self.async_extractor = AsyncISOExtractor()
        self.temp_dir = tempfile.mkdtemp()

    async def asyncTearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_async_extractor_initialization(self):
        """Test async extractor initialization."""
        self.assertIn('.iso', self.async_extractor.supported_extensions)

    async def test_extract_iso_async_nonexistent_file(self):
        """Test async extraction with non-existent file."""
        # Mock the sync extractor
        with patch.object(ISOExtractor, 'extract_iso_sync', return_value=(False, 'File not found')):
            result = await self.async_extractor.extract_iso_async(
                '/nonexistent/file.iso',
                self.temp_dir
            )
            self.assertFalse(result[0])


class TestInstaller(unittest.TestCase):
    """Test USBInstaller class."""

    def setUp(self):
        """Set up test fixtures."""
        self.installer = USBInstaller()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_installer_initialization(self):
        """Test installer initialization."""
        self.assertEqual(self.installer.platform, sys.platform)

    def test_validate_target_device_invalid(self):
        """Test validation of invalid target device."""
        # Unix-like systems
        if sys.platform != 'win32':
            result = self.installer._validate_target_device('/nonexistent/device')
            self.assertFalse(result)

    def test_get_files_to_copy(self):
        """Test getting files to copy."""
        # Create a source directory with test files
        source_dir = os.path.join(self.temp_dir, 'source')
        os.makedirs(source_dir)

        with open(os.path.join(source_dir, 'file1.txt'), 'w') as f:
            f.write('content1')
        with open(os.path.join(source_dir, 'file2.txt'), 'w') as f:
            f.write('content2')

        files = self.installer._get_files_to_copy(source_dir, {})
        self.assertIn('file1.txt', files)
        self.assertIn('file2.txt', files)

    def test_copy_files_to_device_success(self):
        """Test copying files to device (using temp dir as mock device)."""
        # Create source directory with test files
        source_dir = os.path.join(self.temp_dir, 'source')
        os.makedirs(source_dir)

        with open(os.path.join(source_dir, 'file1.txt'), 'w') as f:
            f.write('content1')

        # Use another temp dir as the target device
        target_device = os.path.join(self.temp_dir, 'target')
        os.makedirs(target_device)

        result = self.installer._copy_files_to_device(
            source_dir,
            target_device,
            {}
        )
        self.assertTrue(result)

        # Verify file was copied
        self.assertTrue(os.path.exists(os.path.join(target_device, 'file1.txt')))

    def test_copy_files_to_device_failure(self):
        """Test copying files to non-existent device."""
        source_dir = os.path.join(self.temp_dir, 'source')
        os.makedirs(source_dir)

        with open(os.path.join(source_dir, 'file1.txt'), 'w') as f:
            f.write('content1')

        # Target device doesn't exist and can't be created
        result = self.installer._copy_files_to_device(
            source_dir,
            '/nonexistent/target/device',
            {}
        )
        self.assertFalse(result)

    def test_format_size(self):
        """Test size formatting from utils (used by installer)."""
        from unetbootin.core.utils import format_size
        self.assertEqual(format_size(0), '0 B')
        self.assertEqual(format_size(1024), '1.0 KB')
        self.assertEqual(format_size(1024 * 1024), '1.0 MB')


class TestAsyncInstaller(unittest.IsolatedAsyncioTestCase):
    """Test AsyncUSBInstaller class."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        self.async_installer = AsyncUSBInstaller()
        self.temp_dir = tempfile.mkdtemp()

    async def asyncTearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_async_installer_initialization(self):
        """Test async installer initialization."""
        self.assertEqual(self.async_installer.platform, sys.platform)

    async def test_install_async(self):
        """Test async installation."""
        # Create a simple test case
        source_dir = os.path.join(self.temp_dir, 'source')
        os.makedirs(source_dir)
        with open(os.path.join(source_dir, 'test.txt'), 'w') as f:
            f.write('test')

        target_dir = os.path.join(self.temp_dir, 'target')

        # Mock the sync installer
        with patch.object(
            USBInstaller,
            'install_sync',
            return_value=(True, 'Success')
        ):
            result = await self.async_installer.install_async(
                source_dir,
                target_dir,
                {}
            )
            self.assertTrue(result[0])


# NOTE: TestDownloadWorker and TestExtractWorker were removed. They tested
# the Qt-based DownloadWorker/ExtractWorker QThread classes, which no longer
# exist after the migration from PySide6 to PySimpleGUI. Cancellation is now
# handled via the `cancel_check` callback on the *_sync download/extract
# methods (see TestDownloader), so no equivalent worker classes remain.


if __name__ == '__main__':
    unittest.main()
