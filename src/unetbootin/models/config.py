"""
Configuration management for UNetbootin.
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AppConfig:
    """Application configuration values."""
    lang: str = 'en_US'
    last_iso_path: str = ''
    last_target_drive: str = ''
    last_install_type: str = 'distribution'
    last_distro: str = ''
    last_version: str = ''
    enable_persistence: bool = False
    persistence_size: int = 1000
    check_updates: bool = True
    window_geometry: Dict[str, Any] = field(default_factory=dict)
    # Boot options
    boot_options: str = ''
    enable_uefi_only: bool = False
    enable_secure_boot: bool = False
    # Download settings
    enable_download_resume: bool = True
    preferred_mirror: str = ''
    custom_mirrors: List[str] = field(default_factory=list)
    # Additional user-defined keys not covered by the fixed schema above
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        data = dict(self.extra)
        data.update({
            'lang': self.lang,
            'last_iso_path': self.last_iso_path,
            'last_target_drive': self.last_target_drive,
            'last_install_type': self.last_install_type,
            'last_distro': self.last_distro,
            'last_version': self.last_version,
            'enable_persistence': self.enable_persistence,
            'persistence_size': self.persistence_size,
            'check_updates': self.check_updates,
            'window_geometry': self.window_geometry,
            # Boot options
            'boot_options': self.boot_options,
            'enable_uefi_only': self.enable_uefi_only,
            'enable_secure_boot': self.enable_secure_boot,
            # Download settings
            'enable_download_resume': self.enable_download_resume,
            'preferred_mirror': self.preferred_mirror,
            'custom_mirrors': self.custom_mirrors,
        })
        return data

    _KNOWN_KEYS = ('lang', 'last_iso_path', 'last_target_drive',
                   'last_install_type', 'last_distro', 'last_version',
                   'enable_persistence', 'persistence_size',
                   'check_updates', 'window_geometry',
                   # Boot options
                   'boot_options', 'enable_uefi_only', 'enable_secure_boot',
                   # Download settings
                   'enable_download_resume', 'preferred_mirror', 'custom_mirrors')

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AppConfig':
        """Create AppConfig from dictionary."""
        return cls(
            lang=data.get('lang', 'en_US'),
            last_iso_path=data.get('last_iso_path', ''),
            last_target_drive=data.get('last_target_drive', ''),
            last_install_type=data.get('last_install_type', 'distribution'),
            last_distro=data.get('last_distro', ''),
            last_version=data.get('last_version', ''),
            enable_persistence=data.get('enable_persistence', False),
            persistence_size=data.get('persistence_size', 1000),
            check_updates=data.get('check_updates', True),
            window_geometry=data.get('window_geometry', {}),
            # Boot options
            boot_options=data.get('boot_options', ''),
            enable_uefi_only=data.get('enable_uefi_only', False),
            enable_secure_boot=data.get('enable_secure_boot', False),
            # Download settings
            enable_download_resume=data.get('enable_download_resume', True),
            preferred_mirror=data.get('preferred_mirror', ''),
            custom_mirrors=data.get('custom_mirrors', []),
            extra={k: v for k, v in data.items() if k not in cls._KNOWN_KEYS},
        )


class ConfigManager:
    """Manages application configuration."""

    DEFAULT_CONFIG_DIR = ".unetbootin"
    CONFIG_FILE = "config.json"

    def __init__(self, config_dir: Optional[str] = None):
        """Initialize the configuration manager."""
        self.config_dir = config_dir or self.get_config_dir()
        self.config_file = os.path.join(self.config_dir, self.CONFIG_FILE)
        self.config = AppConfig()
        self.loaded = False

    def get_config_dir(self) -> str:
        """Get the configuration directory path."""
        # Use XDG_CONFIG_HOME on Linux, AppData on Windows, Library on macOS
        if os.name == 'nt':  # Windows
            import winreg
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r'Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders')
                appdata = winreg.QueryValueEx(key, 'AppData')[0]
                return os.path.join(appdata, self.DEFAULT_CONFIG_DIR)
            except OSError:
                return os.path.join(os.path.expanduser('~'), self.DEFAULT_CONFIG_DIR)
        elif sys.platform == 'darwin':  # macOS
            return os.path.join(os.path.expanduser('~'), 'Library',
                                'Application Support', self.DEFAULT_CONFIG_DIR)
        else:  # Linux and other Unix
            xdg_config = os.environ.get('XDG_CONFIG_HOME')
            if xdg_config:
                return os.path.join(xdg_config, self.DEFAULT_CONFIG_DIR)
            return os.path.join(os.path.expanduser(
                '~'), '.config', self.DEFAULT_CONFIG_DIR)

    def ensure_config_dir(self):
        """Ensure the configuration directory exists."""
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir, exist_ok=True)

    def load(self) -> AppConfig:
        """Load configuration from file."""
        if self.loaded:
            return self.config

        self.ensure_config_dir()

        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.config = AppConfig.from_dict(data)
                logger.info(f"Configuration loaded from {self.config_file}")
            except (OSError, json.JSONDecodeError, TypeError) as e:
                logger.error(f"Failed to load configuration: {e}")
                # Keep default config

        self.loaded = True
        return self.config

    def save(self):
        """Save configuration to file."""
        self.ensure_config_dir()

        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config.to_dict(), f, indent=2)
            logger.info(f"Configuration saved to {self.config_file}")
        except (OSError, TypeError) as e:
            logger.error(f"Failed to save configuration: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value (schema field or user-defined key)."""
        if not self.loaded:
            self.load()

        if key in AppConfig._KNOWN_KEYS:
            return getattr(self.config, key, default)
        return self.config.extra.get(key, default)

    def set(self, key: str, value: Any):
        """Set a configuration value (schema field or user-defined key)."""
        if not self.loaded:
            self.load()

        if key in AppConfig._KNOWN_KEYS:
            setattr(self.config, key, value)
        else:
            self.config.extra[key] = value
        self.save()

    def reset(self):
        """Reset configuration to defaults."""
        self.config = AppConfig()
        try:
            if os.path.exists(self.config_file):
                os.remove(self.config_file)
        except OSError as e:
            logger.error(f"Failed to reset configuration: {e}")
