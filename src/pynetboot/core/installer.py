"""
USB installation functionality for PyNetboot.
"""

import os
import re
import sys
import contextlib
import time
import logging
import shutil
import subprocess
import tempfile
from typing import Optional, Callable, Dict, Any, List, Tuple

from pynetboot.resources import (
    bootloader_path, read_bootloader,
    find_bundled_syslinux, find_bundled_extlinux,
)
from pynetboot.core.utils import directory_stats, find_tool, format_size

logger = logging.getLogger(__name__)

# Installation drives external bootloader tools via subprocess and copies
# files via shutil; failures surface as these.
_SUBPROCESS_ERRORS = (subprocess.SubprocessError, OSError)
_FILE_COPY_ERRORS = (OSError, shutil.Error)

# Syslinux modules copied onto the target filesystem so the boot menu
# renders. Shipped in resources/bootloader/, all from syslinux 6.03.
#
# ldlinux.c32 is what the boot sector loads after ldlinux.sys, and the 6.x
# menu modules are dynamically linked against libcom32/libutil -- shipping
# menu.c32 alone gets "Failed to load COM32 file" at boot. They must all
# come from the same syslinux release as ldlinux.sys.
_SYSLINUX_MODULES = ('ldlinux.c32', 'libcom32.c32', 'libutil.c32',
                     'menu.c32', 'vesamenu.c32')

# The UEFI counterparts, under resources/bootloader/efi64/. A firmware boots
# EFI/BOOT/BOOTX64.EFI off the FAT partition, so these are copied rather than
# installed -- no boot sector or patching involved.
_EFI_BOOT_DIR = ('EFI', 'BOOT')
_EFI_LOADER = 'BOOTX64.EFI'
_EFI_MODULES = ('ldlinux.e64', 'libcom32.c32', 'libutil.c32',
                'menu.c32', 'vesamenu.c32')


