"""Main window UI for UNetbootin, built with CustomTkinter.

Replaces the PySimpleGUI/tkinter window with a modern, HiDPI-aware interface
that follows the system light/dark setting.

The public surface is deliberately identical to the previous window, including
an event-queue shim (`read_event`, `window.read`, `window.write_event_value`),
so the application logic in `app.py` — threading, cancellation, progress and
elevation — keeps working unchanged against a callback-driven toolkit.
"""

import os
import queue
import logging
import tkinter
from tkinter import filedialog, messagebox
from typing import Optional, List, Dict, Any

try:
    import customtkinter as ctk
    HAS_CTK = True
except ImportError:  # pragma: no cover - exercised only without the dependency
    HAS_CTK = False
    ctk = None

from unetbootin import APP_TITLE
from unetbootin.core.i18n import _

logger = logging.getLogger(__name__)

# Returned by read_event() when the user closes the window. Matches the value
# app.py already compares against.
WIN_CLOSED = None

# Emitted when a read times out with nothing queued.
TIMEOUT_EVENT = '__TIMEOUT__'

# CustomTkinter draws its widgets on canvases that need Tk 8.6. On Tk 8.5 the
# window opens correctly sized and laid out but nothing is painted, which looks
# like an empty window rather than an error.
MIN_TK_VERSION = 8.6


def check_toolkit() -> Optional[str]:
    """Return a message describing an unusable Tk, or None when it is fine."""
    try:
        version = float(tkinter.TkVersion)
    except (TypeError, ValueError):
        return None
    if version < MIN_TK_VERSION:
        return (f"Tk {version} is too old for this interface (Tk "
                f"{MIN_TK_VERSION}+ is required). The window would open but "
                "stay blank. Please run with a Python built against Tk 8.6.")
    return None


def apply_theme(mode: str = "system"):
    """Set the appearance mode and colour theme.

    'system' follows the desktop's light/dark preference; the previous UI was
    hard-coded to white.
    """
    if not HAS_CTK:
        return
    try:
        ctk.set_appearance_mode(mode)
        ctk.set_default_color_theme("blue")
    except (AttributeError, TypeError, ValueError) as e:
        logger.warning(f"Could not apply theme: {e}")


def window_icon_path() -> Optional[str]:
    """Path to the bundled app icon used for the window/task-bar icon."""
    try:
        from unetbootin.resources import icon_path
        for name in ('unetbootin_128.png', 'unetbootin_64.png',
                     'unetbootin_256.png', 'unetbootin_48.png'):
            candidate = icon_path(name)
            if os.path.exists(candidate):
                return str(candidate)
    except (OSError, ValueError, ImportError) as e:
        logger.debug(f"Bundled window icon unavailable: {e}")
    return None


# --------------------------------------------------------------------------
# Dialog helpers (replacing the PySimpleGUI popups)
# --------------------------------------------------------------------------

def popup_error(message: str, title: str = "Error"):
    """Show an error dialog."""
    try:
        messagebox.showerror(title, message)
    except tkinter.TclError as e:
        logger.error(f"{title}: {message} ({e})")


def popup_ok(message: str, title: str = "Information"):
    """Show an informational dialog."""
    try:
        messagebox.showinfo(title, message)
    except tkinter.TclError as e:
        logger.info(f"{title}: {message} ({e})")


def popup_yes_no(message: str, title: str = "Confirm") -> str:
    """Ask a yes/no question. Returns 'Yes' or 'No' to match the old API."""
    try:
        return 'Yes' if messagebox.askyesno(title, message) else 'No'
    except tkinter.TclError as e:
        logger.warning(f"Could not ask '{title}': {e}")
        return 'No'


def popup_get_file(message: str, title: str = "Select file",
                   file_types=None, **_kwargs) -> Optional[str]:
    """Ask for a file path. Returns None when cancelled."""
    try:
        return filedialog.askopenfilename(title=title or message) or None
    except tkinter.TclError as e:
        logger.warning(f"Could not open file dialog: {e}")
        return None


