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


def load_translations(app: QApplication) -> QTranslator:
    """Load translations based on system locale."""
    translator = QTranslator()
    locale = QLocale.system().name()
    
    # Try to load translation from multiple locations
    translation_paths = [
        "translations",
        "/usr/share/unetbootin/translations",
        "/usr/local/share/unetbootin/translations",
    ]
    
    translation_file = f"unetbootin_{locale}"
    
    for path in translation_paths:
        if translator.load(translation_file, path):
            app.installTranslator(translator)
            return translator
    
    # Fallback to Qt's translation
    qt_translator = QTranslator()
    if qt_translator.load(locale, QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(qt_translator)
    
    return translator


def main():
    """Main entry point."""
    logger = setup_logging()
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")
    
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("UNetbootin")
    
    # Load translations
    load_translations(app)
    
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
    unetbootin = UNetbootinApp()
    unetbootin.show()
    
    # Execute application
    logger.info("Application started, entering main loop")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