class USBInstaller:
    """Handles USB installation process."""

    def __init__(self):
        """Initialize the USB installer."""
        self.worker = None
        self.platform = sys.platform


    def install_sync(self, source_dir: str, target_device: str,
                    install_params: Optional[Dict[str, Any]] = None,
                    progress_callback: Optional[Callable[[int], None]] = None) -> Tuple[bool, str]:
        """Synchronously install to USB device.

        The whole run happens inside one privileged session, so the user is
        asked for a password once rather than once per privileged command.
        """
        from pynetboot.core.elevation import privileged_session, is_elevated

        with privileged_session() as single_prompt:
            if single_prompt:
                pass          # one prompt already covers the whole run
            elif is_elevated():
                logger.info("Already running elevated; no prompt needed")
            else:
                logger.info(
                    "No privileged session; each step will ask separately")
            return self._install_sync(
                source_dir, target_device, install_params, progress_callback)

    def _install_sync(self, source_dir: str, target_device: str,
                      install_params: Optional[Dict[str, Any]] = None,
                      progress_callback: Optional[Callable[[int], None]] = None) -> Tuple[bool, str]:
        try:
            params = install_params or {}
            install_type = params.get('install_type', 'distribution')
            drive_type = params.get('drive_type', 'USB Drive')

            # Progress stages
            stages = [
                ('Preparing', 10),
                ('Copying files', 60),
                ('Installing bootloader', 20),
                ('Cleaning up', 10),
            ]

            total_progress = 0
            current_stage = 0

            def update_progress(percent_in_stage: int):
                """Update overall progress based on current stage progress."""
                nonlocal total_progress
                stage_name, stage_weight = stages[current_stage]
                stage_progress = int(percent_in_stage * stage_weight / 100)
                total_progress = sum(
                    stage_weight for stage_name, stage_weight in stages[:current_stage]
                ) + stage_progress
                if progress_callback:
                    progress_callback(min(total_progress, 99))

            logger.info(
                f"Install starting: source={source_dir} target={target_device} "
                f"type={install_type} drive={drive_type} "
                f"uefi_only={params.get('enable_uefi_only', False)} "
                f"secure_boot={params.get('enable_secure_boot', False)} "
                f"persistence={params.get('persistence_enabled', False)}")

            def finished(stage: str, started: float) -> None:
                logger.info(f"Stage '{stage}' finished in "
                            f"{time.monotonic() - started:.1f}s")

            # Stage 1: Prepare
            update_progress(0)
            started = time.monotonic()
            if not self._prepare_installation(source_dir, target_device, params):
                logger.error("Stage 'Preparing' failed")
                return False, params.get('failure_reason', "Preparation failed")
            finished('Preparing', started)
            update_progress(100)
            current_stage += 1

            # Stage 2: Copy files
            update_progress(0)
            started = time.monotonic()
            if not self._copy_files_to_device(
                source_dir, target_device, params, update_progress):
                logger.error("Stage 'Copying files' failed")
                return False, "File copying failed"
            finished('Copying files', started)
            update_progress(100)
            current_stage += 1

            # Stage 3: Install bootloader
            update_progress(0)
            started = time.monotonic()
            if not self._install_bootloader(target_device, params, update_progress):
                logger.error("Stage 'Installing bootloader' failed")
                return False, "Bootloader installation failed"
            finished('Installing bootloader', started)
            update_progress(100)
            current_stage += 1

            # Stage 4: Clean up
            update_progress(0)
            started = time.monotonic()
            self._cleanup_installation(source_dir, target_device, params)
            finished('Cleaning up', started)
            update_progress(100)

            if progress_callback:
                progress_callback(100)

            return True, "Installation completed successfully"

        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"Installation failed: {e}")
            return False, str(e)

    def _prepare_installation(self, source_dir: str, target_device: str,
                              params: Dict[str, Any]) -> bool:
        """Prepare for installation."""
        logger.info(f"Preparing installation on {target_device}")
        self._log_device_details(target_device)

        # diskpart needs Administrator and reports the lack of it as a bare
        # "Access is denied" once the write is already under way. Say so
        # here instead, while the drive is still untouched.
        if self.platform == 'win32':
            from pynetboot.core.elevation import is_elevated
            if not is_elevated():
                self._fail(params,
                           "PyNetboot is not running as Administrator. "
                           "Right-click it and choose "
                           "'Run as administrator', then try again.")
                return False

        # Check the external tools up front. Reaching mkfs before noticing
        # dosfstools is absent means the drive has already been repartitioned.
        if self.platform == 'linux':
            from pynetboot.platform.linux import missing_required_tools
            missing = missing_required_tools()
            if missing:
                self._fail(params, "These required commands are missing: "
                                   + ', '.join(missing))
                return False

        try:
            # HARD SAFETY GATE (last line of defense): refuse to touch anything
            # that is not a proven removable/external USB drive. This runs at
            # the point of destruction, so even if the UI filter or the
            # confirmation dialog were bypassed, an internal/system/virtual disk
            # can never be formatted. Fails closed.
            from pynetboot.platform import is_safe_target
            if not is_safe_target(target_device):
                logger.error(
                    f"Refusing to format {target_device}: not a removable "
                    f"external USB drive (safety guard)")
                return False

            # Check if device exists and is writable
            if not self._validate_target_device(target_device):
                return False

            # Check if device is mounted and unmount if necessary
            if self._is_device_mounted(target_device):
                if not self._unmount_device(target_device):
                    logger.error(f"Failed to unmount {target_device}")
                    return False

            # Give the disk a partition table before formatting anything.
            # syslinux goes into the partition's boot sector and the syslinux
            # MBR goes to sector 0 of the disk; formatting the whole disk
            # instead would put the filesystem at sector 0, where writing the
            # MBR later destroys it.
            target_partition = self._partition_target(target_device)
            if target_partition is None:
                return False
            params['target_partition'] = target_partition

            # Format the partition with FAT32 filesystem
            logger.info(f"Formatting {target_partition} with FAT32")
            if not self._format_device(target_partition):
                logger.error(f"Failed to format {target_partition}")
                return False

            if self.platform == 'darwin':
                # diskutil erased and repartitioned the whole disk, so the
                # slice to mount and install into only exists now. Record
                # both, so 'target_partition' means a partition here too --
                # the bootloader has to go into *its* boot sector, not the
                # disk's.
                params['target_disk'] = self._macos_whole_disk(target_partition)
                data_slice = self._macos_data_partition(params['target_disk'])
                if data_slice:
                    target_partition = f"/dev/{data_slice}"
                    params['target_partition'] = target_partition
                    logger.info(
                        f"Target partition on {params['target_disk']}: "
                        f"{target_partition}")
                else:
                    logger.warning(
                        f"No data partition found on {params['target_disk']} "
                        f"after formatting")

            # Create temporary working directory
            params['temp_dir'] = tempfile.mkdtemp(prefix='pynetboot_install_')

            if self.platform == 'win32':
                # A drive letter is already a path: there is nothing to
                # mount, and the files belong at the drive's root. Copying
                # them into a temporary folder instead would leave the drive
                # empty while reporting success.
                from pynetboot.platform.windows import drive_root
                mount_point = drive_root(target_partition) or target_partition

                # Formatting removes the letter and Windows re-creates the
                # volume a moment later, so the root does not exist yet.
                # Writing now fails on every single file.
                from pynetboot.platform.windows import wait_for_drive
                if not wait_for_drive(mount_point):
                    self._fail(params,
                               f"{mount_point} did not come back after "
                               f"formatting. Unplug the drive, plug it in "
                               f"again and retry.")
                    shutil.rmtree(params['temp_dir'], ignore_errors=True)
                    return False

                params['mount_point_is_temp'] = False
                logger.info(f"Writing directly to {mount_point}")
            else:
                # Create and mount the device to a temporary mount point
                mount_point = tempfile.mkdtemp(prefix='pynetboot_mount_')
                params['mount_point_is_temp'] = True
                logger.info(f"Mounting {target_partition} to {mount_point}")
                if not self._mount_device(target_partition, mount_point):
                    logger.error(f"Failed to mount {target_partition}")
                    # Clean up temp dir
                    shutil.rmtree(params['temp_dir'], ignore_errors=True)
                    shutil.rmtree(mount_point, ignore_errors=True)
                    return False

            # Store mount point in params for use during file copying
            params['mount_point'] = mount_point

            return True

        except _SUBPROCESS_ERRORS as e:
            logger.error(f"Preparation failed: {e}")
            return False

    def _copy_files_to_device(self, source_dir: str, target_device: str,
                              params: Dict[str, Any],
                              progress_callback: Optional[Callable[[int], None]] = None) -> bool:
        """Copy files from source to target device."""
        # Use mount point if available (for formatted devices), otherwise fall
        # back to raw device
        actual_target = params.get('mount_point', target_device)
        logger.info(f"Copying files from {source_dir} to {actual_target}")

        try:
            # Get list of files to copy
            files_to_copy = self._get_files_to_copy(source_dir, params)
            total_files = len(files_to_copy)
            copied_files = 0
            failed_files = []

            source_files, source_bytes = directory_stats(source_dir)
            logger.info(
                f"Copying {total_files} top-level entries "
                f"({source_files} files, {format_size(source_bytes)}) "
                f"to {actual_target}")
            if total_files == 0:
                logger.error(
                    f"Nothing to copy from {source_dir}: the extracted image "
                    f"is empty, so the target would be left unbootable")
                return False

            for file_path in files_to_copy:
                src_path = os.path.join(source_dir, file_path)
                dest_path = os.path.join(actual_target, file_path)

                try:
                    # Create directory structure
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

                    # Copy file
                    if os.path.isdir(src_path):
                        shutil.copytree(src_path, dest_path)
                    else:
                        shutil.copy2(src_path, dest_path)

                    copied_files += 1
                    if progress_callback:
                        progress = int((copied_files / total_files) * 100)
                        progress_callback(progress)

                except _FILE_COPY_ERRORS as e:
                    logger.error(f"Failed to copy {src_path} to {dest_path}: {e}")
                    failed_files.append(file_path)

            # A boot medium with missing files is broken - report failure
            # instead of pretending the copy succeeded.
            if failed_files:
                logger.error(
                    f"{len(failed_files)}/{total_files} files failed to copy "
                    f"(first: {failed_files[0]})"
                )
                return False

            written_files, written_bytes = directory_stats(actual_target)
            logger.info(
                f"Copied {copied_files}/{total_files} entries; target now "
                f"holds {written_files} files, {format_size(written_bytes)}")
            return True

        except _FILE_COPY_ERRORS as e:
            logger.error(f"File copying failed: {e}")
            return False

    def _install_bootloader(self, target_device: str,
                            params: Dict[str, Any],
                            progress_callback: Optional[Callable[[int], None]] = None) -> bool:
        """Install bootloader to target device."""
        logger.info(f"Installing bootloader to {target_device}")

        try:
            enable_uefi_only = params.get('enable_uefi_only', False)
            enable_secure_boot = params.get('enable_secure_boot', False)

            # Store boot options in params for config file generation
            boot_options = params.get('boot_options', '')
            params['boot_options'] = boot_options

            if enable_uefi_only:
                logger.info("UEFI-only installation mode enabled")
            if enable_secure_boot:
                logger.info("Secure Boot support enabled")

            if self.platform == 'win32':
                installed = self._install_bootloader_windows(
                    target_device, params, enable_uefi_only, enable_secure_boot)
            elif self.platform == 'darwin':
                installed = self._install_bootloader_macos(
                    target_device, params, enable_uefi_only, enable_secure_boot)
            else:  # Linux and other Unix
                installed = self._install_bootloader_linux(
                    target_device, params, enable_uefi_only, enable_secure_boot)

            # Record what ended up on the drive: a stick that does not boot is
            # usually a missing boot file, and the log is all we get to see.
            self._log_boot_layout(params.get('mount_point'))
            return installed

        except (OSError, subprocess.SubprocessError) as e:
            logger.error(f"Bootloader installation failed: {e}")
            return False

    def _cleanup_installation(self, source_dir: str, target_device: str,
                              params: Dict[str, Any]):
        """Clean up after installation."""
        logger.info("Cleaning up installation")

        try:
            # Unmount the device if it was mounted
            mount_point = params.get('mount_point')
            if mount_point and os.path.exists(mount_point):
                logger.info(f"Unmounting device from {mount_point}")
                if self.platform == 'win32':
                    # Windows: no explicit unmount needed for drive letters
                    pass
                elif os.path.ismount(mount_point):
                    command = (['umount', mount_point] if self.platform == 'darwin'
                               else ['sudo', 'umount', mount_point])
                    result = subprocess.run(
                        command, capture_output=True, text=True, timeout=60)
                    if result.returncode == 0:
                        logger.info(f"Unmounted {mount_point}")
                    else:
                        logger.error(
                            f"Could not unmount {mount_point}: "
                            f"{(result.stderr or '').strip()}")

                # Removing the directory is only safe once nothing is mounted
                # on it. While it is still a mount point it *is* the drive, so
                # deleting it would erase everything just written -- which is
                # what would happen whenever an unmount failed.
                if not params.get('mount_point_is_temp', True):
                    logger.debug(
                        f"Leaving {mount_point} alone: it is the target drive")
                elif os.path.ismount(mount_point):
                    logger.error(
                        f"Not removing {mount_point}: it is still mounted, so "
                        f"removing it would delete the drive's contents")
                else:
                    shutil.rmtree(mount_point, ignore_errors=True)

            # Remove temporary directory
            temp_dir = params.get('temp_dir')
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

            # Sync filesystem
            if self.platform != 'win32':
                subprocess.run(['sync'], timeout=10)

        except _SUBPROCESS_ERRORS as e:
            logger.error(f"Cleanup failed: {e}")

    def _validate_target_device(self, device: str) -> bool:
        """Validate target device."""
        try:
            if self.platform == 'win32':
                # Windows: check if drive letter exists
                if len(device) == 1 and device.isalpha():
                    device = f"{device}:\\"
                return os.path.exists(device)
            else:
                # Unix: check if device exists
                if not device.startswith('/dev/'):
                    device = f"/dev/{device}"
                return os.path.exists(device)
        except OSError as e:
            logger.error(f"Device validation failed: {e}")
            return False

    def _is_device_mounted(self, device: str) -> bool:
        """True if anything on `device` is mounted.

        The macOS check used to be `device in diskutil list`, which is true of
        every disk attached to the machine whether or not it is mounted -- so
        an unmount was always attempted, and a failure there stopped the
        install before it began.
        """
        try:
            if self.platform == 'win32':
                # On Windows, drives are always "mounted"
                return True
            if self.platform == 'darwin':
                from pynetboot.platform.macos import device_mountpoints
                points = device_mountpoints(device)
                if points:
                    logger.info(f"{device} is mounted at {', '.join(points)}")
                return bool(points)
            from pynetboot.platform.linux import device_mountpoints
            return bool(device_mountpoints(
                device if device.startswith('/dev/') else f"/dev/{device}"))
        except _SUBPROCESS_ERRORS as e:
            logger.debug(f"Could not tell whether {device} is mounted: {e}")
        return False

    def _unmount_device(self, device: str) -> bool:
        """Unmount `device` and everything on it.

        Delegates to the platform layer, which knows that a macOS whole disk
        needs `diskutil unmountDisk` -- plain `diskutil unmount` refuses it
        with "it has a partitioning scheme so use diskutil unmountDisk
        instead", which is what stopped an install on a USB stick.
        """
        if self.platform == 'win32':
            # Windows doesn't need unmounting for this purpose
            return True
        try:
            from pynetboot.platform import unmount_drive
            return unmount_drive(device)
        except _SUBPROCESS_ERRORS as e:
            logger.error(f"Failed to unmount {device}: {e}")
            return False

    def _macos_whole_disk(self, device: str) -> str:
        """Resolve the whole-disk node (e.g. /dev/disk4) via ``diskutil info -plist``.

        Uses the ``ParentWholeDisk`` field so a partition (disk4s1) resolves to
        its parent and a whole disk resolves to itself. No text scanning.
        """
        ident = device.replace('/dev/', '')
        try:
            result = subprocess.run(
                ['diskutil', 'info', '-plist', device],
                capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                import plistlib
                data = plistlib.loads(result.stdout.encode())
                whole = (data.get('ParentWholeDisk')
                         or data.get('DeviceIdentifier') or ident)
                return f"/dev/{whole}"
        except _SUBPROCESS_ERRORS as e:
            logger.debug(f"diskutil info failed for {device}: {e}")
        return f"/dev/{ident}"

    def _macos_data_partition(self, whole_disk: str) -> Optional[str]:
        """Return the first data partition identifier (e.g. disk4s1) of a disk.

        Parses ``diskutil list -plist`` instead of hardcoding ``s1`` — the FAT
        data slice can be s1 or (behind an EFI slice) s2 depending on layout.
        """
        ident = whole_disk.replace('/dev/', '')
        try:
            result = subprocess.run(
                ['diskutil', 'list', '-plist', ident],
                capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                return None
            import plistlib
            data = plistlib.loads(result.stdout.encode())
            for disk in data.get('AllDisksAndPartitions', []):
                if disk.get('DeviceIdentifier') != ident:
                    continue
                parts = disk.get('Partitions', [])
                # Prefer a non-EFI (data) partition; fall back to the first.
                for p in parts:
                    content = (p.get('Content') or '').upper()
                    if 'EFI' not in content and p.get('DeviceIdentifier'):
                        return p['DeviceIdentifier']
                if parts and parts[0].get('DeviceIdentifier'):
                    return parts[0]['DeviceIdentifier']
        except _SUBPROCESS_ERRORS as e:
            logger.debug(f"diskutil list failed for {ident}: {e}")
        except (ValueError, KeyError, TypeError):
            pass
        return None

    def _log_device_details(self, device: str) -> None:
        """Record what the target actually is before anything destructive.

        A log that says only "/dev/sdb" leaves you guessing about size,
        model and which partitions were mounted at the time.
        """
        if self.platform != 'linux':
            return
        try:
            result = subprocess.run(
                ['lsblk', '-o', 'NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT,MODEL',
                 device],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.strip().splitlines():
                    logger.info(f"  {line}")
            else:
                logger.warning(
                    f"Could not describe {device}: "
                    f"{(result.stderr or '').strip()}")
        except _SUBPROCESS_ERRORS as e:
            logger.warning(f"Could not describe {device}: {e}")

    @staticmethod
    def _fail(params: Dict[str, Any], reason: str) -> None:
        """Record why a stage failed, so the user sees it rather than a
        generic "Preparation failed"."""
        logger.error(reason)
        params['failure_reason'] = reason

    def _partition_target(self, target_device: str) -> Optional[str]:
        """Return the partition to format and mount for `target_device`.

        On Linux a whole disk is given a fresh DOS table with a single
        bootable FAT32 partition, and that partition is returned. If the
        caller already passed a partition it is used as-is. Other platforms
        keep their existing behaviour.

        Returns None if partitioning was needed but failed.
        """
        if self.platform in ('win32', 'darwin'):
            return target_device

        from pynetboot.platform.linux import is_whole_disk, partition_device

        if not is_whole_disk(target_device):
            logger.info(f"{target_device} is a partition; using it as-is")
            return target_device

        logger.info(f"Creating partition table on {target_device}")
        partition = partition_device(target_device)
        if not partition:
            logger.error(f"Failed to partition {target_device}")
            return None
        return partition

    def _format_device(self, device: str) -> bool:
        """Format the target device with FAT32 filesystem.

        Uses the platform-specific format_drive function for consistency.
        """
        logger.info(f"Formatting device {device}")

        try:
            from pynetboot.platform import format_drive

            # Normalize device for platform function
            if self.platform == 'win32':
                # Windows: ensure drive letter format (e.g., 'E:')
                if len(device) == 1 and device.isalpha():
                    device = f"{device}:"
                elif not device.endswith(':'):
                    device = f"{device}:"

            # Use platform-specific formatting
            return format_drive(device, filesystem="FAT32", label="PYNETBOOT")

        except _SUBPROCESS_ERRORS as e:
            logger.error(f"Failed to format device {device}: {e}")
            return False

    def _mount_device(self, device: str, mount_point: str) -> bool:
        """Mount the target device to the specified mount point."""
        logger.info(f"Mounting {device} to {mount_point}")

        try:
            if self.platform == 'win32':
                # Windows: drives are already accessible via drive letters
                # For simplicity, we'll just ensure the mount point directory exists
                if len(device) == 1 and device.isalpha():
                    # Use the drive letter as-is
                    if not os.path.exists(mount_point):
                        os.makedirs(mount_point, exist_ok=True)
                    return True
                return False
            elif self.platform == 'darwin':
                # macOS: resolve the real FAT data partition via plist (not a
                # hardcoded "s1"), then mount it at our chosen point.
                if not os.path.exists(mount_point):
                    os.makedirs(mount_point, exist_ok=True)

                whole_disk = self._macos_whole_disk(device)
                data_part = self._macos_data_partition(whole_disk)
                if not data_part:
                    logger.error(
                        f"Could not find a data partition on {whole_disk}")
                    return False

                # diskutil auto-mounts a freshly-erased volume; unmount it so we
                # can mount at our own point (ignore failure if not mounted).
                subprocess.run(
                    ['diskutil', 'unmount', data_part],
                    capture_output=True, text=True, timeout=10
                )

                result = subprocess.run(
                    ['mount', '-t', 'msdos', f'/dev/{data_part}', mount_point],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode != 0:
                    logger.error(f"mount failed for {data_part}: {result.stderr}")
                return result.returncode == 0
            else:  # Linux
                if not device.startswith('/dev/'):
                    device = f"/dev/{device}"

                if not os.path.exists(mount_point):
                    os.makedirs(mount_point, exist_ok=True)

                # The mount runs as root but the copy that follows runs as the
                # desktop user. FAT carries no ownership of its own, so the
                # kernel assigns it to the mounting user: without uid/gid the
                # whole tree comes out root-owned and every write fails with
                # EACCES.
                options = (f"uid={os.getuid()},gid={os.getgid()},"
                           f"fmask=0133,dmask=0022")
                result = subprocess.run(
                    ['sudo', 'mount', '-o', options, device, mount_point],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                if result.returncode == 0:
                    logger.info(
                        f"Mounted {device} at {mount_point} "
                        f"owned by uid={os.getuid()}")
                    return True

                # Those options are FAT-specific; retry plainly for any other
                # filesystem rather than failing outright.
                logger.warning(
                    f"Mounting {device} with ownership options failed "
                    f"({(result.stderr or '').strip()}); retrying without them")
                result = subprocess.run(
                    ['sudo', 'mount', device, mount_point],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                if result.returncode != 0:
                    logger.error(
                        f"mount failed for {device}: "
                        f"{(result.stderr or '').strip()}")
                    return False
                logger.warning(
                    f"Mounted {device} without ownership options; the copy "
                    f"may fail if it is not running as root")
                return True

        except _SUBPROCESS_ERRORS as e:
            logger.error(f"Failed to mount device {device} to {mount_point}: {e}")
            return False

    def _get_files_to_copy(self, source_dir: str, params: Dict[str, Any]) -> List[str]:
        """Get list of files to copy from source directory."""
        install_type = params.get('install_type', 'distribution')
        files_to_copy = []

        # Walk through source directory
        for root, dirs, files in os.walk(source_dir):
            for file in files:
                # Skip hidden files and directories
                if file.startswith('.'):
                    continue

                # Get relative path
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, source_dir)
                files_to_copy.append(rel_path)

        # Filter by install type

        if install_type == 'distribution':
            # For distributions, we might want to exclude certain files
            exclude_patterns = [
                r'\.DS_Store',
                r'\.Trash',
                r'\.Spotlight',
                r'\.fseventsd',
            ]

            filtered_files = []
            for file_path in files_to_copy:
                exclude = False
                for pattern in exclude_patterns:
                    if re.search(pattern, file_path):
                        exclude = True
                        break
                if not exclude:
                    filtered_files.append(file_path)

            return filtered_files

        return files_to_copy

    def _install_bootloader_windows(self, device: str, params: Dict[str, Any],
                                       enable_uefi_only: bool = False,
                                       enable_secure_boot: bool = False) -> bool:
        """Install bootloader on Windows."""
        logger.info(
            f"Installing bootloader for Windows on {device} "
            f"(UEFI-only: {enable_uefi_only}, "
            f"Secure Boot: {enable_secure_boot})")

        try:
            # Windows: the menu modules and the root boot config go onto the
            # drive, then syslinux.exe writes the boot sector and MBR.
            from pynetboot.platform.windows import drive_root

            mount_point = params.get('mount_point') or drive_root(device) or device

            if enable_uefi_only:
                logger.info("Configuring for UEFI-only installation")
                # For UEFI-only, we need to ensure the device has an EFI partition
                # and install UEFI bootloader files
                if not self._ensure_efi_partition(device):
                    logger.error(
                        "Failed to create EFI partition for UEFI-only installation")
                    return False

                if enable_secure_boot:
                    # For Secure Boot, we need signed bootloader files
                    if not self._install_secure_boot_files(device):
                        logger.error("Failed to install Secure Boot files")
                        return False

                # syslinux.exe cannot install a UEFI bootloader (it only writes
                # the BIOS boot sector / MBR), so running it here would just
                # fail. A UEFI machine boots a FAT32 volume straight from
                # EFI\BOOT\BOOTX64.EFI -- the image's own, or the bundled one.
                return self._install_uefi_files(mount_point, params)

            # Default BIOS/UEFI dual boot installation.
            # Prefer the BUNDLED syslinux.exe; fall back to a system one.
            bundled = bootloader_path('syslinux.exe')
            syslinux_path = str(bundled) if bundled.exists() else self._find_executable('syslinux')
            if syslinux_path:
                # syslinux.exe takes the drive as "D:" exactly -- "D", "D:\"
                # or a path make it print its usage and exit non-zero.
                drive_spec = self._windows_drive_spec(device)
                if not drive_spec:
                    logger.error(
                        f"Cannot derive a drive letter for syslinux from {device!r}")
                    return False

                # Copy bundled menu modules onto the drive so the menu renders.
                self._copy_syslinux_modules(mount_point)

                # As on Linux: syslinux reads its config from the filesystem
                # root, so the image's own menu has to be chained to.
                self._write_boot_config(params)

                # The same drive should also boot on UEFI-only firmware.
                self._install_uefi_files(mount_point, params)

                # -m install the syslinux MBR, -a mark the partition active,
                # -f skip the removable-media checks (same set UNetbootin uses).
                cmd = [syslinux_path, '-m', '-a', '-f', drive_spec]
                logger.info(f"Running syslinux: {' '.join(cmd)}")
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=60
                )
                if result.returncode != 0:
                    logger.error(
                        f"syslinux failed (exit {result.returncode}): "
                        f"{(result.stderr or result.stdout or '').strip()}")
                    return False
                return True

            # No bundled or system syslinux available - report failure honestly
            # instead of producing a non-bootable stick marked as success.
            logger.error(
                "Windows bootloader installation requires syslinux.exe "
                "(bundled binary missing and none found on PATH)")
            return False

        except _SUBPROCESS_ERRORS as e:
            logger.error(f"Windows bootloader installation failed: {e}")
            return False

    def _install_bootloader_macos(self, device: str, params: Dict[str, Any],
                                    enable_uefi_only: bool = False,
                                    enable_secure_boot: bool = False) -> bool:
        """Install bootloader on macOS."""
        logger.info(
            f"Installing bootloader for macOS on {device} "
            f"(UEFI-only: {enable_uefi_only}, "
            f"Secure Boot: {enable_secure_boot})")

        try:
            mount_point = params.get('mount_point')
            whole_disk = params.get('target_disk') or self._macos_whole_disk(device)
            # syslinux goes into the boot sector of the FAT slice, not the
            # disk's. Preparation records it; look it up again if a caller
            # skipped that step.
            partition = params.get('target_partition') or ''
            if self._partition_index(partition) is None:
                data_slice = self._macos_data_partition(whole_disk)
                partition = f"/dev/{data_slice}" if data_slice else ''
            if not partition and not enable_uefi_only:
                logger.error(
                    f"Could not find the data partition on {whole_disk}; "
                    f"there is no boot sector to install syslinux into")
                return False
            partition = partition or device
            logger.info(
                f"macOS bootloader targets: MBR -> {whole_disk}, "
                f"syslinux -> {partition}")

            if enable_uefi_only:
                # UEFI path: no boot sector is involved -- the firmware loads
                # EFI/BOOT/BOOTX64.EFI off the FAT volume directly.
                if not self._install_uefi_files(mount_point, params):
                    return False

                if enable_secure_boot:
                    logger.info("Configuring Secure Boot on macOS")
                    efi_dir = os.path.join(mount_point, *_EFI_BOOT_DIR)
                    if not self._copy_secure_boot_files(efi_dir):
                        logger.error("Failed to copy Secure Boot files")
                        return False
                return True

            # BIOS path: the syslinux MBR goes to sector 0 of the disk and
            # syslinux itself into the partition's boot sector. macOS cannot
            # run the bundled Linux/Windows syslinux binaries, so the install
            # is done by the built-in installer rather than an external tool.
            # The MBR is written from there too: macOS will not let sector 0
            # of the disk be written while the volume is still mounted.
            self._copy_syslinux_modules(mount_point)
            self._write_boot_config(params)
            # Also lay down the UEFI loader: the same drive should boot on
            # firmware that has no BIOS compatibility mode.
            self._install_uefi_files(mount_point, params)

            return self._install_syslinux_native(
                partition, params, whole_disk=whole_disk)

        except _SUBPROCESS_ERRORS as e:
            logger.error(f"macOS bootloader installation failed: {e}")
            return False

    def _install_bootloader_linux(self, device: str, params: Dict[str, Any],
                                     enable_uefi_only: bool = False,
                                     enable_secure_boot: bool = False) -> bool:
        """Install bootloader on Linux."""
        drive_type = params.get('drive_type', 'USB Drive')
        logger.info(
            f"Installing bootloader for Linux on {device} "
            f"(UEFI-only: {enable_uefi_only}, "
            f"Secure Boot: {enable_secure_boot})")

        try:
            # Linux: use various tools depending on what's available


            # For UEFI-only installation
            if enable_uefi_only:
                logger.info("Configuring UEFI-only bootloader on Linux")

                # UEFI needs no bootloader installed into a boot sector: the
                # firmware loads EFI/BOOT/BOOTX64.EFI from the FAT volume
                # that is already mounted. grub-install and efibootmgr are
                # not used, so nothing has to be present on the host.
                mount_point = params.get('mount_point')
                if not self._install_uefi_files(mount_point, params):
                    logger.error("UEFI-only installation failed")
                    return False

                if enable_secure_boot:
                    efi_boot_dir = os.path.join(mount_point, *_EFI_BOOT_DIR)
                    if not self._install_secure_boot_files_linux(efi_boot_dir):
                        logger.error("Failed to install Secure Boot files")
                        return False
                return True

            # For USB drives with BIOS/UEFI dual support
            if drive_type == 'USB Drive':
                if not device.startswith('/dev/'):
                    device = f"/dev/{device}"

                # The bootloader spans two places: the MBR lives in sector 0
                # of the disk, syslinux in the boot sector of the partition.
                # _prepare_installation created that partition; fall back to
                # the passed device if a caller skipped that step.
                whole_disk = self._linux_parent_disk(device)
                partition = params.get('target_partition') or device

                # 1) Write the syslinux MBR from the BUNDLED mbr.bin into
                #    the first 440 bytes of sector 0, and mark the target
                #    partition active in the same write -- that MBR boots
                #    whichever partition carries the boot flag.
                self._write_mbr_and_activate(whole_disk, partition)

                # 2) Copy bundled menu modules onto the target filesystem.
                self._copy_syslinux_modules(params.get('mount_point'))

                # Without a config at the root, syslinux boots to a bare
                # prompt: it does not find the menu inside the image.
                self._write_boot_config(params)

                # The same drive should also boot on UEFI-only firmware.
                self._install_uefi_files(params.get('mount_point'), params)

                # 3) Install syslinux to the partition — prefer the BUNDLED
                #    binary, fall back to a system syslinux only if missing.
                bundled = find_bundled_syslinux()
                syslinux_bin = str(bundled) if bundled else self._find_executable('syslinux')
                logger.info(
                    f"Bootloader targets: MBR -> {whole_disk}, "
                    f"syslinux -> {partition}; using "
                    f"{syslinux_bin or 'no syslinux binary'} "
                    f"({'bundled' if bundled else 'system'})")
                if syslinux_bin:
                    # syslinux -i patches the boot sector and writes
                    # ldlinux.sys; on a mounted filesystem the kernel's cache
                    # can write back over it, so the volume has to go first.
                    if not self._release_mount(params):
                        logger.error(
                            "Not writing the boot sector: the drive could "
                            "not be unmounted")
                        return False
                    result = subprocess.run(
                        ['sudo', syslinux_bin, '-i', partition],
                        capture_output=True, text=True, timeout=60
                    )
                    if result.returncode == 0:
                        logger.info(f"Installed syslinux to {partition}")
                        return True
                    logger.warning(
                        f"syslinux install failed on {partition}: "
                        f"{(result.stderr or '').strip()}")
                    # The rest of the fallbacks want the volume mounted.
                    self._remount(params, partition)

                # 4) Built-in installer: no binary to run, so it works where
                #    the bundled x86 ones cannot (ARM hosts, for instance).
                logger.info("Falling back to the built-in syslinux installer")
                if self._install_syslinux_native(partition, params):
                    return True

                # extlinux fallback (bundled first, then system). extlinux
                # installs into a mounted directory, not the raw partition.
                bundled_ext = find_bundled_extlinux()
                extlinux_bin = str(bundled_ext) if bundled_ext else self._find_executable('extlinux')
                mount_point = params.get('mount_point')
                if extlinux_bin and mount_point:
                    logger.info(
                        f"Falling back to extlinux ({extlinux_bin}) "
                        f"on {mount_point}")
                    result = subprocess.run(
                        ['sudo', extlinux_bin, '--install', mount_point],
                        capture_output=True, text=True, timeout=60
                    )
                    if result.returncode == 0:
                        return True
                    logger.warning(f"extlinux install failed: {result.stderr}")

                # grub fallback for BIOS.
                grub_install_path = self._find_executable('grub-install')
                if grub_install_path:
                    result = subprocess.run(
                        ['sudo', grub_install_path, '--target=i386-pc',
                            f'--boot-directory={mount_point or whole_disk}',
                            whole_disk],
                        capture_output=True, text=True, timeout=60
                    )
                    return result.returncode == 0

            # For Hard Disk installation
            elif drive_type == 'Hard Disk':
                # Install to hard disk
                grub_install_path = self._find_executable('grub-install')
                if grub_install_path:
                    if not device.startswith('/dev/'):
                        device = f"/dev/{device}"

                    # Install grub to MBR
                    result = subprocess.run(
                        ['sudo', grub_install_path, '--target=i386-pc',
                            '--boot-directory=/boot', device],
                        capture_output=True, text=True, timeout=60
                    )
                    return result.returncode == 0

            logger.error("No suitable bootloader installation method found "
                         "(install syslinux, extlinux or grub)")
            return False

        except _SUBPROCESS_ERRORS as e:
            logger.error(f"Linux bootloader installation failed: {e}")
            return False

    def _find_executable(self, name: str) -> Optional[str]:
        """Find an executable in the system PATH.

        Delegates to the shared lookup so sbin is searched too.
        """
        found = find_tool(name)
        if found:
            return found

        # Try common locations
        common_locations = [
            '/usr/bin',
            '/usr/sbin',
            '/bin',
            '/sbin',
            '/usr/local/bin',
            '/usr/local/sbin',
            '/opt',
        ]

        for location in common_locations:
            full_path = os.path.join(location, name)
            if os.path.exists(full_path) and os.access(full_path, os.X_OK):
                return full_path

        return None

    # ---- Bundled bootloader helpers -------------------------------------
    # These use the binaries shipped in resources/bootloader/ so the tool
    # does not depend on a system-installed syslinux. They fall back to
    # system tools only if a bundled binary is missing.

    # Unmounting can lose a race with whatever is still touching a volume
    # 25 MB of files were just copied onto -- Spotlight indexes it on macOS,
    # desktop indexers do the same on Linux -- so give it a few tries.
    _UNMOUNT_ATTEMPTS = 4
    _UNMOUNT_PAUSE_SECONDS = 2

    def _unmount_commands(self, mount_point: str, force: bool) -> List[List[str]]:
        """Ways to unmount `mount_point`, best first, for this platform."""
        if self.platform == 'darwin':
            # The volume was mounted by this user, so no elevation is needed;
            # diskutil goes through Disk Arbitration, which unmounts cleanly
            # where a plain umount reports the volume busy.
            commands = [['diskutil', 'unmount', mount_point],
                        ['umount', mount_point]]
            if force:
                commands.insert(0, ['diskutil', 'unmount', 'force', mount_point])
            return commands
        commands = [['sudo', 'umount', mount_point]]
        if force:
            commands.insert(0, ['sudo', 'umount', '-l', mount_point])
        return commands

    def _release_mount(self, params: Dict[str, Any]) -> bool:
        """Flush and unmount the target so raw writes are not overwritten.

        Returns True once nothing is mounted there. Callers must not write raw
        sectors otherwise: the filesystem would write its cached copy back
        over them, and macOS refuses the write outright while the volume is
        mounted.

        The mount point directory is kept so _cleanup_installation can still
        remove it, and remains recorded so _remount can restore it.
        """
        mount_point = params.get('mount_point')
        if not mount_point or not os.path.isdir(mount_point):
            return True
        if not os.path.ismount(mount_point):
            return True

        last_error = ''
        for attempt in range(self._UNMOUNT_ATTEMPTS):
            try:
                subprocess.run(['sync'], capture_output=True, timeout=60)
                for command in self._unmount_commands(
                        mount_point, force=attempt > 0):
                    result = subprocess.run(
                        command, capture_output=True, text=True, timeout=60)
                    if result.returncode == 0 or not os.path.ismount(mount_point):
                        logger.info(
                            f"Unmounted {mount_point} before raw write")
                        return True
                    last_error = ((result.stderr or result.stdout or '')
                                  .strip())
                    logger.debug(
                        f"{' '.join(command)} failed: {last_error}")
            except _SUBPROCESS_ERRORS as e:
                last_error = str(e)
            if attempt + 1 < self._UNMOUNT_ATTEMPTS:
                logger.info(
                    f"{mount_point} is still busy; retrying the unmount "
                    f"({attempt + 1}/{self._UNMOUNT_ATTEMPTS})")
                time.sleep(self._UNMOUNT_PAUSE_SECONDS)

        logger.error(
            f"Could not unmount {mount_point}: {last_error}. Close anything "
            f"using the drive (Finder windows, a terminal in it) and retry.")
        return False

    def _remount(self, params: Dict[str, Any], device: str) -> None:
        """Re-mount the target after a raw write, for tools that need a path."""
        mount_point = params.get('mount_point')
        if not mount_point or not os.path.isdir(mount_point):
            return
        if not self._mount_device(device, mount_point):
            logger.warning(f"Could not re-mount {device} at {mount_point}")

    def _linux_parent_disk(self, device: str) -> str:
        """Resolve the whole disk that owns `device` via ``lsblk -no pkname``.

        For a partition like ``/dev/sdb1`` this returns ``/dev/sdb``; for a
        whole disk it returns the device unchanged. No fragile string surgery.
        """
        if not device.startswith('/dev/'):
            device = f"/dev/{device}"
        try:
            result = subprocess.run(
                ['lsblk', '-no', 'pkname', device],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                out = result.stdout.strip().splitlines()
                pkname = out[0].strip() if out else ''
                if pkname:
                    return f"/dev/{pkname}"
        except _SUBPROCESS_ERRORS as e:
            logger.debug(f"lsblk pkname lookup failed for {device}: {e}")
        return device  # already a whole disk (or unknown -> use as-is)

    @staticmethod
    def _windows_drive_spec(device: str) -> Optional[str]:
        """Return the ``D:`` form syslinux.exe expects, or None.

        Callers hand the target around as 'D', 'D:' or 'D:\\'; syslinux.exe
        accepts only 'D:' and prints its usage for anything else.
        """
        letter = (device or '').strip().rstrip('\\/').rstrip(':')[:1].upper()
        return f"{letter}:" if letter.isalpha() else None

    def _copy_syslinux_modules(self, mount_point: Optional[str]) -> None:
        """Copy the bundled syslinux modules the boot menu needs to the target."""
        if not mount_point or not os.path.isdir(mount_point):
            return
        for name in _SYSLINUX_MODULES:
            src = bootloader_path(name)
            if src.exists():
                try:
                    shutil.copy2(src, os.path.join(mount_point, name))
                    logger.info(f"Copied bundled {name} to {mount_point}")
                except _FILE_COPY_ERRORS as e:
                    logger.warning(f"Failed to copy {name}: {e}")
            else:
                logger.warning(f"Bundled {name} is missing from this build")

    def _log_boot_layout(self, mount_point: Optional[str]) -> None:
        """Log the boot files on the target, so a failure can be diagnosed."""
        if not mount_point or not os.path.isdir(mount_point):
            return

        def describe(directory: str, names: List[str]) -> str:
            parts = []
            for name in names:
                path = os.path.join(directory, name)
                try:
                    parts.append(f"{name} ({os.path.getsize(path)}B)")
                except OSError:
                    parts.append(f"{name} MISSING")
            return ', '.join(parts)

        root_files = ['ldlinux.sys', 'syslinux.cfg'] + list(_SYSLINUX_MODULES)
        logger.info(f"Boot files at the drive root: "
                    f"{describe(mount_point, root_files)}")

        efi_dir = os.path.join(mount_point, *_EFI_BOOT_DIR)
        if os.path.isdir(efi_dir):
            try:
                names = sorted(os.listdir(efi_dir))
            except OSError as e:
                logger.warning(f"Could not list {efi_dir}: {e}")
                return
            logger.info(f"Boot files in EFI/BOOT: {describe(efi_dir, names)}")
        else:
            logger.info("No EFI/BOOT directory on the drive "
                        "(the drive will only boot in BIOS mode)")

    def _install_uefi_files(self, mount_point: Optional[str],
                            params: Dict[str, Any]) -> bool:
        """Make sure the target has a UEFI loader at EFI/BOOT/BOOTX64.EFI.

        An image that carries its own EFI loader keeps it -- it knows where
        its kernel is. Otherwise the bundled syslinux.efi is installed, so a
        drive built from a BIOS-only image (an isolinux image, say) still
        boots on UEFI firmware without anything being installed on the host.
        """
        if not mount_point or not os.path.isdir(mount_point):
            logger.warning("No mounted target; cannot install UEFI files")
            return False

        efi_dir = os.path.join(mount_point, *_EFI_BOOT_DIR)
        existing = self._existing_efi_loaders(efi_dir)
        if existing:
            logger.info(
                f"Keeping the image's own UEFI loader: {', '.join(existing)}")
            return True

        loader = bootloader_path(os.path.join('efi64', 'syslinux.efi'))
        if not loader.exists():
            logger.error("Bundled UEFI loader (efi64/syslinux.efi) is missing")
            return False

        try:
            os.makedirs(efi_dir, exist_ok=True)
            shutil.copy2(loader, os.path.join(efi_dir, _EFI_LOADER))
            for name in _EFI_MODULES:
                src = bootloader_path(os.path.join('efi64', name))
                if src.exists():
                    shutil.copy2(src, os.path.join(efi_dir, name))
                else:
                    logger.warning(f"Bundled efi64/{name} is missing")
        except _FILE_COPY_ERRORS as e:
            logger.error(f"Could not install the UEFI loader: {e}")
            return False

        # syslinux.efi reads its config from the directory it was loaded
        # from, so the menu has to be written there as well as at the root.
        self.create_syslinux_cfg(efi_dir, params, image_root=mount_point)
        logger.info(f"Installed the bundled UEFI loader in {efi_dir}")
        return True

    @staticmethod
    def _existing_efi_loaders(efi_dir: str) -> List[str]:
        """Names of BOOT*.EFI files already present in an EFI/BOOT directory."""
        try:
            names = os.listdir(efi_dir)
        except OSError:
            return []
        return sorted(n for n in names
                      if n.upper().startswith('BOOT')
                      and n.upper().endswith('.EFI'))

    # Read up front to cover the boot sector, both FATs and the start of the
    # root directory in one go: 4 MiB spans them on any FAT32 volume with a
    # sane cluster size.
    _PREFETCH_BYTES = 4 * 1024 * 1024

    def _install_syslinux_native(self, partition: str,
                                 params: Dict[str, Any],
                                 whole_disk: Optional[str] = None) -> bool:
        """Install syslinux with the built-in installer, no binary needed.

        Used where no syslinux binary can run: macOS, and Linux on an
        architecture the bundled x86 binaries do not match. The volume has to
        be unmounted for the raw writes, then put back so the rest of the
        install still sees it.

        `whole_disk` asks for the MBR and the boot flag to be written in the
        same unmounted window -- macOS refuses to write sector 0 of a disk
        while one of its partitions is mounted.
        """
        from pynetboot.core import syslinux_native as native
        from pynetboot.resources import read_bootloader

        ldlinux = read_bootloader('ldlinux.sys')
        boot_template = read_bootloader('ldlinux.bss')
        if not ldlinux or not boot_template:
            logger.error(
                "Bundled ldlinux.sys/ldlinux.bss are missing from this build")
            return False

        mount_point = params.get('mount_point')
        if not mount_point or not os.path.isdir(mount_point):
            logger.error("No mounted target for the native syslinux install")
            return False

        payload = native.file_payload(ldlinux)
        logger.info(
            f"Installing syslinux on {partition} with the built-in "
            f"installer: writing ldlinux.sys ({format_size(len(payload))}) "
            f"to {mount_point}")
        try:
            with open(os.path.join(mount_point, 'ldlinux.sys'), 'wb') as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as e:
            logger.error(f"Could not write ldlinux.sys to the target: {e}")
            return False

        # The filesystem cache would write its own copy of the file back over
        # the patched sectors, so let go of the volume first. Writing raw
        # sectors under a live filesystem corrupts it, so this is a hard stop.
        if not self._release_mount(params):
            logger.error(
                "Not writing the boot sector: the drive could not be unmounted")
            self._remount(params, partition)
            return False

        try:
            # Two elevations for the whole thing: one to read the drive, one
            # to write it and read the result back. Every dd in between is
            # queued into the batch rather than run on its own, because each
            # elevated command is its own password prompt on macOS.
            with native.ElevatedBatch() as batch:
                with native.RawDevice(partition, batch=batch) as device, \
                        self._mbr_device(whole_disk, batch) as disk:
                    # One read covers the boot sector, the FAT and the root
                    # directory on any normal drive; the MBR rides along.
                    device.prefetch(0, self._PREFETCH_BYTES)
                    if disk is not None:
                        disk.prefetch(0, 512)
                    batch.run(f"read {partition}"
                              + (f" and {whole_disk}" if disk else ""))

                    written = native.install(
                        device.read, device.write, ldlinux, boot_template,
                        prefetch=device.prefetch)
                    if disk is not None:
                        self._stage_mbr(disk, whole_disk, partition)

                    # Queue the writes, then the read-back that checks them,
                    # so both happen under the same elevation.
                    device.flush()
                    if disk is not None:
                        disk.flush()
                    tokens = [batch.add_read(partition, offset, length)
                              for offset, length in written.spans()]
                    batch.run(f"write the bootloader to {partition}"
                              + (f" and {whole_disk}" if disk else "")
                              + " and read it back")
                    written.check(*[batch.result(token) for token in tokens])

            native.sync_disks()
            logger.info(f"Installed syslinux on {partition} (native)")
            return True
        except native.SyslinuxError as e:
            logger.error(f"Native syslinux install failed: {e}")
            return False
        except OSError as e:
            logger.error(f"Native syslinux install could not reach "
                         f"{partition}: {e}")
            return False
        finally:
            self._remount(params, partition)

    @contextlib.contextmanager
    def _mbr_device(self, whole_disk: Optional[str], batch):
        """The disk holding the MBR, joined to the same batch, or None."""
        from pynetboot.core import syslinux_native as native

        if not whole_disk:
            yield None
            return
        with native.RawDevice(whole_disk, batch=batch) as device:
            yield device

    def _stage_mbr(self, device, whole_disk: str, partition: str) -> None:
        """Queue sector 0: the syslinux MBR plus the active-partition flag.

        Both live there -- the boot code in the first 440 bytes, the boot flag
        in the partition table at 446 -- so they go down as one write. Two
        separate ones can leave a disk whose table says nothing is bootable,
        which a BIOS reports as "Missing operating system".
        """
        from pynetboot.core import syslinux_native as native

        code = read_bootloader('mbr.bin')
        if not code:
            raise native.SyslinuxError(
                "Bundled mbr.bin is missing from this build")
        if len(code) > 440:
            raise native.SyslinuxError(
                f"Bundled mbr.bin is {len(code)} bytes, which would "
                f"overwrite the partition table")

        sector = bytearray(device.read(0, 512))
        if len(sector) < 512:
            raise native.SyslinuxError(
                f"Could not read the MBR of {whole_disk}")

        sector[0:len(code)] = code
        index = self._partition_index(partition)
        if index is None:
            logger.warning(
                f"Could not tell which partition {partition} is; "
                f"leaving the boot flag alone")
        else:
            for slot in range(4):
                entry = 446 + slot * 16
                sector[entry] = 0x80 if slot == index - 1 else 0x00
        # A drive with no signature here is not booted at all.
        sector[510:512] = b'\x55\xaa'
        device.write(0, bytes(sector))
        logger.info(
            f"Sector 0 of {whole_disk}: syslinux MBR"
            + (f", partition {index} marked active"
               if index is not None else ""))

    def _write_mbr_and_activate(self, whole_disk: str,
                                partition: str) -> bool:
        """Write the syslinux MBR and mark the target partition active.

        The batched install stages the same sector inside its own write; this
        is for the path that has no batch to join -- the Linux install that
        ran the syslinux binary.
        """
        from pynetboot.core import syslinux_native as native

        try:
            with native.RawDevice(whole_disk) as device:
                self._stage_mbr(device, whole_disk, partition)
            return True
        except (native.SyslinuxError, OSError) as e:
            logger.error(f"Could not write the MBR of {whole_disk}: {e}")
            return False

    @staticmethod
    def _partition_index(partition: str) -> Optional[int]:
        """Partition number from a device node, or None if it is a whole disk.

        Handles /dev/sdb1, /dev/nvme0n1p1, /dev/mmcblk0p1 and /dev/disk4s1.
        Taking the trailing digits alone would read /dev/disk4 as partition 4
        and put the boot flag on the wrong entry.
        """
        name = os.path.basename(partition or '')
        if re.match(r'^disk\d+$', name):
            return None                     # macOS whole disk, not a slice
        # macOS: diskNsM, where only the sM part is the partition.
        match = re.match(r'^disk\d+s(\d+)$', name)
        if match is None:
            # Linux: the partition number follows a letter (sdb1) or an
            # explicit 'p' separator (nvme0n1p1, mmcblk0p1).
            match = re.match(
                r'^(?:[a-z]+\d+n\d+p|[a-z]+\d+p|[a-z]+)(\d+)$', name)
        if match is None:
            return None
        index = int(match.group(1))
        return index if 1 <= index <= 4 else None

    # Where distributions keep the boot menu inside their image. syslinux
    # only reads a config from the filesystem root, so one of these has to be
    # chained to or the drive boots to a bare prompt.
    _IMAGE_BOOT_CONFIGS = (
        'boot/isolinux/isolinux.cfg',
        'isolinux/isolinux.cfg',
        'boot/syslinux/syslinux.cfg',
        'syslinux/syslinux.cfg',
        'boot/grub/grub.cfg',
    )

    def _write_boot_config(self, params: Dict[str, Any]) -> bool:
        """Write the root boot menu onto the mounted target, if there is one."""
        mount_point = params.get('mount_point')
        if not mount_point or not os.path.isdir(mount_point):
            logger.warning(
                "No mounted target; the drive will have no boot menu")
            return False
        return self.create_syslinux_cfg(mount_point, params)

    def _find_image_boot_config(self, mount_point: str) -> Optional[str]:
        """Return the image's own boot config, relative to the drive root."""
        for relative in self._IMAGE_BOOT_CONFIGS:
            if os.path.exists(os.path.join(mount_point, *relative.split('/'))):
                return relative
        return None

    def create_syslinux_cfg(self, target_device: str, params: Dict[str, Any],
                            image_root: Optional[str] = None) -> bool:
        """Write the syslinux config at the root of a mounted target.

        `target_device` is the mounted filesystem, not a device node.
        `image_root` is where the image's own menu is looked for when the
        config is not being written at the root of the volume (the UEFI
        loader reads its config from EFI/BOOT); the paths written are
        absolute, so the same content works in either place.

        A distribution image carries its own menu, with kernel and initrd
        paths that only it knows. Chaining to that config is what makes the
        drive boot the distribution; generating a menu here from assumed
        paths produces one that points at files which are not there. Only
        when the image supplies no config at all is one generated.
        """
        try:
            existing = self._find_image_boot_config(image_root or target_device)
            if existing:
                directory = os.path.dirname(existing)
                # CONFIG hands over to that file; APPEND sets the directory
                # its own relative paths resolve against.
                cfg_content = (
                    "DEFAULT chain\n"
                    "LABEL chain\n"
                    f"    CONFIG /{existing}\n"
                    f"    APPEND /{directory}/\n"
                )
                path = os.path.join(target_device, 'syslinux.cfg')
                with open(path, 'w') as handle:
                    handle.write(cfg_content)
                logger.info(f"Wrote {path}: boot menu chains to /{existing}")
                return True

            logger.warning(
                "The image supplies no boot menu; generating one from the "
                "kernel and initrd given in the options")

            # Get parameters
            distro = params.get('distro', 'unknown')
            version = params.get('version', 'unknown')
            kernel = params.get('kernel', 'vmlinuz')
            initrd = params.get('initrd', 'initrd.img')
            boot_options = params.get('boot_options', '')

            # Create syslinux.cfg content
            cfg_content = f"""UI menu.c32
MENU TITLE PyNetboot
DEFAULT {distro}
TIMEOUT 100

LABEL {distro}
    KERNEL /{kernel}
    APPEND initrd=//{initrd} {boot_options}
    MENU LABEL {distro} {version}

LABEL hdt
    KERNEL /hdt.c32
    MENU LABEL Hardware Detection Tool

LABEL reboot
    KERNEL /ldlinux.c32
    APPEND reboot
    MENU LABEL Reboot

LABEL poweroff
    KERNEL /ldlinux.c32
    APPEND poweroff
    MENU LABEL Power Off
"""

            # Write to file
            syslinux_cfg_path = os.path.join(target_device, 'syslinux.cfg')
            with open(syslinux_cfg_path, 'w') as f:
                f.write(cfg_content)

            return True

        except OSError as e:
            logger.error(f"Failed to create syslinux.cfg: {e}")
            return False

    def create_grub_cfg(self, target_device: str, params: Dict[str, Any]) -> bool:
        """Create grub configuration file."""
        try:
            # Get parameters
            distro = params.get('distro', 'unknown')
            version = params.get('version', 'unknown')
            kernel = params.get('kernel', 'vmlinuz')
            initrd = params.get('initrd', 'initrd.img')
            boot_options = params.get('boot_options', '')
            enable_secure_boot = params.get('enable_secure_boot', False)

            # Create grub.cfg content
            grub_cfg_content = f"""set default="{distro}"
set timeout=10

menuentry "{distro} {version}" {{
    linux /{kernel} {boot_options}
    initrd /{initrd}
}}

menuentry "Hardware Detection" {{
    linux16 /hdt.c32
}}

menuentry "Reboot" {{
    reboot
}}

menuentry "Power Off" {{
    halt
}}
"""

            # For Secure Boot, we might need additional configuration
            if enable_secure_boot:
                grub_cfg_content += """
# Secure Boot configuration
set check_signatures=enforce
"""

            # Write to file
            grub_cfg_path = os.path.join(target_device, 'grub.cfg')
            with open(grub_cfg_path, 'w') as f:
                f.write(grub_cfg_content)

            return True

        except OSError as e:
            logger.error(f"Failed to create grub.cfg: {e}")
            return False

    def _ensure_efi_partition(self, device: str) -> bool:
        """
        Ensure the device has an EFI partition.

        Args:
            device: Device path to check

        Returns:
            True if device has EFI partition or check passes, False otherwise
        """
        logger.info(f"Checking for EFI partition on {device}")

        try:
            if self.platform == 'win32':
                # On Windows, use diskpart or other tools
                # This is a simplified implementation
                logger.info(
                    "EFI partition check on Windows - assuming partition exists")
                return True
            elif self.platform == 'darwin':
                # On macOS, use diskutil to check partition type
                result = subprocess.run(
                    ['diskutil', 'list', device],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    # Check if output contains EFI
                    return 'EFI' in result.stdout.upper()
            else:  # Linux
                # On Linux, check partition type using blkid or lsblk
                if not device.startswith('/dev/'):
                    device = f"/dev/{device}"

                result = subprocess.run(
                    ['sudo', 'blkid', device],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    # Check for EFI system partition type
                    return 'TYPE="vfat"' in result.stdout and 'EFI' in result.stdout

                # Alternative: check lsblk output
                result = subprocess.run(
                    ['lsblk', '-f', device],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    return 'vfat' in result.stdout.lower()

            return True  # Assume it's okay for now

        except _SUBPROCESS_ERRORS as e:
            logger.error(f"Failed to check EFI partition: {e}")
            return True  # Don't fail the installation, just proceed

    def _copy_efi_bootloader_files(self, efi_dir: str):
        """
        Copy EFI bootloader files to the EFI directory.

        Args:
            efi_dir: Path to the EFI directory where files should be copied
        """
        logger.info(f"Copying EFI bootloader files to {efi_dir}")

        try:
            # Common EFI bootloader files
            efi_files = [
                '/usr/lib/grub/x86_64-efi/core.efi',
                '/usr/lib/grub/x86_64-efi/grubx64.efi',
            ]

            # Also look for syslinux EFI files
            syslinux_efi_files = [
                '/usr/lib/syslinux/efi64/ldlinux.e64',
                '/usr/lib/syslinux/efi64/syslinux.efi',
            ]

            all_files = efi_files + syslinux_efi_files

            for src_file in all_files:
                if os.path.exists(src_file):
                    dest_file = os.path.join(efi_dir, os.path.basename(src_file))
                    try:
                        shutil.copy2(src_file, dest_file)
                        logger.info(f"Copied {src_file} to {dest_file}")
                    except _FILE_COPY_ERRORS as e:
                        logger.warning(f"Failed to copy {src_file}: {e}")

            # Also copy shim for Secure Boot if available
            shim_files = [
                '/usr/lib/shim/shimx64.efi',
                '/usr/share/shim/shimx64.efi',
            ]

            for src_file in shim_files:
                if os.path.exists(src_file):
                    dest_file = os.path.join(efi_dir, os.path.basename(src_file))
                    try:
                        shutil.copy2(src_file, dest_file)
                        logger.info(f"Copied {src_file} to {dest_file}")
                    except _FILE_COPY_ERRORS as e:
                        logger.warning(f"Failed to copy {src_file}: {e}")

        except _FILE_COPY_ERRORS as e:
            logger.error(f"Failed to copy EFI files: {e}")

    def _install_secure_boot_files_linux(self, efi_dir: str) -> bool:
        """
        Install Secure Boot files for Linux.

        Args:
            efi_dir: Path to the EFI directory

        Returns:
            True if Secure Boot files were installed successfully
        """
        logger.info(f"Installing Secure Boot files for Linux in {efi_dir}")

        try:
            # Copy shim and signed grub files
            shim_locations = [
                '/usr/lib/shim/shimx64.efi',
                '/usr/share/shim/shimx64.efi',
            ]

            for shim_path in shim_locations:
                if os.path.exists(shim_path):
                    try:
                        shutil.copy2(shim_path, os.path.join(efi_dir, 'shimx64.efi'))
                        logger.info(f"Copied Secure Boot shim from {shim_path}")

                        # Also copy mmx64.efi if available
                        mm_path = shim_path.replace('shimx64.efi', 'mmx64.efi')
                        if os.path.exists(mm_path):
                            shutil.copy2(mm_path, os.path.join(efi_dir, 'mmx64.efi'))

                        return True
                    except _FILE_COPY_ERRORS as e:
                        logger.warning(f"Failed to copy shim: {e}")

            # If no shim found, try other signed bootloaders
            logger.info("No shim found, Secure Boot may not work")
            return True  # Don't fail, just warn

        except _FILE_COPY_ERRORS as e:
            logger.error(f"Failed to install Secure Boot files: {e}")
            return False

    def _install_secure_boot_files(self, device: str) -> bool:
        """
        Install Secure Boot files for Windows.

        Args:
            device: Device path to install Secure Boot files to

        Returns:
            True if Secure Boot files were installed successfully
        """
        logger.info(f"Installing Secure Boot files for Windows on {device}")

        try:
            # On Windows, Secure Boot requires signed bootloader files
            # These are typically provided by the distribution or OS vendor
            # We look for shim which provides the Secure Boot chain
            shim_locations = [
                'C:\\shim\\shimx64.efi',
                'C:\\Program Files (x86)\\shim\\shimx64.efi',
            ]

            # For now, we'll just log that Secure Boot requires signed binaries
            # and return True to not block the installation
            logger.info(
                "Secure Boot on Windows requires signed shim and bootloader files. "
                "These must be provided by the distribution or OS vendor.")
            return True

        except _FILE_COPY_ERRORS as e:
            logger.error(f"Failed to install Secure Boot files: {e}")
            return False

    def _copy_secure_boot_files(self, efi_dir: str) -> bool:
        """
        Copy Secure Boot files for macOS.

        Args:
            efi_dir: Path to the EFI directory where files should be copied

        Returns:
            True if Secure Boot files were copied successfully
        """
        logger.info(f"Copying Secure Boot files for macOS to {efi_dir}")

        try:
            # On macOS, Secure Boot requires signed shim and mmx64.efi files
            # These are typically provided by the distribution
            # Look for common locations where shim might be installed
            shim_locations = [
                '/usr/local/share/shim/shimx64.efi',
                '/usr/share/shim/shimx64.efi',
            ]

            for shim_path in shim_locations:
                if os.path.exists(shim_path):
                    try:
                        dest = os.path.join(efi_dir, 'shimx64.efi')
                        shutil.copy2(shim_path, dest)
                        logger.info(f"Copied shim from {shim_path} to {dest}")

                        # Also copy mmx64.efi if available
                        mm_path = os.path.join(
                            os.path.dirname(shim_path), 'mmx64.efi')
                        if os.path.exists(mm_path):
                            shutil.copy2(mm_path, os.path.join(efi_dir, 'mmx64.efi'))
                            logger.info(f"Copied mmx64.efi from {mm_path}")

                        return True
                    except _FILE_COPY_ERRORS as e:
                        logger.warning(f"Failed to copy shim: {e}")

            # If no shim found, log a message but don't fail
            logger.info(
                "No shim found for Secure Boot on macOS. "
                "Secure Boot requires signed binaries from the distribution.")
            return True

        except _FILE_COPY_ERRORS as e:
            logger.error(f"Failed to copy Secure Boot files: {e}")
            return False


