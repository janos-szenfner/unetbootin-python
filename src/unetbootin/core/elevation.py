"""Elevation module for UNetbootin.

Provides cross-platform privilege elevation without relying on per-command
sudo calls or terminal-dependent flows. Uses:
- Linux: pkexec (PolicyKit) for GUI password prompts
- macOS: osascript with administrator privileges for native elevation
- Windows: ShellExecute with runas verb (UAC prompt)

This allows the application to run privileged commands without requiring
a terminal or hardcoded sudo calls.

Usage:
    # Run a single elevated command
    returncode, stdout, stderr = run_elevated(['mkfs.vfat', '-F32', '/dev/sdb1'])

    # Or use the subprocess-like interface
    result = elevated_subprocess.run(['mount', '/dev/sdb1', '/mnt'])
"""

import sys
import os
import subprocess
import logging
from typing import List, Optional, Tuple, Any
from pathlib import Path

logger = logging.getLogger(__name__)


# Platform detection
_IS_LINUX = sys.platform.startswith('linux')
_IS_MACOS = sys.platform == 'darwin'
_IS_WINDOWS = sys.platform == 'win32'


class ElevationError(Exception):
    """Raised when privilege elevation fails."""
    pass


class ElevationNotAvailableError(ElevationError):
    """Raised when elevation is not available on the current platform."""
    pass


class ElevationCancelledError(ElevationError):
    """Raised when the user cancels the elevation prompt."""
    pass


def is_elevated() -> bool:
    """Check if the current process is running with elevated privileges."""
    if _IS_WINDOWS:
        # Check if we have admin privileges on Windows
        import ctypes
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except (OSError, AttributeError):
            # OSError: ctypes failure; AttributeError: shell32 not available
            return False
    elif _IS_MACOS:
        # Check if we're running as root on macOS
        return os.geteuid() == 0
    elif _IS_LINUX:
        # Check if we're running as root on Linux
        return os.geteuid() == 0
    return False


def check_elevation_availability() -> bool:
    """Check if privilege elevation is available on the current platform."""
    if _IS_LINUX:
        # Any OS-standard helper suffices: pkexec (PolicyKit, GUI prompt) is
        # preferred, with sudo as the universal fallback. No third-party
        # toolkit is required or bundled.
        return _command_exists('pkexec') or _command_exists('sudo')
    elif _IS_MACOS:
        # Authorization Services should always be available on macOS
        return True
    elif _IS_WINDOWS:
        # UAC is always available on Windows
        return True
    return False


def _command_exists(command: str) -> bool:
    """Check if a command exists in PATH."""
    import shutil
    return shutil.which(command) is not None


def run_elevated(
    command: List[str],
    timeout: Optional[float] = None,
    capture_output: bool = True,
    text: bool = True
) -> Tuple[int, str, str]:
    """Run a command with elevated privileges.

    This is the main entry point for running privileged operations.
    It uses platform-specific elevation mechanisms:
    - Linux: pkexec (GUI password prompt via PolicyKit)
    - macOS: osascript with Authorization Services (native GUI prompt)
    - Windows: ShellExecute with runas verb (UAC prompt)

    Args:
        command: The command and arguments to run
        timeout: Optional timeout in seconds
        capture_output: Whether to capture stdout/stderr
        text: Whether to return strings (True) or bytes (False)

    Returns:
        Tuple of (return_code, stdout, stderr)

    Raises:
        ElevationNotAvailableError: If elevation is not available
        ElevationCancelledError: If user cancels the elevation prompt
        ElevationError: If elevation fails for other reasons
    """
    if is_elevated():
        # Already elevated, run directly
        try:
            result = subprocess.run(
                command,
                capture_output=capture_output,
                text=text,
                timeout=timeout
            )
            return (result.returncode, result.stdout or '', result.stderr or '')
        except subprocess.TimeoutExpired:
            return (-1, '', 'Command timed out')
        except (subprocess.SubprocessError, OSError) as e:
            # SubprocessError: Popen/communication errors; OSError: file/exec issues
            return (-1, '', str(e))

    # Not elevated, need to elevate
    if _IS_LINUX:
        return _run_elevated_linux(command, timeout, capture_output, text)
    elif _IS_MACOS:
        return _run_elevated_macos(command, timeout, capture_output, text)
    elif _IS_WINDOWS:
        return _run_elevated_windows(command, timeout, capture_output, text)
    else:
        raise ElevationNotAvailableError(
            f"Privilege elevation not supported on {sys.platform}"
        )


