"""
Linux-specific functionality for PyNetboot.
"""

import os
import re
import time
import shlex
import logging
import subprocess
from typing import Optional, List, Dict, Any

from pynetboot.core.utils import find_tool

logger = logging.getLogger(__name__)

# How long to wait for udev to create the partition node after the table is
# written. Slow USB bridges can take several seconds to re-enumerate.
_PARTITION_SETTLE_SECONDS = 15

# Linux drivers shell out to lsblk/findmnt/blkid/etc. and parse their JSON or
# text output. json.JSONDecodeError is a ValueError subclass, so ValueError
# also covers malformed JSON.
_SUBPROCESS_ERRORS = (subprocess.SubprocessError, OSError)
_SUBPROCESS_PARSE_ERRORS = (subprocess.SubprocessError, OSError,
                            ValueError, KeyError, TypeError)

# Byte multipliers for lsblk human-readable sizes (K=1024-based, as lsblk uses).
_SIZE_UNITS = {'B': 1, 'K': 1024, 'M': 1024 ** 2, 'G': 1024 ** 3,
               'T': 1024 ** 4, 'P': 1024 ** 5}


def _parse_size(value: Any) -> int:
    """Parse an lsblk SIZE field to a byte count.

    Handles plain byte counts (``lsblk -b`` or JSON integers) *and* the
    human-readable form lsblk emits by default (e.g. ``100G``, ``14.5G``,
    ``512M``). Returns 0 for anything unparseable rather than raising —
    ``int("100G")`` used to crash drive enumeration.
    """
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return 0
    try:
        return int(text)  # already bytes
    except ValueError:
        pass
    match = re.match(r'^([\d.]+)\s*([BKMGTP])i?B?$', text, re.IGNORECASE)
    if match:
        try:
            number = float(match.group(1))
        except ValueError:
            return 0
        return int(number * _SIZE_UNITS.get(match.group(2).upper(), 1))
    return 0


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
                        'size': _parse_size(device.get('size', 0)),
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
                                            'size': _parse_size(partition.get('size', 0)),
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
                                        device_info['size'] = _parse_size(device.get('size', 0))
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
    """Serial number for a device, or None when it cannot be determined.

    Tries udevadm, then sg_vpd, then hdparm. Each is attempted independently:
    previously one shared try block meant the first missing tool skipped the
    remaining fallbacks entirely. A tool that is absent is also not an error -
    the serial is optional metadata, and inside a Flatpak sandbox none of these
    host utilities are present.
    """
    import shutil

    if not device.startswith('/dev/'):
        device = f"/dev/{device}"

    def _run(command):
        """Run a probe, returning its output or None if it cannot be used."""
        if shutil.which(command[0]) is None:
            logger.debug(f"{command[0]} not available; skipping serial probe")
            return None
        try:
            result = subprocess.run(command, capture_output=True, text=True,
                                    timeout=5)
        except _SUBPROCESS_ERRORS as e:
            logger.debug(f"{command[0]} failed for {device}: {e}")
            return None
        return result.stdout if result.returncode == 0 else None

    output = _run(['udevadm', 'info', '--query=property', '--name=' + device])
    if output:
        for line in output.split('\n'):
            if line.startswith('ID_SERIAL='):
                return line.split('=', 1)[1].strip()

    output = _run(['sg_vpd', '--page=0x80', device])
    if output:
        for line in output.split('\n'):
            if 'Unit serial number' in line:
                return line.split(':')[1].strip()

    output = _run(['hdparm', '-I', device])
    if output:
        for line in output.split('\n'):
            if 'Serial number' in line:
                return line.split(':')[1].strip()

    logger.debug(f"No serial number available for {device}")
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
                        'size': _parse_size(device.get('size', 0)),
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


