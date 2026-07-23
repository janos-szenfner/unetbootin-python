"""
Distribution models and manager for UNetbootin.
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DistributionVersion:
    """Represents a version of a distribution."""
    name: str
    url: str
    size: int = 0
    description: str = ""
    category: str = ""
    sha256: Optional[str] = None
    sha1: Optional[str] = None
    md5: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            'name': self.name,
            'url': self.url,
            'size': self.size,
            'description': self.description,
            'category': self.category,
        }
        if self.sha256:
            result['sha256'] = self.sha256
        if self.sha1:
            result['sha1'] = self.sha1
        if self.md5:
            result['md5'] = self.md5
        return result
    
    def get_checksum(self, checksum_type: str = "sha256") -> Optional[str]:
        """Get checksum by type, preferring SHA256 if available."""
        if checksum_type == "sha256" and self.sha256:
            return self.sha256
        elif checksum_type == "sha1" and self.sha1:
            return self.sha1
        elif checksum_type == "md5" and self.md5:
            return self.md5
        # Fallback to any available checksum
        return self.sha256 or self.sha1 or self.md5


@dataclass
class Distribution:
    """Represents a Linux distribution."""
    name: str
    display_name: str = ""
    description: str = ""
    category: str = ""
    versions: List[DistributionVersion] = field(default_factory=list)
    icon: str = ""
    homepage: str = ""
    
    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'display_name': self.display_name,
            'description': self.description,
            'category': self.category,
            'versions': [v.to_dict() for v in self.versions],
            'icon': self.icon,
            'homepage': self.homepage,
        }


class DistributionManager:
    """Manages the list of supported distributions."""
    
    def __init__(self):
        """Initialize the distribution manager."""
        self.distributions: Dict[str, Distribution] = {}
        self.loaded = False
    
    def get_distributions(self) -> List[Dict[str, Any]]:
        """Get the list of all distributions."""
        if not self.loaded:
            self.load_distributions()
        
        return [d.to_dict() for d in self.distributions.values()]
    
    def get_distribution(self, name: str) -> Optional[Distribution]:
        """Get a specific distribution by name."""
        if not self.loaded:
            self.load_distributions()
        return self.distributions.get(name)
    
    def get_versions(self, distro_name: str) -> List[Dict[str, Any]]:
        """Get versions for a specific distribution."""
        distro = self.get_distribution(distro_name)
        if distro:
            return [v.to_dict() for v in distro.versions]
        return []
    
    def load_distributions(self):
        """Load distributions from built-in data and/or external sources."""
        logger.info("Loading distributions")
        
        # Built-in distribution list (simplified from original C++ version)
        # This is a partial list - the full list would be much larger
        builtin_distros = [
            {
                'name': 'ubuntu',
                'display_name': 'Ubuntu',
                'description': 'Ubuntu Linux distribution',
                'category': 'Ubuntu',
                'homepage': 'https://ubuntu.com',
                'versions': [
                    {'name': '24.04 LTS', 'url': 'https://releases.ubuntu.com/24.04/ubuntu-24.04.4-desktop-amd64.iso', 'size': 4500000000},
                    {'name': '22.04 LTS', 'url': 'https://releases.ubuntu.com/22.04/ubuntu-22.04.5-desktop-amd64.iso', 'size': 3800000000},
                    {'name': '20.04 LTS', 'url': 'https://releases.ubuntu.com/20.04/ubuntu-20.04.6-desktop-amd64.iso', 'size': 3200000000},
                ],
                'icon': 'ubuntu',
            },
            {
                'name': 'debian',
                'display_name': 'Debian',
                'description': 'Debian Linux distribution',
                'category': 'Debian',
                'homepage': 'https://debian.org',
                'versions': [
                    # Note: point-release filenames under current/ change over time;
                    # prefer refreshing these via an external JSON definition.
                    {'name': '13 (Trixie)', 'url': 'https://cdimage.debian.org/debian-cd/current/amd64/iso-dvd/debian-13.6.0-amd64-DVD-1.iso', 'size': 4200000000},
                ],
                'icon': 'debian',
            },
            {
                'name': 'fedora',
                'display_name': 'Fedora',
                'description': 'Fedora Linux distribution',
                'category': 'Fedora',
                'homepage': 'https://fedoraproject.org',
                'versions': [
                    {'name': '44', 'url': 'https://dl.fedoraproject.org/pub/fedora/linux/releases/44/Everything/x86_64/iso/Fedora-Everything-netinst-x86_64-44-1.7.iso', 'size': 1200000000},
                    {'name': '43', 'url': 'https://dl.fedoraproject.org/pub/fedora/linux/releases/43/Everything/x86_64/iso/Fedora-Everything-netinst-x86_64-43-1.6.iso', 'size': 1100000000},
                ],
                'icon': 'fedora',
            },
            {
                'name': 'linuxmint',
                'display_name': 'Linux Mint',
                'description': 'Linux Mint distribution',
                'category': 'Ubuntu',
                'homepage': 'https://linuxmint.com',
                'versions': [
                    {'name': '22.2 (Zara)', 'url': 'https://mirrors.kernel.org/linuxmint/stable/22.2/linuxmint-22.2-cinnamon-64bit.iso', 'size': 3500000000},
                    {'name': '22.1 (Xia)', 'url': 'https://mirrors.kernel.org/linuxmint/stable/22.1/linuxmint-22.1-cinnamon-64bit.iso', 'size': 3400000000},
                ],
                'icon': 'linuxmint',
            },
            {
                'name': 'archlinux',
                'display_name': 'Arch Linux',
                'description': 'Arch Linux distribution',
                'category': 'Arch',
                'homepage': 'https://archlinux.org',
                'versions': [
                    {'name': 'Latest', 'url': 'https://geo.mirror.pkgbuild.com/iso/latest/archlinux-x86_64.iso', 'size': 800000000},
                ],
                'icon': 'archlinux',
            },
            {
                'name': 'opensuse',
                'display_name': 'openSUSE',
                'description': 'openSUSE distribution',
                'category': 'SUSE',
                'homepage': 'https://opensuse.org',
                'versions': [
                    {'name': 'Tumbleweed', 'url': 'https://download.opensuse.org/tumbleweed/iso/openSUSE-Tumbleweed-DVD-x86_64-Current.iso', 'size': 4700000000},
                    {'name': 'Leap 15.6', 'url': 'https://download.opensuse.org/distribution/leap/15.6/iso/openSUSE-Leap-15.6-DVD-x86_64-Media.iso', 'size': 4600000000},
                ],
                'icon': 'opensuse',
            },
        ]
        
        # Convert to Distribution objects
        for distro_data in builtin_distros:
            versions = [
                DistributionVersion(**version_data) 
                for version_data in distro_data.get('versions', [])
            ]
            distro = Distribution(
                name=distro_data['name'],
                display_name=distro_data.get('display_name', distro_data['name']),
                description=distro_data.get('description', ''),
                category=distro_data.get('category', ''),
                versions=versions,
                icon=distro_data.get('icon', ''),
                homepage=distro_data.get('homepage', ''),
            )
            self.distributions[distro.name] = distro
        
        self.loaded = True
        logger.info(f"Loaded {len(self.distributions)} distributions")
    
    def load_from_file(self, filepath: str):
        """Load distributions from a JSON file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for distro_data in data.get('distributions', []):
                versions = [
                    DistributionVersion(**v) for v in distro_data.get('versions', [])
                ]
                distro = Distribution(
                    name=distro_data['name'],
                    display_name=distro_data.get('display_name', distro_data['name']),
                    description=distro_data.get('description', ''),
                    category=distro_data.get('category', ''),
                    versions=versions,
                    icon=distro_data.get('icon', ''),
                    homepage=distro_data.get('homepage', ''),
                )
                self.distributions[distro.name] = distro
            
            self.loaded = True
            logger.info(f"Loaded {len(self.distributions)} distributions from {filepath}")
            
        except Exception as e:
            logger.error(f"Failed to load distributions from {filepath}: {e}")
    
    def load_from_directory(self, directory: str):
        """Load distributions from a directory of JSON files."""
        try:
            distro_dir = Path(directory)
            if distro_dir.exists():
                for json_file in distro_dir.glob('*.json'):
                    self.load_from_file(str(json_file))
        except Exception as e:
            logger.error(f"Failed to load distributions from {directory}: {e}")
    
    def get_categories(self) -> List[str]:
        """Get list of all categories."""
        if not self.loaded:
            self.load_distributions()
        
        categories = set()
        for distro in self.distributions.values():
            if distro.category:
                categories.add(distro.category)
        
        return sorted(categories)
    
    def get_distributions_by_category(self, category: str) -> List[Dict[str, Any]]:
        """Get distributions filtered by category."""
        if not self.loaded:
            self.load_distributions()
        
        return [
            d.to_dict() for d in self.distributions.values()
            if d.category == category
        ]
    
    def search_distributions(self, query: str) -> List[Dict[str, Any]]:
        """Search distributions by name or description."""
        if not self.loaded:
            self.load_distributions()
        
        query = query.lower()
        results = []
        
        for distro in self.distributions.values():
            if (query in distro.name.lower() or 
                query in distro.display_name.lower() or 
                query in distro.description.lower()):
                results.append(distro.to_dict())
        
        return results