# Graphical askpass helpers shipped by desktops/distros. Only used to let
# `sudo` prompt for a password from its own GUI process (thread-safe) when
# pkexec is not installed. Nothing here is bundled — these are OS-provided.
_ASKPASS_CANDIDATES = (
    "/usr/libexec/openssh/gnome-ssh-askpass",
    "/usr/lib/openssh/gnome-ssh-askpass",
    "/usr/lib/ssh/x11-ssh-askpass",
    "/usr/bin/ssh-askpass",
    "/usr/bin/x11-ssh-askpass",
    "/usr/bin/ksshaskpass",
    "/usr/bin/lxqt-openssh-askpass",
    "/usr/bin/ssh-askpass-fullscreen",
)


def _find_graphical_askpass() -> Optional[str]:
    """Return an OS-provided graphical askpass for `sudo -A`, or None."""
    import shutil
    env = os.environ.get("SUDO_ASKPASS")
    if env and os.path.exists(env):
        return env
    for path in _ASKPASS_CANDIDATES:
        if os.path.exists(path):
            return path
    for name in ("ssh-askpass", "ksshaskpass", "lxqt-openssh-askpass"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _run_elevated_linux(
    command: List[str],
    timeout: Optional[float],
    capture_output: bool,
    text: bool
) -> Tuple[int, str, str]:
    """Elevate on Linux with OS-standard helpers: pkexec first, then sudo.

    No extra toolkit is bundled or required beyond what the OS already provides
    — pkexec (PolicyKit) on desktops, or sudo, which is present on virtually
    every Linux system.
    """
    # 1) pkexec (PolicyKit): native GUI password prompt in its own process.
    if _command_exists('pkexec'):
        try:
            result = subprocess.run(
                ['pkexec'] + command,
                capture_output=capture_output,
                text=text,
                timeout=timeout
            )
            if result.returncode == 126:
                # pkexec: not authorized (user cancelled or wrong password)
                raise ElevationCancelledError(
                    "User cancelled elevation or authentication failed"
                )
            if result.returncode == 127:
                # pkexec: the specified command was not found
                raise ElevationError(f"Command not found: {' '.join(command)}")
            return (result.returncode, result.stdout or '', result.stderr or '')
        except subprocess.TimeoutExpired:
            return (-1, '', 'Elevated command timed out')
        except FileNotFoundError:
            pass  # pkexec vanished between check and exec; fall back to sudo.

    # 2) sudo: the universal fallback when pkexec is not installed.
    if _command_exists('sudo'):
        return _run_with_sudo(command, timeout, capture_output, text)

    raise ElevationNotAvailableError(
        "No privilege-elevation helper found. Install polkit (pkexec) or sudo, "
        "or start the application from a terminal with sudo."
    )


def _run_with_sudo(
    command: List[str],
    timeout: Optional[float],
    capture_output: bool,
    text: bool
) -> Tuple[int, str, str]:
    """Run a command via sudo, prompting graphically only when needed."""
    # Cached credentials or NOPASSWD: run non-interactively, no prompt at all.
    probe = subprocess.run(['sudo', '-n', 'true'], capture_output=True, text=True)
    if probe.returncode == 0:
        try:
            result = subprocess.run(
                ['sudo', '-n'] + command,
                capture_output=capture_output, text=text, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return (-1, '', 'Elevated command timed out')
        return (result.returncode, result.stdout or '', result.stderr or '')

    # A password is required. Use a graphical askpass so the GUI can prompt
    # without a controlling terminal (sudo -A). After the first success sudo
    # caches the credential, so later commands reuse it without re-prompting.
    askpass = _find_graphical_askpass()
    if askpass:
        env = dict(os.environ, SUDO_ASKPASS=askpass)
        try:
            result = subprocess.run(
                ['sudo', '-A'] + command,
                capture_output=capture_output, text=text, timeout=timeout,
                env=env
            )
        except subprocess.TimeoutExpired:
            return (-1, '', 'Elevated command timed out')
        return (result.returncode, result.stdout or '', result.stderr or '')

    raise ElevationNotAvailableError(
        "Administrative rights are required but no graphical password prompt "
        "is available. Install polkit (pkexec), or start the application from "
        "a terminal so sudo can ask for your password."
    )


def _run_elevated_macos(
    command: List[str],
    timeout: Optional[float],
    capture_output: bool,
    text: bool
) -> Tuple[int, str, str]:
    """Run a command with elevated privileges on macOS using Authorization Services.

    Uses osascript to execute the command with administrator privileges.
    This provides a native GUI password prompt.
    """
    import shlex

    # Build the shell command
    cmd_str = shlex.join(command)

    # Use osascript to run with admin privileges
    script = f'do shell script "{cmd_str}" with administrator privileges'

    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=capture_output,
            text=text,
            timeout=timeout
        )

        # Check for specific errors
        if result.returncode != 0:
            stderr = result.stderr or ''
            if 'User canceled' in stderr:
                raise ElevationCancelledError("User cancelled elevation")
            elif 'not authorized' in stderr:
                raise ElevationError("Administrator authorization failed")

        return (result.returncode, result.stdout or '', result.stderr or '')

    except subprocess.TimeoutExpired:
        return (-1, '', 'Elevated command timed out')
    except FileNotFoundError:
        raise ElevationNotAvailableError("osascript not found")


def _run_elevated_windows(
    command: List[str],
    timeout: Optional[float],
    capture_output: bool,
    text: bool
) -> Tuple[int, str, str]:
    """Run a command with elevated privileges on Windows using UAC.

    Uses ShellExecute with runas verb to trigger UAC elevation.
    """
    import ctypes
    from ctypes import wintypes

    # ShellExecuteW constants
    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SEE_MASK_WAITFORINPUTIDLE = 0x00000200
    SW_SHOWNORMAL = 1

    # Build command line
    cmd_line = ' '.join(command)

    # Initialize process handle
    hProcess = wintypes.HANDLE()

    try:
        # Call ShellExecuteW with runas verb
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,
            'runas',
            command[0],
            cmd_line,
            None,
            SW_SHOWNORMAL,
            SEE_MASK_NOCLOSEPROCESS | SEE_MASK_WAITFORINPUTIDLE,
            ctypes.byref(hProcess)
        )

        # Check return value
        if ret <= 32:
            # Error occurred
            if ret == 0:
                # The system is busy or a memory error occurred
                raise ElevationError("Failed to start elevated process")
            elif ret == ERROR_CANCELLED:
                # User cancelled the UAC prompt
                raise ElevationCancelledError("User cancelled UAC prompt")
            elif ret == ERROR_ACCESS_DENIED:
                # Access denied
                raise ElevationError("Access denied")
            else:
                raise ElevationError(f"ShellExecute failed with error code {ret}")

        # Wait for process to complete
        if timeout is not None:
            wait_result = ctypes.windll.kernel32.WaitForSingleObject(
                hProcess, int(timeout * 1000)
            )
            if wait_result != 0:  # WAIT_OBJECT_0 = 0
                return (-1, '', 'Elevated command timed out')
        else:
            ctypes.windll.kernel32.WaitForSingleObject(hProcess, 0xFFFFFFFF)

        # Get exit code
        exit_code = wintypes.DWORD()
        ctypes.windll.kernel32.GetExitCodeProcess(hProcess, ctypes.byref(exit_code))

        # For Windows, we can't easily capture output from ShellExecute
        # So we return empty strings for stdout/stderr
        return (exit_code.value, '', '')

    except (OSError, ctypes.ArgumentError, ValueError) as e:
        # OSError: system call failures; ArgumentError/ValueError: ctypes issues
        raise ElevationError(f"Failed to run elevated command: {e}")
    finally:
        if hProcess.value:
            ctypes.windll.kernel32.CloseHandle(hProcess)


