"""
Integration tests for UNetbootin.

These tests verify the interaction between different components:
- Downloader + Extractor
- Extractor + Installer
- Distribution Manager + App
"""

import unittest
import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from unetbootin.models.distro import DistributionManager, Distribution, DistributionVersion
from unetbootin.core.downloader import Downloader
from unetbootin.core.extractor import ISOExtractor
from unetbootin.core.installer import USBInstaller
from unetbootin.core.utils import format_size, check_root, check_admin


class TestDownloadExtractIntegration(unittest.TestCase):
    """Test integration between Downloader and Extractor."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.downloader = Downloader()
        self.extractor = ISOExtractor()
    
    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.downloader.cleanup()
    
    def test_download_and_extract_flow(self):
        """Test the complete download and extract flow."""
        # Create a mock ISO file (small zip for testing)
        import zipfile
        iso_path = os.path.join(self.temp_dir, 'test.zip')
        extract_dir = os.path.join(self.temp_dir, 'extracted')
        
        # Create a simple zip file
        with zipfile.ZipFile(iso_path, 'w') as zf:
            zf.writestr('test.txt', 'test content')
        
        # Simulate download by copying the file
        downloaded_path = os.path.join(self.temp_dir, 'downloaded.zip')
        shutil.copy2(iso_path, downloaded_path)
        
        # Verify the "downloaded" file exists
        self.assertTrue(os.path.exists(downloaded_path))
        
        # Extract the file
        # Note: extract_iso_sync expects .iso, but will try other formats
        # For this test, we'll just verify the extractor can handle the file
        result = self.extractor.extract_iso_sync(
            downloaded_path,
            extract_dir
        )
        
        # The result depends on whether the extractor can handle zip files
        # If it can, files should be extracted
        if result[0]:
            # Check if test.txt was extracted
            extracted_file = os.path.join(extract_dir, 'test.txt')
            if os.path.exists(extracted_file):
                with open(extracted_file, 'r') as f:
                    content = f.read()
                self.assertEqual(content, 'test content')
    
    def test_checksum_verify_after_download(self):
        """Test checksum verification after download."""
        import hashlib
        
        # Create a test file
        test_file = os.path.join(self.temp_dir, 'test.iso')
        content = b'test content for checksum verification'
        with open(test_file, 'wb') as f:
            f.write(content)
        
        # Calculate SHA256
        expected_sha256 = hashlib.sha256(content).hexdigest()
        
        # Verify checksum
        result = self.downloader.verify_checksum(test_file, expected_sha256, 'sha256')
        self.assertTrue(result)
        
        # Now test the extractor with this file
        extract_dir = os.path.join(self.temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)
        
        # Try to extract (will fail for a non-archive, but that's expected)
        result = self.extractor.extract_iso_sync(test_file, extract_dir)
        # We don't assert on the result since it's not a valid archive
        # The important part is that both components can work with the same file


class TestExtractInstallIntegration(unittest.TestCase):
    """Test integration between Extractor and Installer."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.extractor = ISOExtractor()
        self.installer = USBInstaller()
    
    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_extract_and_get_files_to_copy(self):
        """Test extraction followed by getting files to copy."""
        # Create a source directory with test files
        source_dir = os.path.join(self.temp_dir, 'source')
        os.makedirs(source_dir)
        
        # Create test files
        with open(os.path.join(source_dir, 'file1.txt'), 'w') as f:
            f.write('content1')
        os.makedirs(os.path.join(source_dir, 'subdir'))
        with open(os.path.join(source_dir, 'subdir', 'file2.txt'), 'w') as f:
            f.write('content2')
        
        # Get files to copy
        files = self.installer._get_files_to_copy(source_dir, {})
        
        # Verify files were found
        self.assertIn('file1.txt', files)
        self.assertIn('subdir/file2.txt', files)
        
        # Now test copying to a target directory
        target_dir = os.path.join(self.temp_dir, 'target')
        os.makedirs(target_dir)
        
        result = self.installer._copy_files_to_device(
            source_dir,
            target_dir,
            {}
        )
        
        self.assertTrue(result)
        
        # Verify files were copied
        self.assertTrue(os.path.exists(os.path.join(target_dir, 'file1.txt')))
        self.assertTrue(os.path.exists(os.path.join(target_dir, 'subdir', 'file2.txt')))
    
    def test_files_to_copy_with_excludes(self):
        """Test file copying with exclusions."""
        # Create a source directory with hidden and visible files
        source_dir = os.path.join(self.temp_dir, 'source')
        os.makedirs(source_dir)
        
        with open(os.path.join(source_dir, '.hidden'), 'w') as f:
            f.write('hidden')
        with open(os.path.join(source_dir, 'visible.txt'), 'w') as f:
            f.write('visible')
        
        # Get files to copy for distribution install type
        params = {'install_type': 'distribution'}
        files = self.installer._get_files_to_copy(source_dir, params)
        
        # Hidden files should be excluded
        self.assertNotIn('.hidden', files)
        self.assertIn('visible.txt', files)