def device_mountpoints(drive: str) -> List[str]:
    """Return every mount point held by a device *and its partitions*.

    ``findmnt /dev/sdb`` only reports a filesystem mounted on that exact
    node, so it misses ``/dev/sdb1`` — which is what a desktop auto-mounts.
    Leaving the partition mounted keeps the whole disk busy, and mkfs opens
    block devices with O_EXCL, so formatting then fails with EBUSY.
    ``lsblk`` walks the disk and its children in one call.
    """
    if not drive.startswith('/dev/'):
        drive = f"/dev/{drive}"

    try:
        result = subprocess.run(
            ['lsblk', '-nro', 'MOUNTPOINT', drive],
            capture_output=True,
            text=True,
            timeout=5
        )
    except _SUBPROCESS_ERRORS as e:
        logger.warning(f"Could not list mount points for {drive}: {e}")
        return []

    if result.returncode != 0:
        logger.warning(
            f"lsblk failed for {drive}: {(result.stderr or '').strip()}")
        return []

    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def unmount_drive(drive: str) -> bool:
    """Unmount a drive, and every partition on it, on Linux."""
    try:
        if not drive.startswith('/dev/'):
            drive = f"/dev/{drive}"

        mount_points = device_mountpoints(drive)
        if not mount_points:
            logger.info(f"No mounted filesystems on {drive}")
            return True

        all_unmounted = True
        for mount_point in mount_points:
            result = subprocess.run(
                ['sudo', 'umount', mount_point],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                logger.info(f"Unmounted {mount_point}")
            else:
                logger.warning(
                    f"Failed to unmount {mount_point}: "
                    f"{(result.stderr or '').strip()}")
                all_unmounted = False

        return all_unmounted

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


# Writing a drive shells out to these. The deb and rpm depend on the packages
# that provide them, but the AppImage declares no dependencies and the Flatpak
# ships its own, so the set is checked at runtime instead of assumed.
_REQUIRED_TOOLS = {
    'lsblk': 'util-linux',
    'mount': 'util-linux',
    'umount': 'util-linux',
    'parted': 'parted',
    'mkfs.vfat': 'dosfstools',
}

# mkfs.vfat and parted live in sbin, which is usually absent from a desktop
# user's PATH even though the commands run fine once elevated.




def missing_required_tools() -> List[str]:
    """Return 'command (package)' for each tool needed but not installed."""
    return [f"{tool} ({package})"
            for tool, package in sorted(_REQUIRED_TOOLS.items())
            if find_tool(tool) is None]


def is_whole_disk(device: str) -> bool:
    """True if `device` is a whole disk rather than one of its partitions."""
    if not device.startswith('/dev/'):
        device = f"/dev/{device}"
    try:
        result = subprocess.run(
            ['lsblk', '-ndo', 'TYPE', device],
            capture_output=True, text=True, timeout=5
        )
    except _SUBPROCESS_ERRORS as e:
        logger.debug(f"lsblk TYPE lookup failed for {device}: {e}")
        return False
    return result.returncode == 0 and result.stdout.strip() == 'disk'


def first_partition(disk: str) -> Optional[str]:
    """Return a disk's first partition, or None if it has none.

    Asks lsblk instead of appending "1", because the naming differs between
    /dev/sdb1 and /dev/nvme0n1p1 or /dev/mmcblk0p1.
    """
    if not disk.startswith('/dev/'):
        disk = f"/dev/{disk}"
    try:
        result = subprocess.run(
            ['lsblk', '-nro', 'NAME,TYPE', disk],
            capture_output=True, text=True, timeout=5
        )
    except _SUBPROCESS_ERRORS as e:
        logger.debug(f"lsblk partition lookup failed for {disk}: {e}")
        return None

    if result.returncode != 0:
        return None

    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1] == 'part':
            return f"/dev/{fields[0]}"
    return None


def partition_device(disk: str) -> Optional[str]:
    """Put a DOS partition table with one bootable FAT32 partition on `disk`.

    A BIOS-bootable USB stick needs a partition table: the syslinux MBR goes
    to the disk's sector 0 while syslinux itself goes to the *partition's*
    boot sector. Formatting the whole disk instead (a "superfloppy") puts a
    FAT boot sector at sector 0, so writing the MBR over it destroys the
    filesystem's BPB and the stick does not boot.

    Returns the new partition (e.g. /dev/sdb1), or None on failure.
    """
    if not disk.startswith('/dev/'):
        disk = f"/dev/{disk}"

    parted = find_tool('parted')
    if parted is None:
        logger.error(
            "parted is required to partition the target drive but was not "
            "found. Install the 'parted' package and try again.")
        return None

    if not unmount_drive(disk):
        logger.error(f"Could not unmount every filesystem on {disk} before "
                     "partitioning it")
        return None

    # Wiping stale signatures, writing the table and re-reading it are three
    # privileged steps. Running them separately means three separate
    # elevation prompts, so they go in as one script under a single one.
    # wipefs is tolerated failing; the rest must succeed.
    script = ' && '.join((
        f"wipefs -a {shlex.quote(disk)} || true",
        ' '.join(shlex.quote(a) for a in (
            parted, '-s', '--align', 'optimal', disk,
            'mklabel', 'msdos',
            'mkpart', 'primary', 'fat32', '1MiB', '100%',
            'set', '1', 'boot', 'on')),
        f"partprobe {shlex.quote(disk)} || true",
    ))

    try:
        result = subprocess.run(
            ['sudo', 'sh', '-c', script],
            capture_output=True, text=True, timeout=300
        )
    except _SUBPROCESS_ERRORS as e:
        logger.error(f"Partitioning {disk} failed: {e}")
        return None

    if result.returncode != 0:
        detail = ((result.stderr or '') + (result.stdout or '')).strip()
        logger.error(
            f"parted failed on {disk} (exit {result.returncode}): "
            f"{detail or 'no output'}")
        return None

    # udevadm needs no privileges, so it stays outside the elevated script.
    try:
        subprocess.run(['udevadm', 'settle'],
                       capture_output=True, text=True, timeout=60)
    except _SUBPROCESS_ERRORS as e:
        logger.debug(f"udevadm settle failed (continuing): {e}")

    deadline = time.monotonic() + _PARTITION_SETTLE_SECONDS
    while time.monotonic() < deadline:
        partition = first_partition(disk)
        if partition and os.path.exists(partition):
            logger.info(f"Created {partition} on {disk}")
            return partition
        time.sleep(0.5)

    logger.error(
        f"Partition table written to {disk} but no partition device appeared "
        f"within {_PARTITION_SETTLE_SECONDS}s")
    return None


