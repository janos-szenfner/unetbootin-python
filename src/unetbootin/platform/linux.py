"""
Linux-specific functionality for UNetbootin.
"""

import os
import re
import sys
import logging
import subprocess
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Linux drivers shell out to lsblk/findmnt/blkid/etc. and parse their JSON or
# text output. json.JSONDecodeError is a ValueError subclass, so ValueError
# also covers malformed JSON.
_SUBPROCESS_ERRORS = (subprocess.SubprocessError, OSError)
_SUBPROCESS_PARSE_ERRORS = (subprocess.SubprocessError, OSError,
                            ValueError, KeyError, TypeError)


def get_drive_list() -> List[Dict[str, Any]]:
    """Get list of available drives on Linux."""
    drives = []

    try:
        # Method 1: Use lsblk (preferred)
        result = subprocess.run(
            ['lsblk', '-J', '-d', '-o', 'NAME,SIZE,TYPE,RM,MODEL,VENDOR,HCTL,TRAN,REV'],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode == 0:
            import json
            try:
                data = json.loads(result.stdout)
                for device in data.get('blockdevices', []):
                    drive_info = {
                        'device': f"/dev/{device.get('name', '')}",
                        'name': device.get('name', ''),
                        'size': int(device.get('size', 0)),
                        'type': device.get('type', ''),
                        'removable': device.get('rm', False),
                        'model': device.get('model', ''),
                        'vendor': device.get('vendor', ''),
                        'hctl': device.get('hctl', ''),
                        'transport': device.get('tran', ''),
                        'serial': '',
                        'mountpoint': '',
                        'partitions': [],
                    }

                    # Get mount point and partitions
                    result2 = subprocess.run(
                        ['lsblk', '-J', '-o', 'NAME,SIZE,TYPE,MOUNTPOINT'],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )

                    if result2.returncode == 0:
                        data2 = json.loads(result2.stdout)
                        for device2 in data2.get('blockdevices', []):
                            if device2.get('name') == device.get('name'):
                                drive_info['mountpoint'] = device2.get('mountpoint', '')
                                if 'children' in device2:
                                    for partition in device2['children']:
                                        drive_info['partitions'].append({
                                            'name': partition.get('name', ''),
                                            'size': int(partition.get('size', 0)),
                                            'type': partition.get('type', ''),
                                            'mountpoint': partition.get('mountpoint', ''),
                                        })
                                break

                    # Get serial number
                    if drive_info['type'] == 'disk':
                        serial = get_drive_serial(drive_info['device'])
                        if serial:
                            drive_info['serial'] = serial

                    drives.append(drive_info)
            except (ValueError, KeyError, TypeError) as e:
                logger.error(f"Failed to parse lsblk output: {e}")

        # Method 2: Fallback to /dev/disk/by-id
        if not drives:
            try:
                by_id_dir = '/dev/disk/by-id'
                if os.path.exists(by_id_dir):
                    for entry in os.listdir(by_id_dir):
                        link_path = os.path.join(by_id_dir, entry)
                        try:
                            target = os.readlink(link_path)
                            device_path = f"/dev/{target}"

                            # Get device info
                            result = subprocess.run(
                                ['lsblk', '-J', '-d', '-o', 'NAME,SIZE,TYPE,RM'],
                                capture_output=True,
                                text=True,
                                timeout=5
                            )

                            device_info = {
                                'device': device_path,
                                'name': target,
                                'size': 0,
                                'type': 'disk',
                                'removable': 'usb' in entry.lower(),
                                'serial': entry,
                            }

                            if result.returncode == 0:
                                import json
                                data = json.loads(result.stdout)
                                for device in data.get('blockdevices', []):
                                    if device.get('name') == target:
                                        device_info['size'] = int(device.get('size', 0))
                                        device_info['type'] = device.get('type', '')
                                        device_info['removable'] = device.get(
                                            'rm', False)
                                        break

                            drives.append(device_info)
                        except OSError:
                            continue
            except (OSError, ValueError) as e:
                logger.error(f"Failed to read {by_id_dir}: {e}")

    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Failed to get drive list: {e}")

    return drives


def get_drive_serial(device: str) -> Optional[str]:
    """Get serial number for a device on Linux."""
    try:
        if not device.startswith('/dev/'):
            device = f"/dev/{device}"

        # Method 1: Use udevadm
        result = subprocess.run(
            ['udevadm', 'info', '--query=property', '--name=' + device],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if line.startswith('ID_SERIAL='):
                    return line.split('=', 1)[1].strip()

        # Method 2: Use sg_vpd
        result = subprocess.run(
            ['sg_vpd', '--page=0x80', device],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            # Parse VPD page 0x80 (Unit Serial Number)
            for line in result.stdout.split('\n'):
                if 'Unit serial number' in line:
                    return line.split(':')[1].strip()

        # Method 3: Use hdparm
        result = subprocess.run(
            ['hdparm', '-I', device],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'Serial number' in line:
                    return line.split(':')[1].strip()

    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Failed to get serial for {device}: {e}")

    return None


def get_drive_info(drive: str) -> Optional[Dict[str, Any]]:
    """Get detailed information about a specific drive on Linux."""
    try:
        if not drive.startswith('/dev/'):
            drive = f"/dev/{drive}"

        result = subprocess.run(
            ['lsblk', '-J', '-d', '-o', 'NAME,SIZE,TYPE,RM,MODEL,VENDOR,HCTL,TRAN,REV'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)

            for device in data.get('blockdevices', []):
                if f"/dev/{device.get('name')}" == drive or device.get(
                    'name') == drive.split('/')[-1]:
                    info = {
                        'device': drive,
                        'name': device.get('name', ''),
                        'size': int(device.get('size', 0)),
                        'type': device.get('type', ''),
                        'removable': device.get('rm', False),
                        'model': device.get('model', ''),
                        'vendor': device.get('vendor', ''),
                        'hctl': device.get('hctl', ''),
                        'transport': device.get('tran', ''),
                        'serial': '',
                        'mountpoint': '',
                    }

                    # Get serial
                    info['serial'] = get_drive_serial(drive)

                    # Get mount point
                    result2 = subprocess.run(
                        ['findmnt', '-J', drive],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )

                    if result2.returncode == 0:
                        data2 = json.loads(result2.stdout)
                        if 'filesystems' in data2:
                            info['mountpoint'] = data2['filesystems'][0].get(
                                'target', '')

                    return info

        # Fallback: use block device info
        result = subprocess.run(
            ['blockdev', '--getsize64', drive],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            size = int(result.stdout.strip())
            return {
                'device': drive,
                'size': size,
                'type': 'disk',
                'removable': False,
            }

    except _SUBPROCESS_PARSE_ERRORS as e:
        logger.error(f"Failed to get drive info for {drive}: {e}")

    return None


def unmount_drive(drive: str) -> bool:
    """Unmount a drive on Linux."""
    try:
        if not drive.startswith('/dev/'):
            drive = f"/dev/{drive}"

        # First, find mount points for the device
        result = subprocess.run(
            ['findmnt', '-J', drive],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)

            if 'filesystems' in data:
                for fs in data['filesystems']:
                    mount_point = fs.get('target', '')
                    if mount_point:
                        result = subprocess.run(
                            ['sudo', 'umount', mount_point],
                            capture_output=True,
                            text=True,
                            timeout=10
                        )
                        if result.returncode != 0:
                            logger.warning(
                                f"Failed to unmount {mount_point}: {result.stderr}")
                            return False
                return True

        # Alternative: try to unmount by device
        result = subprocess.run(
            ['sudo', 'umount', drive],
            capture_output=True,
            text=True,
            timeout=10
        )

        return result.returncode == 0

    except _SUBPROCESS_PARSE_ERRORS as e:
        logger.error(f"Failed to unmount {drive}: {e}")
        return False


def mount_drive(drive: str, mount_point: str = None) -> bool:
    """Mount a drive on Linux."""
    try:
        if not drive.startswith('/dev/'):
            drive = f"/dev/{drive}"

        if mount_point is None:
            # Let system choose mount point
            result = subprocess.run(
                ['sudo', 'mount', drive],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        else:
            # Mount to specific point
            os.makedirs(mount_point, exist_ok=True)
            result = subprocess.run(
                ['sudo', 'mount', drive, mount_point],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0

    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Failed to mount {drive}: {e}")
        return False


def format_drive(drive: str, filesystem: str = "vfat",
                 label: str = "UNETBOOTIN") -> bool:
    """Format a drive on Linux."""
    try:
        if not drive.startswith('/dev/'):
            drive = f"/dev/{drive}"

        # First, unmount the drive
        unmount_drive(drive)

        # Determine partition or whole device
        # For whole device formatting, we might need to use parted or fdisk
        # This is a simplified version that assumes we're formatting a partition

        if filesystem.lower() in ['vfat', 'fat32', 'fat16']:
            # Use mkfs.vfat
            result = subprocess.run(
                ['sudo', 'mkfs.vfat', '-F32', '-n', label, drive],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0

        elif filesystem.lower() in ['ext2', 'ext3', 'ext4']:
            fs_type = filesystem.lower()
            result = subprocess.run(
                ['sudo', f'mkfs.{fs_type}', '-L', label, drive],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0

        elif filesystem.lower() == 'ntfs':
            result = subprocess.run(
                ['sudo', 'mkfs.ntfs', '-f', '-L', label, drive],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0

        elif filesystem.lower() == 'exfat':
            result = subprocess.run(
                ['sudo', 'mkfs.exfat', '-n', label, drive],
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode == 0

        logger.error(f"Unsupported filesystem type: {filesystem}")
        return False

    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Failed to format {drive} as {filesystem}: {e}")
        return False


def get_parent_disk(device: str) -> Optional[str]:
    """Resolve the whole-disk device for a partition (or return the device
    itself if it is already a whole disk), using lsblk metadata."""
    try:
        if not device.startswith('/dev/'):
            device = f"/dev/{device}"

        # If it's a partition, lsblk reports its parent kernel name (pkname)
        result = subprocess.run(
            ['lsblk', '-no', 'pkname', device],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            pkname = result.stdout.strip().splitlines(
            )[0].strip() if result.stdout.strip() else ''
            if pkname:
                return f"/dev/{pkname}"

        # No parent: check it really is a disk before returning it
        result = subprocess.run(
            ['lsblk', '-no', 'type', '-d', device],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip() == 'disk':
            return device
    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Failed to resolve parent disk for {device}: {e}")

    return None


def install_bootloader(drive: str, bootloader_type: str = "syslinux") -> bool:
    """Install bootloader to a drive on Linux."""
    try:
        if not drive.startswith('/dev/'):
            drive = f"/dev/{drive}"

        if bootloader_type.lower() == 'syslinux':
            # Install syslinux bootloader

            # Resolve the parent (whole) disk for the given device. Never
            # guess by stripping trailing digits: that mangles NVMe/eMMC
            # names (nvme0n1p1, mmcblk0p1) and we are about to dd an MBR
            # to whatever this resolves to.
            whole_disk = get_parent_disk(drive)
            if not whole_disk:
                logger.error(
                    f"Cannot determine parent disk for {drive}; refusing to write MBR")
                return False

            # Check if syslinux is installed
            if not os.path.exists('/usr/lib/syslinux/mbr/mbr.bin'):
                logger.error("syslinux MBR files not found")
                return False

            # Install MBR
            result = subprocess.run(
                ['sudo', 'dd', 'if=/usr/lib/syslinux/mbr/mbr.bin',
                    f'of={whole_disk}', 'bs=440', 'count=1'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                logger.warning(f"Failed to install MBR: {result.stderr}")
                # Try alternative location
                if os.path.exists('/usr/share/syslinux/mbr.bin'):
                    result = subprocess.run(
                        ['sudo', 'dd', 'if=/usr/share/syslinux/mbr.bin',
                            f'of={whole_disk}', 'bs=440', 'count=1'],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    if result.returncode != 0:
                        return False
                else:
                    return False

            # Install bootloader to partition
            result = subprocess.run(
                ['sudo', 'syslinux', drive],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                # Try alternative: extlinux
                result = subprocess.run(
                    ['sudo', 'extlinux', '--install', drive],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode != 0:
                    return False

            return True

        elif bootloader_type.lower() == 'grub':
            # Install grub bootloader
            result = subprocess.run(
                ['sudo', 'grub-install', '--target=i386-pc',
                    '--boot-directory=/boot', drive],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0

        elif bootloader_type.lower() == 'grub2':
            # Install grub2
            result = subprocess.run(
                ['sudo', 'grub2-install', '--target=i386-pc',
                    '--boot-directory=/boot', drive],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0

        logger.error(f"Unsupported bootloader type: {bootloader_type}")
        return False

    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Failed to install bootloader to {drive}: {e}")
        return False


def get_volume_label(drive: str) -> Optional[str]:
    """Get volume label for a drive on Linux."""
    try:
        if not drive.startswith('/dev/'):
            drive = f"/dev/{drive}"

        # Try blkid first
        result = subprocess.run(
            ['sudo', 'blkid', drive],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'LABEL=' in line:
                    return line.split('LABEL=')[1].split()[0].strip('"')

        # Try e2label for ext filesystem
        result = subprocess.run(
            ['sudo', 'e2label', drive],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            return result.stdout.strip()

        # Try dosfslabel for FAT filesystem
        result = subprocess.run(
            ['sudo', 'dosfslabel', drive],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            return result.stdout.strip()

    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Failed to get volume label for {drive}: {e}")

    return None


def set_volume_label(drive: str, label: str) -> bool:
    """Set volume label for a drive on Linux."""
    try:
        if not drive.startswith('/dev/'):
            drive = f"/dev/{drive}"

        # Determine filesystem type
        result = subprocess.run(
            ['sudo', 'blkid', drive],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode != 0:
            logger.error(f"Failed to get filesystem type for {drive}")
            return False

        fs_type = None
        for line in result.stdout.split('\n'):
            if 'TYPE=' in line:
                fs_type = line.split('TYPE=')[1].split()[0].strip('"')
                break

        if not fs_type:
            logger.error(f"Could not determine filesystem type for {drive}")
            return False

        # Set label based on filesystem type
        if fs_type in ['vfat', 'fat32', 'fat16']:
            result = subprocess.run(
                ['sudo', 'dosfslabel', drive, label],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0

        elif fs_type in ['ext2', 'ext3', 'ext4']:
            result = subprocess.run(
                ['sudo', 'e2label', drive, label],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0

        elif fs_type == 'ntfs':
            result = subprocess.run(
                ['sudo', 'ntfslabel', drive, label],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0

        logger.error(f"Unsupported filesystem type for labeling: {fs_type}")
        return False

    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Failed to set volume label for {drive}: {e}")
        return False


def get_device_size(drive: str) -> Optional[int]:
    """Get size of a device in bytes on Linux."""
    try:
        if not drive.startswith('/dev/'):
            drive = f"/dev/{drive}"

        result = subprocess.run(
            ['blockdev', '--getsize64', drive],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            return int(result.stdout.strip())

        # Fallback: use cat /sys/block/.../size
        if drive.startswith('/dev/'):
            base_device = drive.replace('/dev/', '')
            sys_path = f'/sys/block/{base_device}/size'
            if os.path.exists(sys_path):
                with open(sys_path, 'r') as f:
                    sector_count = int(f.read().strip())

                # Get sector size
                sector_size_path = f'/sys/block/{base_device}/queue/hw_sector_size'
                if os.path.exists(sector_size_path):
                    with open(sector_size_path, 'r') as f:
                        sector_size = int(f.read().strip())
                    return sector_count * sector_size
                else:
                    return sector_count * 512  # Default sector size

    except _SUBPROCESS_PARSE_ERRORS as e:
        logger.error(f"Failed to get size for {drive}: {e}")

    return None


def check_drive_writable(drive: str) -> bool:
    """Check if a drive is writable on Linux."""
    try:
        if not drive.startswith('/dev/'):
            drive = f"/dev/{drive}"

        # Check if device is writable
        result = subprocess.run(
            ['test', '-w', drive],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0

    except _SUBPROCESS_ERRORS:
        return False


def sync_filesystem() -> bool:
    """Sync the filesystem on Linux."""
    try:
        result = subprocess.run(['sync'], timeout=10)
        return result.returncode == 0
    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Failed to sync filesystem: {e}")
        return False


def get_mount_point(device: str) -> Optional[str]:
    """Get the mount point for a device on Linux."""
    try:
        if not device.startswith('/dev/'):
            device = f"/dev/{device}"

        result = subprocess.run(
            ['findmnt', '-n', '-o', 'TARGET', '--first-only', device],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            return result.stdout.strip()

        # Fallback: use mount command
        result = subprocess.run(['mount'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if device in line:
                    parts = line.split()
                    return parts[2] if len(parts) > 2 else None

    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Failed to get mount point for {device}: {e}")

    return None


def is_external_drive(drive: str) -> bool:
    """Check if a drive is external (USB, etc.) on Linux."""
    try:
        if not drive.startswith('/dev/'):
            drive = f"/dev/{drive}"

        # Check if device is removable
        result = subprocess.run(
            ['lsblk', '-J', '-d', '-o', 'NAME,RM'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            device_name = drive.split('/')[-1]
            for device in data.get('blockdevices', []):
                if device.get('name') == device_name:
                    return device.get('rm', False)

        # Check /dev/disk/by-id for usb
        by_id_dir = '/dev/disk/by-id'
        if os.path.exists(by_id_dir):
            for entry in os.listdir(by_id_dir):
                link_path = os.path.join(by_id_dir, entry)
                try:
                    target = os.readlink(link_path)
                    if target == drive or target.endswith(drive.split('/')[-1]):
                        return 'usb' in entry.lower() or 'ata' in entry.lower()
                except OSError:
                    continue

        return False

    except _SUBPROCESS_PARSE_ERRORS:
        return False


# Vendor/model substrings that indicate a virtual disk (VM / hypervisor).
_VIRTUAL_MARKERS = ('VBOX', 'VMWARE', 'QEMU', 'VIRTUAL', 'VIRTIO', 'PARALLELS')
# Mountpoints that mark a disk as holding the running system.
_SYSTEM_MOUNTPOINTS = ('/', '/boot', '/boot/efi', '/usr', '/var', '/home',
                       '[SWAP]')


def is_safe_target(device: str) -> bool:
    """Whether `device` is a safe (removable/USB, non-system, non-virtual) target.

    A device qualifies only if ALL of the following hold:
      * it is a whole disk (``TYPE == disk``), not a partition/loop/rom;
      * it is USB-attached (``TRAN == usb``) or flagged removable (``RM``);
      * it is not a virtual disk (vendor/model/transport not VM-like);
      * none of its partitions host the running system (``/``, ``/boot``…).

    Fails closed (returns False) on any uncertainty, so an internal or virtual
    disk can never be selected — not even as an exception.
    """
    try:
        if not device.startswith('/dev/'):
            device = f"/dev/{device}"
        name = device.split('/')[-1]

        result = subprocess.run(
            ['lsblk', '-J', '-o',
             'NAME,TYPE,RM,TRAN,VENDOR,MODEL,MOUNTPOINT', device],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return False

        import json
        data = json.loads(result.stdout)
        blk = data.get('blockdevices', [])
        dev = next((b for b in blk if b.get('name') == name), None)
        if dev is None:
            return False

        # Must be a whole disk
        if dev.get('type') != 'disk':
            return False

        tran = (dev.get('tran') or '').lower()
        is_removable = bool(dev.get('rm'))
        is_usb = tran == 'usb'
        if not (is_usb or is_removable):
            return False

        # Reject virtual disks
        ident = f"{dev.get('vendor') or ''} {dev.get('model') or ''}".upper()
        if tran in ('virtio',) or any(m in ident for m in _VIRTUAL_MARKERS):
            return False

        # Reject if the disk (or any of its partitions) hosts the system
        def _hosts_system(node) -> bool:
            mp = (node.get('mountpoint') or '').strip()
            if mp in _SYSTEM_MOUNTPOINTS:
                return True
            return any(_hosts_system(c) for c in node.get('children', []))

        if _hosts_system(dev):
            return False

        return True

    except _SUBPROCESS_PARSE_ERRORS:
        return False


def check_root_privileges() -> bool:
    """Check if running with root privileges."""
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False
