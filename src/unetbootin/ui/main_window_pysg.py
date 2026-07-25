"""
Main window UI for UNetbootin using PySimpleGUI.
This replaces the Qt-based UI with a lightweight PySimpleGUI implementation.
"""

import os
import logging
from typing import Optional, List, Dict, Any

try:
    import PySimpleGUI as sg
    HAS_PYSIMPLEGUI = True
except ImportError:
    HAS_PYSIMPLEGUI = False
    sg = None

from unetbootin.core.i18n import _

logger = logging.getLogger(__name__)


def apply_theme():
    """Apply the app's look: a white background with black text.

    Set explicitly rather than relying on a named theme so the colours are the
    same on every platform and PySimpleGUI build.
    """
    if not HAS_PYSIMPLEGUI:
        return
    try:
        sg.theme('Default1')
        sg.theme_background_color('white')
        sg.theme_element_background_color('white')
        sg.theme_text_element_background_color('white')
        sg.theme_text_color('black')
        sg.theme_input_background_color('white')
        sg.theme_input_text_color('black')
        sg.theme_button_color(('black', '#e8e8e8'))
    except (AttributeError, TypeError) as e:
        logger.warning(f"Could not apply white theme: {e}")


class MainWindowPySG:
    """
    Main window for UNetbootin using PySimpleGUI.

    This class provides a complete PySimpleGUI-based user interface for the application,
    including distribution selection, installation type configuration, drive selection,
    and advanced options with tabs for persistence, boot options, and firmware settings.
    """

    def __init__(self, parent=None):
        """Initialize the main window UI."""
        if not HAS_PYSIMPLEGUI:
            raise ImportError(
                "PySimpleGUI is required but not installed. "
                "Please install it with: pip install PySimpleGUI")

        logger.info("Creating MainWindow UI with PySimpleGUI")

        self.distributions = {}
        self.categories = []
        self.current_distro = None
        self.current_version = None
        self.install_type = "distribution"
        self.window = None
        self.drive_data = []
        # Advanced options are shown by default; the toggle button closes them.
        self.advanced_visible = True

        # Initialize UI
        self.init_ui()

    def init_ui(self):
        """
        Initialize the user interface components.
        """
        apply_theme()

        # Drop-down fields: a larger font makes the tkinter combo box taller,
        # and the vertical padding stops the rows from looking cramped.
        combo_font = ('Helvetica', 11)
        combo_pad = ((0, 6), (5, 5))

        # Minimal transparent GIF icon (compatible with old tkinter)
        transparent_gif = "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAICRAEAOw=="

        # Define the layout
        layout = [
            # Title
            [sg.Text("UNetbootin", font=('Helvetica', 16), pad=(0, (0, 10))),
             sg.Push(),
             sg.Button(_("About"), key='-ABOUT-', pad=(0, (0, 10)),
                       tooltip="About UNetbootin")],

            # Install Type Radio Buttons
            [
                sg.Radio(
    "Distribution",
    "install_type",
    default=True,
    key='-RADIO_DISTRO-',
    enable_events=True,
     tooltip="Select from a list of supported distributions"),
                sg.Radio(
    "Disk image",
    "install_type",
    default=False,
    key='-RADIO_FLOPPY-',
    enable_events=True,
     tooltip="Specify a disk image file to load"),
                sg.Radio(
    "Custom",
    "install_type",
    default=False,
    key='-RADIO_MANUAL-',
    enable_events=True,
     tooltip="Manually specify a kernel and initrd to load"),
            ],

            # Distribution selection
            [
                sg.Combo(
    [],
    key='-CATEGORY_SELECT-',
    font=combo_font,
    pad=combo_pad,
    size=(24, 1),
    expand_x=True,
    readonly=True,
    enable_events=True,
    tooltip="Select distribution category"),
                sg.Combo(
    [],
    key='-DISTRO_SELECT-',
    font=combo_font,
    pad=combo_pad,
    size=(34, 1),
    expand_x=True,
    readonly=True,
    enable_events=True,
    tooltip="Select from a list of supported distributions"),
                sg.Combo(
    [],
    key='-VERSION_SELECT-',
    font=combo_font,
    pad=combo_pad,
    size=(30, 1),
    expand_x=True,
    readonly=True,
    enable_events=True,
    disabled=True,
    tooltip="Select the distribution version"),
            ],

            # Floppy image selection (hidden initially)
            [
                sg.Text("Disk image:", key='-FLOPPY_LABEL-', visible=False),
                sg.Input(
    size=(
        45,
        1),
        key='-FLOPPY_FILE-',
        visible=False,
         tooltip="Path to disk image file"),
                sg.Button(
    "...",
    size=(
        4,
        1),
        key='-FLOPPY_BROWSE-',
        visible=False,
         tooltip="Browse for disk image file"),
            ],

            # Manual installation options (hidden initially)
            [
                sg.Text("Kernel:", key='-KERNEL_LABEL-', visible=False),
                sg.Input(size=(40, 1), key='-KERNEL_FILE-', visible=False),
                sg.Button("...", size=(4, 1), key='-KERNEL_BROWSE-', visible=False),
            ],
            [
                sg.Text("Initrd:", key='-INITRD_LABEL-', visible=False),
                sg.Input(size=(40, 1), key='-INITRD_FILE-', visible=False),
                sg.Button("...", size=(4, 1), key='-INITRD_BROWSE-', visible=False),
            ],
            [
                sg.Text("Cfg:", key='-CFG_LABEL-', visible=False),
                sg.Input(size=(40, 1), key='-CFG_FILE-', visible=False),
                sg.Button("...", size=(4, 1), key='-CFG_BROWSE-', visible=False),
            ],

            # Drive selection
            [
                sg.Text(_("Target Drive:"), size=(12, 1)),
                sg.Combo(
    [],
    key='-DRIVE_SELECT-',
    font=combo_font,
    pad=combo_pad,
    size=(56, 1),
    expand_x=True,
    readonly=True,
    enable_events=True,
    tooltip="Select the target drive"),
                sg.Button(
    _("Refresh"),
    key='-REFRESH_DRIVES-',
     tooltip="Refresh the list of available drives"),
            ],

            # Install type (USB Drive / Hard Disk). NOTE: the combo *values*
            # ("USB Drive"/"Hard Disk") are semantic keys compared in the
            # installer, so they must NOT be translated — only the label is.
            [
                sg.Text(_("Type:"), size=(12, 1)),
                sg.Combo(["USB Drive",
    "Hard Disk"],
    key='-TYPE_SELECT-',
    font=combo_font,
    pad=combo_pad,
    default_value="USB Drive",
    size=(24, 1),
    expand_x=True,
    readonly=True,
    enable_events=True,
    tooltip="Select the installation target type"),
            ],

            # Info message
            [sg.Text("Select a distribution or ISO file, then select your "
                     "USB drive below.",
                     key='-INFO_MESSAGE-', size=(60, 1), expand_x=True)],

            # Advanced options toggle (open by default) with the inline
            # download/installation progress beside it. The bar, its status
            # text and the Cancel button stay hidden until work starts.
            [
                sg.Button(
    _("Close advanced option"),
    key='-ADVANCED_TOGGLE-',
    tooltip="Show or hide the advanced options"),
                sg.Text("", key='-PROGRESS_TEXT-', size=(34, 1),
                        visible=False),
                sg.ProgressBar(100, orientation='h', size=(22, 18),
                               key='-PROGRESS_BAR-', expand_x=True,
                               visible=False),
                sg.Button(_("Cancel download"), key='-CANCEL_DOWNLOAD-',
                          visible=False,
                          tooltip="Stop the download in progress"),
            ],

            # Advanced options (initially hidden)
            [
                sg.Column([
                    [sg.TabGroup([
                        [sg.Tab(_("Persistence"), [
                            [sg.Checkbox(_("Enable persistence"),
    key='-PERSISTENCE_CHECK-',
    enable_events=True,
     tooltip="Enable persistence for live USB")],
                            [sg.Text(_("Persistence (MB):"),
    key='-PERSISTENCE_LABEL-'),
    sg.Spin([i for i in range(0,
    10001)],
    initial_value=1000,
    size=(10,
    1),
    key='-PERSISTENCE_SIZE-',
    disabled=True,
     tooltip="Size of persistence partition in MB")],
                        ])],
                        [sg.Tab(_("Boot Options"), [
                            [sg.Text(_("Boot Options:"), key='-BOOT_LABEL-')],
                            [sg.Multiline(size=(50, 4), key='-BOOT_OPTIONS-',
                                          tooltip="Custom boot options for "
                                                  "the live USB")],
                            [sg.Text("Example: quiet splash persistent noapic",
                                     text_color='gray')],
                        ])],
                        [sg.Tab(_("Firmware"), [
                            [sg.Checkbox(_("UEFI-only installation"), key='-UEFI_ONLY-',
                                         tooltip="Install for UEFI systems only "
                                                 "(no BIOS/CSM support)")],
                            [
    sg.Checkbox(
        _("Enable Secure Boot"),
        key='-SECURE_BOOT-',
         tooltip="Enable Secure Boot support (requires signed bootloader)")],
                        ])],
                        [sg.Tab(_("ISO Location"), [
                            [sg.Text(_("Download the selected ISO to:"))],
                            [
                                sg.Input(
                                    key='-ISO_DIR-',
                                    size=(44, 1),
                                    expand_x=True,
                                    tooltip="Folder to download the ISO into. "
                                            "Leave empty to use a temporary "
                                            "folder that is deleted afterwards."),
                                sg.FolderBrowse(
                                    _("Browse"),
                                    key='-ISO_DIR_BROWSE-',
                                    target='-ISO_DIR-'),
                            ],
                            [sg.Text(
                                _("Leave empty to use a temporary folder. When a "
                                  "folder is set the downloaded ISO is kept there "
                                  "instead of being deleted after the install."),
                                text_color='gray', size=(58, 2))],
                        ])],
                    ], key='-ADVANCED_TABS-', visible=True)]
                ], key='-ADVANCED_COLUMN-', visible=True)
            ],

            # Buttons
            [
                sg.Push(),
                sg.Button(_("OK"), key='-OK-', tooltip="Start the installation"),
                sg.Button(_("ISO Download"), key='-ISO_DOWNLOAD-',
                          tooltip="Only download the selected ISO into the "
                                  "folder set in Advanced Options > ISO Location"),
                sg.Button(_("Cancel"), key='-CANCEL-', tooltip="Cancel and exit"),
                sg.Button(_("Exit"), key='-EXIT-', tooltip="Exit the application"),
            ],
        ]

        # Create the window
        # Wrap the layout in a Column that fills the window. `resizable=True`
        # alone only lets the frame be dragged — without an expanding container
        # the contents keep their original size and sit in the top-left corner.
        self.window = sg.Window(
    "UNetbootin",
    [[sg.Column(layout, key='-MAIN_COLUMN-',
                expand_x=True, expand_y=True,
                pad=(0, 0))]],
    finalize=True,
    resizable=True,
    margins=(
        10,
        10),
        use_default_focus=False,
         icon=transparent_gif)

        # Finalize the window immediately so elements can be updated
        self.window.finalize()

        # Let the container (and with it the expand_x elements) actually track
        # the window size. Guarded: a PySimpleGUI build without expand() must
        # not stop the app from starting.
        try:
            self.window['-MAIN_COLUMN-'].expand(expand_x=True, expand_y=True)
            self.window.set_min_size((640, 480))
        except (AttributeError, TypeError) as e:
            logger.warning(f"Window expand not supported by this PySimpleGUI: {e}")

        self._apply_combo_heights()

        # Store references to elements for easier access
        self.elements = {
            'category_select': self.window['-CATEGORY_SELECT-'],
            'distro_select': self.window['-DISTRO_SELECT-'],
            'version_select': self.window['-VERSION_SELECT-'],
            'floppy_file': self.window['-FLOPPY_FILE-'],
            'floppy_label': self.window['-FLOPPY_LABEL-'],
            'floppy_browse': self.window['-FLOPPY_BROWSE-'],
            'kernel_file': self.window['-KERNEL_FILE-'],
            'kernel_label': self.window['-KERNEL_LABEL-'],
            'kernel_browse': self.window['-KERNEL_BROWSE-'],
            'initrd_file': self.window['-INITRD_FILE-'],
            'initrd_label': self.window['-INITRD_LABEL-'],
            'initrd_browse': self.window['-INITRD_BROWSE-'],
            'cfg_file': self.window['-CFG_FILE-'],
            'cfg_label': self.window['-CFG_LABEL-'],
            'cfg_browse': self.window['-CFG_BROWSE-'],
            'drive_select': self.window['-DRIVE_SELECT-'],
            'type_select': self.window['-TYPE_SELECT-'],
            'info_message': self.window['-INFO_MESSAGE-'],
            'advanced_toggle': self.window['-ADVANCED_TOGGLE-'],
            'advanced_column': self.window['-ADVANCED_COLUMN-'],
            'advanced_tabs': self.window['-ADVANCED_TABS-'],
            'iso_dir': self.window['-ISO_DIR-'],
            'progress_text': self.window['-PROGRESS_TEXT-'],
            'progress_bar': self.window['-PROGRESS_BAR-'],
            'cancel_download': self.window['-CANCEL_DOWNLOAD-'],
            'persistence_check': self.window['-PERSISTENCE_CHECK-'],
            'persistence_size': self.window['-PERSISTENCE_SIZE-'],
            'persistence_label': self.window['-PERSISTENCE_LABEL-'],
            'boot_options': self.window['-BOOT_OPTIONS-'],
            'uefi_only': self.window['-UEFI_ONLY-'],
            'secure_boot': self.window['-SECURE_BOOT-'],
            'radio_distro': self.window['-RADIO_DISTRO-'],
            'radio_floppy': self.window['-RADIO_FLOPPY-'],
            'radio_manual': self.window['-RADIO_MANUAL-'],
        }

        # Set up visibility based on initial install type
        self.update_install_type_ui()

    def setup_connections(self):
        """Setup event handlers for UI elements."""
        pass

    def set_distributions(self, distros: List[Dict[str, Any]]):
        """Set the list of available distributions."""
        logger.info(f"Setting {len(distros)} distributions")
        self.distributions = {d['name']: d for d in distros}

        # Extract all categories
        categories = set()
        for distro in distros:
            if distro.get('category'):
                categories.add(distro['category'])

        self.set_categories(sorted(categories))
        self.update_distro_list()

    def set_categories(self, categories: List[str]):
        """Set the list of available categories."""
        logger.info(f"Setting {len(categories)} categories")
        self.categories = categories

        category_values = ['All'] + categories
        self.elements['category_select'].update(values=category_values, value='All')

    def update_distro_list(self, category_filter: str = None):
        """Update the distribution list based on category filter."""
        if category_filter is None:
            category_filter = self.elements['category_select'].get()

        if category_filter and category_filter != "All":
            filtered_distros = [
                d for d in self.distributions.values()
                if d.get('category') == category_filter
            ]
        else:
            filtered_distros = list(self.distributions.values())

        distro_names = [
    d.get(
        'display_name',
        d['name']) for d in sorted(
            filtered_distros,
            key=lambda x: (
                x.get(
                    'display_name',
                    x['name']),
                     x['name']))]
        current_value = self.elements['distro_select'].get()
        self.elements['distro_select'].update(values=distro_names)

        if current_value and current_value in distro_names:
            self.elements['distro_select'].update(value=current_value)

    def set_drive_list(self, drives: List[tuple]):
        """Set the list of available drives."""
        logger.info(f"Setting {len(drives)} drives")

        current_value = self.elements['drive_select'].get()
        current_device = None
        if current_value and self.drive_data:
            for display, device in self.drive_data:
                if display == current_value:
                    current_device = device
                    break

        self.drive_data = drives
        display_list = [display for display, device in drives]
        self.elements['drive_select'].update(values=display_list)
        self.elements['drive_select'].update(disabled=len(drives) == 0)

        if current_device:
            for display, device in drives:
                if device == current_device:
                    self.elements['drive_select'].update(value=display)
                    break
        elif display_list:
            self.elements['drive_select'].update(value=display_list[0])

        return len(drives) > 0

    def update_version_list(self, distro_name: str = None):
        """Update version list for selected distribution."""
        if distro_name is None:
            distro_name = self.get_current_distro_name()

        if distro_name not in self.distributions:
            return

        distro = self.distributions[distro_name]
        versions = distro.get('versions', [])
        version_names = [v['name'] for v in versions]
        self.elements['version_select'].update(
    values=version_names, disabled=len(versions) == 0)

        if versions:
            self.elements['version_select'].update(value=version_names[0])

        if distro_name and distro_name in self.distributions:
            distro = self.distributions[distro_name]
            info = distro.get('description', f"Selected: {distro_name}")
            self.elements['info_message'].update(value=info)

    def get_current_distro_name(self):
        """Get the currently selected distribution name."""
        display_name = self.elements['distro_select'].get()
        if not display_name:
            return None

        for name, distro in self.distributions.items():
            if distro.get('display_name', name) == display_name:
                return name
        return None

    def get_current_version_name(self):
        """Get the currently selected version name."""
        return self.elements['version_select'].get()

    def get_current_drive(self):
        """Get the currently selected drive device path."""
        display_text = self.elements['drive_select'].get()
        if not display_text:
            return None

        for display, device in self.drive_data or []:
            if display == display_text:
                return device
        return None

    def update_install_type(self, install_type: str):
        """Update the install type UI."""
        self.install_type = install_type
        self.update_install_type_ui()

    def update_install_type_ui(self):
        """Update UI visibility based on current install type."""
        radio_distro = self.elements['radio_distro'].get()
        radio_floppy = self.elements['radio_floppy'].get()
        radio_manual = self.elements['radio_manual'].get()

        if radio_distro:
            install_type = 'distribution'
        elif radio_floppy:
            install_type = 'floppy'
        elif radio_manual:
            install_type = 'manual'
        else:
            install_type = 'distribution'

        self.install_type = install_type

        if install_type == 'distribution':
            self.elements['category_select'].update(visible=True)
            self.elements['distro_select'].update(visible=True)
            self.elements['version_select'].update(visible=True)
            self.elements['floppy_label'].update(visible=False)
            self.elements['floppy_file'].update(visible=False)
            self.elements['floppy_browse'].update(visible=False)
            self.elements['kernel_label'].update(visible=False)
            self.elements['kernel_file'].update(visible=False)
            self.elements['kernel_browse'].update(visible=False)
            self.elements['initrd_label'].update(visible=False)
            self.elements['initrd_file'].update(visible=False)
            self.elements['initrd_browse'].update(visible=False)
            self.elements['cfg_label'].update(visible=False)
            self.elements['cfg_file'].update(visible=False)
            self.elements['cfg_browse'].update(visible=False)
        elif install_type == 'floppy':
            self.elements['category_select'].update(visible=False)
            self.elements['distro_select'].update(visible=False)
            self.elements['version_select'].update(visible=False)
            self.elements['floppy_label'].update(visible=True)
            self.elements['floppy_file'].update(visible=True)
            self.elements['floppy_browse'].update(visible=True)
            self.elements['kernel_label'].update(visible=False)
            self.elements['kernel_file'].update(visible=False)
            self.elements['kernel_browse'].update(visible=False)
            self.elements['initrd_label'].update(visible=False)
            self.elements['initrd_file'].update(visible=False)
            self.elements['initrd_browse'].update(visible=False)
            self.elements['cfg_label'].update(visible=False)
            self.elements['cfg_file'].update(visible=False)
            self.elements['cfg_browse'].update(visible=False)
        elif install_type == 'manual':
            self.elements['category_select'].update(visible=False)
            self.elements['distro_select'].update(visible=False)
            self.elements['version_select'].update(visible=False)
            self.elements['floppy_label'].update(visible=False)
            self.elements['floppy_file'].update(visible=False)
            self.elements['floppy_browse'].update(visible=False)
            self.elements['kernel_label'].update(visible=True)
            self.elements['kernel_file'].update(visible=True)
            self.elements['kernel_browse'].update(visible=True)
            self.elements['initrd_label'].update(visible=True)
            self.elements['initrd_file'].update(visible=True)
            self.elements['initrd_browse'].update(visible=True)
            self.elements['cfg_label'].update(visible=True)
            self.elements['cfg_file'].update(visible=True)
            self.elements['cfg_browse'].update(visible=True)

    def get_installation_parameters(self) -> Dict[str, Any]:
        """Get current installation parameters from UI."""
        params = {}

        if self.elements['radio_distro'].get():
            params['install_type'] = 'distribution'
        elif self.elements['radio_floppy'].get():
            params['install_type'] = 'floppy'
        elif self.elements['radio_manual'].get():
            params['install_type'] = 'manual'
        else:
            params['install_type'] = 'distribution'

        params['drive_type'] = self.elements['type_select'].get()
        params['target_drive'] = self.get_current_drive()

        if params['install_type'] == 'distribution':
            params['distro'] = self.get_current_distro_name()
            params['version'] = self.get_current_version_name()
        elif params['install_type'] == 'floppy':
            params['floppy_image'] = self.elements['floppy_file'].get()
        elif params['install_type'] == 'manual':
            params['kernel'] = self.elements['kernel_file'].get()
            params['initrd'] = self.elements['initrd_file'].get()
            params['cfg'] = self.elements['cfg_file'].get()

        if self.advanced_visible:
            params['persistence_enabled'] = self.elements['persistence_check'].get()
            params['persistence_size'] = self.elements['persistence_size'].get()

            boot_options_text = self.elements['boot_options'].get().strip()
            if boot_options_text:
                params['boot_options'] = boot_options_text

            params['enable_uefi_only'] = self.elements['uefi_only'].get()
            params['enable_secure_boot'] = self.elements['secure_boot'].get()

            iso_dir = (self.elements['iso_dir'].get() or '').strip()
            if iso_dir:
                params['iso_download_dir'] = iso_dir

        return params

    _COMBO_KEYS = ('-CATEGORY_SELECT-', '-DISTRO_SELECT-', '-VERSION_SELECT-',
                   '-DRIVE_SELECT-', '-TYPE_SELECT-')

    def _apply_combo_heights(self):
        """Make the drop-down fields taller.

        A ttk Combobox takes its height from the style's padding, not from the
        element `size` (whose height only sets the drop-down list length), so
        widen the padding on each combo's own ttk style. Best-effort: a failure
        here must never stop the window from opening.
        """
        try:
            import tkinter as tk
            import tkinter.ttk as ttk

            style = ttk.Style()
            for key in self._COMBO_KEYS:
                element = self.window[key]
                widget = getattr(element, 'Widget', None)
                if widget is None:
                    continue
                # Keep PySimpleGUI's own style (it carries the theme colours)
                # and only extend its padding.
                style_name = widget.cget('style') or 'TCombobox'
                style.configure(style_name, padding=(6, 8))
                try:
                    widget.configure(height=12)   # rows shown when opened
                except tk.TclError:
                    pass
        except (ImportError, AttributeError, TypeError) as e:
            logger.warning(f"Could not adjust combo height: {e}")
        except Exception as e:  # noqa: BLE001 - cosmetic only, never fatal
            logger.warning(f"Could not adjust combo height: {e}")

    def show_about(self):
        """Show a small modal About dialog (icon, version, repo link, notice)."""
        from unetbootin import APP_NAME, APP_VERSION

        repo_url = "https://github.com/janos-szenfner/unetbootin-python"

        # The bundled PNG renders on tkinter 8.6; if the icon can't be loaded
        # (very old tkinter, missing file) just omit it rather than fail.
        icon_row = []
        try:
            from unetbootin.resources import icon_path
            png = icon_path('unetbootin_64.png')
            if os.path.exists(png):
                icon_row = [sg.Image(filename=str(png), pad=((0, 12), (0, 0)))]
        except (OSError, ValueError, ImportError) as e:
            logger.debug(f"About icon unavailable: {e}")

        header = icon_row + [
            sg.Column([
                [sg.Text(APP_NAME, font=('Helvetica', 16))],
                [sg.Text(f"{_('Version')} {APP_VERSION}")],
            ], pad=(0, 0))
        ]

        layout = [
            header,
            [sg.Text("")],
            [sg.Text(_("Create bootable USB drives from ISO files"))],
            [sg.Text(repo_url, enable_events=True, key='-ABOUT_LINK-',
                     text_color='blue', tooltip=_("Open the project page"))],
            [sg.Text("")],
            [sg.Text(
                _("This project is a creative endeavour, built for learning and "
                  "experimentation. Use it at your own responsibility. It writes "
                  "directly to storage devices and can overwrite data, so "
                  "double-check your target drive before proceeding. The software "
                  "is provided \"as is\", without warranty of any kind, and the "
                  "authors accept no liability for any data loss or damage "
                  "arising from its use."),
                size=(58, 6))],
            [sg.Push(), sg.Button(_("Close"), key='-ABOUT_CLOSE-'), sg.Push()],
        ]

        win = sg.Window(f"{_('About')} {APP_NAME}", layout, modal=True,
                        keep_on_top=True, finalize=True)
        while True:
            event, _values = win.read()
            if event in (sg.WIN_CLOSED, '-ABOUT_CLOSE-', None):
                break
            if event == '-ABOUT_LINK-':
                try:
                    import webbrowser
                    webbrowser.open(repo_url)
                except (ImportError, OSError) as e:
                    logger.warning(f"Could not open {repo_url}: {e}")
        win.close()

    def update_advanced_visibility(self, visible: bool):
        """Show or hide the advanced options (persistence/boot/firmware tabs)."""
        logger.debug(f"Advanced options visible: {visible}")
        self.advanced_visible = bool(visible)
        self.elements['advanced_column'].update(visible=self.advanced_visible)
        self.elements['advanced_tabs'].update(visible=self.advanced_visible)
        self.elements['advanced_toggle'].update(
            text=_("Close advanced option") if self.advanced_visible
            else _("Open advanced option"))
        # The window was sized without the tabs, so grow/shrink to fit them.
        if self.window:
            self.window.refresh()

    # Controls that must not be touched while a long operation is running.
    _BUSY_KEYS = ('-OK-', '-ISO_DOWNLOAD-', '-REFRESH_DRIVES-', '-ABOUT-',
                  '-ADVANCED_TOGGLE-', '-CATEGORY_SELECT-', '-DISTRO_SELECT-',
                  '-VERSION_SELECT-', '-DRIVE_SELECT-', '-TYPE_SELECT-',
                  '-RADIO_DISTRO-', '-RADIO_FLOPPY-', '-RADIO_MANUAL-')

    def set_busy(self, busy: bool):
        """Grey out the controls while work is running, then restore them.

        Clicks are ignored during a transfer anyway, so disabling makes that
        visible instead of letting presses silently do nothing. The previous
        enabled/disabled state is remembered so restoring never enables a
        control that was legitimately disabled (e.g. the version list).
        """
        if busy:
            self._pre_busy_state = {}
            for key in self._BUSY_KEYS:
                try:
                    element = self.window[key]
                    self._pre_busy_state[key] = getattr(element, 'Disabled', False)
                    element.update(disabled=True)
                except (KeyError, TypeError, AttributeError):
                    continue
        else:
            for key, was_disabled in (getattr(self, '_pre_busy_state', {}) or {}).items():
                try:
                    self.window[key].update(disabled=bool(was_disabled))
                except (KeyError, TypeError, AttributeError):
                    continue
            self._pre_busy_state = {}
        if self.window:
            self.window.refresh()

    def set_cancellable(self, cancellable: bool):
        """Show the Cancel button only while the work can really be stopped.

        Only the download is cancellable; extraction and writing to the device
        are not, so the button is hidden then rather than doing nothing.
        """
        self.elements['cancel_download'].update(visible=cancellable)
        if self.window:
            self.window.refresh()

    def begin_progress(self, text: str = "", cancellable: bool = True):
        """Reveal the inline progress bar, status text and Cancel button."""
        self.elements['progress_bar'].update(current_count=0, visible=True)
        self.elements['progress_text'].update(value=text, visible=True)
        self.elements['cancel_download'].update(visible=cancellable)
        self.set_busy(True)
        if self.window:
            self.window.refresh()

    def set_progress(self, percent: Optional[int] = None,
                     text: Optional[str] = None):
        """Update the inline progress bar and/or its status text."""
        if percent is not None:
            self.elements['progress_bar'].update(
                current_count=max(0, min(int(percent), 100)))
        if text is not None:
            self.elements['progress_text'].update(value=text)
        if self.window:
            self.window.refresh()

    def end_progress(self):
        """Hide the inline progress widgets and re-enable the controls."""
        self.elements['progress_bar'].update(current_count=0, visible=False)
        self.elements['progress_text'].update(value="", visible=False)
        self.elements['cancel_download'].update(visible=False)
        self.set_busy(False)
        if self.window:
            self.window.refresh()

    def toggle_advanced(self):
        """Flip the advanced options open/closed (the toggle button)."""
        self.update_advanced_visibility(not self.advanced_visible)

    def show(self):
        """Show the window."""
        self.window.un_hide()
        return self.window

    def hide(self):
        """Hide the window."""
        if self.window:
            self.window.hide()

    def close(self):
        """Close the window."""
        if self.window:
            self.window.close()

    def is_visible(self):
        """Check if window is visible."""
        return self.window and not self.window.was_closed()

    def read_event(self, timeout: int = None):
        """Read an event from the window with optional timeout."""
        if self.window:
            return self.window.read(timeout=timeout)
        return None, None

    def refresh(self):
        """Refresh the window."""
        if self.window:
            self.window.refresh()
