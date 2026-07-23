"""
Tests for UNetbootin models.
"""

import unittest
import os
import sys

# Add src to path for testing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from unetbootin.models.distro import Distribution, DistributionVersion, DistributionManager
from unetbootin.models.config import ConfigManager, AppConfig


class TestDistribution(unittest.TestCase):
    """Test Distribution model."""
    
    def test_distribution_creation(self):
        """Test creating a distribution."""
        distro = Distribution(
            name="test",
            display_name="Test Distro",
            description="A test distribution",
            category="Test",
            icon="test.png",
            homepage="https://test.com"
        )
        
        self.assertEqual(distro.name, "test")
        self.assertEqual(distro.display_name, "Test Distro")
        self.assertEqual(distro.description, "A test distribution")
        self.assertEqual(distro.category, "Test")
        self.assertEqual(distro.icon, "test.png")
        self.assertEqual(distro.homepage, "https://test.com")
        self.assertEqual(len(distro.versions), 0)
    
    def test_distribution_default_display_name(self):
        """Test that display_name defaults to name."""
        distro = Distribution(name="test")
        self.assertEqual(distro.display_name, "test")
    
    def test_distribution_to_dict(self):
        """Test converting distribution to dict."""
        distro = Distribution(
            name="test",
            display_name="Test Distro",
            versions=[
                DistributionVersion(name="1.0", url="https://test.com/1.0.iso")
            ]
        )
        
        data = distro.to_dict()
        self.assertIn('name', data)
        self.assertIn('display_name', data)
        self.assertIn('versions', data)
        self.assertEqual(len(data['versions']), 1)


class TestDistributionVersion(unittest.TestCase):
    """Test DistributionVersion model."""
    
    def test_version_creation(self):
        """Test creating a distribution version."""
        version = DistributionVersion(
            name="20.04 LTS",
            url="https://test.com/20.04.iso",
            size=2500000000,
            description="Latest LTS release",
            category="LTS"
        )
        
        self.assertEqual(version.name, "20.04 LTS")
        self.assertEqual(version.url, "https://test.com/20.04.iso")
        self.assertEqual(version.size, 2500000000)
    
    def test_version_to_dict(self):
        """Test converting version to dict."""
        version = DistributionVersion(name="1.0", url="https://test.com/1.0.iso")
        data = version.to_dict()
        
        self.assertIn('name', data)
        self.assertIn('url', data)
        self.assertEqual(data['name'], "1.0")
    
    def test_version_with_checksums(self):
        """Test DistributionVersion with checksum fields."""
        version = DistributionVersion(
            name="24.04 LTS",
            url="https://test.com/24.04.iso",
            size=4500000000,
            sha256="abc123",
            sha1="def456",
            md5="ghi789"
        )
        
        self.assertEqual(version.sha256, "abc123")
        self.assertEqual(version.sha1, "def456")
        self.assertEqual(version.md5, "ghi789")
    
    def test_version_to_dict_with_checksums(self):
        """Test to_dict includes checksums when present."""
        version = DistributionVersion(
            name="24.04 LTS",
            url="https://test.com/24.04.iso",
            sha256="abc123",
            sha1="def456"
        )
        
        data = version.to_dict()
        
        self.assertIn('sha256', data)
        self.assertEqual(data['sha256'], "abc123")
        self.assertIn('sha1', data)
        self.assertEqual(data['sha1'], "def456")
    
    def test_version_to_dict_without_checksums(self):
        """Test to_dict excludes checksums when not present."""
        version = DistributionVersion(
            name="24.04 LTS",
            url="https://test.com/24.04.iso"
        )
        
        data = version.to_dict()
        
        # Checksums should not be in dict if not set
        self.assertNotIn('sha256', data)
        self.assertNotIn('sha1', data)
        self.assertNotIn('md5', data)
    
    def test_version_get_checksum_prefers_sha256(self):
        """Test get_checksum prefers SHA256."""
        version = DistributionVersion(
            name="24.04 LTS",
            url="https://test.com/24.04.iso",
            sha256="sha256_value",
            sha1="sha1_value",
            md5="md5_value"
        )
        
        # Default should be sha256
        checksum = version.get_checksum()
        self.assertEqual(checksum, "sha256_value")
        
        # Explicit types
        self.assertEqual(version.get_checksum("sha256"), "sha256_value")
        self.assertEqual(version.get_checksum("sha1"), "sha1_value")
        self.assertEqual(version.get_checksum("md5"), "md5_value")
    
    def test_version_get_checksum_fallback(self):
        """Test get_checksum falls back to available checksum."""
        version = DistributionVersion(
            name="24.04 LTS",
            url="https://test.com/24.04.iso",
            sha1="sha1_value"
        )
        
        # Should fall back to sha1 since sha256 is not set
        checksum = version.get_checksum()
        self.assertEqual(checksum, "sha1_value")
    
    def test_version_get_checksum_none_available(self):
        """Test get_checksum returns None when no checksums available."""
        version = DistributionVersion(
            name="24.04 LTS",
            url="https://test.com/24.04.iso"
        )
        
        checksum = version.get_checksum()
        self.assertIsNone(checksum)


