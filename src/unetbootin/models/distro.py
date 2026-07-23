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
    """
    Represents a version of a distribution.
    
    Attributes:
        name: Version name/identifier
        url: Download URL for this version
        size: File size in bytes
        description: Human-readable description
        category: Version category
        sha256: SHA256 checksum for verification
        sha1: SHA1 checksum for verification
        md5: MD5 checksum for verification
        mirrors: List of mirror URLs for this version
    """
    name: str
    url: str
    size: int = 0
    description: str = ""
    category: str = ""
    sha256: Optional[str] = None
    sha1: Optional[str] = None
    md5: Optional[str] = None
    mirrors: List[str] = field(default_factory=list)
    
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
        if self.mirrors:
            result['mirrors'] = self.mirrors
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
    """
    Represents a Linux distribution.
    
    Attributes:
        name: Internal name/identifier
        display_name: Human-readable display name
        description: Distribution description
        category: Distribution category (Ubuntu, Debian, etc.)
        versions: List of available versions
        icon: Icon filename for UI display
        homepage: Distribution homepage URL
        mirrors: List of default mirror URLs
    """
    name: str
    display_name: str = ""
    description: str = ""
    category: str = ""
    versions: List[DistributionVersion] = field(default_factory=list)
    icon: str = ""
    homepage: str = ""
    mirrors: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            'name': self.name,
            'display_name': self.display_name,
            'description': self.description,
            'category': self.category,
            'versions': [v.to_dict() for v in self.versions],
            'icon': self.icon,
            'homepage': self.homepage,
        }
        if self.mirrors:
            result['mirrors'] = self.mirrors
        return result


