"""
Distribution models and manager for PyNetboot.
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
        sha512: SHA512 checksum for verification
        sha512_url: URL of a published SHA512 file, for publishers that offer
            no SHA256 (NetBSD)
        md5_url: URL of a published MD5 file, for publishers that offer
            nothing stronger (DragonFly BSD)
        sha256_url: URL of a published SHA256SUMS-style file. When no static
            `sha256` is set, the checksum is fetched from here at download time
            and matched against the ISO filename — this keeps verification
            working across point releases without hardcoding hashes that rot.
        mirrors: List of mirror URLs for this version
        download_page: Official page to obtain the image from when no direct
            URL exists (e.g. Windows, whose ISOs are served through
            session-based pages). Such a version has an empty `url` and is
            offered for writing a locally supplied image instead.
    """
    name: str
    url: str
    size: int = 0
    description: str = ""
    category: str = ""
    sha256: Optional[str] = None
    sha1: Optional[str] = None
    md5: Optional[str] = None
    sha256_url: Optional[str] = None
    sha512: Optional[str] = None
    sha512_url: Optional[str] = None
    md5_url: Optional[str] = None
    download_page: Optional[str] = None
    mirrors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert distribution version to dictionary."""
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
        if self.sha256_url:
            result['sha256_url'] = self.sha256_url
        if self.sha512:
            result['sha512'] = self.sha512
        if self.sha512_url:
            result['sha512_url'] = self.sha512_url
        if self.md5_url:
            result['md5_url'] = self.md5_url
        if self.download_page:
            result['download_page'] = self.download_page
        if self.mirrors:
            result['mirrors'] = self.mirrors
        return result

    def get_checksum(self, checksum_type: str = "sha256") -> Optional[str]:
        """Get checksum by type, preferring SHA256 if available."""
        if checksum_type == "sha256" and self.sha256:
            return self.sha256
        elif checksum_type == "sha1" and self.sha1:
            return self.sha1
        elif checksum_type == "sha512" and self.sha512:
            return self.sha512
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
        """Post-initialize: set display_name to name if not provided."""
        if not self.display_name:
            self.display_name = self.name

    def to_dict(self) -> Dict[str, Any]:
        """Convert distribution to dictionary."""
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
                # LTS first so it stays the default selection; the interim
                # (non-LTS) release follows it.
                'versions': [
                    {'name': '26.04 LTS',
                     'url': 'https://releases.ubuntu.com/26.04/ubuntu-26.04-desktop-amd64.iso',
                     'sha256_url': 'https://releases.ubuntu.com/26.04/SHA256SUMS',
                     'size': 6518974464},
                    {'name': '24.04 LTS',
                     'url': 'https://releases.ubuntu.com/24.04/ubuntu-24.04.4-desktop-amd64.iso',
                     'sha256_url': 'https://releases.ubuntu.com/24.04/SHA256SUMS',
                     'size': 4500000000},
                    {'name': '25.10 (non-LTS)',
                     'url': 'https://releases.ubuntu.com/25.10/ubuntu-25.10-desktop-amd64.iso',
                     'sha256_url': 'https://releases.ubuntu.com/25.10/SHA256SUMS',
                     'size': 5702520832},
                    {'name': '22.04 LTS',
                     'url': 'https://releases.ubuntu.com/22.04/ubuntu-22.04.5-desktop-amd64.iso',
                     'sha256_url': 'https://releases.ubuntu.com/22.04/SHA256SUMS',
                     'size': 3800000000},
                    {'name': '20.04 LTS',
                     'url': 'https://releases.ubuntu.com/20.04/ubuntu-20.04.6-desktop-amd64.iso',
                     'sha256_url': 'https://releases.ubuntu.com/20.04/SHA256SUMS',
                     'size': 3200000000},
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
                    {
                     'name': '13 (Trixie)',
                     'url': 'https://cdimage.debian.org/debian-cd/current/amd64/iso-dvd/debian-13.6.0-amd64-DVD-1.iso',
                     'sha256_url': 'https://cdimage.debian.org/debian-cd/current/amd64/iso-dvd/SHA256SUMS',
                     'size': 4200000000},
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
                    {
                     'name': '44',
                     'url': 'https://dl.fedoraproject.org/pub/fedora/linux/releases/44/Everything/x86_64/iso/Fedora-Everything-netinst-x86_64-44-1.7.iso',
                     'sha256_url': 'https://dl.fedoraproject.org/pub/fedora/linux/releases/44/Everything/x86_64/iso/Fedora-Everything-44-1.7-x86_64-CHECKSUM',
                     'size': 1200000000},
                    {
                     'name': '43',
                     'url': 'https://dl.fedoraproject.org/pub/fedora/linux/releases/43/Everything/x86_64/iso/Fedora-Everything-netinst-x86_64-43-1.6.iso',
                     'sha256_url': 'https://dl.fedoraproject.org/pub/fedora/linux/releases/43/Everything/x86_64/iso/Fedora-Everything-43-1.6-x86_64-CHECKSUM',
                     'size': 1100000000},
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
                    {'name': '22.3 Cinnamon (Zena)',
                     'url': 'https://mirrors.kernel.org/linuxmint/stable/22.3/linuxmint-22.3-cinnamon-64bit.iso',
                     'sha256_url': 'https://mirrors.kernel.org/linuxmint/stable/22.3/sha256sum.txt',
                     'size': 3091660800},
                    {'name': '22.3 MATE (Zena)',
                     'url': 'https://mirrors.kernel.org/linuxmint/stable/22.3/linuxmint-22.3-mate-64bit.iso',
                     'sha256_url': 'https://mirrors.kernel.org/linuxmint/stable/22.3/sha256sum.txt',
                     'size': 3134275584},
                    {'name': '22.2 Cinnamon (Zara)',
                     'url': 'https://mirrors.kernel.org/linuxmint/stable/22.2/linuxmint-22.2-cinnamon-64bit.iso',
                     'sha256_url': 'https://mirrors.kernel.org/linuxmint/stable/22.2/sha256sum.txt',
                     'size': 3500000000},
                ],
                'icon': 'linuxmint',
            },
            {
                'name': 'manjaro',
                'display_name': 'Manjaro Linux',
                'description': 'Arch-based distribution with a guided installer',
                'category': 'Linux',
                'homepage': 'https://manjaro.org',
                'versions': [
                    {'name': '26.0.4 Xfce',
                     'url': 'https://download.manjaro.org/xfce/26.0.4/manjaro-xfce-26.0.4-260327-linux618.iso',
                     'sha256_url': 'https://download.manjaro.org/xfce/26.0.4/manjaro-xfce-26.0.4-260327-linux618.iso.sha256',
                     'size': 5363275776},
                    {'name': '26.0.4 KDE Plasma',
                     'url': 'https://download.manjaro.org/kde/26.0.4/manjaro-kde-26.0.4-260327-linux618.iso',
                     'sha256_url': 'https://download.manjaro.org/kde/26.0.4/manjaro-kde-26.0.4-260327-linux618.iso.sha256',
                     'size': 5669099520},
                    {'name': '26.0.4 GNOME',
                     'url': 'https://download.manjaro.org/gnome/26.0.4/manjaro-gnome-26.0.4-260327-linux618.iso',
                     'sha256_url': 'https://download.manjaro.org/gnome/26.0.4/manjaro-gnome-26.0.4-260327-linux618.iso.sha256',
                     'size': 5518409728},
                ],
                'icon': 'manjaro',
            },
            {
                'name': 'archlinux',
                'display_name': 'Arch Linux',
                'description': 'Arch Linux distribution',
                'category': 'Linux',
                'homepage': 'https://archlinux.org',
                'versions': [
                    {'name': 'Latest',
    'url': 'https://geo.mirror.pkgbuild.com/iso/latest/archlinux-x86_64.iso',
                     'sha256_url': 'https://geo.mirror.pkgbuild.com/iso/latest/sha256sums.txt',
     'size': 800000000},
                ],
                'icon': 'archlinux',
            },
            {
                # Tumbleweed (rolling) and Leap (stable) are one distribution
                # with two release streams, selectable like Ubuntu's versions.
                'name': 'opensuse',
                'display_name': 'openSUSE',
                'description': 'openSUSE - Leap (stable) and Tumbleweed (rolling)',
                'category': 'Linux',
                'homepage': 'https://get.opensuse.org',
                'versions': [
                    {
    'name': 'Leap 16.1 (Stable)',
    'url': 'https://download.opensuse.org/distribution/leap/16.1/offline/Leap-16.1-offline-installer-x86_64.install.iso',
     'size': 4552916992},
                    {
    'name': 'Leap 16.0 (Stable)',
    'url': 'https://download.opensuse.org/distribution/leap/16.0/offline/Leap-16.0-offline-installer-x86_64.install.iso',
     'size': 4538236928},
                    {
    'name': 'Tumbleweed (Rolling)',
    'url': 'https://download.opensuse.org/tumbleweed/iso/openSUSE-Tumbleweed-DVD-x86_64-Current.iso',
                     'sha256_url': 'https://download.opensuse.org/tumbleweed/iso/openSUSE-Tumbleweed-DVD-x86_64-Current.iso.sha256',
     'size': 4469030912},
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
                    # cdn.zorincdn.com no longer resolves, so these come from
                    # a public mirror. The 18.1 images live in the "18"
                    # directory alongside the 18 revisions, rather than in a
                    # directory of their own.
                    {'name': 'Core 18.1',
                     'url': 'https://mirrors.dotsrc.org/zorinos/18/Zorin-OS-18.1-Core-64-bit.iso',
                     'sha256_url': 'https://mirrors.dotsrc.org/zorinos/18/SHA256SUMS.txt',
                     'size': 3909091328},
                    {'name': 'Lite 18.1',
                     'url': 'https://mirrors.dotsrc.org/zorinos/18/Zorin-OS-18.1-Lite-64-bit.iso',
                     'sha256_url': 'https://mirrors.dotsrc.org/zorinos/18/SHA256SUMS.txt',
                     'size': 3981279232},
                    {'name': 'Core 18 (r3)',
                     'url': 'https://mirrors.dotsrc.org/zorinos/18/Zorin-OS-18-Core-64-bit-r3.iso',
                     'sha256_url': 'https://mirrors.dotsrc.org/zorinos/18/SHA256SUMS.txt',
                     'size': 3787948032},
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
                    {
    'name': 'Latest (2026.2)',
    'url': 'https://cdimage.kali.org/kali-2026.2/kali-linux-2026.2-installer-amd64.iso',
                     'sha256_url': 'https://cdimage.kali.org/kali-2026.2/SHA256SUMS',
     'size': 3800000000},
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
                    {
    'name': 'Latest (15.0)',
    'url': 'https://mirrors.slackware.com/slackware/slackware-iso/slackware64-15.0-iso/slackware64-15.0-install-dvd.iso',
                     'sha256_url': 'https://mirrors.slackware.com/slackware/slackware-iso/slackware64-15.0-iso/slackware64-15.0-install-dvd.iso.sha256',
     'size': 4800000000},
                ],
                'icon': 'slackware',
            },
            {
                # ROME (rolling) and 6.0 (stable) are one distribution with two
                # release streams, selectable like Ubuntu's versions.
                # The old downloads.openmandriva.org host no longer resolves;
                # these paths are on the project's live mirror.
                'name': 'openmandriva',
                'display_name': 'OpenMandriva',
                'description': 'OpenMandriva Lx - 6.0 (stable) and ROME (rolling)',
                'category': 'Linux',
                'homepage': 'https://www.openmandriva.org',
                'versions': [
                    {
    'name': '6.0 (Stable, Plasma 6)',
    'url': 'https://mirror.openmandriva.org/release_current/6.0/openmandriva-6.0-plasma6-x11.x86_64.iso',
     'size': 3227226112},
                    {
    'name': 'ROME (Rolling, GNOME)',
    'url': 'https://mirror.openmandriva.org/release_current/ROME/OpenMandrivaLx.rolling-rome-gnome3.x86_64.iso',
     'size': 3401375744},
                ],
                'icon': 'openmandriva',
            },
            {
                # Rocky Linux ships stable point releases only - there is no
                # rolling variant; CentOS Stream (below) fills that role for
                # the RHEL family.
                'name': 'rocky',
                'display_name': 'Rocky Linux',
                'description': 'Rocky Linux - Enterprise (RHEL-compatible) distribution',
                'category': 'Linux',
                'homepage': 'https://rockylinux.org',
                'versions': [
                    {
    'name': '10.2 (Stable)',
    'url': 'https://download.rockylinux.org/pub/rocky/10.2/isos/x86_64/Rocky-10.2-x86_64-minimal.iso',
                     'sha256_url': 'https://download.rockylinux.org/pub/rocky/10.2/isos/x86_64/Rocky-10.2-x86_64-minimal.iso.CHECKSUM',
     'size': 2072444928},
                    {
    'name': '9.8 (Stable)',
    'url': 'https://download.rockylinux.org/pub/rocky/9.8/isos/x86_64/Rocky-9.8-x86_64-minimal.iso',
                     'sha256_url': 'https://download.rockylinux.org/pub/rocky/9.8/isos/x86_64/Rocky-9.8-x86_64-minimal.iso.CHECKSUM',
     'size': 2755067904},
                ],
                'icon': 'rocky',
            },
            {
                # CentOS Stream is the continuously delivered (rolling)
                # upstream of Red Hat Enterprise Linux, and unlike RHEL itself
                # it is freely downloadable without a subscription.
                'name': 'centos_stream',
                'display_name': 'CentOS Stream',
                'description': 'CentOS Stream - Rolling upstream of Red Hat Enterprise Linux',
                'category': 'Linux',
                'homepage': 'https://www.centos.org/centos-stream/',
                'versions': [
                    {
    'name': '10 (Rolling)',
    'url': 'https://mirror.stream.centos.org/10-stream/BaseOS/x86_64/iso/CentOS-Stream-10-latest-x86_64-dvd1.iso',
     'size': 10379788288},
                    {
    'name': '9 (Rolling)',
    'url': 'https://mirror.stream.centos.org/9-stream/BaseOS/x86_64/iso/CentOS-Stream-9-latest-x86_64-dvd1.iso',
     'size': 15567552512},
                ],
                'icon': 'centos',
            },
            {
                'name': 'tinycore',
                'display_name': 'Tiny Core Linux',
                'description': 'Tiny Core Linux - Minimal Linux desktop',
                'category': 'Linux',
                'homepage': 'https://www.tinycorelinux.net',
                # The release ISOs live under the x86 tree, not x86_64 (that
                # tree only holds CorePure64), and the site does not serve
                # HTTPS — the previous https://…/x86_64/… URL always failed.
                'versions': [
                    {
    'name': '17.1 TinyCore',
    'url': 'http://tinycorelinux.net/17.x/x86/release/TinyCore-17.1.iso',
                     'md5': '42db5663757add090857059c096a6801',
     'size': 27262976},
                    {
    'name': '17.1 Core Plus',
    'url': 'http://tinycorelinux.net/17.x/x86/release/CorePlus-17.1.iso',
                     'md5': 'c681af3450c9890b6bd816fb8d8ea491',
     'size': 289406976},
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
                    {
    'name': 'Latest (15.1)',
    'url': 'https://download.freebsd.org/releases/amd64/amd64/ISO-IMAGES/15.1/FreeBSD-15.1-RELEASE-amd64-disc1.iso',
                     'sha256_url': 'https://download.freebsd.org/releases/amd64/amd64/ISO-IMAGES/15.1/CHECKSUM.SHA256-FreeBSD-15.1-RELEASE-amd64',
     'size': 1900000000},
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
                    {'name': 'Latest (10.1)',
    'url': 'https://cdn.netbsd.org/pub/NetBSD/images/10.1/NetBSD-10.1-amd64.iso',
                     # NetBSD publishes no SHA256 for its images.
                     'sha512_url': 'https://cdn.netbsd.org/pub/NetBSD/images/10.1/SHA512',
     'size': 360000000},
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
                    {
    # mirror.midnightbsd.org no longer resolves; 3.2.3 is also long superseded.
    'name': 'Latest (4.0.6)',
    'url': 'https://discovery.midnightbsd.org/ftp/releases/amd64/ISO-IMAGES/4.0.6/MidnightBSD-4.0.6--amd64-disc1.iso',
     'size': 1062742016},
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
                    {
    'name': 'Latest (26.1-R15.0p2)',
    'url': 'https://download.ghostbsd.org/releases/amd64/26.1-R15.0p2/GhostBSD-26.1-R15.0p2.iso',
                     'sha256_url': 'https://download.ghostbsd.org/releases/amd64/26.1-R15.0p2/GhostBSD-26.1-R15.0p2.iso.sha256',
     'size': 1900000000},
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
                    {
    'name': 'Latest (6.4.2)',
    'url': 'https://mirror-master.dragonflybsd.org/iso-images/dfly-x86_64-6.4.2_REL.iso',
                     # DragonFly publishes nothing stronger than MD5.
                     'md5_url': 'https://mirror-master.dragonflybsd.org/iso-images/md5.txt',
     'size': 800000000},
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
                    {
    'name': 'Latest (SCALE Goldeye 25.10.5)',
    'url': 'https://download.truenas.com/TrueNAS-SCALE-Goldeye/25.10.5/TrueNAS-SCALE-25.10.5.iso',
                     'sha256_url': 'https://download.truenas.com/TrueNAS-SCALE-Goldeye/25.10.5/TrueNAS-SCALE-25.10.5.iso.sha256',
     'size': 1600000000},
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
                # Microsoft serves Windows ISOs through session-based pages,
                # so no stable direct link exists and the old download.microsoft
                # .com URLs are dead. Only the current release is listed, with
                # the official page to obtain it from; write the downloaded
                # image with the "Disk image" option.
                'versions': [
                    {
    'name': '25H2 (download from Microsoft)',
    'url': '',
    'download_page': 'https://www.microsoft.com/software-download/windows11'},
                ],
                'icon': 'windows',
            },
            {
                'name': 'windows10',
                'display_name': 'Windows 10',
                'description': 'Windows 10 installation media',
                'category': 'Windows',
                'homepage': 'https://www.microsoft.com/software-download/windows10',
                # 22H2 is the final Windows 10 release. As with Windows 11 the
                # ISO must be obtained from Microsoft's own page.
                'versions': [
                    {
    'name': '22H2 (download from Microsoft)',
    'url': '',
    'download_page': 'https://www.microsoft.com/software-download/windows10'},
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
            logger.info(
                f"Loaded {len(self.distributions)} distributions from {filepath}")

        except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"Failed to load distributions from {filepath}: {e}")

    def load_from_directory(self, directory: str):
        """Load distributions from a directory of JSON files."""
        try:
            distro_dir = Path(directory)
            if distro_dir.exists():
                for json_file in distro_dir.glob('*.json'):
                    self.load_from_file(str(json_file))
        except OSError as e:
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