# Windows error codes
ERROR_CANCELLED = 1223
ERROR_ACCESS_DENIED = 5


def create_elevated_process(
    command: List[str],
    timeout: Optional[float] = None
) -> subprocess.Popen:
    """Create an elevated subprocess that can be communicated with.

    This is useful for commands that need to maintain a connection
    with the elevated process for streaming output.

    Note: This is more limited than run_elevated() and may not work
    on all platforms for all commands.
    """
    if is_elevated():
        return subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

    raise NotImplementedError(
        "Interactive elevated processes not yet supported on non-elevated contexts"
    )


def run_elevated_subprocess(
    args: List[str],
    **kwargs: Any
) -> subprocess.CompletedProcess:
    """Drop-in replacement for subprocess.run that handles privilege elevation.

    This function can be used as a replacement for subprocess.run calls that
    currently use sudo. It will:
    - If already elevated: run the command directly
    - If not elevated: use platform-specific elevation (pkexec, osascript, UAC)

    Example:
        # Instead of: subprocess.run(['sudo', 'mkfs.vfat', ...])
        # Use: run_elevated_subprocess(['mkfs.vfat', ...])

    Note: This doesn't prepend 'sudo' - pass the command without sudo.
    """
    if is_elevated():
        return subprocess.run(args, **kwargs)

    # Not elevated - use our elevation mechanism
    capture_output = kwargs.get('capture_output', False)
    text = kwargs.get('text', False)
    timeout = kwargs.get('timeout', None)

    try:
        returncode, stdout, stderr = run_elevated(
            args,
            timeout=timeout,
            capture_output=capture_output,
            text=text
        )

        # Create a mock CompletedProcess to match subprocess.run API
        class MockCompletedProcess:
            def __init__(self, args, returncode, stdout, stderr):
                self.args = args
                self.returncode = returncode
                self.stdout = stdout if text else stdout.encode() if stdout else b''
                self.stderr = stderr if text else stderr.encode() if stderr else b''

            def check_returncode(self):
                if self.returncode != 0:
                    raise subprocess.CalledProcessError(
                        self.returncode, self.args, self.stdout, self.stderr
                    )

            def __repr__(self):
                return f"CompletedProcess(args={self.args!r}, returncode={self.returncode})"

        return MockCompletedProcess(args, returncode, stdout, stderr)

    except (ElevationError, ElevationNotAvailableError) as e:
        # Return a failed CompletedProcess
        class MockCompletedProcess:
            def __init__(self, args, returncode, stdout, stderr):
                self.args = args
                self.returncode = -1
                self.stdout = ''
                self.stderr = str(e)

            def check_returncode(self):
                raise subprocess.CalledProcessError(
                    self.returncode, self.args, self.stdout, self.stderr
                )

        return MockCompletedProcess(args, -1, '', str(e))