class DistributionManager:
    """
    Manages the list of supported distributions.
    
    This class handles loading, organizing, and retrieving distribution information
    from both built-in data and external sources like JSON files.
    """
    
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
        
        # Built-in distribution list organized by categories
        # Linux distributions
        linux_distros = [
            {
                'name': 'ubuntu',
                'display_name': 'Ubuntu',
                'description': 'Ubuntu Linux distribution',
                'category': 'Linux',
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
                'category': 'Linux',
                'homepage': 'https://debian.org',
                'versions': [
                    {'name': '13 (Trixie)', 'url': 'https://cdimage.debian.org/debian-cd/current/amd64/iso-dvd/debian-13.6.0-amd64-DVD-1.iso', 'size': 4200000000},
                ],
                'icon': 'debian',
            },
            {
                'name': 'fedora',
                'display_name': 'Fedora',
                'description': 'Fedora Linux distribution',
                'category': 'Linux',
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
                'category': 'Linux',
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
                'category': 'Linux',
                'homepage': 'https://archlinux.org',
                'versions': [
                    {'name': 'Latest', 'url': 'https://geo.mirror.pkgbuild.com/iso/latest/archlinux-x86_64.iso', 'size': 800000000},
                ],
                'icon': 'archlinux',
            },
            {
                'name': 'suse_tumbleweed',
                'display_name': 'SUSE Tumbleweed',
                'description': 'openSUSE Tumbleweed - Rolling release distribution',
                'category': 'Linux',
                'homepage': 'https://get.opensuse.org/tumbleweed',
                'versions': [
                    {'name': 'Latest', 'url': 'https://download.opensuse.org/tumbleweed/iso/openSUSE-Tumbleweed-DVD-x86_64-Current.iso', 'size': 4700000000},
                ],
                'icon': 'opensuse',
            },
            {
                'name': 'suse_leap',
                'display_name': 'SUSE Leap',
                'description': 'openSUSE Leap - Stable release distribution',
                'category': 'Linux',
                'homepage': 'https://get.opensuse.org/leap',
                'versions': [
                    {'name': '16.0', 'url': 'https://download.opensuse.org/distribution/leap/16.0/offline/Leap-16.0-offline-installer-x86_64.install.iso', 'size': 4200000000},
                ],
                'icon': 'opensuse',
            },
            {
                'name': 'zorin',
                'display_name': 'Zorin OS',
                'description': 'Zorin OS - Linux for everyone',
                'category': 'Linux',
                'homepage': 'https://zorin.com/os',
                'versions': [
                    {'name': 'Latest Free', 'url': 'https://cdn.zorincdn.com/zorin/os/17.1/zorin-os-17.1-core-64-bit.iso', 'size': 3200000000},
                ],
                'icon': 'zorin',
            },
            {
                'name': 'kali',
                'display_name': 'Kali Linux',
                'description': 'Kali Linux - Penetration Testing and Security Auditing',
                'category': 'Linux',
                'homepage': 'https://www.kali.org',
                'versions': [
                    {'name': 'Latest', 'url': 'https://cdimage.kali.org/kali-images/kali-linux-2024.2-installer-amd64.iso', 'size': 3500000000},
                ],
                'icon': 'kali',
            },
            {
                'name': 'slackware',
                'display_name': 'Slackware Linux',
                'description': 'Slackware Linux distribution',
                'category': 'Linux',
                'homepage': 'https://www.slackware.com',
                'versions': [
                    {'name': 'Latest (15.0)', 'url': 'https://mirrors.slackware.com/slackware/slackware64-15.0/iso/slackware64-15.0-install-dvd.iso', 'size': 4800000000},
                ],
                'icon': 'slackware',
            },
            {
                'name': 'openmandriva',
                'display_name': 'OpenMandriva',
                'description': 'OpenMandriva Lx - Freedom in Diversity',
                'category': 'Linux',
                'homepage': 'https://www.openmandriva.org',
                'versions': [
                    {'name': 'Latest (ROME)', 'url': 'https://downloads.openmandriva.org/ROME/OpenMandrivaLx-ROME-Plasma5-x86_64.iso', 'size': 2800000000},
                ],
                'icon': 'openmandriva',
            },
            {
                'name': 'tinycore',
                'display_name': 'Tiny Core Linux',
                'description': 'Tiny Core Linux - Minimal Linux desktop',
                'category': 'Linux',
                'homepage': 'https://www.tinycorelinux.net',
                'versions': [
                    {'name': 'Latest (15.x)', 'url': 'https://www.tinycorelinux.net/15.x/x86_64/release/TinyCore-current.iso', 'size': 210000000},
                ],
                'icon': 'tinycore',
            },
        ]
        
        # BSD distributions
        bsd_distros = [
            {
                'name': 'freebsd',
                'display_name': 'FreeBSD',
                'description': 'FreeBSD operating system',
                'category': 'BSD',
                'homepage': 'https://www.freebsd.org',
                'versions': [
                    {'name': 'Latest (14.0)', 'url': 'https://download.freebsd.org/releases/amd64/amd64/ISO-IMAGES/14.0/FreeBSD-14.0-RELEASE-amd64-disc1.iso', 'size': 1800000000},
                ],
                'icon': 'freebsd',
            },
            {
                'name': 'netbsd',
                'display_name': 'NetBSD',
                'description': 'NetBSD operating system',
                'category': 'BSD',
                'homepage': 'https://www.netbsd.org',
                'versions': [
                    {'name': 'Latest (10.0)', 'url': 'https://cdn.netbsd.org/pub/NetBSD/NetBSD-10.0/amd64cd.iso', 'size': 350000000},
                ],
                'icon': 'netbsd',
            },
            {
                'name': 'midnightbsd',
                'display_name': 'MidnightBSD',
                'description': 'MidnightBSD - A BSD derived OS',
                'category': 'BSD',
                'homepage': 'https://www.midnightbsd.org',
                'versions': [
                    {'name': 'Latest (3.1.0)', 'url': 'https://mirror.midnightbsd.org/pub/MidnightBSD/ISO/3.1.0/amd64/MIDNIGHT310.iso', 'size': 1200000000},
                ],
                'icon': 'midnightbsd',
            },
            {
                'name': 'ghostbsd',
                'display_name': 'GhostBSD',
                'description': 'GhostBSD - A simple, elegant Desktop BSD Operating System',
                'category': 'BSD',
                'homepage': 'https://ghostbsd.org',
                'versions': [
                    {'name': 'Latest (24.03)', 'url': 'https://ghostbsd.org/releases/24.03/iso/GhostBSD-24.03-RELEASE-amd64.iso', 'size': 1800000000},
                ],
                'icon': 'ghostbsd',
            },
            {
                'name': 'dragonflybsd',
                'display_name': 'DragonFly BSD',
                'description': 'DragonFly BSD operating system',
                'category': 'BSD',
                'homepage': 'https://www.dragonflybsd.org',
                'versions': [
                    {'name': 'Latest (6.4)', 'url': 'https://mirror-master.dragonflybsd.org/iso-images/dfly-x86_64-6.4.0_REL.iso', 'size': 800000000},
                ],
                'icon': 'dragonflybsd',
            },
            {
                'name': 'truenas',
                'display_name': 'TrueNAS',
                'description': 'TrueNAS - Open Source Storage Operating System',
                'category': 'BSD',
                'homepage': 'https://www.truenas.com',
                'versions': [
                    {'name': 'Latest (SCALE Bluefin)', 'url': 'https://download.truenas.com/TrueNAS-SCALE-Bluefin/TrueNAS-SCALE-24.04.0.iso', 'size': 1500000000},
                ],
                'icon': 'truenas',
            },
        ]
        
        # Windows distributions
        windows_distros = [
            {
                'name': 'windows11',
                'display_name': 'Windows 11',
                'description': 'Windows 11 installation media',
                'category': 'Windows',
                'homepage': 'https://www.microsoft.com/software-download/windows11',
                'versions': [
                    {'name': '24H2', 'url': 'https://download.microsoft.com/download/5/6/3/563ed5c9-354f-4d24-a30b-c26d4b965057/Win11_24H2_English_x64.iso', 'size': 5800000000},
                    {'name': '23H2', 'url': 'https://download.microsoft.com/download/8/8/1/881f6949-78c6-4b02-8c2a-5ca1d8b8069d/Win11_23H2_English_x64.iso', 'size': 5500000000},
                    {'name': '22H2', 'url': 'https://download.microsoft.com/download/6/7/d/67d659af-0b5d-4e48-8888-59627791019d/Win11_22H2_English_x64.iso', 'size': 5200000000},
                ],
                'icon': 'windows',
            },
            {
                'name': 'windows10',
                'display_name': 'Windows 10',
                'description': 'Windows 10 installation media',
                'category': 'Windows',
                'homepage': 'https://www.microsoft.com/software-download/windows10',
                'versions': [
                    {'name': '22H2', 'url': 'https://download.microsoft.com/download/9/7/N/97NDMP3FVML3P/Win10_22H2_English_x64.iso', 'size': 5500000000},
                    {'name': '21H2', 'url': 'https://download.microsoft.com/download/1/7/D/17D422A7-A94D-4C89-96F8-927085F74E15/Win10_21H2_English_x64.iso', 'size': 5200000000},
                ],
                'icon': 'windows',
            },
        ]
        
        # Combine all distributions
        builtin_distros = linux_distros + bsd_distros + windows_distros
        
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
