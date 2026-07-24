"""Tests for the resource resolver, bundled bootloader lookup, dynamic
checksum fetching, hardened device resolution, and the i18n layer.
"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestResourceResolver(unittest.TestCase):
    """The bundled resource resolver + bootloader lookup."""

    def test_resource_path_finds_bundled_mbr(self):
        from unetbootin.resources import bootloader_path
        self.assertTrue(bootloader_path('mbr.bin').exists())

    def test_find_bundled_syslinux(self):
        from unetbootin.resources import find_bundled_syslinux
        p = find_bundled_syslinux()
        self.assertIsNotNone(p)
        self.assertIn('ubnsylnx', p.name)

    def test_ensure_executable_missing_file(self):
        from unetbootin.resources import ensure_executable
        self.assertFalse(ensure_executable('/no/such/binary'))


class TestChecksumFetch(unittest.TestCase):
    """Dynamic SHA256 fetching from published checksum files."""

    def setUp(self):
        from unetbootin.core.downloader import Downloader
        self.downloader = Downloader()

    def _fetch(self, text, iso):
        with patch.object(self.downloader, 'download_page_contents',
                          return_value=text):
            return self.downloader.fetch_checksum_from_url(
                'https://example.com/SHA256SUMS', iso)

    def test_coreutils_format_with_star_marker(self):
        h = 'a' * 64
        text = f"{h} *ubuntu-24.04.4-desktop-amd64.iso\n" \
               f"{'b'*64} *ubuntu-24.04.4-live-server-amd64.iso\n"
        self.assertEqual(self._fetch(text, 'ubuntu-24.04.4-desktop-amd64.iso'), h)

    def test_coreutils_format_double_space(self):
        h = 'c' * 64
        text = f"{h}  debian-13.6.0-amd64-DVD-1.iso\n"
        self.assertEqual(self._fetch(text, 'debian-13.6.0-amd64-DVD-1.iso'), h)

    def test_bsd_fedora_format(self):
        h = 'd' * 64
        text = ("# Comment\nHash: SHA256\n\n"
                f"SHA256 (Fedora-Everything-netinst-x86_64-44-1.7.iso) = {h}\n")
        self.assertEqual(
            self._fetch(text, 'Fedora-Everything-netinst-x86_64-44-1.7.iso'), h)

    def test_no_match_returns_none(self):
        text = f"{'e'*64} *some-other.iso\n"
        self.assertIsNone(self._fetch(text, 'wanted.iso'))

    def test_empty_document_returns_none(self):
        with patch.object(self.downloader, 'download_page_contents',
                          return_value=None):
            self.assertIsNone(self.downloader.fetch_checksum_from_url(
                'https://example.com/SHA256SUMS', 'x.iso'))


class TestI18n(unittest.TestCase):
    """The translation layer that parses the bundled .ts catalogs."""

    def tearDown(self):
        from unetbootin.core import i18n
        i18n.set_language('en')  # reset global state

    def test_known_language_translates(self):
        from unetbootin.core import i18n
        self.assertEqual(i18n.set_language('de'), 'de')
        self.assertEqual(i18n._('USB Drive'), 'USB-Laufwerk')
        self.assertEqual(i18n._('Hard Disk'), 'Festplatte')

    def test_locale_is_normalized(self):
        from unetbootin.core import i18n
        self.assertEqual(i18n.set_language('fr_FR.UTF-8'), 'fr')
        self.assertEqual(i18n._('USB Drive'), 'Lecteur USB')

    def test_unknown_language_falls_back_to_english(self):
        from unetbootin.core import i18n
        self.assertEqual(i18n.set_language('xx'), 'en')
        self.assertEqual(i18n._('USB Drive'), 'USB Drive')  # source verbatim

    def test_unknown_string_returns_source(self):
        from unetbootin.core import i18n
        i18n.set_language('de')
        self.assertEqual(i18n._('a string with no translation'),
                         'a string with no translation')


class TestDeviceResolution(unittest.TestCase):
    """Hardened device resolution helpers on the installer."""

    def setUp(self):
        from unetbootin.core.installer import USBInstaller
        self.installer = USBInstaller.__new__(USBInstaller)

    def test_linux_parent_disk_uses_pkname(self):
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='sdb\n')
            self.assertEqual(
                self.installer._linux_parent_disk('/dev/sdb1'), '/dev/sdb')

    def test_linux_parent_disk_whole_disk(self):
        with patch('subprocess.run') as mock_run:
            # A whole disk has no pkname -> empty output; device returned as-is
            mock_run.return_value = MagicMock(returncode=0, stdout='\n')
            self.assertEqual(
                self.installer._linux_parent_disk('/dev/sdb'), '/dev/sdb')

    @unittest.skipIf(sys.platform != 'darwin', 'macOS-only')
    def test_macos_whole_disk_uses_parent(self):
        import plistlib
        payload = plistlib.dumps({'ParentWholeDisk': 'disk4',
                                  'DeviceIdentifier': 'disk4s1'}).decode()
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=payload)
            self.assertEqual(
                self.installer._macos_whole_disk('/dev/disk4s1'), '/dev/disk4')

    @unittest.skipIf(sys.platform != 'darwin', 'macOS-only')
    def test_macos_data_partition_skips_efi(self):
        import plistlib
        payload = plistlib.dumps({'AllDisksAndPartitions': [{
            'DeviceIdentifier': 'disk4',
            'Partitions': [
                {'DeviceIdentifier': 'disk4s1', 'Content': 'EFI'},
                {'DeviceIdentifier': 'disk4s2', 'Content': 'Microsoft Basic Data'},
            ],
        }]}).decode()
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=payload)
            self.assertEqual(
                self.installer._macos_data_partition('/dev/disk4'), 'disk4s2')


if __name__ == '__main__':
    unittest.main()