def ensure_elevated() -> None:
    """Ensure the application is running with elevated privileges.

    If not elevated, attempts to relaunch with elevation.
    If relaunch is not possible, raises an exception.

    Raises:
        ElevationNotAvailableError: If elevation is not available
        ElevationCancelledError: If user cancels
        ElevationError: If elevation fails
    """
    if is_elevated():
        return

    if not check_elevation_availability():
        raise ElevationNotAvailableError(
            "Privilege elevation not available on this system. "
            "Please run from a terminal with sudo or as administrator."
        )

    # Try to relaunch with elevation
    import sys
    import shlex

    if _IS_LINUX:
        # On Linux, we use pkexec to relaunch
        try:
            subprocess.run(
                ['pkexec'] + sys.argv,
                check=True
            )
            # If we get here, pkexec succeeded and we should exit
            sys.exit(0)
        except subprocess.CalledProcessError as e:
            if e.returncode == 126:
                raise ElevationCancelledError("User cancelled elevation")
            raise ElevationError(f"Failed to elevate: {e}")

    elif _IS_MACOS:
        # On macOS, use osascript to relaunch
        cmd_str = shlex.join(sys.argv)
        try:
            subprocess.run(
                ['osascript', '-e', f'do shell script "{cmd_str}" with administrator privileges'],
                check=True
            )
            sys.exit(0)
        except subprocess.CalledProcessError:
            raise ElevationError("Failed to elevate privileges")

    elif _IS_WINDOWS:
        # On Windows, we can't easily relaunch ourselves with UAC
        # This would need a manifest and special handling
        # For now, show error with instructions
        try:
            import sg
            sg.popup_error(
                "Please run UNetbootin as Administrator.\n\n"
                "Right-click on the application and select 'Run as administrator'.",
                title="Administrator Required"
            )
        except ImportError:
            # PySimpleGUI not available (CLI mode)
            print("Please run UNetbootin as Administrator.")
            print("Right-click on the application and select 'Run as administrator'.")
        raise ElevationError("Windows UAC automatic relaunch not yet implemented")