def _run_mkfs(command: List[str], drive: str) -> bool:
    """Run a mkfs command, logging why it failed rather than just False.

    The timeout is generous because the elevation prompt happens inside this
    call: the clock covers however long the user takes over the PolicyKit
    password dialog, not just the format itself.
    """
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=300
        )
    except subprocess.TimeoutExpired:
        logger.error(f"{command[1]} timed out formatting {drive}")
        return False

    if result.returncode == 0:
        return True

    detail = ((result.stderr or '') + (result.stdout or '')).strip()
    logger.error(
        f"{command[1]} failed on {drive} (exit {result.returncode}): "
        f"{detail or 'no output'}")
    return False


def format_drive(drive: str, filesystem: str = "vfat",
                 label: str = "PYNETBOOT") -> bool:
    """Format a drive on Linux."""
    try:
        if not drive.startswith('/dev/'):
            drive = f"/dev/{drive}"

        # Every filesystem on the disk has to go first. mkfs opens the block
        # device with O_EXCL, so a single still-mounted partition makes the
        # format fail with "Device or resource busy".
        if not unmount_drive(drive):
            logger.error(
                f"Could not unmount every filesystem on {drive}; formatting "
                "would fail with 'Device or resource busy'. Close anything "
                "using the drive and try again.")
            return False

        # Determine partition or whole device
        # For whole device formatting, we might need to use parted or fdisk
        # This is a simplified version that assumes we're formatting a partition

        if filesystem.lower() in ['vfat', 'fat32', 'fat16']:
            return _run_mkfs(
                ['sudo', 'mkfs.vfat', '-F32', '-n', label, drive], drive)

        elif filesystem.lower() in ['ext2', 'ext3', 'ext4']:
            fs_type = filesystem.lower()
            return _run_mkfs(
                ['sudo', f'mkfs.{fs_type}', '-L', label, drive], drive)

        elif filesystem.lower() == 'ntfs':
            return _run_mkfs(
                ['sudo', 'mkfs.ntfs', '-f', '-L', label, drive], drive)

        elif filesystem.lower() == 'exfat':
            return _run_mkfs(
                ['sudo', 'mkfs.exfat', '-n', label, drive], drive)

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

# Transports that can only be an externally attached disk. Used by the
# "Hard Disk" target type, which also accepts fixed external drives.
_EXTERNAL_TRANSPORTS = ('usb', 'thunderbolt', 'ieee1394', 'firewire')
# Mountpoints that mark a disk as holding the running system.
_SYSTEM_MOUNTPOINTS = ('/', '/boot', '/boot/efi', '/usr', '/var', '/home',
                       '[SWAP]')


def is_safe_target(device: str, allow_external_fixed: bool = False) -> bool:
    """Whether `device` is a safe (external, non-system, non-virtual) target.

    A device qualifies only if ALL of the following hold:
      * it is a whole disk (``TYPE == disk``), not a partition/loop/rom;
      * it is USB-attached (``TRAN == usb``) or flagged removable (``RM``);
      * it is not a virtual disk (vendor/model/transport not VM-like);
      * none of its partitions host the running system (``/``, ``/boot``…).

    With ``allow_external_fixed=True`` (the "Hard Disk" target type) the second
    rule is widened to any externally attached disk — USB/Thunderbolt/FireWire
    or kernel-hotpluggable — so external hard drives that are not flagged as
    removable media also qualify. Every other rule still applies, so the system
    disk, internal disks and virtual disks remain excluded.

    Fails closed (returns False) on any uncertainty, so an internal or virtual
    disk can never be selected — not even as an exception.
    """
    try:
        if not device.startswith('/dev/'):
            device = f"/dev/{device}"
        name = device.split('/')[-1]

        result = subprocess.run(
            ['lsblk', '-J', '-o',
             'NAME,TYPE,RM,TRAN,VENDOR,MODEL,MOUNTPOINT,HOTPLUG', device],
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
        if allow_external_fixed:
            # "Hard Disk" mode: any externally attached disk qualifies, even a
            # fixed one (external HDDs report RM=0 but are hot-pluggable).
            is_external_bus = tran in _EXTERNAL_TRANSPORTS
            is_hotplug = bool(dev.get('hotplug'))
            if not (is_usb or is_removable or is_external_bus or is_hotplug):
                return False
        elif not (is_usb or is_removable):
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
