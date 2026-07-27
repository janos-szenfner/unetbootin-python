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

from pynetboot.core.downloader import Downloader, AsyncDownloader
from pynetboot.core.extractor import ISOExtractor, AsyncISOExtractor
from pynetboot.core.installer import USBInstaller, AsyncUSBInstaller


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
        from pynetboot import APP_VERSION
        self.assertIsNotNone(self.downloader.session)
        # Derive the expected UA from the current version so a version bump
        # doesn't break this test.
        self.assertEqual(self.downloader.session.headers['User-Agent'],
                         f'PyNetboot/{APP_VERSION}')

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

    def test_extraction_reporting_success_without_output_is_a_failure(self):
        """A backend that exits 0 but unpacks nothing must not count.

        Regression test: the backends report success from the exit code
        alone. Trusting that would copy an empty tree to the target drive
        and install a bootloader over it, reporting a completed install for
        a drive that cannot boot.
        """
        empty_dest = os.path.join(self.temp_dir, 'empty')
        os.makedirs(empty_dest, exist_ok=True)

        with patch.object(ISOExtractor, '_try_xorriso', return_value=True), \
                patch.object(ISOExtractor, '_try_7z', return_value=False), \
                patch.object(ISOExtractor, '_try_bsdtar', return_value=False), \
                patch.object(ISOExtractor, '_try_python_libs', return_value=False):
            success, message = self.extractor._extract_iso(
                '/some/file.iso', empty_dest, None, None)

        self.assertFalse(success)
        self.assertIn('xorriso', message)

    def test_extraction_falls_through_to_the_next_backend(self):
        """A backend that writes nothing must not end the chain."""
        dest = os.path.join(self.temp_dir, 'dest')
        os.makedirs(dest, exist_ok=True)

        def writes_a_file(archive, dest_dir, files, cb):
            with open(os.path.join(dest_dir, 'vmlinuz'), 'w') as handle:
                handle.write('kernel')
            return True

        with patch.object(ISOExtractor, '_try_xorriso', return_value=True), \
                patch.object(ISOExtractor, '_try_7z', side_effect=writes_a_file), \
                patch.object(ISOExtractor, '_try_bsdtar', return_value=False):
            success, _ = self.extractor._extract_iso(
                '/some/file.iso', dest, None, None)

        self.assertTrue(success)
        self.assertIn('vmlinuz', os.listdir(dest))

    def test_extraction_succeeds_when_files_are_written(self):
        """The ordinary case still passes."""
        dest = os.path.join(self.temp_dir, 'ok')
        os.makedirs(dest, exist_ok=True)

        def writes_a_file(archive, dest_dir, files, cb):
            with open(os.path.join(dest_dir, 'boot.cat'), 'w') as handle:
                handle.write('x')
            return True

        with patch.object(ISOExtractor, '_try_xorriso', side_effect=writes_a_file):
            success, message = self.extractor._extract_iso(
                '/some/file.iso', dest, None, None)

        self.assertTrue(success)
        self.assertEqual(message, "Extraction completed successfully")

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

    def test_partition_target_partitions_a_whole_disk(self):
        """A whole disk is given a partition table, and that partition used.

        Regression test: the installer used to format the whole disk as a
        partitionless "superfloppy", then write the syslinux MBR over
        sector 0 -- destroying the FAT boot sector it had just created.
        """
        self.installer.platform = 'linux'
        with patch('pynetboot.platform.linux.is_whole_disk', return_value=True), \
                patch('pynetboot.platform.linux.partition_device',
                      return_value='/dev/sdb1') as mock_partition:
            self.assertEqual(
                self.installer._partition_target('/dev/sdb'), '/dev/sdb1')
            mock_partition.assert_called_once_with('/dev/sdb')

    def test_partition_target_leaves_an_existing_partition_alone(self):
        """A caller that already passed a partition must not be repartitioned."""
        self.installer.platform = 'linux'
        with patch('pynetboot.platform.linux.is_whole_disk', return_value=False), \
                patch('pynetboot.platform.linux.partition_device') as mock_partition:
            self.assertEqual(
                self.installer._partition_target('/dev/sdb1'), '/dev/sdb1')
            mock_partition.assert_not_called()

    def test_partition_target_reports_failure(self):
        """A failed partitioning aborts preparation rather than formatting."""
        self.installer.platform = 'linux'
        with patch('pynetboot.platform.linux.is_whole_disk', return_value=True), \
                patch('pynetboot.platform.linux.partition_device',
                      return_value=None):
            self.assertIsNone(self.installer._partition_target('/dev/sdb'))

    def test_bootloader_writes_mbr_to_disk_and_syslinux_to_partition(self):
        """The two halves of the bootloader must go to different places.

        The MBR belongs in sector 0 of the disk; syslinux belongs in the
        boot sector of the partition. Sending both to the same device is
        what corrupted the filesystem.
        """
        self.installer.platform = 'linux'
        params = {'drive_type': 'USB Drive',
                  'target_partition': '/dev/sdb1',
                  'mount_point': None}

        with patch.object(self.installer, '_linux_parent_disk',
                          return_value='/dev/sdb'), \
                patch.object(self.installer, '_write_syslinux_mbr',
                             return_value=True) as mock_mbr, \
                patch.object(self.installer, '_copy_syslinux_modules'), \
                patch.object(self.installer, '_release_mount'), \
                patch('pynetboot.core.installer.find_bundled_syslinux',
                      return_value=None), \
                patch.object(self.installer, '_find_executable',
                             side_effect=lambda n: '/usr/bin/syslinux'
                             if n == 'syslinux' else None), \
                patch('subprocess.run') as mock_run:
            ok = MagicMock()
            ok.returncode = 0
            ok.stderr = ''
            mock_run.return_value = ok

            self.installer._install_bootloader_linux('/dev/sdb', params)

            mock_mbr.assert_called_once_with('/dev/sdb')
            syslinux_argv = mock_run.call_args_list[0].args[0]
            self.assertEqual(syslinux_argv[-1], '/dev/sdb1')

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
        from pynetboot.core.utils import format_size
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


class TestArchiveExtractionSafety(unittest.TestCase):
    """Archive members must never be written outside the destination."""

    def test_traversal_and_absolute_members_are_rejected(self):
        import tempfile
        from pynetboot.core.extractor import safe_archive_names

        dest = tempfile.mkdtemp()
        names = ['boot/grub.cfg', '../../etc/passwd', '/etc/shadow',
                 '../outside.txt', 'nested/dir/file.bin', 'a/../b.txt']
        safe = safe_archive_names(names, dest)

        for bad in ('../../etc/passwd', '/etc/shadow', '../outside.txt'):
            self.assertNotIn(bad, safe, f"{bad} must be rejected")
        for good in ('boot/grub.cfg', 'nested/dir/file.bin', 'a/../b.txt'):
            self.assertIn(good, safe, f"{good} must be kept")

    def test_no_unguarded_extractall_remains(self):
        """Every extractall must restrict members, as the tar path does."""
        import ast, inspect
        from pynetboot.core import extractor

        tree = ast.parse(inspect.getsource(extractor))
        unguarded = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ('extractall', 'extract')):
                kwargs = {kw.arg for kw in node.keywords}
                # tar: filter='data'; others must pass validated members/targets
                if not kwargs & {'filter', 'members', 'targets'}:
                    unguarded.append(node.lineno)
        self.assertEqual(
            unguarded, [],
            f"extraction without member validation at lines {unguarded}")