def install_sudo_interceptor() -> None:
    """Install a monkey-patch that intercepts subprocess.run calls with sudo.

    This allows existing code that uses subprocess.run(['sudo', ...]) to work
    with the new elevation system without modifying every call site.

    Usage:
        from unetbootin.core.elevation import install_sudo_interceptor
        install_sudo_interceptor()

        # Now subprocess.run(['sudo', 'mkfs.vfat', ...]) will use elevation
    """
    original_run = subprocess.run
    original_Popen = subprocess.Popen

    def patched_run(args, **kwargs):
        """Patched subprocess.run that handles sudo commands."""
        # Check if this is a sudo command
        if args and len(args) > 0 and args[0] == 'sudo':
            # Extract the actual command (remove 'sudo')
            actual_cmd = args[1:]
            if not actual_cmd:
                # Just 'sudo' with no command - pass through
                return original_run(args, **kwargs)

            logger.debug(f"Intercepted sudo command: {actual_cmd}")
            return run_elevated_subprocess(actual_cmd, **kwargs)

        return original_run(args, **kwargs)

    def patched_Popen(args, **kwargs):
        """Patched subprocess.Popen that handles sudo commands."""
        if args and len(args) > 0 and args[0] == 'sudo':
            actual_cmd = args[1:]
            if not actual_cmd:
                return original_Popen(args, **kwargs)

            logger.debug(f"Intercepted sudo Popen: {actual_cmd}")
            # For Popen, we need to handle it differently
            # For now, just use run and return a mock
            result = run_elevated_subprocess(actual_cmd, **kwargs)

            # Create a mock Popen that returns the result
            class MockPopen:
                def __init__(self, result):
                    self.returncode = result.returncode
                    self.stdout = result.stdout
                    self.stderr = result.stderr
                    self.args = args

                def communicate(self, input=None, timeout=None):
                    return (self.stdout, self.stderr)

                def wait(self, timeout=None):
                    return self.returncode

                def poll(self):
                    return self.returncode

            return MockPopen(result)

        return original_Popen(args, **kwargs)

    # Apply the patches
    subprocess.run = patched_run
    subprocess.Popen = patched_Popen

    logger.info("Sudo interceptor installed - subprocess.run(['sudo', ...]) will use elevation")
