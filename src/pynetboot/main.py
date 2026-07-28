#!/usr/bin/env python3
"""
Main entry point for PyNetboot Python rewrite.
Uses CustomTkinter for a modern, lightweight, no-Qt GUI.
"""

import sys
import os
import logging
from typing import Optional

try:
    from pynetboot.ui import main_window_ctk as sg
    HAS_GUI = sg.HAS_CTK
except ImportError:
    HAS_GUI = False
    sg = None

import locale as _locale

from pynetboot.core.utils import parse_command_line_args, normalize_language_code
from pynetboot.core import i18n
from pynetboot import APP_NAME, APP_VERSION

logger = logging.getLogger(__name__)


def setup_logging():
    """Configure logging: console, a file, and an in-memory buffer.

    The buffer backs the Log window, so the user can read the log without
    hunting for the file. The file itself now goes to a predictable per-user
    directory rather than whatever directory the app was launched from.
    """
    from pynetboot.core import log_buffer

    handlers = [logging.StreamHandler(sys.stdout)]

    log_path = None
    try:
        directory = log_buffer.default_log_directory()
        os.makedirs(directory, exist_ok=True)
        log_path = os.path.join(directory, "pynetboot.log")
        handlers.append(logging.FileHandler(log_path))
    except OSError:
        # Fall back to the working directory rather than losing file logging.
        try:
            log_path = os.path.abspath("pynetboot.log")
            handlers.append(logging.FileHandler(log_path))
        except OSError:
            log_path = None

    logging.basicConfig(
        level=logging.INFO,
        format=log_buffer.LOG_FORMAT,
        handlers=handlers,
    )
    # Capture into memory as well, so the Log window has something to show.
    log_buffer.install()
    log_buffer.set_log_file(log_path)

    logger = logging.getLogger(__name__)
    if log_path:
        logger.info(f"Log file: {log_path}")
    return logger


def load_translations(lang: Optional[str] = None):
    """Activate the UI translation catalog for the requested/detected language.

    Loads the matching ``.ts`` catalog (de/es/fr/it/hu) via ``core.i18n`` so
    UI strings wrapped in ``_()`` are translated. Falls back to English.

    Args:
        lang: Optional language code from the command line (e.g. ``de_DE``).

    Returns:
        The short language code actually activated (e.g. ``de`` or ``en``).
    """
    locale_to_try = lang
    if not locale_to_try:
        # Detect the system locale (e.g. 'de_DE') if the user didn't ask.
        try:
            locale_to_try = _locale.getdefaultlocale()[0]
        except (ValueError, OSError):
            locale_to_try = None

    active = i18n.set_language(locale_to_try)
    logger.info(f"UI language: {active}")
    return active


def main():
    """Main entry point."""
    logger = setup_logging()
    logger.info(f"Starting {APP_NAME} v{APP_VERSION} with CustomTkinter")

    if not HAS_GUI:
        error_msg = (
            "customtkinter is not installed. "
            "Please install it with: pip install customtkinter"
        )
        logger.error(error_msg)
        sys.exit(1)

    # Run the GUI as a normal user. Privileged device operations elevate
    # themselves per-command (pkexec/PolicyKit) through this interceptor, which
    # rewrites the installer's subprocess `sudo` calls. Relaunching the whole
    # app as root is unnecessary and, via pkexec, would strip DISPLAY/XAUTHORITY
    # and break the GUI — so we deliberately do NOT force elevation at startup.
    from pynetboot.core.elevation import install_sudo_interceptor, is_elevated
    install_sudo_interceptor()

    # Windows embeds a requireAdministrator manifest, so this should already
    # be true there. Recorded because when it is not, the failure surfaces
    # much later as an opaque "Access is denied" from diskpart.
    logger.info(f"Running elevated: {is_elevated()}")

    # Must happen before any window exists, or Windows keeps showing the
    # host interpreter's generic icon in the task bar.
    sg.claim_windows_taskbar_identity()

    # Parse command line arguments (--lang, --rootcheck, --automate, ...)
    cli_args = parse_command_line_args()

    # Load translations with language from command line if specified
    app_lang = load_translations(lang=cli_args.get('lang'))
    logger.info(f"Using language: {app_lang}")

    # Fail loudly on a Tk too old to paint the widgets, instead of showing an
    # empty window.
    toolkit_problem = sg.check_toolkit()
    if toolkit_problem:
        logger.error(toolkit_problem)
        print(f"ERROR: {toolkit_problem}", file=sys.stderr)
        sys.exit(1)

    # Appearance follows the system light/dark setting.
    sg.apply_theme()

    # Import here to avoid import errors if the toolkit is not installed
    from pynetboot.app import PyNetbootApp

    # Create and run main application
    try:
        app = PyNetbootApp(cli_args=cli_args)
        app.run()
        logger.info("Application exited successfully")
    except Exception as e:  # noqa: BLE001 - top-level last-resort handler: show a dialog and exit cleanly instead of dumping a traceback
        logger.error(f"Application failed: {e}")
        sg.popup_error(
            f"Application failed: {str(e)}",
            title="Fatal Error"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
