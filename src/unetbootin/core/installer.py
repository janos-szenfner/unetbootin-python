"""
USB installation functionality for UNetbootin.
"""

import os
import re
import sys
import time
import logging
import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List, Tuple

from PySide6.QtCore import QObject, Signal, Slot, QThread, QProcess

logger = logging.getLogger(__name__)


class InstallWorker(QThread):
    """Worker thread for installation operations."""
    
    progress_updated = Signal(int)
    finished = Signal(bool, str)
    
    def __init__(self, source_dir: str, target_device: str, 
                 install_params: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.source_dir = source_dir
        self.target_device = target_device
        self.install_params = install_params or {}
        self.stop_requested = False
    
    def run(self):
        """Perform the installation."""
        try:
            installer = USBInstaller()
            success, message = installer.install_sync(
                self.source_dir,
                self.target_device,
                self.install_params,
                self.on_progress_update
            )
            self.finished.emit(success, message)
        except Exception as e:
            logger.error(f"Installation failed: {e}")
            self.finished.emit(False, str(e))
    
    def stop(self):
        """Request stop."""
        self.stop_requested = True
    
    def on_progress_update(self, percent: int):
        """Handle progress update."""
        if not self.stop_requested:
            self.progress_updated.emit(percent)


class USBInstaller(QObject):
    """Handles USB installation process."""
    
    progress_updated = Signal(int)
    installation_complete = Signal(bool, str)
    
    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.worker = None
        self.platform = sys.platform
    
    def install(self, source_dir: str, target_device: str,
                install_params: Optional[Dict[str, Any]] = None,
                progress_callback: Optional[Callable[[int], None]] = None):
        """Install to USB device."""
        logger.info(f"Installing from {source_dir} to {target_device}")
        
        # Create worker thread
        self.worker = InstallWorker(source_dir, target_device, install_params)
        
        if progress_callback:
            self.worker.progress_updated.connect(progress_callback)
        self.worker.progress_updated.connect(self.progress_updated.emit)
        self.worker.finished.connect(self.installation_complete.emit)
        
        self.worker.start()
    
    def install_sync(self, source_dir: str, target_device: str,
                    install_params: Optional[Dict[str, Any]] = None,
                    progress_callback: Optional[Callable[[int], None]] = None) -> Tuple[bool, str]:
        """Synchronously install to USB device."""
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
                nonlocal total_progress, current_stage
                stage_name, stage_weight = stages[current_stage]
                stage_progress = int(percent_in_stage * stage_weight / 100)
                total_progress = sum(
                    stage_weight for stage_name, stage_weight in stages[:current_stage]
                ) + stage_progress
                if progress_callback:
                    progress_callback(min(total_progress, 99))
            
            # Stage 1: Prepare
            update_progress(0)
            if not self._prepare_installation(source_dir, target_device, params):
                return False, "Preparation failed"
            update_progress(100)
            current_stage += 1
            
            # Stage 2: Copy files
            update_progress(0)
            if not self._copy_files_to_device(source_dir, target_device, params, update_progress):
                return False, "File copying failed"
            update_progress(100)
            current_stage += 1
            
            # Stage 3: Install bootloader
            update_progress(0)
            if not self._install_bootloader(target_device, params, update_progress):
                return False, "Bootloader installation failed"
            update_progress(100)
            current_stage += 1
            
            # Stage 4: Clean up
            update_progress(0)
            self._cleanup_installation(source_dir, target_device, params)
            update_progress(100)
            
            if progress_callback:
                progress_callback(100)
            
            return True, "Installation completed successfully"
            
        except Exception as e:
            logger.error(f"Installation failed: {e}")
            return False, str(e)
    
    def _prepare_installation(self, source_dir: str, target_device: str,
                              params: Dict[str, Any]) -> bool:
        """Prepare for installation."""
        logger.info("Preparing installation")
        
        try:
            # Check if device exists and is writable
            if not self._validate_target_device(target_device):
                return False
            
            # Check if device is mounted and unmount if necessary
            if self._is_device_mounted(target_device):
                if not self._unmount_device(target_device):
                    logger.error(f"Failed to unmount {target_device}")
                    return False
            
            # Format the device with FAT32 filesystem
            logger.info(f"Formatting {target_device} with FAT32")
            if not self._format_device(target_device):
                logger.error(f"Failed to format {target_device}")
                return False
            
            # Create temporary working directory
            params['temp_dir'] = tempfile.mkdtemp(prefix='unetbootin_install_')
            
            # Create and mount the device to a temporary mount point
            mount_point = tempfile.mkdtemp(prefix='unetbootin_mount_')
            logger.info(f"Mounting {target_device} to {mount_point}")
            if not self._mount_device(target_device, mount_point):
                logger.error(f"Failed to mount {target_device}")
                # Clean up temp dir
                shutil.rmtree(params['temp_dir'], ignore_errors=True)
                shutil.rmtree(mount_point, ignore_errors=True)
                return False
            
            # Store mount point in params for use during file copying
            params['mount_point'] = mount_point
            
            return True
            
        except Exception as e:
            logger.error(f"Preparation failed: {e}")
            return False
    
    def _copy_files_to_device(self, source_dir: str, target_device: str,
                              params: Dict[str, Any],
                              progress_callback: Optional[Callable[[int], None]] = None) -> bool:
        """Copy files from source to target device."""
        # Use mount point if available (for formatted devices), otherwise fall back to raw device
        actual_target = params.get('mount_point', target_device)
        logger.info(f"Copying files from {source_dir} to {actual_target}")
        
        try:
            # Get list of files to copy
            files_to_copy = self._get_files_to_copy(source_dir, params)
            total_files = len(files_to_copy)
            copied_files = 0
            failed_files = []

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

                except Exception as e:
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

            return True

        except Exception as e:
            logger.error(f"File copying failed: {e}")
            return False
    
    def _install_bootloader(self, target_device: str,
                            params: Dict[str, Any],
                            progress_callback: Optional[Callable[[int], None]] = None) -> bool:
        """Install bootloader to target device."""
        logger.info(f"Installing bootloader to {target_device}")
        
        try:
            install_type = params.get('install_type', 'distribution')
            drive_type = params.get('drive_type', 'USB Drive')
            
            if self.platform == 'win32':
                return self._install_bootloader_windows(target_device, params)
            elif self.platform == 'darwin':
                return self._install_bootloader_macos(target_device, params)
            else:  # Linux and other Unix
                return self._install_bootloader_linux(target_device, params)
            
        except Exception as e:
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
                elif self.platform == 'darwin':
                    # Find what's mounted at this point and unmount it
                    result = subprocess.run(
                        ['mount'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        for line in result.stdout.split('\n'):
                            if mount_point in line:
                                parts = line.strip().split()
                                if len(parts) >= 1:
                                    subprocess.run(
                                        ['umount', mount_point],
                                        capture_output=True,
                                        timeout=5
                                    )
                                break
                else:  # Linux
                    subprocess.run(
                        ['sudo', 'umount', mount_point],
                        capture_output=True,
                        timeout=5
                    )
                
                # Remove the mount point directory
                shutil.rmtree(mount_point, ignore_errors=True)
            
            # Remove temporary directory
            temp_dir = params.get('temp_dir')
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            
            # Sync filesystem
            if self.platform != 'win32':
                subprocess.run(['sync'], timeout=10)
            
        except Exception as e:
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
        except Exception as e:
            logger.error(f"Device validation failed: {e}")
            return False
    
    def _is_device_mounted(self, device: str) -> bool:
        """Check if device is mounted."""
        try:
            if self.platform == 'win32':
                # On Windows, drives are always "mounted"
                return True
            elif self.platform == 'darwin':
                result = subprocess.run(
                    ['diskutil', 'list'],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    return device in result.stdout
            else:  # Linux
                result = subprocess.run(
                    ['mount'],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    return device in result.stdout
        except Exception:
            pass
        
        return False
    
    def _unmount_device(self, device: str) -> bool:
        """Unmount device."""
        try:
            if self.platform == 'win32':
                # Windows doesn't need unmounting for this purpose
                return True
            elif self.platform == 'darwin':
                # macOS: find the disk identifier for the device
                result = subprocess.run(
                    ['diskutil', 'list'],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    # Parse to find the correct disk identifier
                    # This is simplified
                    disk_identifier = device
                    result = subprocess.run(
                        ['diskutil', 'unmount', disk_identifier],
                        capture_output=True, text=True, timeout=10
                    )
                    return result.returncode == 0
            else:  # Linux
                if not device.startswith('/dev/'):
                    device = f"/dev/{device}"
                
                # Find mount point
                result = subprocess.run(
                    ['mount'],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if device in line:
                            mount_point = line.split()[2]
                            result = subprocess.run(
                                ['umount', mount_point],
                                capture_output=True, text=True, timeout=10
                            )
                            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to unmount {device}: {e}")
        
        return False
    
    def _format_device(self, device: str) -> bool:
        """Format the target device with FAT32 filesystem."""
        logger.info(f"Formatting device {device}")
        
        try:
            if self.platform == 'win32':
                # Windows: use format command
                if len(device) == 1 and device.isalpha():
                    device = f"{device}:"
                # Use Windows format command with FAT32
                result = subprocess.run(
                    ['format', device, '/FS:FAT32', '/Q', '/Y'],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                return result.returncode == 0
            elif self.platform == 'darwin':
                # macOS: use diskutil eraseVolume
                # Find the disk identifier
                result = subprocess.run(
                    ['diskutil', 'list'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode != 0:
                    return False
                
                # Parse to find the correct disk identifier
                disk_identifier = None
                for line in result.stdout.split('\n'):
                    if device in line and 'disk' in line:
                        # Extract disk identifier like disk2
                        parts = line.strip().split()
                        for part in parts:
                            if part.startswith('disk') and part != 'disk':
                                disk_identifier = part
                                break
                        if disk_identifier:
                            break
                
                if not disk_identifier:
                    logger.error(f"Could not find disk identifier for {device}")
                    return False
                
                # Format as FAT32
                result = subprocess.run(
                    ['diskutil', 'eraseVolume', 'FAT32', 'UNETBOOTIN', 'MBRFormat', disk_identifier],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                return result.returncode == 0
            else:  # Linux
                # Linux: use mkfs.vfat
                if not device.startswith('/dev/'):
                    device = f"/dev/{device}"
                
                # Check if this is a whole device or partition
                # For safety, we should operate on partitions, not whole devices
                # But for simplicity, we'll assume it's a partition or the user knows what they're doing
                result = subprocess.run(
                    ['sudo', 'mkfs.vfat', '-F32', '-n', 'UNETBOOTIN', device],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                return result.returncode == 0
                
        except Exception as e:
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
                # macOS: use diskutil mount
                if not os.path.exists(mount_point):
                    os.makedirs(mount_point, exist_ok=True)
                
                # Find the disk identifier
                result = subprocess.run(
                    ['diskutil', 'list'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode != 0:
                    return False
                
                # Parse to find the correct disk identifier
                disk_identifier = None
                for line in result.stdout.split('\n'):
                    if device in line and 'disk' in line:
                        parts = line.strip().split()
                        for part in parts:
                            if part.startswith('disk') and part != 'disk':
                                disk_identifier = part
                                break
                        if disk_identifier:
                            break
                
                if not disk_identifier:
                    logger.error(f"Could not find disk identifier for {device}")
                    return False
                
                result = subprocess.run(
                    ['diskutil', 'mount', disk_identifier],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode != 0:
                    return False
                
                # Now mount to our specific mount point
                result = subprocess.run(
                    ['mount', '-t', 'msdos', f'/dev/{disk_identifier}s1', mount_point],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                return result.returncode == 0
            else:  # Linux
                if not device.startswith('/dev/'):
                    device = f"/dev/{device}"
                
                if not os.path.exists(mount_point):
                    os.makedirs(mount_point, exist_ok=True)
                
                result = subprocess.run(
                    ['sudo', 'mount', device, mount_point],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                return result.returncode == 0
                
        except Exception as e:
            logger.error(f"Failed to mount device {device} to {mount_point}: {e}")
            return False
    
    def _get_files_to_copy(self, source_dir: str, params: Dict[str, Any]) -> List[str]:
        """Get list of files to copy from source directory."""
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
        install_type = params.get('install_type', 'distribution')
        
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
    
    def _install_bootloader_windows(self, device: str, params: Dict[str, Any]) -> bool:
        """Install bootloader on Windows."""
        logger.info(f"Installing bootloader for Windows on {device}")
        
        try:
            # Windows: use external tools like syslinux, grub4dos, etc.
            # This is a simplified implementation
            
            # For Windows, we would typically:
            # 1. Copy bootloader files to the USB drive
            # 2. Run a tool to make it bootable
            
            # Check for syslinux
            syslinux_path = self._find_executable('syslinux')
            if syslinux_path:
                if len(device) == 1 and device.isalpha():
                    device = f"{device}:"

                result = subprocess.run(
                    [syslinux_path, '-ma', device],
                    capture_output=True, text=True, timeout=60
                )
                if result.returncode != 0:
                    logger.error(f"syslinux failed: {result.stderr}")
                    return False
                return True

            # No known bootloader tool available - report failure honestly
            # instead of producing a non-bootable stick marked as success.
            logger.error("Windows bootloader installation requires syslinux.exe on PATH")
            return False
            
        except Exception as e:
            logger.error(f"Windows bootloader installation failed: {e}")
            return False
    
    def _install_bootloader_macos(self, device: str, params: Dict[str, Any]) -> bool:
        """Install bootloader on macOS."""
        logger.info(f"Installing bootloader for macOS on {device}")
        
        try:
            # macOS: use diskutil and possibly bless
            
            # For macOS, we would typically:
            # 1. Copy bootloader files
            # 2. Use bless to make it bootable
            
            # Find the disk identifier
            result = subprocess.run(
                ['diskutil', 'list'],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0:
                # Parse to find the correct disk
                # This is simplified
                disk_identifier = device
                
                # Use bless to make it bootable
                # bless --mount /Volumes/USB --setBoot --folder /Volumes/USB/EFI --file /Volumes/USB/EFI/BOOT/BOOTX64.EFI
                result = subprocess.run(
                    ['bless', '--mount', device, '--setBoot', '--folder', f'{device}/EFI', 
                     '--file', f'{device}/EFI/BOOT/BOOTX64.EFI'],
                    capture_output=True, text=True, timeout=10
                )
                
                return result.returncode == 0
            
            return False
            
        except Exception as e:
            logger.error(f"macOS bootloader installation failed: {e}")
            return False
    
    def _install_bootloader_linux(self, device: str, params: Dict[str, Any]) -> bool:
        """Install bootloader on Linux."""
        logger.info(f"Installing bootloader for Linux on {device}")
        
        try:
            # Linux: use various tools depending on what's available
            
            install_type = params.get('install_type', 'distribution')
            drive_type = params.get('drive_type', 'USB Drive')
            
            # For USB drives, we typically use syslinux or extlinux
            if drive_type == 'USB Drive':
                # Try syslinux first
                syslinux_path = self._find_executable('syslinux')
                if syslinux_path:
                    if not device.startswith('/dev/'):
                        device = f"/dev/{device}"
                    
                    # Install MBR
                    result = subprocess.run(
                        ['sudo', 'dd', 'if=/usr/lib/syslinux/mbr/mbr.bin', f'of={device}', 'bs=440', 'count=1'],
                        capture_output=True, text=True, timeout=10
                    )
                    if result.returncode != 0:
                        logger.warning(f"Failed to install MBR: {result.stderr}")
                    
                    # Install bootloader
                    result = subprocess.run(
                        ['sudo', syslinux_path, device],
                        capture_output=True, text=True, timeout=10
                    )
                    return result.returncode == 0
                
                # Try extlinux
                extlinux_path = self._find_executable('extlinux')
                if extlinux_path:
                    if not device.startswith('/dev/'):
                        device = f"/dev/{device}"
                    
                    # Install bootloader
                    result = subprocess.run(
                        ['sudo', extlinux_path, '--install', device],
                        capture_output=True, text=True, timeout=10
                    )
                    return result.returncode == 0
                
                # Try grub
                grub_install_path = self._find_executable('grub-install')
                if grub_install_path:
                    if not device.startswith('/dev/'):
                        device = f"/dev/{device}"
                    
                    result = subprocess.run(
                        ['sudo', grub_install_path, '--target=i386-pc', '--boot-directory=' + device, device],
                        capture_output=True, text=True, timeout=10
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
                        ['sudo', grub_install_path, '--target=i386-pc', '--boot-directory=/boot', device],
                        capture_output=True, text=True, timeout=10
                    )
                    return result.returncode == 0
            
            logger.error("No suitable bootloader installation method found "
                         "(install syslinux, extlinux or grub)")
            return False
            
        except Exception as e:
            logger.error(f"Linux bootloader installation failed: {e}")
            return False
    
    def _find_executable(self, name: str) -> Optional[str]:
        """Find an executable in the system PATH."""
        try:
            result = subprocess.run(
                ['which', name],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                path = result.stdout.strip()
                if os.path.exists(path):
                    return path
        except Exception:
            pass
        
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
    
    def create_syslinux_cfg(self, target_device: str, params: Dict[str, Any]) -> bool:
        """Create syslinux configuration file."""
        try:
            # Get parameters
            distro = params.get('distro', 'unknown')
            version = params.get('version', 'unknown')
            kernel = params.get('kernel', 'vmlinuz')
            initrd = params.get('initrd', 'initrd.img')
            boot_options = params.get('boot_options', '')
            
            # Create syslinux.cfg content
            cfg_content = f"""UI menu.c32
MENU TITLE UNetbootin
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
            
        except Exception as e:
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
            
            # Write to file
            grub_cfg_path = os.path.join(target_device, 'grub.cfg')
            with open(grub_cfg_path, 'w') as f:
                f.write(grub_cfg_content)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create grub.cfg: {e}")
            return False


class AsyncUSBInstaller:
    """Async USB installer for non-blocking I/O operations.
    
    This class provides async/await compatible methods for USB installation,
    which can be used with asyncio event loops. It runs the installation in a
    thread pool executor since most filesystem operations are synchronous.
    """
    
    def __init__(self):
        """Initialize the async installer."""
        self.platform = sys.platform
    
    async def install_async(
        self,
        source_dir: str,
        target_device: str,
        install_params: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> Tuple[bool, str]:
        """Install to USB device asynchronously.
        
        Args:
            source_dir: Source directory containing files to install
            target_device: Target device path (e.g., /dev/sdb or D:)\n            install_params: Optional installation parameters
            progress_callback: Optional callback for progress (0-100)
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        logger.info(f"Async installing from {source_dir} to {target_device}")
        
        loop = asyncio.get_event_loop()
        installer = USBInstaller()
        
        # Run sync installation in executor
        return await loop.run_in_executor(
            None,
            lambda: installer.install_sync(
                source_dir,
                target_device,
                install_params,
                progress_callback=progress_callback
            )
        )
    
    async def format_device_async(self, device: str) -> bool:
        """Format device asynchronously."""
        loop = asyncio.get_event_loop()
        installer = USBInstaller()
        return await loop.run_in_executor(
            None,
            installer._format_device,
            device
        )
    
    async def mount_device_async(self, device: str, mount_point: str) -> bool:
        """Mount device asynchronously."""
        loop = asyncio.get_event_loop()
        installer = USBInstaller()
        return await loop.run_in_executor(
            None,
            installer._mount_device,
            device, mount_point
        )
    
    async def copy_files_to_device_async(
        self,
        source_dir: str,
        target_device: str,
        params: Dict[str, Any],
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> bool:
        """Copy files to device asynchronously."""
        loop = asyncio.get_event_loop()
        installer = USBInstaller()
        return await loop.run_in_executor(
            None,
            installer._copy_files_to_device,
            source_dir, target_device, params, progress_callback
        )
    
    async def install_bootloader_async(
        self,
        target_device: str,
        params: Dict[str, Any],
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> bool:
        """Install bootloader asynchronously."""
        loop = asyncio.get_event_loop()
        installer = USBInstaller()
        return await loop.run_in_executor(
            None,
            installer._install_bootloader,
            target_device, params, progress_callback
        )
    
    async def cleanup_installation_async(
        self,
        source_dir: str,
        target_device: str,
        params: Dict[str, Any]
    ) -> None:
        """Clean up installation asynchronously."""
        loop = asyncio.get_event_loop()
        installer = USBInstaller()
        await loop.run_in_executor(
            None,
            installer._cleanup_installation,
            source_dir, target_device, params
        )