class _Element:
    """Adapter giving a widget the ``.get()`` / ``.update()`` API app.py uses."""

    def __init__(self, widget, kind: str = 'generic',
                 variable=None, owner: 'MainWindowCTk' = None):
        self.widget = widget
        self.kind = kind
        self.variable = variable
        self.owner = owner

    def get(self):
        """Current value of the widget."""
        try:
            if self.variable is not None:
                return self.variable.get()
            if self.kind == 'text':
                # tkinter Text/CTkTextbox needs an index range.
                return self.widget.get("1.0", "end").strip()
            if self.kind == 'entry':
                return self.widget.get()
            if self.kind in ('combo', 'option'):
                return self.widget.get()
            if hasattr(self.widget, 'get'):
                return self.widget.get()
        except (tkinter.TclError, AttributeError) as e:
            logger.debug(f"Could not read widget value: {e}")
        return ''

    def update(self, value=None, values=None, visible=None, disabled=None,
               text=None, current_count=None, filename=None, **_kwargs):
        """Apply the subset of updates the application performs."""
        try:
            if values is not None and hasattr(self.widget, 'configure'):
                self.widget.configure(values=list(values))
            if value is not None:
                if self.variable is not None:
                    self.variable.set(value)
                elif self.kind == 'entry':
                    self.widget.delete(0, 'end')
                    self.widget.insert(0, str(value))
                elif hasattr(self.widget, 'set'):
                    self.widget.set(value)
            if text is not None and hasattr(self.widget, 'configure'):
                self.widget.configure(text=text)
            if current_count is not None and hasattr(self.widget, 'set'):
                # CTkProgressBar works on a 0..1 scale.
                self.widget.set(max(0.0, min(float(current_count) / 100.0, 1.0)))
            if filename is not None:
                self.owner._set_image(self.widget, filename)
            if disabled is not None and hasattr(self.widget, 'configure'):
                self.widget.configure(state='disabled' if disabled else 'normal')
            if visible is not None:
                self.owner._set_visible(self.widget, visible)
        except (tkinter.TclError, AttributeError, ValueError) as e:
            logger.debug(f"Could not update widget: {e}")


class _WindowShim:
    """Presents the tk root through the small API `app.py` expects."""

    def __init__(self, owner: 'MainWindowCTk'):
        self._owner = owner

    def hide(self):
        self._owner.hide()

    def un_hide(self):
        self._owner.show()

    def read(self, timeout: Optional[int] = None):
        return self._owner.read_event(timeout=timeout)

    def write_event_value(self, key, value):
        self._owner.emit(key, value)

    def close(self):
        self._owner.close()

    def refresh(self):
        self._owner.refresh()

    def was_closed(self) -> bool:
        return self._owner.closed


