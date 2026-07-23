"""
Main window UI for UNetbootin.
This recreates the Qt UI from the original C++ version.
"""

import os
import logging
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QRadioButton, QComboBox, QLabel, QTextBrowser,
    QPushButton, QFileDialog, QGroupBox, QButtonGroup,
    QLineEdit, QCheckBox, QSpinBox, QTextEdit, QTabWidget
)
from PySide6.QtCore import Signal, Slot, Qt, QObject, QSize
from PySide6.QtGui import QIcon

logger = logging.getLogger(__name__)


class MainWindow(QWidget):
    """
    Main window widget for UNetbootin.
    
    This class provides the complete Qt-based user interface for the application,
    including distribution selection, installation type configuration, drive selection,
    and advanced options with tabs for persistence, boot options, and firmware settings.
    """
    
    # Signals
    distro_selected = Signal(str)
    version_selected = Signal(str)
    install_type_changed = Signal(str)
    ok_button_clicked = Signal()
    cancel_button_clicked = Signal()
    exit_button_clicked = Signal()
    refresh_drive_list = Signal()
    
    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize the main window UI."""
        super().__init__(parent)
        logger.info("Creating MainWindow UI")
        
        self.distributions = {}
        self.categories = []
        self.current_distro = None
        self.current_version = None
        self.install_type = "distribution"
        
        self.init_ui()
        self.setup_connections()
    
    def init_ui(self):
        """
        Initialize the user interface components.
        
        Creates and configures all UI elements including distribution selectors,
        installation type options, drive selection, and advanced configuration tabs.
        """
        # Main layout
        main_layout = QGridLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)
        
        # Create first layer widget
        first_layer = QWidget(self)
        first_layer_layout = QGridLayout(first_layer)
        first_layer_layout.setContentsMargins(6, 6, 6, 6)
        first_layer_layout.setSpacing(6)
        
        # Row 0: Distribution selection
        self.radio_distro = QRadioButton("&Distribution", self)
        self.radio_distro.setChecked(True)
        
        distro_layout = QHBoxLayout()
        
        # Category combo box
        self.category_select = QComboBox(self)
        self.category_select.setMinimumWidth(120)
        self.category_select.setToolTip("Select distribution category (Linux, BSD, Windows)")
        self.category_select.setCurrentIndex(-1)
        
        # Distribution combo box
        self.distro_select = QComboBox(self)
        self.distro_select.setMinimumWidth(200)
        self.distro_select.setToolTip("Select from a list of supported distributions")
        self.distro_select.setCurrentIndex(-1)
        
        # Version combo box
        self.version_select = QComboBox(self)
        self.version_select.setMinimumWidth(150)
        self.version_select.setToolTip("Select the distribution version")
        self.version_select.setCurrentIndex(-1)
        self.version_select.setEnabled(False)
        
        distro_layout.addWidget(self.category_select)
        distro_layout.addWidget(self.distro_select)
        distro_layout.addWidget(self.version_select)
        
        first_layer_layout.addWidget(self.radio_distro, 0, 0)
        first_layer_layout.addLayout(distro_layout, 0, 1)
        
        # Row 1: Info message
        self.info_message = QTextBrowser(self)
        self.info_message.setMinimumHeight(30)
        self.info_message.setStyleSheet("background-color: transparent;")
        self.info_message.setFrameShape(QTextBrowser.NoFrame)
        self.info_message.setOpenExternalLinks(True)
        self.info_message.setHtml(
            "<html><body><p>Select a distribution or ISO file, then select your USB drive below.</p></body></html>"
        )
        first_layer_layout.addWidget(self.info_message, 1, 0, 1, 2)
        
        # Row 2: Radio button layout for install type
        radio_layout = QVBoxLayout()
        
        radio_button_layout = QVBoxLayout()
        
        # Disk image radio button
        self.radio_floppy = QRadioButton("Disk&image", self)
        self.radio_floppy.setMinimumHeight(25)
        self.radio_floppy.setToolTip("Specify a disk image file to load")
        
        # Custom/Manual radio button
        self.radio_manual = QRadioButton("&Custom", self)
        self.radio_manual.setMinimumHeight(30)
        self.radio_manual.setToolTip("Manually specify a kernel and initrd to load")
        
        radio_button_layout.addWidget(self.radio_floppy)
        radio_button_layout.addWidget(self.radio_manual)
        
        radio_layout.addLayout(radio_button_layout)
        radio_layout.addStretch()
        
        first_layer_layout.addLayout(radio_layout, 2, 0)
        
        # Floppy image selection (hidden by default)
        self.floppy_layout = QHBoxLayout()
        self.floppy_file_label = QLabel("Disk image:", self)
        self.floppy_file_selector = QPushButton("...", self)
        self.floppy_file_selector.setMaximumWidth(30)
        self.floppy_file_selector.setToolTip("Select a disk image file")
        self.floppy_file_line = QLineEdit(self)
        self.floppy_file_line.setEnabled(False)
        
        self.floppy_layout.addWidget(self.floppy_file_label)
        self.floppy_layout.addWidget(self.floppy_file_line)
        self.floppy_layout.addWidget(self.floppy_file_selector)
        self.floppy_layout.setContentsMargins(0, 0, 0, 0)
        
        first_layer_layout.addLayout(self.floppy_layout, 2, 1)
        self.floppy_layout.setContentsMargins(10, 0, 0, 0)
        
        # Manual installation options (hidden by default)
        self.manual_group = QGroupBox(self)
        self.manual_group.setVisible(False)
        manual_layout = QGridLayout(self.manual_group)
        
        # Kernel selection
        kernel_label = QLabel("Kernel:", self)
        self.kernel_file_line = QLineEdit(self)
        self.kernel_file_selector = QPushButton("...", self)
        self.kernel_file_selector.setMaximumWidth(30)
        
        # Initrd selection
        initrd_label = QLabel("Initrd:", self)
        self.initrd_file_line = QLineEdit(self)
        self.initrd_file_selector = QPushButton("...", self)
        self.initrd_file_selector.setMaximumWidth(30)
        
        # Cfg selection
        cfg_label = QLabel("Cfg:", self)
        self.cfg_file_line = QLineEdit(self)
        self.cfg_file_selector = QPushButton("...", self)
        self.cfg_file_selector.setMaximumWidth(30)
        
        manual_layout.addWidget(kernel_label, 0, 0)
        manual_layout.addWidget(self.kernel_file_line, 0, 1)
        manual_layout.addWidget(self.kernel_file_selector, 0, 2)
        manual_layout.addWidget(initrd_label, 1, 0)
        manual_layout.addWidget(self.initrd_file_line, 1, 1)
        manual_layout.addWidget(self.initrd_file_selector, 1, 2)
        manual_layout.addWidget(cfg_label, 2, 0)
        manual_layout.addWidget(self.cfg_file_line, 2, 1)
        manual_layout.addWidget(self.cfg_file_selector, 2, 2)
        
        first_layer_layout.addWidget(self.manual_group, 3, 0, 1, 2)
        
        # Row 3: Install type selection
        type_layout = QHBoxLayout()
        type_label = QLabel("Type:", self)
        
        self.type_select = QComboBox(self)
        self.type_select.addItems(["USB Drive", "Hard Disk"])
        self.type_select.setToolTip("Select the installation target type")
        self.type_select.setCurrentIndex(0)
        
        type_layout.addWidget(type_label)
        type_layout.addWidget(self.type_select)
        type_layout.addStretch()
        
        first_layer_layout.addLayout(type_layout, 4, 0, 1, 2)
        
        # Row 4: Drive selection
        drive_layout = QHBoxLayout()
        drive_label = QLabel("Drive:", self)
        
        self.drive_select = QComboBox(self)
        self.drive_select.setMinimumWidth(300)
        self.drive_select.setToolTip("Select the target drive")
        self.drive_select.setCurrentIndex(-1)
        
        self.refresh_button = QPushButton("Refresh", self)
        self.refresh_button.setToolTip("Refresh the list of available drives")
        
        drive_layout.addWidget(drive_label)
        drive_layout.addWidget(self.drive_select)
        drive_layout.addWidget(self.refresh_button)
        
        first_layer_layout.addLayout(drive_layout, 5, 0, 1, 2)
        
        # Add first layer to main layout
        main_layout.addWidget(first_layer, 1, 1)
        
        # Row 5: Advanced options
        self.advanced_group = QGroupBox("Advanced", self)
        self.advanced_group.setCheckable(True)
        self.advanced_group.setChecked(False)
        
        advanced_layout = QGridLayout(self.advanced_group)
        
        # Create a tab widget for advanced options
        self.advanced_tabs = QTabWidget(self)
        
        # Tab 1: Persistence
        persistence_tab = QWidget()
        persistence_layout = QGridLayout(persistence_tab)
        
        self.persistence_check = QCheckBox("Enable persistence", self)
        self.persistence_check.setToolTip("Enable persistence for live USB")
        
        persistence_size_label = QLabel("Persistence (MB):", self)
        self.persistence_size_spin = QSpinBox(self)
        self.persistence_size_spin.setRange(0, 10000)
        self.persistence_size_spin.setValue(1000)
        self.persistence_size_spin.setEnabled(False)
        
        persistence_layout.addWidget(self.persistence_check, 0, 0, 1, 2)
        persistence_layout.addWidget(persistence_size_label, 1, 0)
        persistence_layout.addWidget(self.persistence_size_spin, 1, 1)
        persistence_layout.setContentsMargins(6, 6, 6, 6)
        
        # Tab 2: Boot Options
        boot_tab = QWidget()
        boot_layout = QGridLayout(boot_tab)
        
        self.boot_options_label = QLabel("Boot Options:", self)
        self.boot_options_edit = QTextEdit(self)
        self.boot_options_edit.setToolTip("Custom boot options for the live USB (e.g., quiet splash persistent)")
        self.boot_options_edit.setMaximumHeight(80)
        self.boot_options_edit.setPlaceholderText("Enter boot options (e.g., quiet splash persistent noapic)")
        
        boot_layout.addWidget(self.boot_options_label, 0, 0)
        boot_layout.addWidget(self.boot_options_edit, 1, 0, 1, 2)
        boot_layout.setContentsMargins(6, 6, 6, 6)
        
        # Tab 3: UEFI & Secure Boot
        firmware_tab = QWidget()
        firmware_layout = QGridLayout(firmware_tab)
        
        self.uefi_only_check = QCheckBox("UEFI-only installation", self)
        self.uefi_only_check.setToolTip("Install for UEFI systems only (no BIOS/CSM support)")
        
        self.secure_boot_check = QCheckBox("Enable Secure Boot", self)
        self.secure_boot_check.setToolTip("Enable Secure Boot support (requires signed bootloader)")
        
        firmware_layout.addWidget(self.uefi_only_check, 0, 0, 1, 2)
        firmware_layout.addWidget(self.secure_boot_check, 1, 0, 1, 2)
        firmware_layout.setContentsMargins(6, 6, 6, 6)
        
        # Add tabs to the tab widget
        self.advanced_tabs.addTab(persistence_tab, "Persistence")
        self.advanced_tabs.addTab(boot_tab, "Boot Options")
        self.advanced_tabs.addTab(firmware_tab, "Firmware")
        
        # Add the tab widget to the advanced layout
        advanced_layout.addWidget(self.advanced_tabs, 0, 0, 1, 2)
        
        main_layout.addWidget(self.advanced_group, 6, 1)
        
        # Row 7: Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.ok_button = QPushButton("OK", self)
        self.ok_button.setDefault(True)
        self.ok_button.setToolTip("Start the installation")
        
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.setToolTip("Cancel and exit")
        
        self.exit_button = QPushButton("Exit", self)
        self.exit_button.setToolTip("Exit the application")
        
        button_layout.addWidget(self.ok_button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.exit_button)
        
        main_layout.addLayout(button_layout, 7, 1)
        
        # Add spacing
        main_layout.setRowStretch(0, 1)
        main_layout.setRowStretch(8, 1)
        
        # Connect persistence checkbox
        self.persistence_check.stateChanged.connect(
            lambda state: self.persistence_size_spin.setEnabled(state == Qt.Checked)
        )
    
    def setup_connections(self):
        """
        Setup signal-slot connections for UI elements.
        
        Connects all UI element signals to their respective handlers.
        """
        # Category selection
        self.category_select.currentIndexChanged.connect(self.on_category_changed)
        
        # Distribution selection
        self.distro_select.currentTextChanged.connect(self.on_distro_text_changed)
        self.version_select.currentTextChanged.connect(self.on_version_text_changed)
        
        # Install type selection
        self.radio_distro.toggled.connect(self.on_radio_distro_toggled)
        self.radio_floppy.toggled.connect(self.on_radio_floppy_toggled)
        self.radio_manual.toggled.connect(self.on_radio_manual_toggled)
        
        # Button connections
        self.ok_button.clicked.connect(self.on_ok_clicked)
        self.cancel_button.clicked.connect(self.on_cancel_clicked)
        self.exit_button.clicked.connect(self.on_exit_clicked)
        self.refresh_button.clicked.connect(self.on_refresh_clicked)
        
        # File selector connections
        self.floppy_file_selector.clicked.connect(self.on_floppy_selector_clicked)
        self.kernel_file_selector.clicked.connect(self.on_kernel_selector_clicked)
        self.initrd_file_selector.clicked.connect(self.on_initrd_selector_clicked)
        self.cfg_file_selector.clicked.connect(self.on_cfg_selector_clicked)
        
        # Type selection
        self.type_select.currentIndexChanged.connect(self.on_type_changed)
    
    def set_distributions(self, distros: List[Dict[str, Any]]):
        """
        Set the list of available distributions.
        
        Args:
            distros: List of distribution dictionaries with name, display_name, category, etc.
        """
        logger.info(f"Setting {len(distros)} distributions")
        self.distributions = {d['name']: d for d in distros}
        
        # Extract all categories
        categories = set()
        for distro in distros:
            if distro.get('category'):
                categories.add(distro['category'])
        
        # Set categories in the category combo box
        self.set_categories(sorted(categories))
        
        # Update distribution list based on current category filter
        self.update_distro_list()
    
    def set_categories(self, categories: List[str]):
        """
        Set the list of available categories.
        
        Args:
            categories: List of category names (e.g., ['Linux', 'BSD', 'Windows'])
        """
        logger.info(f"Setting {len(categories)} categories")
        self.categories = categories
        
        # Clear existing items
        self.category_select.clear()
        
        # Add "All" option to show all distributions
        self.category_select.addItem("All", "")
        
        # Add categories to combo box
        for category in categories:
            self.category_select.addItem(category, category)
    
    def update_distro_list(self, category_filter: str = None):
        """
        Update the distribution list based on category filter.
        
        Args:
            category_filter: Category to filter by, or None for current selection
        """
        # Use provided filter or current selection
        if category_filter is None:
            category_filter = self.category_select.currentData() or ""
        
        # Clear existing items
        self.distro_select.clear()
        
        # Filter distributions by category if specified
        if category_filter and category_filter != "":
            filtered_distros = [
                d for d in self.distributions.values() 
                if d.get('category') == category_filter
            ]
        else:
            filtered_distros = list(self.distributions.values())
        
        # Add distributions to combo box (sorted by display_name, then name)
        for distro in sorted(filtered_distros, key=lambda x: (x.get('display_name', x['name']), x['name'])):
            self.distro_select.addItem(distro.get('display_name', distro['name']), distro['name'])
    
    def set_drive_list(self, drives: List[tuple]):
        """Set the list of available drives.

        Args:
            drives: List of (display_string, device_path) tuples. The device
                path is stored as item userData so installation targets the
                real device, not the decorated display text.
        """
        logger.info(f"Setting {len(drives)} drives")

        # Remember current selection (by device path) if any
        current_device = self.drive_select.currentData() if self.drive_select.count() > 0 else None

        # Clear existing items
        self.drive_select.clear()

        # Add drives to combo box: visible label + device path as userData
        for display, device in drives:
            self.drive_select.addItem(display, device)

        # Try to restore previous selection
        if current_device:
            index = self.drive_select.findData(current_device)
            if index >= 0:
                self.drive_select.setCurrentIndex(index)

        # Enable/disable based on whether we have drives
        self.drive_select.setEnabled(len(drives) > 0)

        return len(drives) > 0
    
    def update_version_list(self, distro_name: str):
        """Update version list for selected distribution."""
        if distro_name not in self.distributions:
            return
        
        distro = self.distributions[distro_name]
        versions = distro.get('versions', [])
        
        self.version_select.clear()
        self.version_select.setEnabled(len(versions) > 0)
        
        for version in versions:
            self.version_select.addItem(version['name'], version['name'])
        
        if versions:
            self.version_select.setCurrentIndex(0)
    
    def update_install_type(self, install_type: str):
        """Update the install type UI."""
        self.install_type = install_type
        
        # Show/hide appropriate sections
        show_floppy = install_type == "floppy"
        show_manual = install_type == "manual"
        
        # For now, we handle this in the radio button toggles
    
    def get_installation_parameters(self) -> Dict[str, Any]:
        """Get current installation parameters from UI."""
        params = {
            'install_type': 'distribution' if self.radio_distro.isChecked() 
                         else ('floppy' if self.radio_floppy.isChecked() 
                               else 'manual'),
            'drive_type': self.type_select.currentText(),
            # currentData() holds the real device path (set in set_drive_list);
            # currentText() is only the decorated display label.
            'target_drive': self.drive_select.currentData(),
        }
        
        if params['install_type'] == 'distribution':
            params['distro'] = self.distro_select.currentText()
            params['version'] = self.version_select.currentText()
        elif params['install_type'] == 'floppy':
            params['floppy_image'] = self.floppy_file_line.text()
        elif params['install_type'] == 'manual':
            params['kernel'] = self.kernel_file_line.text()
            params['initrd'] = self.initrd_file_line.text()
            params['cfg'] = self.cfg_file_line.text()
        
        # Advanced options
        if self.advanced_group.isChecked():
            params['persistence_enabled'] = self.persistence_check.isChecked()
            params['persistence_size'] = self.persistence_size_spin.value()
            
            # Boot options
            boot_options_text = self.boot_options_edit.toPlainText().strip()
            if boot_options_text:
                params['boot_options'] = boot_options_text
            
            # UEFI and Secure Boot
            params['enable_uefi_only'] = self.uefi_only_check.isChecked()
            params['enable_secure_boot'] = self.secure_boot_check.isChecked()
        
        return params
    
    # Event handlers
    @Slot(str)
    def on_distro_text_changed(self, text: str):
        """Handle distribution selection change."""
        self.current_distro = text
        self.distro_selected.emit(text)
        self.update_version_list(text)
        
        # Update info message
        if text and text in self.distributions:
            distro = self.distributions[text]
            info = distro.get('description', f"Selected: {text}")
            self.info_message.setHtml(f"<html><body><p>{info}</p></body></html>")
    
    @Slot(str)
    def on_version_text_changed(self, text: str):
        """Handle version selection change."""
        self.current_version = text
        self.version_selected.emit(text)
    
    @Slot(int)
    def on_category_changed(self, index: int):
        """
        Handle category selection change.
        
        Args:
            index: The index of the selected category
        """
        category = self.category_select.itemData(index)
        self.update_distro_list(category)
        logger.info(f"Category changed to: {category}")
    
    @Slot(bool)
    def on_radio_distro_toggled(self, checked: bool):
        """Handle Distribution radio button toggle."""
        if checked:
            self.install_type = "distribution"
            self.install_type_changed.emit("distribution")
            self.floppy_layout.setContentsMargins(10, 0, 0, 0)
            self.manual_group.setVisible(False)
    
    @Slot(bool)
    def on_radio_floppy_toggled(self, checked: bool):
        """Handle Disk image radio button toggle."""
        if checked:
            self.install_type = "floppy"
            self.install_type_changed.emit("floppy")
            self.manual_group.setVisible(False)
    
    @Slot(bool)
    def on_radio_manual_toggled(self, checked: bool):
        """Handle Custom radio button toggle."""
        if checked:
            self.install_type = "manual"
            self.install_type_changed.emit("manual")
            self.manual_group.setVisible(True)
    
    @Slot()
    def on_ok_clicked(self):
        """Handle OK button click."""
        self.ok_button_clicked.emit()
    
    @Slot()
    def on_cancel_clicked(self):
        """Handle Cancel button click."""
        self.cancel_button_clicked.emit()
    
    @Slot()
    def on_exit_clicked(self):
        """Handle Exit button click."""
        self.exit_button_clicked.emit()
    
    @Slot()
    def on_refresh_clicked(self):
        """Handle Refresh button click."""
        logger.info("Refresh button clicked - refreshing drive list")
        self.refresh_drive_list.emit()
    
    @Slot()
    def on_floppy_selector_clicked(self):
        """Handle floppy file selector click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Disk Image", 
            "", 
            "All files (*);;ISO files (*.iso);;IMG files (*.img)"
        )
        if file_path:
            self.floppy_file_line.setText(file_path)
    
    @Slot()
    def on_kernel_selector_clicked(self):
        """Handle kernel file selector click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Kernel File", 
            "", 
            "All files (*)"
        )
        if file_path:
            self.kernel_file_line.setText(file_path)
    
    @Slot()
    def on_initrd_selector_clicked(self):
        """Handle initrd file selector click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Initrd File", 
            "", 
            "All files (*)"
        )
        if file_path:
            self.initrd_file_line.setText(file_path)
    
    @Slot()
    def on_cfg_selector_clicked(self):
        """Handle cfg file selector click."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Config File", 
            "", 
            "All files (*);;CFG files (*.cfg)"
        )
        if file_path:
            self.cfg_file_line.setText(file_path)
    
    @Slot(int)
    def on_type_changed(self, index: int):
        """Handle install type selection change."""
        pass
