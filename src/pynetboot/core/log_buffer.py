"""In-memory log capture, so the running application can show its own log.

A packaged app writes its log file wherever it happens to be started from,
which is rarely somewhere the user can find. Keeping the records in memory as
well lets the interface display them directly.
"""

import os
import logging
import threading
from collections import deque
from typing import Optional

# Enough to cover a full install without growing without bound.
MAX_RECORDS = 5000

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


class LogBuffer(logging.Handler):
    """Logging handler retaining the most recent formatted records."""

    def __init__(self, capacity: int = MAX_RECORDS):
        super().__init__()
        self._records = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord):
        """Store a formatted record. Never raise: logging must not break."""
        try:
            line = self.format(record)
        except Exception:  # noqa: BLE001 - a bad record must not kill logging
            return
        with self._lock:
            self._records.append(line)

    def get_text(self) -> str:
        """Everything captured so far, oldest first."""
        with self._lock:
            return "\n".join(self._records)

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    def clear(self):
        with self._lock:
            self._records.clear()


# Installed once and shared: the UI reads from this.
_buffer: Optional[LogBuffer] = None
_log_file: Optional[str] = None


def install(capacity: int = MAX_RECORDS) -> LogBuffer:
    """Attach the buffer to the root logger. Safe to call more than once."""
    global _buffer
    if _buffer is None:
        _buffer = LogBuffer(capacity)
        _buffer.setFormatter(logging.Formatter(LOG_FORMAT))
        logging.getLogger().addHandler(_buffer)
    return _buffer


def get_buffer() -> Optional[LogBuffer]:
    """The installed buffer, or None if logging was never configured."""
    return _buffer


def get_text() -> str:
    """Captured log text, or an explanatory line when nothing is available."""
    if _buffer is None:
        return "Logging is not initialised, so no messages were captured."
    text = _buffer.get_text()
    return text or "No log messages have been recorded yet."


def set_log_file(path: Optional[str]):
    """Record where the log file is being written, for display."""
    global _log_file
    _log_file = path


def get_log_file() -> Optional[str]:
    """Path of the log file, when one is in use."""
    return _log_file


def default_log_directory() -> str:
    """A predictable per-user location for the log file.

    Follows XDG_STATE_HOME where set, so the log does not land in whatever
    directory the application happened to be launched from.
    """
    base = os.environ.get('XDG_STATE_HOME')
    if not base:
        home = os.path.expanduser('~')
        if os.name == 'nt':
            base = os.environ.get('LOCALAPPDATA') or os.path.join(home, 'AppData',
                                                                  'Local')
        elif os.uname().sysname == 'Darwin' if hasattr(os, 'uname') else False:
            base = os.path.join(home, 'Library', 'Logs')
        else:
            base = os.path.join(home, '.local', 'state')
    return os.path.join(base, 'pynetboot')