class MainWindowCTk:
    """The application's main window."""

    _CATEGORY_ICONS = {
        'linux': 'category_linux.png',
        'bsd': 'category_bsd.png',
        'windows': 'category_windows.png',
    }

    # Controls disabled while a long operation runs.
    _BUSY_ELEMENTS = ('ok', 'iso_download', 'refresh', 'about',
                      'advanced_toggle', 'category_select', 'distro_select',
                      'version_select', 'drive_select', 'type_select',
                      'radio_distro', 'radio_floppy', 'radio_manual')

    def __init__(self, parent=None):
        if not HAS_CTK:
            raise ImportError(
                "customtkinter is required but not installed. "
                "Please install it with: pip install customtkinter")

        logger.info("Creating MainWindow UI with CustomTkinter")

        self.distributions: Dict[str, Any] = {}
        self.categories: List[str] = []
        self.current_distro = None
        self.current_version = None
        self.install_type = "distribution"
        self.drive_data: List[tuple] = []
        self.advanced_visible = True
        self.closed = False

        self._events: "queue.Queue" = queue.Queue()
        self._images: Dict[int, Any] = {}
        self._geometry: Dict[int, Dict[str, Any]] = {}
        self._pre_busy_state: Dict[str, bool] = {}

        self.elements: Dict[str, _Element] = {}
        self.window = _WindowShim(self)

        self.init_ui()

    # ---------------------------------------------------------------- layout

    def init_ui(self):
        """Build the window."""
        apply_theme()

        self.root = ctk.CTk()
        self.root.title(APP_TITLE)
        self.root.geometry("900x680")
        self.root.minsize(760, 560)
        self.root.protocol("WM_DELETE_WINDOW", lambda: self.emit(WIN_CLOSED, None))
        self._apply_window_icon()

        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(4, weight=1)

        pad = {'padx': 16, 'pady': (10, 0)}

        # ---- header -------------------------------------------------------
        header = ctk.CTkFrame(self.root, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", **pad)
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text=APP_TITLE,
                     font=ctk.CTkFont(size=22, weight="bold")).grid(
            row=0, column=0, sticky="w")
        about = ctk.CTkButton(header, text=_("About"), width=90,
                              command=lambda: self.emit('-ABOUT-'))
        about.grid(row=0, column=2, sticky="e")
        self.elements['about'] = _Element(about, 'button', owner=self)

        # ---- source selection --------------------------------------------
        source = ctk.CTkFrame(self.root)
        source.grid(row=1, column=0, sticky="ew", **pad)
        source.grid_columnconfigure((1, 2, 3), weight=1)

        self._install_type = ctk.StringVar(value="distribution")
        radios = ctk.CTkFrame(source, fg_color="transparent")
        radios.grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(12, 4))
        for i, (label, value, key) in enumerate((
                (_("Distribution"), "distribution", 'radio_distro'),
                (_("Disk image"), "floppy", 'radio_floppy'),
                (_("Custom"), "manual", 'radio_manual'))):
            rb = ctk.CTkRadioButton(
                radios, text=label, variable=self._install_type, value=value,
                command=lambda v=value: self._on_install_type(v))
            rb.grid(row=0, column=i, padx=(0, 18))
            self.elements[key] = _Element(rb, 'radio', owner=self)

        # Distribution pickers
        self._category_icon = ctk.CTkLabel(source, text="", width=36)
        self._category_icon.grid(row=1, column=0, padx=(12, 6), pady=(4, 12))
        self.elements['category_icon'] = _Element(
            self._category_icon, 'image', owner=self)

        self._category = ctk.CTkOptionMenu(
            source, values=["All"], width=170,
            command=lambda v: self.emit('-CATEGORY_SELECT-', v))
        self._category.grid(row=1, column=1, sticky="ew", padx=6, pady=(4, 12))
        self.elements['category_select'] = _Element(
            self._category, 'option', owner=self)

        self._distro = ctk.CTkOptionMenu(
            source, values=[""], width=240,
            command=lambda v: self.emit('-DISTRO_SELECT-', v))
        self._distro.grid(row=1, column=2, sticky="ew", padx=6, pady=(4, 12))
        self.elements['distro_select'] = _Element(
            self._distro, 'option', owner=self)

        self._version = ctk.CTkOptionMenu(
            source, values=[""], width=210,
            command=lambda v: self.emit('-VERSION_SELECT-', v))
        self._version.grid(row=1, column=3, sticky="ew", padx=(6, 12), pady=(4, 12))
        self.elements['version_select'] = _Element(
            self._version, 'option', owner=self)

        # File pickers for the disk-image / custom modes
        self._file_rows = ctk.CTkFrame(source, fg_color="transparent")
        self._file_rows.grid(row=2, column=0, columnspan=4, sticky="ew",
                             padx=12, pady=(0, 12))
        # One shared grid for all four rows: column 0 sizes itself to the
        # widest label, so the entries and buttons line up exactly whatever the
        # labels say. (Per-row layouts are what made these look ragged before.)
        self._file_rows.grid_columnconfigure(0, minsize=96)
        self._file_rows.grid_columnconfigure(1, weight=1)
        self._file_rows.grid_remove()

        for row, (label, key, event) in enumerate((
                (_("Disk image:"), 'floppy_file', '-FLOPPY_BROWSE-'),
                (_("Kernel:"), 'kernel_file', '-KERNEL_BROWSE-'),
                (_("Initrd:"), 'initrd_file', '-INITRD_BROWSE-'),
                (_("Cfg:"), 'cfg_file', '-CFG_BROWSE-'))):
            lbl = ctk.CTkLabel(self._file_rows, text=label, anchor="w")
            lbl.grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
            entry = ctk.CTkEntry(self._file_rows)
            entry.grid(row=row, column=1, sticky="ew", padx=(0, 8), pady=4)
            btn = ctk.CTkButton(self._file_rows, text="...", width=48,
                                command=lambda e=event: self.emit(e))
            btn.grid(row=row, column=2, sticky="e", pady=4)
            self.elements[key] = _Element(entry, 'entry', owner=self)
            self.elements[key + '_label'] = _Element(lbl, 'label', owner=self)
            self.elements[key + '_browse'] = _Element(btn, 'button', owner=self)

        # ---- target -------------------------------------------------------
        target = ctk.CTkFrame(self.root)
        target.grid(row=2, column=0, sticky="ew", **pad)
        target.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(target, text=_("Target Drive:"), width=110,
                     anchor="w").grid(row=0, column=0, sticky="w",
                                      padx=(12, 6), pady=(12, 6))
        self._drive = ctk.CTkOptionMenu(
            target, values=[""],
            command=lambda v: self.emit('-DRIVE_SELECT-', v))
        self._drive.grid(row=0, column=1, sticky="ew", padx=6, pady=(12, 6))
        self.elements['drive_select'] = _Element(self._drive, 'option', owner=self)
        refresh = ctk.CTkButton(target, text=_("Refresh"), width=100,
                                command=lambda: self.emit('-REFRESH_DRIVES-'))
        refresh.grid(row=0, column=2, padx=(6, 12), pady=(12, 6))
        self.elements['refresh'] = _Element(refresh, 'button', owner=self)

        ctk.CTkLabel(target, text=_("Type:"), width=110,
                     anchor="w").grid(row=1, column=0, sticky="w",
                                      padx=(12, 6), pady=(0, 12))
        # NOTE: these values are semantic keys compared by the installer and
        # must not be translated.
        self._type = ctk.CTkOptionMenu(
            target, values=["USB Drive", "Hard Disk"],
            command=lambda v: self.emit('-TYPE_SELECT-', v))
        self._type.set("USB Drive")
        self._type.grid(row=1, column=1, sticky="w", padx=6, pady=(0, 12))
        self.elements['type_select'] = _Element(self._type, 'option', owner=self)

        self._info = ctk.CTkLabel(
            target, anchor="w",
            text=_("Select a distribution or ISO file, then select your "
                   "USB drive below."))
        self._info.grid(row=2, column=0, columnspan=3, sticky="ew",
                        padx=12, pady=(0, 12))
        self.elements['info_message'] = _Element(self._info, 'label', owner=self)

        # ---- advanced options + progress ----------------------------------
        bar = ctk.CTkFrame(self.root, fg_color="transparent")
        bar.grid(row=3, column=0, sticky="ew", **pad)
        bar.grid_columnconfigure(1, weight=1)

        toggle = ctk.CTkButton(bar, text=_("Close advanced option"), width=190,
                               command=lambda: self.emit('-ADVANCED_TOGGLE-'))
        toggle.grid(row=0, column=0, sticky="w")
        self.elements['advanced_toggle'] = _Element(toggle, 'button', owner=self)

        self._progress_text = ctk.CTkLabel(bar, text="", anchor="e")
        self._progress_text.grid(row=0, column=1, sticky="ew", padx=10)
        self.elements['progress_text'] = _Element(
            self._progress_text, 'label', owner=self)

        self._progress = ctk.CTkProgressBar(bar, width=220)
        self._progress.set(0)
        self._progress.grid(row=0, column=2, padx=10)
        self.elements['progress_bar'] = _Element(self._progress, 'progress',
                                                 owner=self)

        cancel = ctk.CTkButton(bar, text=_("Cancel download"), width=140,
                               fg_color="#b23b3b", hover_color="#8f2f2f",
                               command=lambda: self.emit('-CANCEL_DOWNLOAD-'))
        cancel.grid(row=0, column=3, sticky="e")
        self.elements['cancel_download'] = _Element(cancel, 'button', owner=self)

        self._set_visible(self._progress, False)
        self._set_visible(self._progress_text, False)
        self._set_visible(cancel, False)

        self._build_advanced()

        # ---- action buttons ------------------------------------------------
        actions = ctk.CTkFrame(self.root, fg_color="transparent")
        actions.grid(row=5, column=0, sticky="ew", padx=16, pady=14)
        actions.grid_columnconfigure(0, weight=1)

        for i, (label, key, event, kwargs) in enumerate((
                (_("OK"), 'ok', '-OK-', {}),
                (_("ISO Download"), 'iso_download', '-ISO_DOWNLOAD-', {}),
                (_("Cancel"), 'cancel', '-CANCEL-', {'fg_color': 'transparent',
                                                     'border_width': 1}),
                (_("Exit"), 'exit', '-EXIT-', {'fg_color': 'transparent',
                                               'border_width': 1}))):
            btn = ctk.CTkButton(actions, text=label, width=130,
                                command=lambda e=event: self.emit(e), **kwargs)
            btn.grid(row=0, column=i + 1, padx=6)
            self.elements[key] = _Element(btn, 'button', owner=self)

        self.root.update_idletasks()

    def _build_advanced(self):
        """Build the advanced options panel (visible by default)."""
        self._advanced = ctk.CTkFrame(self.root)
        self._advanced.grid(row=4, column=0, sticky="nsew", padx=16, pady=(10, 0))
        self._advanced.grid_columnconfigure(0, weight=1)
        self._advanced.grid_rowconfigure(0, weight=1)
        self.elements['advanced_column'] = _Element(self._advanced, 'frame',
                                                    owner=self)

        tabs = ctk.CTkTabview(self._advanced)
        tabs.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.elements['advanced_tabs'] = _Element(tabs, 'tabs', owner=self)

        persistence = tabs.add(_("Persistence"))
        boot = tabs.add(_("Boot Options"))
        firmware = tabs.add(_("Firmware"))
        iso_location = tabs.add(_("ISO Location"))

        # Persistence
        self._persistence = ctk.CTkCheckBox(
            persistence, text=_("Enable persistence"),
            command=lambda: self.emit('-PERSISTENCE_CHECK-',
                                      bool(self._persistence.get())))
        self._persistence.grid(row=0, column=0, sticky="w", padx=10, pady=10)
        self.elements['persistence_check'] = _Element(
            self._persistence, 'check', owner=self)

        ctk.CTkLabel(persistence, text=_("Persistence (MB):")).grid(
            row=1, column=0, sticky="w", padx=10)
        size = ctk.CTkEntry(persistence, width=120)
        size.insert(0, "1000")
        size.configure(state='disabled')
        size.grid(row=1, column=1, sticky="w", padx=10, pady=6)
        self.elements['persistence_size'] = _Element(size, 'entry', owner=self)

        # Boot options
        ctk.CTkLabel(boot, text=_("Boot Options:")).grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 2))
        boot_box = ctk.CTkTextbox(boot, height=90)
        boot_box.grid(row=1, column=0, sticky="ew", padx=10)
        boot.grid_columnconfigure(0, weight=1)
        self.elements['boot_options'] = _Element(boot_box, 'text', owner=self)
        ctk.CTkLabel(boot, text="Example: quiet splash persistent noapic",
                     text_color="gray").grid(row=2, column=0, sticky="w",
                                             padx=10, pady=(4, 10))

        # Firmware
        self._uefi = ctk.CTkCheckBox(firmware, text=_("UEFI-only installation"))
        self._uefi.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 4))
        self.elements['uefi_only'] = _Element(self._uefi, 'check', owner=self)
        self._secure = ctk.CTkCheckBox(firmware, text=_("Enable Secure Boot"))
        self._secure.grid(row=1, column=0, sticky="w", padx=10, pady=4)
        self.elements['secure_boot'] = _Element(self._secure, 'check', owner=self)

        # ISO location
        ctk.CTkLabel(iso_location, text=_("Download the selected ISO to:")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(10, 4))
        iso_dir = ctk.CTkEntry(iso_location)
        iso_dir.grid(row=1, column=0, sticky="ew", padx=10)
        iso_location.grid_columnconfigure(0, weight=1)
        self.elements['iso_dir'] = _Element(iso_dir, 'entry', owner=self)
        ctk.CTkButton(iso_location, text=_("Browse"), width=100,
                      command=self._browse_iso_dir).grid(row=1, column=1, padx=10)
        ctk.CTkLabel(
            iso_location, text_color="gray", justify="left", anchor="w",
            text=_("Leave empty to use your Downloads folder; the ISO is then "
                   "deleted after the drive has been created.")).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(6, 10))

    # ------------------------------------------------------------ utilities

    def _browse_iso_dir(self):
        """Pick the folder ISOs are downloaded into."""
        try:
            chosen = filedialog.askdirectory(title=_("Select ISO folder"))
        except tkinter.TclError as e:
            logger.warning(f"Could not open folder dialog: {e}")
            return
        if chosen:
            self.elements['iso_dir'].update(value=chosen)

    def _on_install_type(self, value: str):
        """Radio buttons map onto the events app.py already handles."""
        self.emit({'distribution': '-RADIO_DISTRO-',
                   'floppy': '-RADIO_FLOPPY-',
                   'manual': '-RADIO_MANUAL-'}[value])

    def _set_visible(self, widget, visible: bool):
        """Show or hide a gridded widget, remembering its position."""
        try:
            key = id(widget)
            if visible:
                info = self._geometry.pop(key, None)
                if info:
                    widget.grid(**info)
                else:
                    widget.grid()
            else:
                info = widget.grid_info()
                if info:
                    self._geometry[key] = {
                        k: info[k] for k in
                        ('row', 'column', 'rowspan', 'columnspan',
                         'sticky', 'padx', 'pady') if k in info
                    }
                widget.grid_remove()
        except (tkinter.TclError, AttributeError) as e:
            logger.debug(f"Could not change visibility: {e}")

    def _set_image(self, widget, filename: str):
        """Put a bundled PNG on a label, keeping a reference alive."""
        try:
            from PIL import Image
            image = ctk.CTkImage(light_image=Image.open(filename),
                                 dark_image=Image.open(filename),
                                 size=(28, 28))
            self._images[id(widget)] = image
            widget.configure(image=image, text="")
        except Exception as e:  # noqa: BLE001 - decorative only
            logger.debug(f"Could not set image {filename}: {e}")

    def _apply_window_icon(self):
        """Give the window the real app icon."""
        icon = window_icon_path()
        if not icon:
            return
        try:
            self.root.iconphoto(True, tkinter.PhotoImage(file=icon))
        except Exception as e:  # noqa: BLE001 - cosmetic only
            logger.warning(f"Could not set the window icon: {e}")

    # --------------------------------------------------------------- events

    def emit(self, key, value=None):
        """Queue an event for read_event(). Safe to call from any thread."""
        self._events.put((key, value))

    def read_event(self, timeout: Optional[int] = None):
        """Pump the toolkit and return the next (event, values) pair.

        Mirrors the previous window's blocking read so app.py's loops work
        unchanged: widget callbacks enqueue events, and this drains that queue
        while keeping the interface responsive.
        """
        if self.closed:
            return WIN_CLOSED, {}

        deadline = (timeout or 0) / 1000.0
        waited = 0.0
        step = 0.01

        while True:
            try:
                self.root.update()
            except tkinter.TclError:
                self.closed = True
                return WIN_CLOSED, {}

            try:
                key, value = self._events.get_nowait()
            except queue.Empty:
                pass
            else:
                if key is WIN_CLOSED:
                    self.closed = True
                    return WIN_CLOSED, {}
                values = self._collect_values()
                values[key] = value
                return key, values

            if timeout is not None and waited >= deadline:
                return TIMEOUT_EVENT, self._collect_values()

            try:
                self.root.after(int(step * 1000))
            except tkinter.TclError:
                self.closed = True
                return WIN_CLOSED, {}
            waited += step

    def _collect_values(self) -> Dict[str, Any]:
        """Values dict in the shape app.py reads."""
        return {
            '-CATEGORY_SELECT-': self.elements['category_select'].get(),
            '-DISTRO_SELECT-': self.elements['distro_select'].get(),
            '-VERSION_SELECT-': self.elements['version_select'].get(),
            '-DRIVE_SELECT-': self.elements['drive_select'].get(),
            '-TYPE_SELECT-': self.elements['type_select'].get(),
            '-PERSISTENCE_CHECK-': bool(self.elements['persistence_check'].get()),
        }

    # ------------------------------------------------------- window control

    def show(self):
        self.root.deiconify()
        self.root.lift()
        return self.root

    def hide(self):
        self.root.withdraw()

    def close(self):
        self.closed = True
        try:
            self.root.destroy()
        except tkinter.TclError:
            pass

    def refresh(self):
        try:
            self.root.update_idletasks()
        except tkinter.TclError:
            pass

    def is_visible(self) -> bool:
        return not self.closed

    # ------------------------------------------------------------- contents

    def set_distributions(self, distributions: List[Dict[str, Any]]):
        """Populate the distribution list and its categories."""
        logger.info(f"Setting {len(distributions)} distributions")
        self.distributions = {d['name']: d for d in distributions}
        categories = []
        for d in distributions:
            category = d.get('category')
            if category and category not in categories:
                categories.append(category)
        self.set_categories(categories)
        self.update_distro_list()

    def set_categories(self, categories: List[str]):
        self.categories = categories
        values = ['All'] + categories
        self.elements['category_select'].update(values=values, value='All')
        self.set_category_icon('All')

    def set_category_icon(self, category: Optional[str]):
        """Show the icon for the selected category beside the drop-down."""
        filename = self._CATEGORY_ICONS.get((category or '').strip().lower())
        try:
            if not filename:
                self._category_icon.configure(image=None, text="")
                return
            from unetbootin.resources import icon_path
            path = icon_path(filename)
            if os.path.exists(path):
                self._set_image(self._category_icon, str(path))
        except Exception as e:  # noqa: BLE001 - decorative only
            logger.warning(f"Could not set category icon: {e}")

    def update_distro_list(self, category_filter: str = None):
        """Refresh the distribution names, alphabetically."""
        if category_filter is None:
            category_filter = self.elements['category_select'].get()

        if category_filter and category_filter != "All":
            filtered = [d for d in self.distributions.values()
                        if d.get('category') == category_filter]
        else:
            filtered = list(self.distributions.values())

        # Case-insensitive: a plain sort puts lowercase-initial names
        # (openSUSE) after every capitalised one.
        def sort_key(distro):
            display = distro.get('display_name', distro['name'])
            return (display.lower(), distro['name'].lower())

        names = [d.get('display_name', d['name'])
                 for d in sorted(filtered, key=sort_key)]

        current = self.elements['distro_select'].get()
        self.elements['distro_select'].update(values=names or [""])
        if current and current in names:
            self.elements['distro_select'].update(value=current)
        elif names:
            self.elements['distro_select'].update(value=names[0])
            self.update_version_list(names[0])

    def update_version_list(self, distro_name: str = None):
        """Refresh the versions of the selected distribution."""
        if distro_name is None:
            distro_name = self.get_current_distro_name()

        distro = self._find_distro(distro_name)
        if not distro:
            return

        versions = distro.get('versions', [])
        names = [v['name'] for v in versions]
        self.elements['version_select'].update(values=names or [""])
        if names:
            self.elements['version_select'].update(value=names[0])
            self.elements['version_select'].update(disabled=False)
        else:
            self.elements['version_select'].update(disabled=True)

        info = distro.get('description') or distro.get('display_name', '')
        self.elements['info_message'].update(text=info)

    def _find_distro(self, display_or_name: str) -> Optional[Dict[str, Any]]:
        """Look a distribution up by display name or internal name."""
        if not display_or_name:
            return None
        for d in self.distributions.values():
            if display_or_name in (d.get('display_name'), d.get('name')):
                return d
        return None

    def get_current_distro_name(self) -> Optional[str]:
        """Internal name of the selected distribution."""
        distro = self._find_distro(self.elements['distro_select'].get())
        return distro['name'] if distro else None

    def get_current_version_name(self) -> Optional[str]:
        return self.elements['version_select'].get()

    def set_drive_list(self, drives: List[tuple]) -> bool:
        """Populate the target-drive list."""
        logger.info(f"Setting {len(drives)} drives")
        current = self.elements['drive_select'].get()
        current_device = None
        for display, device in self.drive_data:
            if display == current:
                current_device = device
                break

        self.drive_data = drives
        display_list = [display for display, _device in drives]
        self.elements['drive_select'].update(values=display_list or [""])
        self.elements['drive_select'].update(disabled=not drives)

        if current_device:
            for display, device in drives:
                if device == current_device:
                    self.elements['drive_select'].update(value=display)
                    break
        elif display_list:
            self.elements['drive_select'].update(value=display_list[0])

        return len(drives) > 0

    def get_current_drive(self) -> Optional[str]:
        """Device path of the selected drive."""
        display = self.elements['drive_select'].get()
        for text, device in self.drive_data:
            if text == display:
                return device
        return None

    def update_install_type(self, install_type: str):
        self.install_type = install_type
        self.update_install_type_ui()

    def update_install_type_ui(self):
        """Show only the fields relevant to the selected source."""
        mode = self._install_type.get()
        distro_mode = mode == 'distribution'

        for widget in (self._category_icon, self._category,
                       self._distro, self._version):
            self._set_visible(widget, distro_mode)

        if distro_mode:
            self._file_rows.grid_remove()
            return

        self._file_rows.grid()
        floppy = mode == 'floppy'
        for key, shown in (('floppy_file', floppy),
                           ('kernel_file', not floppy),
                           ('initrd_file', not floppy),
                           ('cfg_file', not floppy)):
            for suffix in ('', '_label', '_browse'):
                self.elements[key + suffix].update(visible=shown)

    # ------------------------------------------------------------- progress

    def set_busy(self, busy: bool):
        """Disable the controls while work runs, then restore them."""
        if busy:
            self._pre_busy_state = {}
            for key in self._BUSY_ELEMENTS:
                element = self.elements.get(key)
                if element is None:
                    continue
                try:
                    state = str(element.widget.cget('state'))
                except (tkinter.TclError, AttributeError, ValueError):
                    state = 'normal'
                self._pre_busy_state[key] = state == 'disabled'
                element.update(disabled=True)
        else:
            for key, was_disabled in (self._pre_busy_state or {}).items():
                element = self.elements.get(key)
                if element is not None:
                    element.update(disabled=bool(was_disabled))
            self._pre_busy_state = {}
        self.refresh()

    def set_cancellable(self, cancellable: bool):
        """Offer Cancel only while the work can really be stopped."""
        self.elements['cancel_download'].update(visible=cancellable)
        self.refresh()

    def begin_progress(self, text: str = "", cancellable: bool = True):
        self.elements['progress_bar'].update(current_count=0, visible=True)
        self.elements['progress_text'].update(text=text, visible=True)
        self.elements['cancel_download'].update(visible=cancellable)
        self.set_busy(True)
        self.refresh()

    def set_progress(self, percent: Optional[int] = None,
                     text: Optional[str] = None):
        if percent is not None:
            self.elements['progress_bar'].update(current_count=percent)
        if text is not None:
            self.elements['progress_text'].update(text=text)
        self.refresh()

    def end_progress(self):
        self.elements['progress_bar'].update(current_count=0, visible=False)
        self.elements['progress_text'].update(text="", visible=False)
        self.elements['cancel_download'].update(visible=False)
        self.set_busy(False)
        self.refresh()

    # ------------------------------------------------------------- advanced

    def update_advanced_visibility(self, visible: bool):
        self.advanced_visible = bool(visible)
        if self.advanced_visible:
            self._advanced.grid()
        else:
            self._advanced.grid_remove()
        self.elements['advanced_toggle'].update(
            text=_("Close advanced option") if self.advanced_visible
            else _("Open advanced option"))
        self.refresh()

    def toggle_advanced(self):
        self.update_advanced_visibility(not self.advanced_visible)

    # -------------------------------------------------------------- results

    def get_installation_parameters(self) -> Dict[str, Any]:
        """Collect the current selection for the installer."""
        mode = self._install_type.get()
        params: Dict[str, Any] = {'install_type': mode}

        if mode == 'distribution':
            params['distro'] = self.get_current_distro_name()
            params['version'] = self.get_current_version_name()
        elif mode == 'floppy':
            params['floppy_image'] = self.elements['floppy_file'].get()
        else:
            params['kernel'] = self.elements['kernel_file'].get()
            params['initrd'] = self.elements['initrd_file'].get()
            params['cfg'] = self.elements['cfg_file'].get()

        params['drive_type'] = self.elements['type_select'].get()
        params['target_drive'] = self.get_current_drive()

        if self.advanced_visible:
            params['persistence_enabled'] = bool(
                self.elements['persistence_check'].get())
            try:
                params['persistence_size'] = int(
                    self.elements['persistence_size'].get() or 0)
            except (TypeError, ValueError):
                params['persistence_size'] = 0

            boot_options = (self.elements['boot_options'].get() or '').strip()
            if boot_options:
                params['boot_options'] = boot_options

            params['enable_uefi_only'] = bool(self.elements['uefi_only'].get())
            params['enable_secure_boot'] = bool(
                self.elements['secure_boot'].get())

            iso_dir = (self.elements['iso_dir'].get() or '').strip()
            if iso_dir:
                params['iso_download_dir'] = iso_dir

        return params

    # ----------------------------------------------------------------- about

    def show_about(self):
        """Small modal About dialog."""
        from unetbootin import APP_NAME, APP_VERSION

        repo_url = "https://github.com/janos-szenfner/unetbootin-python"

        win = ctk.CTkToplevel(self.root)
        win.title(f"{_('About')} {APP_TITLE}")
        win.geometry("470x360")
        win.resizable(False, False)
        win.transient(self.root)

        icon = window_icon_path()
        if icon:
            try:
                from PIL import Image
                image = ctk.CTkImage(light_image=Image.open(icon),
                                     dark_image=Image.open(icon), size=(64, 64))
                label = ctk.CTkLabel(win, image=image, text="")
                label.image = image
                label.pack(pady=(18, 6))
            except Exception as e:  # noqa: BLE001 - decorative only
                logger.debug(f"About icon unavailable: {e}")

        ctk.CTkLabel(win, text=APP_NAME,
                     font=ctk.CTkFont(size=20, weight="bold")).pack()
        ctk.CTkLabel(win, text=f"{_('Version')} {APP_VERSION}").pack(pady=(0, 8))
        ctk.CTkLabel(
            win, text=_("Create bootable USB drives from ISO files")).pack()

        link = ctk.CTkLabel(win, text=repo_url, text_color="#3b82f6",
                            cursor="hand2")
        link.pack(pady=(6, 10))
        link.bind("<Button-1>", lambda _e: self._open_url(repo_url))

        ctk.CTkLabel(
            win, wraplength=420, justify="left", text_color="gray",
            text=_("This project is a creative endeavour, built for learning "
                   "and experimentation. Use it at your own responsibility. It "
                   "writes directly to storage devices and can overwrite data, "
                   "so double-check your target drive before proceeding. The "
                   "software is provided \"as is\", without warranty of any "
                   "kind.")).pack(padx=22, pady=(0, 12))

        ctk.CTkButton(win, text=_("Close"), width=110,
                      command=win.destroy).pack(pady=(0, 16))

        try:
            win.grab_set()
        except tkinter.TclError:
            pass

    @staticmethod
    def _open_url(url: str):
        try:
            import webbrowser
            webbrowser.open(url)
        except (ImportError, OSError) as e:
            logger.warning(f"Could not open {url}: {e}")


# Backwards-compatible alias: the application imports this name.
MainWindowPySG = MainWindowCTk
