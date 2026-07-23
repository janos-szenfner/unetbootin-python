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

from unetbootin.core.utils import parse_command_line_args, normalize_language_code
from unetbootin import APP_NAME, APP_VERSION


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
    """Load translations based on system locale or specified language.
    
    For now, this just sets the app language. Full translation support
    would need to be implemented with gettext or similar.
    
    Args:
        lang: Optional language code to use (from command line args)
    """
    # Determine which language to use
    if lang:
        locale_to_try = lang
    else:
        # Use system locale or default to English
        locale_to_try = 'en'
    
    # Normalize the language code
    normalized_lang = normalize_language_code(locale_to_try)
    return normalized_lang


def main():
    """Main entry point."""
    logger = setup_logging()
    logger.info(f"Starting {APP_NAME} v{APP_VERSION} with PySimpleGUI")
    
    if not HAS_PYSIMPLEGUI:
        logger.error("PySimpleGUI is not installed. Please install it with: pip install PySimpleGUI")
        print("Error: PySimpleGUI is not installed.")
        print("Please install it with: pip install PySimpleGUI")
        sys.exit(1)
    
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
    except Exception as e:
        logger.error(f"Application failed: {e}")
        sg.popup_error(f"Application failed: {str(e)}", title="Fatal Error")
        sys.exit(1)


if __name__ == "__main__":
    main()
