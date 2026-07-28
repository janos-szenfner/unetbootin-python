"""Tests for the native file and folder pickers.

The Linux path is exercised on any platform by faking the platform check,
so these do not depend on the machine running them.
"""

import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from pynetboot.ui import native_dialogs as nd


def reply(returncode=0, stdout=''):
    return MagicMock(returncode=returncode, stdout=stdout, stderr='')


def only(command):
    """Pretend `command` is the sole chooser installed."""
    return lambda name: f'/usr/bin/{name}' if name == command else None


class TestNativeChooserSelection(unittest.TestCase):

    def setUp(self):
        patcher = patch.object(nd, '_tk_is_native', return_value=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_zenity_is_asked_for_a_directory(self):
        with patch.object(nd, '_available', side_effect=only('zenity')), \
                patch('subprocess.run',
                      return_value=reply(0, '/home/u/ISOs\n')) as run:
            self.assertEqual(
                nd.ask_directory('Select ISO folder', '/home/u/Downloads'),
                '/home/u/ISOs')

        argv = run.call_args.args[0]
        self.assertEqual(argv[0], 'zenity')
        self.assertIn('--directory', argv)
        # A trailing slash is what makes zenity open inside the folder
        # rather than selecting it.
        self.assertIn('--filename=/home/u/Downloads/', argv)

    def test_zenity_is_asked_for_a_file_without_directory_flag(self):
        with patch.object(nd, '_available', side_effect=only('zenity')), \
                patch('subprocess.run',
                      return_value=reply(0, '/home/u/a.iso\n')) as run:
            self.assertEqual(nd.ask_open_filename('Pick'), '/home/u/a.iso')
        self.assertNotIn('--directory', run.call_args.args[0])

    def test_kdialog_is_used_on_kde(self):
        with patch.object(nd, '_available', side_effect=only('kdialog')), \
                patch('subprocess.run',
                      return_value=reply(0, '/srv/iso\n')) as run:
            self.assertEqual(nd.ask_directory('t', '/start'), '/srv/iso')

        argv = run.call_args.args[0]
        self.assertEqual(argv[:3], ['kdialog', '--getexistingdirectory', '/start'])

    def test_qarma_stands_in_for_zenity(self):
        with patch.object(nd, '_available', side_effect=only('qarma')), \
                patch('subprocess.run',
                      return_value=reply(0, '/data\n')) as run:
            self.assertEqual(nd.ask_directory('t'), '/data')
        self.assertEqual(run.call_args.args[0][0], 'qarma')

    def test_cancelling_does_not_reopen_the_tk_dialog(self):
        """Cancel is an answer, not a failure.

        Falling back here would show the dated Tk chooser every time
        someone dismissed the native one.
        """
        with patch.object(nd, '_available', side_effect=only('zenity')), \
                patch('subprocess.run', return_value=reply(1, '')), \
                patch('tkinter.filedialog.askdirectory') as tk_dialog:
            self.assertIsNone(nd.ask_directory('t'))
            tk_dialog.assert_not_called()

    def test_tk_is_used_when_no_chooser_is_installed(self):
        with patch.object(nd, '_available', return_value=None), \
                patch('tkinter.filedialog.askdirectory',
                      return_value='/tk/pick') as tk_dialog:
            self.assertEqual(nd.ask_directory('t'), '/tk/pick')
            tk_dialog.assert_called_once()

    def test_tk_is_used_when_the_chooser_cannot_run(self):
        with patch.object(nd, '_available', side_effect=only('zenity')), \
                patch('subprocess.run', side_effect=OSError('boom')), \
                patch('tkinter.filedialog.askdirectory',
                      return_value='/tk/pick') as tk_dialog:
            self.assertEqual(nd.ask_directory('t'), '/tk/pick')
            tk_dialog.assert_called_once()

    def test_tk_is_used_when_the_chooser_hangs(self):
        with patch.object(nd, '_available', side_effect=only('zenity')), \
                patch('subprocess.run',
                      side_effect=subprocess.TimeoutExpired('zenity', 1)), \
                patch('tkinter.filedialog.askdirectory',
                      return_value='/tk/pick') as tk_dialog:
            self.assertEqual(nd.ask_directory('t'), '/tk/pick')
            tk_dialog.assert_called_once()


class TestPlatformRouting(unittest.TestCase):

    def test_windows_and_macos_keep_the_os_dialogs(self):
        """Tk already hands these to the OS on win32 and aqua."""
        for platform in ('win32', 'darwin'):
            with patch.object(nd.sys, 'platform', platform):
                self.assertTrue(nd._tk_is_native())

    def test_linux_does_not(self):
        with patch.object(nd.sys, 'platform', 'linux'):
            self.assertFalse(nd._tk_is_native())

    def test_no_chooser_is_spawned_on_a_native_platform(self):
        with patch.object(nd.sys, 'platform', 'darwin'), \
                patch('subprocess.run') as run, \
                patch('tkinter.filedialog.askdirectory', return_value='/x'):
            nd.ask_directory('t')
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