class TestDistributionManager(unittest.TestCase):
    """Test DistributionManager."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.manager = DistributionManager()
    
    def test_get_distributions(self):
        """Test getting distributions."""
        distros = self.manager.get_distributions()
        
        self.assertIsInstance(distros, list)
        self.assertGreater(len(distros), 0)
        
        # Check that we have some known distributions
        distro_names = [d['name'] for d in distros]
        self.assertIn('ubuntu', distro_names)
        self.assertIn('debian', distro_names)
    
    def test_get_distribution(self):
        """Test getting a specific distribution."""
        distro = self.manager.get_distribution('ubuntu')
        
        self.assertIsNotNone(distro)
        self.assertEqual(distro.name, 'ubuntu')
    
    def test_get_versions(self):
        """Test getting versions for a distribution."""
        versions = self.manager.get_versions('ubuntu')
        
        self.assertIsInstance(versions, list)
        self.assertGreater(len(versions), 0)
    
    def test_get_categories(self):
        """Test getting distribution categories."""
        categories = self.manager.get_categories()
        
        self.assertIsInstance(categories, list)
        self.assertGreater(len(categories), 0)
    
    def test_get_distributions_by_category(self):
        """Test getting distributions by category."""
        ubuntu_distros = self.manager.get_distributions_by_category('Ubuntu')
        
        self.assertIsInstance(ubuntu_distros, list)
        for distro in ubuntu_distros:
            self.assertEqual(distro['category'], 'Ubuntu')
    
    def test_search_distributions(self):
        """Test searching distributions."""
        results = self.manager.search_distributions('ubuntu')
        
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)
        
        for result in results:
            self.assertTrue('ubuntu' in result['name'].lower() or 
                          'ubuntu' in result['display_name'].lower() or
                          'ubuntu' in result['description'].lower())


class TestConfigManager(unittest.TestCase):
    """Test ConfigManager."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Use a temporary directory for testing
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.config_manager = ConfigManager(config_dir=self.temp_dir)
    
    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_save_and_load(self):
        """Test saving and loading configuration."""
        # Set some values
        self.config_manager.set('lang', 'fr_FR')
        self.config_manager.set('persistence_size', 2000)
        
        # Load configuration
        config = self.config_manager.load()
        
        self.assertEqual(config.lang, 'fr_FR')
        self.assertEqual(config.persistence_size, 2000)
    
    def test_get_set(self):
        """Test get and set methods."""
        self.config_manager.set('test_value', 'test')
        value = self.config_manager.get('test_value')
        
        self.assertEqual(value, 'test')
    
    def test_default_values(self):
        """Test default configuration values."""
        config = AppConfig()
        
        self.assertEqual(config.lang, 'en_US')
        self.assertEqual(config.persistence_size, 1000)
        self.assertTrue(config.check_updates)
        self.assertFalse(config.enable_persistence)


class TestAppConfig(unittest.TestCase):
    """Test AppConfig model."""
    
    def test_to_dict(self):
        """Test converting AppConfig to dict."""
        config = AppConfig(
            lang='fr_FR',
            last_iso_path='/path/to/iso.iso',
            enable_persistence=True,
            persistence_size=2000
        )
        
        data = config.to_dict()
        
        self.assertEqual(data['lang'], 'fr_FR')
        self.assertEqual(data['last_iso_path'], '/path/to/iso.iso')
        self.assertTrue(data['enable_persistence'])
        self.assertEqual(data['persistence_size'], 2000)
    
    def test_from_dict(self):
        """Test creating AppConfig from dict."""
        data = {
            'lang': 'de_DE',
            'last_iso_path': '/path/to/other.iso',
            'persistence_size': 3000,
        }
        
        config = AppConfig.from_dict(data)
        
        self.assertEqual(config.lang, 'de_DE')
        self.assertEqual(config.last_iso_path, '/path/to/other.iso')
        self.assertEqual(config.persistence_size, 3000)
        # Check default for missing field
        self.assertFalse(config.enable_persistence)


if __name__ == '__main__':
    unittest.main()
