#!/usr/bin/env python3
"""
Main entry point for UNetbootin Python rewrite.
"""

import sys
import os
import logging
from pathlib import Path

# Add src directory to path for development
sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QLocale, QTranslator, QLibraryInfo
from PySide6.QtGui import QIcon

from unetbootin.app import UNetbootinApp
from unetbootin.core.utils import parse_command_line_args, normalize_language_code, is_language_supported
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


def load_translations(app: QApplication, lang: Optional[str] = None) -> QTranslator:
    """Load translations based on system locale or specified language.
    
    Only loads translations for supported languages: de, es, fr, it, hu.
    English (en) is the default and doesn't require a translation file.
    
    Args:
        app: QApplication instance
        lang: Optional language code to use (from command line args)
        
    Returns:
        QTranslator instance that was installed
    """
    translator = QTranslator()
    
    # Determine which language to use
    if lang:
        # Language specified via command line
        locale_to_try = lang
    else:
        # Use system locale
        locale_to_try = QLocale.system().name()
    
    # Normalize and validate the language code
    normalized_lang = normalize_language_code(locale_to_try)
    
    # Only try to load translation if it's a supported language
    if normalized_lang:
        # Try to load translation from multiple locations
        translation_paths = [
            "translations",
            "/usr/share/unetbootin/translations",
            "/usr/local/share/unetbootin/translations",
        ]
        
        translation_file = f"unetbootin_{normalized_lang}"
        
        for path in translation_paths:
            if translator.load(translation_file, path):
                app.installTranslator(translator)
                return translator
    
    # If language is not supported or translation file not found,
    # the app will use English (default strings)
    return translator


def main():
    """Main entry point."""
    logger = setup_logging()
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")

    # Parse command line arguments (--lang, --rootcheck, --automate, ...)
    cli_args = parse_command_line_args()

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("UNetbootin")
    
    # Load translations with language from command line if specified
    load_translations(app, lang=cli_args.get('lang'))
    
    # Set application icon
    icon = QIcon()
    icon_paths = [
        "resources/unetbootin_16.png",
        "resources/unetbootin_22.png", 
        "resources/unetbootin_24.png",
        "resources/unetbootin_32.png",
        "resources/unetbootin_48.png",
        "/usr/share/pixmaps/unetbootin.png",
    ]
    for path in icon_paths:
        if os.path.exists(path):
            icon.addFile(path)
    app.setWindowIcon(icon)
    
    # Create and show main application
    unetbootin = UNetbootinApp(cli_args=cli_args)
    unetbootin.show()
    
    # Execute application
    logger.info("Application started, entering main loop")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