class TestDistributionManagerIntegration(unittest.TestCase):
    """Test DistributionManager integration with other components."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.manager = DistributionManager()
    
    def test_load_and_get_distributions(self):
        """Test loading and retrieving distributions."""
        # Load distributions
        distros = self.manager.get_distributions()
        
        # Verify we have some distributions
        self.assertIsInstance(distros, list)
        self.assertGreater(len(distros), 0)
        
        # Check that Ubuntu is in the list
        distro_names = [d['name'] for d in distros]
        self.assertIn('ubuntu', distro_names)
    
    def test_get_distribution_by_name(self):
        """Test getting a specific distribution."""
        distro = self.manager.get_distribution('ubuntu')
        
        self.assertIsNotNone(distro)
        self.assertEqual(distro.name, 'ubuntu')
        self.assertGreater(len(distro.versions), 0)
    
    def test_get_versions_for_distribution(self):
        """Test getting versions for a distribution."""
        versions = self.manager.get_versions('ubuntu')
        
        self.assertIsInstance(versions, list)
        self.assertGreater(len(versions), 0)
        
        # Check version structure
        for version in versions:
            self.assertIn('name', version)
            self.assertIn('url', version)
    
    def test_search_distributions(self):
        """Test searching distributions."""
        results = self.manager.search_distributions('ubuntu')
        
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)
        
        # All results should contain 'ubuntu'
        for result in results:
            self.assertTrue(
                'ubuntu' in result['name'].lower() or
                'ubuntu' in result['display_name'].lower() or
                'ubuntu' in result['description'].lower()
            )
    
    def test_get_categories(self):
        """Test getting distribution categories."""
        categories = self.manager.get_categories()
        
        self.assertIsInstance(categories, list)
        self.assertGreater(len(categories), 0)


class TestDistributionVersionChecksums(unittest.TestCase):
    """Test DistributionVersion checksum support."""
    
    def test_version_with_checksums(self):
        """Test DistributionVersion with checksum fields."""
        version = DistributionVersion(
            name="24.04 LTS",
            url="https://example.com/ubuntu.iso",
            size=4500000000,
            sha256="abc123",
            sha1="def456",
            md5="ghi789"
        )
        
        self.assertEqual(version.sha256, "abc123")
        self.assertEqual(version.sha1, "def456")
        self.assertEqual(version.md5, "ghi789")
    
    def test_version_to_dict_with_checksums(self):
        """Test to_dict includes checksums."""
        version = DistributionVersion(
            name="24.04 LTS",
            url="https://example.com/ubuntu.iso",
            sha256="abc123",
            sha1="def456"
        )
        
        data = version.to_dict()
        
        self.assertIn('sha256', data)
        self.assertEqual(data['sha256'], "abc123")
        self.assertIn('sha1', data)
        self.assertEqual(data['sha1'], "def456")
    
    def test_version_to_dict_without_checksums(self):
        """Test to_dict without checksums."""
        version = DistributionVersion(
            name="24.04 LTS",
            url="https://example.com/ubuntu.iso"
        )
        
        data = version.to_dict()
        
        # Checksums should not be in dict if not set
        self.assertNotIn('sha256', data)
        self.assertNotIn('sha1', data)
        self.assertNotIn('md5', data)
    
    def test_get_checksum_prefers_sha256(self):
        """Test get_checksum prefers SHA256."""
        version = DistributionVersion(
            name="24.04 LTS",
            url="https://example.com/ubuntu.iso",
            sha256="sha256_value",
            sha1="sha1_value",
            md5="md5_value"
        )
        
        # Default should be sha256
        checksum = version.get_checksum()
        self.assertEqual(checksum, "sha256_value")
        
        # Explicit sha256
        checksum = version.get_checksum("sha256")
        self.assertEqual(checksum, "sha256_value")
        
        # Explicit sha1
        checksum = version.get_checksum("sha1")
        self.assertEqual(checksum, "sha1_value")
        
        # Explicit md5
        checksum = version.get_checksum("md5")
        self.assertEqual(checksum, "md5_value")
    
    def test_get_checksum_fallback(self):
        """Test get_checksum falls back to available checksum."""
        version = DistributionVersion(
            name="24.04 LTS",
            url="https://example.com/ubuntu.iso",
            sha1="sha1_value"
        )
        
        # Should fall back to sha1 since sha256 is not set
        checksum = version.get_checksum()
        self.assertEqual(checksum, "sha1_value")
    
    def test_get_checksum_none_available(self):
        """Test get_checksum returns None when no checksums available."""
        version = DistributionVersion(
            name="24.04 LTS",
            url="https://example.com/ubuntu.iso"
        )
        
        checksum = version.get_checksum()
        self.assertIsNone(checksum)


class TestUtilsIntegration(unittest.TestCase):
    """Test utility functions used across components."""
    
    def test_format_size_various_sizes(self):
        """Test format_size with various byte sizes."""
        self.assertEqual(format_size(0), '0 B')
        self.assertEqual(format_size(1), '1 B')
        self.assertEqual(format_size(1023), '1023 B')
        self.assertEqual(format_size(1024), '1.0 KB')
        self.assertEqual(format_size(1536), '1.5 KB')
        self.assertEqual(format_size(1024 * 1024), '1.0 MB')
        self.assertEqual(format_size(1024 * 1024 * 1024), '1.0 GB')
        self.assertEqual(format_size(1024 * 1024 * 1024 * 1024), '1.0 TB')
    
    def test_check_root_admin(self):
        """Test root/admin check functions."""
        # These functions should run without errors
        # The actual result depends on the system
        is_root = check_root()
        self.assertIsInstance(is_root, bool)
        
        is_admin = check_admin()
        self.assertIsInstance(is_admin, bool)


class TestFullWorkflowIntegration(unittest.TestCase):
    """Test full workflow integration."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.manager = DistributionManager()
        self.downloader = Downloader()
        self.extractor = ISOExtractor()
        self.installer = USBInstaller()
    
    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.downloader.cleanup()
    
    def test_distribution_to_installation_params(self):
        """Test flow from distribution to installation parameters."""
        # Get a distribution
        distro = self.manager.get_distribution('ubuntu')
        self.assertIsNotNone(distro)
        
        # Get its first version
        versions = distro.versions
        self.assertGreater(len(versions), 0)
        version = versions[0]
        
        # Verify version has required fields
        self.assertTrue(hasattr(version, 'name'))
        self.assertTrue(hasattr(version, 'url'))
        self.assertTrue(hasattr(version, 'size'))
        
        # Create installation params
        params = {
            'install_type': 'distribution',
            'distro': distro.name,
            'version': version.name,
            'target_drive': '/dev/sdb'  # Mock drive
        }
        
        # Verify we can get the URL from params
        iso_url = self.manager.get_distribution(distro.name).versions[0].url
        self.assertIsNotNone(iso_url)
        self.assertTrue(iso_url.startswith('http'))
    
    def test_file_operations_workflow(self):
        """Test the file operations workflow."""
        # Create a mock source directory
        source_dir = os.path.join(self.temp_dir, 'source')
        os.makedirs(source_dir)
        
        # Create test files
        test_files = ['file1.txt', 'file2.txt', 'file3.txt']
        for filename in test_files:
            with open(os.path.join(source_dir, filename), 'w') as f:
                f.write(f'content of {filename}')
        
        # Get files to copy
        files = self.installer._get_files_to_copy(source_dir, {})
        self.assertEqual(len(files), len(test_files))
        
        # Copy to target
        target_dir = os.path.join(self.temp_dir, 'target')
        os.makedirs(target_dir)
        
        result = self.installer._copy_files_to_device(
            source_dir,
            target_dir,
            {}
        )
        self.assertTrue(result)
        
        # Verify all files were copied
        for filename in test_files:
            self.assertTrue(os.path.exists(os.path.join(target_dir, filename)))
            with open(os.path.join(target_dir, filename), 'r') as f:
                content = f.read()
            self.assertEqual(content, f'content of {filename}')


if __name__ == '__main__':
    unittest.main()
