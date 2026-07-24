#!/usr/bin/env python3
"""
Main entry point for UNetbootin Python rewrite.
Uses PySimpleGUI + Tkinter for a lightweight, no-Qt GUI.
"""

import sys
import os
import logging
from pathlib import Path
from typing import Optional

try:
    import PySimpleGUI as sg
    HAS_PYSIMPLEGUI = True
except ImportError:
    HAS_PYSIMPLEGUI = False

import locale as _locale

from unetbootin.core.utils import parse_command_line_args, normalize_language_code
from unetbootin.core import i18n
from unetbootin import APP_NAME, APP_VERSION

logger = logging.getLogger(__name__)


def setup_logging():
    """Configure logging for the application."""
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("unetbootin.log"),
        ],
    )
    return logging.getLogger(__name__)


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
    logger.info(f"Starting {APP_NAME} v{APP_VERSION} with PySimpleGUI")
    
    if not HAS_PYSIMPLEGUI:
        error_msg = (
            "PySimpleGUI is not installed. "
            "Please install it with: pip install PySimpleGUI"
        )
        logger.error(error_msg)
        sys.exit(1)
    
    # Install sudo interceptor early so all subsequent subprocess.run calls
    # with sudo will use the elevation system
    from unetbootin.core.elevation import (
        install_sudo_interceptor, ensure_elevated, ElevationError
    )
    install_sudo_interceptor()
    
    # Ensure we're running with elevated privileges
    # This will attempt to relaunch with elevation if needed
    try:
        ensure_elevated()
    except ElevationError as e:
        logger.warning(f"Elevation not available or failed: {e}")
        # Continue anyway - individual commands will prompt for elevation as needed
        # or fail with clear error messages
    
    # Parse command line arguments (--lang, --rootcheck, --automate, ...)
    cli_args = parse_command_line_args()
    
    # Load translations with language from command line if specified
    app_lang = load_translations(lang=cli_args.get('lang'))
    logger.info(f"Using language: {app_lang}")
    
    # Set PySimpleGUI theme
    sg.theme('Default1')
    
    # Import here to avoid import errors if PySimpleGUI is not installed
    from unetbootin.app import UNetbootinAppPySG
    
    # Create and run main application
    try:
        unetbootin = UNetbootinAppPySG(cli_args=cli_args)
        unetbootin.run()
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
