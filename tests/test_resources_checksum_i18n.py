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
        from pynetboot.resources import bootloader_path
        self.assertTrue(bootloader_path('mbr.bin').exists())

    def test_find_bundled_syslinux(self):
        from pynetboot.resources import find_bundled_syslinux
        p = find_bundled_syslinux()
        self.assertIsNotNone(p)
        self.assertIn('ubnsylnx', p.name)

    def test_ensure_executable_missing_file(self):
        from pynetboot.resources import ensure_executable
        self.assertFalse(ensure_executable('/no/such/binary'))


class TestChecksumFetch(unittest.TestCase):
    """Dynamic SHA256 fetching from published checksum files."""

    def setUp(self):
        from pynetboot.core.downloader import Downloader
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
        from pynetboot.core import i18n
        i18n.set_language('en')  # reset global state

    def test_known_language_translates(self):
        from pynetboot.core import i18n
        self.assertEqual(i18n.set_language('de'), 'de')
        self.assertEqual(i18n._('USB Drive'), 'USB-Laufwerk')
        self.assertEqual(i18n._('Hard Disk'), 'Festplatte')

    def test_locale_is_normalized(self):
        from pynetboot.core import i18n
        self.assertEqual(i18n.set_language('fr_FR.UTF-8'), 'fr')
        self.assertEqual(i18n._('USB Drive'), 'Lecteur USB')

    def test_unknown_language_falls_back_to_english(self):
        from pynetboot.core import i18n
        self.assertEqual(i18n.set_language('xx'), 'en')
        self.assertEqual(i18n._('USB Drive'), 'USB Drive')  # source verbatim

    def test_unknown_string_returns_source(self):
        from pynetboot.core import i18n
        i18n.set_language('de')
        self.assertEqual(i18n._('a string with no translation'),
                         'a string with no translation')


class TestDeviceResolution(unittest.TestCase):
    """Hardened device resolution helpers on the installer."""

    def setUp(self):
        from pynetboot.core.installer import USBInstaller
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



class TestCompanionChecksumFile(unittest.TestCase):
    """`<iso>.sha256` files name one image and often omit the name."""

    def setUp(self):
        from pynetboot.core.downloader import Downloader
        self.downloader = Downloader()

    def _fetch(self, text, iso, url):
        with patch.object(self.downloader, 'download_page_contents',
                          return_value=text):
            return self.downloader.fetch_checksum_from_url(url, iso)

    def test_a_bare_hash_in_a_companion_file_is_accepted(self):
        """TrueNAS publishes the hash alone, with no filename at all."""
        self.assertEqual(
            self._fetch('a' * 64, 'x.iso', 'https://e.test/x.iso.sha256'),
            'a' * 64)

    def test_a_companion_naming_the_dated_build_is_accepted(self):
        """openSUSE's -Current alias points at a dated snapshot."""
        text = f"{'b' * 64}  openSUSE-Tumbleweed-DVD-x86_64-Snapshot2026-Media.iso\n"
        self.assertEqual(
            self._fetch(text, 'openSUSE-Tumbleweed-DVD-x86_64-Current.iso',
                        'https://e.test/openSUSE-Tumbleweed-DVD-x86_64-Current.iso.sha256'),
            'b' * 64)

    def test_a_sums_file_listing_another_image_is_still_refused(self):
        """Otherwise the hash of the wrong image passes as verification."""
        text = f"{'c' * 64} *some-other.iso\n"
        self.assertIsNone(
            self._fetch(text, 'wanted.iso', 'https://e.test/SHA256SUMS'))

    def test_a_companion_with_several_hashes_is_refused(self):
        text = f"{'d' * 64}  a.iso\n{'e' * 64}  b.iso\n"
        self.assertIsNone(
            self._fetch(text, 'x.iso', 'https://e.test/x.iso.sha256'))


class TestOtherDigestAlgorithms(unittest.TestCase):
    """Some publishers offer no SHA256 at all.

    NetBSD publishes only SHA512 and DragonFly only MD5, so those images
    were downloaded with nothing checking them.
    """

    def setUp(self):
        from pynetboot.core.downloader import Downloader
        self.downloader = Downloader()

    def _fetch(self, text, iso, algorithm):
        with patch.object(self.downloader, 'download_page_contents',
                          return_value=text):
            return self.downloader.fetch_checksum_from_url(
                'https://e.test/SUMS', iso, algorithm)

    def test_sha512_in_bsd_layout(self):
        h = 'a' * 128
        self.assertEqual(
            self._fetch(f"SHA512 (NetBSD-10.1-amd64.iso) = {h}\n",
                        'NetBSD-10.1-amd64.iso', 'sha512'), h)

    def test_md5_in_bsd_layout(self):
        h = 'b' * 32
        text = (f"MD5 (dfly-x86_64-5.8.1_REL.img) = {'c' * 32}\n"
                f"MD5 (dfly-x86_64-6.4.2_REL.iso) = {h}\n")
        self.assertEqual(
            self._fetch(text, 'dfly-x86_64-6.4.2_REL.iso', 'md5'), h)

    def test_a_digest_of_the_wrong_width_is_not_accepted(self):
        """A SHA256 line must not satisfy a request for SHA512."""
        self.assertIsNone(
            self._fetch(f"SHA256 (x.iso) = {'d' * 64}\n", 'x.iso', 'sha512'))

    def test_verify_checksum_supports_the_new_algorithms(self):
        import hashlib, tempfile, os
        handle = tempfile.NamedTemporaryFile(delete=False)
        handle.write(b'pynetboot' * 100)
        handle.close()
        try:
            for algorithm in ('sha256', 'sha512', 'sha1', 'md5'):
                digest = getattr(hashlib, algorithm)(
                    open(handle.name, 'rb').read()).hexdigest()
                self.assertTrue(
                    self.downloader.verify_checksum(handle.name, digest, algorithm))
                self.assertFalse(
                    self.downloader.verify_checksum(
                        handle.name, '0' * len(digest), algorithm))
        finally:
            os.unlink(handle.name)


if __name__ == '__main__':
    unittest.main()
