"""
Download functionality for UNetbootin.
"""

import os
import re
import time
import logging
import asyncio
import requests
import hashlib
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot, QThread, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

logger = logging.getLogger(__name__)

# Try to import aiohttp for async downloads
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    logger.debug("aiohttp not available, async downloads will use threading")


@dataclass
class DownloadFileInfo:
    """Information about a file to download."""
    url: str
    dest_path: str
    size: int = 0
    checksum: Optional[str] = None
    checksum_type: str = "sha256"


@dataclass
class MirrorInfo:
    """Information about a download mirror."""
    url: str
    name: str = ""
    country: str = ""
    priority: int = 0
    protocol: str = "https"
    
    def get_base_url(self) -> str:
        """Get the base URL for this mirror."""
        return f"{self.protocol}://{self.url}"


class DownloadResumeManager:
    """Manages download resume functionality using partial downloads and checksums."""
    
    def __init__(self, dest_path: str):
        """Initialize the resume manager."""
        self.dest_path = dest_path
        self.temp_path = f"{dest_path}.part"
        self.checksum_path = f"{dest_path}.checksum"
        self.resume_info_path = f"{dest_path}.resume"
    
    def get_resume_info(self) -> Dict[str, Any]:
        """Get saved resume information."""
        try:
            if os.path.exists(self.resume_info_path):
                with open(self.resume_info_path, 'r') as f:
                    import json
                    return json.load(f)
        except Exception:
            pass
        return {}
    
    def save_resume_info(self, info: Dict[str, Any]):
        """Save resume information."""
        try:
            os.makedirs(os.path.dirname(self.resume_info_path) or '.', exist_ok=True)
            with open(self.resume_info_path, 'w') as f:
                import json
                json.dump(info, f)
        except Exception as e:
            logger.error(f"Failed to save resume info: {e}")
    
    def get_partial_file_size(self) -> int:
        """Get the size of the partial download file."""
        if os.path.exists(self.temp_path):
            return os.path.getsize(self.temp_path)
        return 0
    
    def get_partial_file_checksum(self) -> Optional[str]:
        """Get the checksum of the partial file."""
        if os.path.exists(self.checksum_path):
            try:
                with open(self.checksum_path, 'r') as f:
                    return f.read().strip()
            except Exception:
                pass
        return None
    
    def save_partial_file_checksum(self, checksum: str, checksum_type: str = "sha256"):
        """Save the checksum of the partial file."""
        try:
            with open(self.checksum_path, 'w') as f:
                f.write(f"{checksum_type}:{checksum}")
        except Exception as e:
            logger.error(f"Failed to save partial checksum: {e}")
    
    def cleanup(self):
        """Clean up temporary files."""
        for path in [self.temp_path, self.checksum_path, self.resume_info_path]:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception as e:
                logger.error(f"Failed to clean up {path}: {e}")
    
    def rename_partial_to_final(self) -> bool:
        """Rename partial file to final destination."""
        try:
            if os.path.exists(self.temp_path):
                if os.path.exists(self.dest_path):
                    os.remove(self.dest_path)
                os.rename(self.temp_path, self.dest_path)
                self.cleanup()
                return True
        except Exception as e:
            logger.error(f"Failed to rename partial to final: {e}")
        return False


class MirrorManager:
    """Manages a list of download mirrors and selects the best one."""
    
    def __init__(self):
        """Initialize the mirror manager."""
        self.mirrors: List[MirrorInfo] = []
        self.custom_mirrors: List[str] = []
    
    def add_mirror(self, mirror: MirrorInfo):
        """Add a mirror to the list."""
        self.mirrors.append(mirror)
        # Sort by priority (higher priority first)
        self.mirrors.sort(key=lambda m: m.priority, reverse=True)
    
    def add_mirrors(self, mirrors: List[MirrorInfo]):
        """Add multiple mirrors."""
        for mirror in mirrors:
            self.add_mirror(mirror)
    
    def set_custom_mirrors(self, urls: List[str]):
        """Set custom mirror URLs."""
        self.custom_mirrors = urls
    
    def get_all_mirrors(self) -> List[str]:
        """Get all mirror base URLs."""
        urls = [m.get_base_url() for m in self.mirrors]
        urls.extend(self.custom_mirrors)
        return urls
    
    def get_best_mirror(self, base_url: str) -> str:
        """Get the best mirror for a given base URL."""
        # If we have custom mirrors, prefer them
        if self.custom_mirrors:
            return self.custom_mirrors[0]
        
        # Return the first built-in mirror or the original URL
        if self.mirrors:
            return self.mirrors[0].get_base_url()
        
        return base_url
    
    def replace_url_base(self, url: str, new_base: str) -> str:
        """Replace the base URL of a URL with a new base."""
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            # Extract the path from the original URL
            path = parsed.path
            if parsed.query:
                path += f"?{parsed.query}"
            if parsed.fragment:
                path += f"#{parsed.fragment}"
            return urljoin(new_base, path)
        return url


class DownloadWorker(QThread):
    """Worker thread for download operations."""
    
    progress_updated = Signal(int, int)
    progress_estimated = Signal(int, int, int)  # percent, bytes_received, estimated_total
    finished = Signal(bool, str)
    failed = Signal(str, str)
    
    def __init__(self, url: str, dest_path: str, min_size: int = 0, 
                 enable_resume: bool = True, preferred_mirror: str = None,
                 custom_mirrors: List[str] = None):
        super().__init__()
        self.url = url
        self.dest_path = dest_path
        self.min_size = min_size
        self.stop_requested = False
        self.start_time = 0
        self.last_bytes = 0
        self.last_time = 0
        self.last_speed = 0
        self.enable_resume = enable_resume
        self.preferred_mirror = preferred_mirror
        self.custom_mirrors = custom_mirrors or []
        self.resume_manager = None
        self.mirror_manager = None
    
    def run(self):
        """Perform the download."""
        try:
            self.start_time = time.time()
            self.last_bytes = 0
            self.last_time = self.start_time
            self.last_speed = 0
            
            # Initialize resume and mirror managers
            self.resume_manager = DownloadResumeManager(self.dest_path)
            self.mirror_manager = MirrorManager()
            self.mirror_manager.set_custom_mirrors(self.custom_mirrors)
            
            # Get the effective URL (possibly with mirror replacement)
            effective_url = self.url
            if self.preferred_mirror:
                effective_url = self.mirror_manager.replace_url_base(
                    self.url, self.preferred_mirror
                )
            
            downloader = Downloader()
            
            # Check if we can resume
            resume_info = {}
            if self.enable_resume:
                resume_info = self.resume_manager.get_resume_info()
                logger.info(f"Resume info: {resume_info}")
            
            success, message = downloader.download_file_sync(
                effective_url,
                self.dest_path,
                self.min_size,
                self.on_progress_update,
                cancel_check=lambda: self.stop_requested,
                enable_resume=self.enable_resume,
                resume_info=resume_info,
                resume_manager=self.resume_manager
            )
            
            if success:
                self.finished.emit(True, message)
            else:
                self.failed.emit(self.url, message)
                
        except Exception as e:
            logger.error(f"Download failed: {e}")
            self.failed.emit(self.url, str(e))
    
    def stop(self):
        """Request stop."""
        self.stop_requested = True
    
    def on_progress_update(self, bytes_received: int, bytes_total: int):
        """Handle progress update with estimation."""
        if self.stop_requested:
            return
        
        current_time = time.time()
        
        # Calculate speed
        elapsed = current_time - self.last_time
        if elapsed > 0.5:  # Update speed every 0.5 seconds
            bytes_diff = bytes_received - self.last_bytes
            self.last_speed = bytes_diff / elapsed if elapsed > 0 else 0
            self.last_bytes = bytes_received
            self.last_time = current_time
        
        # Emit actual progress
        self.progress_updated.emit(bytes_received, bytes_total)
        
        # Always emit estimated progress (includes ETA when total is known)
        self.emit_estimated_progress(bytes_received, bytes_total, current_time)
    
    def emit_estimated_progress(self, bytes_received: int, bytes_total: int, current_time: float):
        """Emit estimated progress with ETA calculation.
        
        Args:
            bytes_received: Number of bytes downloaded so far
            bytes_total: Total size of the file (0 if unknown)
            current_time: Current time
        """
        downloader = Downloader()
        
        # Calculate ETA
        eta_seconds = downloader.calculate_eta(
            bytes_received, bytes_total, self.start_time, current_time
        )
        
        # Calculate percentage if we know the total
        if bytes_total > 0:
            percentage = min(int((bytes_received / bytes_total) * 100), 100)
        else:
            percentage = -1  # Unknown percentage
        
        # Emit all useful information
        # Signal: percentage, bytes_received, bytes_total_or_estimated_speed
        if bytes_total > 0:
            # We know the total, emit ETA information
            self.progress_estimated.emit(percentage, bytes_received, int(eta_seconds or 0))
        else:
            # We don't know the total, emit speed instead
            self.progress_estimated.emit(-1, bytes_received, int(self.last_speed))


class Downloader(QObject):
    """Handles file downloads with progress tracking."""
    
    progress_updated = Signal(int, int)
    progress_estimated = Signal(int, int, int)  # percent, bytes_received, estimated_total
    download_complete = Signal(str, str)
    download_failed = Signal(str, str)
    
    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'UNetbootin/' + self.get_version()
        })
        self.worker = None
    
    def get_version(self) -> str:
        """Get application version."""
        try:
            from unetbootin import APP_VERSION
            return APP_VERSION
        except ImportError:
            return "0.1.0"
    
    def download_file(self, url: str, dest_path: str, 
                     min_size: int = 0,
                     progress_callback: Optional[Callable[[int, int], None]] = None,
                     progress_estimated_callback: Optional[Callable[[int, int, int], None]] = None):
        """Download a file with progress tracking.
        
        Args:
            url: URL to download from
            dest_path: Destination file path
            min_size: Minimum expected file size
            progress_callback: Callback for actual progress (bytes_received, bytes_total)
            progress_estimated_callback: Callback for estimated progress (percentage, bytes_received, eta_or_speed)
        """
        logger.info(f"Downloading {url} to {dest_path}")
        
        # Create worker thread
        self.worker = DownloadWorker(url, dest_path, min_size)
        
        if progress_callback:
            self.worker.progress_updated.connect(progress_callback)
        self.worker.progress_updated.connect(self.progress_updated.emit)
        
        if progress_estimated_callback:
            self.worker.progress_estimated.connect(progress_estimated_callback)
        self.worker.progress_estimated.connect(self.progress_estimated.emit)
        
        self.worker.finished.connect(lambda success, msg: self.download_complete.emit(url, msg))
        self.worker.failed.connect(self.download_failed.emit)
        
        self.worker.start()
    
    def download_file_sync(self, url: str, dest_path: str,
                           min_size: int = 0,
                           progress_callback: Optional[Callable[[int, int], None]] = None,
                           progress_estimated_callback: Optional[Callable[[int, int, int], None]] = None,
                           cancel_check: Optional[Callable[[], bool]] = None,
                           enable_resume: bool = True,
                           resume_info: Optional[Dict[str, Any]] = None,
                           resume_manager: Optional[DownloadResumeManager] = None) -> tuple:
        """Synchronously download a file.

        Args:
            url: URL to download from
            dest_path: Destination file path
            min_size: Minimum expected file size
            progress_callback: Callback for actual progress (bytes_received, bytes_total)
            progress_estimated_callback: Callback for estimated progress (percentage, bytes_received, eta_or_speed)
            cancel_check: Optional callable checked between chunks; return True to abort
            enable_resume: Enable download resume functionality
            resume_info: Information for resuming a download
            resume_manager: Manager for handling resume operations
        """
        try:
            # Create destination directory
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            
            # Initialize resume manager if not provided
            if resume_manager is None and enable_resume:
                resume_manager = DownloadResumeManager(dest_path)
            
            # Get file size if possible (may be None if the server does not
            # answer HEAD requests or omits Content-Length)
            file_size = self.get_remote_file_size(url)
            if min_size > 0 and file_size is not None and file_size < min_size:
                return False, f"File size ({file_size}) is smaller than minimum required ({min_size})"
            
            # Check if we can resume a partial download
            partial_size = 0
            if enable_resume and resume_manager:
                partial_size = resume_manager.get_partial_file_size()
                logger.info(f"Found partial download of {partial_size} bytes")
            
            # Download with progress
            downloaded_bytes = partial_size if enable_resume and partial_size > 0 else 0
            chunk_size = 8192
            start_time = time.time()
            last_bytes = downloaded_bytes
            last_time = start_time
            last_speed = 0
            
            # Determine if we're resuming
            is_resuming = enable_resume and partial_size > 0
            
            # Use streaming download
            headers = {}
            if is_resuming:
                # Request to continue from where we left off
                headers['Range'] = f'bytes={partial_size}-'
                logger.info(f"Resuming download from byte {partial_size}")
            
            with self.session.get(url, stream=True, timeout=30, headers=headers) as response:
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', file_size or 0))
                
                # If we're resuming, adjust total_size
                if is_resuming and total_size > 0:
                    total_size += partial_size
                
                if total_size < min_size and min_size > 0:
                    return False, f"Downloaded file size ({total_size}) is smaller than minimum required ({min_size})"
                
                # Use temporary file for resume support
                temp_path = dest_path if not enable_resume else resume_manager.temp_path
                
                # If resuming, open in append mode, otherwise in write mode
                mode = 'ab' if is_resuming else 'wb'
                
                with open(temp_path, mode) as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if cancel_check and cancel_check():
                            f.close()
                            try:
                                if enable_resume:
                                    resume_manager.cleanup()
                                else:
                                    os.remove(dest_path)
                            except OSError:
                                pass
                            return False, "Download cancelled"
                        if chunk:
                            f.write(chunk)
                            downloaded_bytes += len(chunk)
                            current_time = time.time()
                            
                            # Calculate speed
                            elapsed = current_time - last_time
                            if elapsed > 0.5:  # Update speed every 0.5 seconds
                                bytes_diff = downloaded_bytes - last_bytes
                                last_speed = bytes_diff / elapsed if elapsed > 0 else 0
                                last_bytes = downloaded_bytes
                                last_time = current_time
                            
                            if progress_callback:
                                progress_callback(downloaded_bytes, total_size)
                            
                            # Emit estimated progress
                            if progress_estimated_callback:
                                eta_seconds = self.calculate_eta(
                                    downloaded_bytes, total_size, start_time, current_time
                                )
                                if total_size > 0:
                                    percentage = min(int((downloaded_bytes / total_size) * 100), 100)
                                    progress_estimated_callback(percentage, downloaded_bytes, int(eta_seconds or 0))
                                else:
                                    # No total size, emit speed instead
                                    progress_estimated_callback(-1, downloaded_bytes, int(last_speed))
            
            # If we used a temporary file, move it to final destination
            if enable_resume and os.path.exists(temp_path) and temp_path != dest_path:
                if not resume_manager.rename_partial_to_final():
                    return False, "Failed to finalize download"
            
            # Verify file size
            actual_size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
            if actual_size < min_size and min_size > 0:
                if enable_resume:
                    resume_manager.cleanup()
                else:
                    try:
                        os.remove(dest_path)
                    except OSError:
                        pass
                return False, f"Downloaded file size ({actual_size}) is smaller than minimum required ({min_size})"
            
            return True, f"Downloaded {actual_size} bytes"
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Download failed: {e}")
            # Clean up on failure
            if enable_resume and resume_manager:
                # Don't cleanup on failure - keep partial download for resume
                pass
            return False, f"Download failed: {str(e)}"
        except Exception as e:
            logger.error(f"Download failed: {e}")
            return False, str(e)
    
    def get_remote_file_size(self, url: str) -> Optional[int]:
        """Get the size of a remote file."""
        try:
            response = self.session.head(url, timeout=10, allow_redirects=True)
            if response.status_code == 200:
                content_length = response.headers.get('content-length')
                if content_length:
                    return int(content_length)
        except Exception as e:
            logger.debug(f"Failed to get file size for {url}: {e}")
        
        return None
    
    def get_download_speed(self, bytes_received: int, elapsed_time: float) -> float:
        """Calculate download speed in bytes/second."""
        if elapsed_time <= 0:
            return 0
        return bytes_received / elapsed_time
    
    def format_download_speed(self, bytes_per_second: float) -> str:
        """Format download speed to human readable string."""
        if bytes_per_second < 1024:
            return f"{bytes_per_second:.0f} B/s"
        elif bytes_per_second < 1024 * 1024:
            return f"{bytes_per_second / 1024:.1f} KB/s"
        elif bytes_per_second < 1024 * 1024 * 1024:
            return f"{bytes_per_second / (1024 * 1024):.1f} MB/s"
        else:
            return f"{bytes_per_second / (1024 * 1024 * 1024):.1f} GB/s"
    
    def calculate_eta(self, bytes_received: int, bytes_total: int, 
                     start_time: float, current_time: float) -> Optional[float]:
        """Calculate Estimated Time of Arrival (ETA) in seconds.
        
        Args:
            bytes_received: Number of bytes downloaded so far
            bytes_total: Total size of the file (0 if unknown)
            start_time: When the download started
            current_time: Current time
            
        Returns:
            ETA in seconds, or None if it cannot be calculated
        """
        elapsed = current_time - start_time
        if elapsed <= 0:
            return None
        
        if bytes_total <= 0:
            # Can't estimate without knowing total size
            return None
        
        if bytes_received >= bytes_total:
            return 0  # Download complete
        
        # Calculate remaining time based on current speed
        speed = bytes_received / elapsed
        if speed <= 0:
            return None
        
        remaining_bytes = bytes_total - bytes_received
        remaining_time = remaining_bytes / speed
        
        return remaining_time
    
    def format_eta(self, eta_seconds: Optional[float]) -> str:
        """Format ETA to human readable string."""
        if eta_seconds is None or eta_seconds < 0:
            return "--:--"
        
        if eta_seconds < 60:
            return f"{int(eta_seconds)}s"
        elif eta_seconds < 3600:
            minutes = int(eta_seconds // 60)
            seconds = int(eta_seconds % 60)
            return f"{minutes}:{seconds:02d}"
        else:
            hours = int(eta_seconds // 3600)
            minutes = int((eta_seconds % 3600) // 60)
            return f"{hours}:{minutes:02d}:--"
    
    def format_elapsed_time(self, elapsed_seconds: float) -> str:
        """Format elapsed time to human readable string."""
        if elapsed_seconds < 60:
            return f"{int(elapsed_seconds)}s"
        elif elapsed_seconds < 3600:
            minutes = int(elapsed_seconds // 60)
            seconds = int(elapsed_seconds % 60)
            return f"{minutes}:{seconds:02d}"
        else:
            hours = int(elapsed_seconds // 3600)
            minutes = int((elapsed_seconds % 3600) // 60)
            return f"{hours}:{minutes:02d}:--"
    
    def download_page_contents(self, url: str, timeout: int = 30) -> Optional[str]:
        """Download and return the contents of a web page."""
        try:
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"Failed to download page {url}: {e}")
            return None
    
    def list_ftp_directory(self, url: str, min_size: int = 0, max_size: int = 0) -> List[str]:
        """List files in an FTP directory."""
        files = []
        try:
            if not url.startswith('ftp://'):
                url = 'ftp://' + url
            
            parsed = urlparse(url)
            import ftplib
            
            ftp = ftplib.FTP(parsed.hostname)
            ftp.login()
            
            # Change to directory
            directory = parsed.path or '/'
            try:
                ftp.cwd(directory)
            except Exception:
                pass
            
            # List files (max_size <= 0 means "no upper bound")
            upper = max_size if max_size > 0 else float('inf')
            for name, facts in ftp.mlsd():
                if facts.get('type') == 'file':
                    size = int(facts.get('size', 0))
                    if min_size <= size <= upper:
                        files.append(name)
            
            ftp.quit()
            
        except Exception as e:
            logger.error(f"Failed to list FTP directory {url}: {e}")
        
        return files
    
    def list_http_directory(self, url: str) -> List[str]:
        """List files in an HTTP directory."""
        files = []
        try:
            if not url.endswith('/'):
                url += '/'
            
            response = self.session.get(url, timeout=30)
            if response.status_code == 200:
                # Parse HTML to find file links
                from bs4 import BeautifulSoup
                try:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    for link in soup.find_all('a'):
                        href = link.get('href', '')
                        if href and not href.startswith('?') and not href.startswith('#'):
                            files.append(href)
                except ImportError:
                    # Fallback: simple regex parsing
                    import re
                    pattern = re.compile(r'href=["\']([^"\']+)["\']')
                    for match in pattern.finditer(response.text):
                        href = match.group(1)
                        if href and not href.startswith('?') and not href.startswith('#'):
                            files.append(href)
        except Exception as e:
            logger.error(f"Failed to list HTTP directory {url}: {e}")
        
        return files
    
    def list_directory(self, url: str, min_size: int = 0, max_size: int = 0) -> List[str]:
        """List files in a directory (HTTP, HTTPS, or FTP)."""
        parsed = urlparse(url)
        
        if parsed.scheme in ['ftp', '']:
            return self.list_ftp_directory(url, min_size, max_size)
        else:
            return self.list_http_directory(url)
    
    def filter_directory_listing(self, files: List[str], 
                                 patterns: List[str], 
                                 min_size: int = 0, 
                                 max_size: int = 0) -> List[str]:
        """Filter a directory listing by patterns and size."""
        import re
        
        compiled_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
        filtered = []
        
        for filename in files:
            # Check patterns
            pattern_match = True
            for pattern in compiled_patterns:
                if not pattern.search(filename):
                    pattern_match = False
                    break
            
            if not pattern_match:
                continue
            
            # Check size (would need to fetch each file's size)
            # This is a simplified version
            filtered.append(filename)
        
        return filtered
    
    def find_best_match(self, files: List[str], patterns: List[str]) -> Optional[str]:
        """Find the best matching file from a list."""
        import re
        
        compiled_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
        
        for filename in files:
            for i, pattern in enumerate(compiled_patterns):
                if pattern.search(filename):
                    # Return the first match with highest priority pattern
                    return filename
        
        return None
    
    def get_redirect_url(self, url: str) -> str:
        """Follow redirects and return final URL."""
        try:
            response = self.session.head(url, allow_redirects=True, timeout=10)
            return response.url
        except Exception as e:
            logger.error(f"Failed to get redirect URL for {url}: {e}")
            return url
    
    def verify_checksum(self, file_path: str, expected_checksum: str, 
                       checksum_type: str = "sha256") -> bool:
        """Verify file checksum."""
        try:
            import hashlib
            
            if checksum_type == "sha256":
                hasher = hashlib.sha256()
            elif checksum_type == "sha1":
                hasher = hashlib.sha1()
            elif checksum_type == "md5":
                hasher = hashlib.md5()
            else:
                logger.error(f"Unsupported checksum type: {checksum_type}")
                return False
            
            with open(file_path, 'rb') as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    hasher.update(chunk)
            
            actual_checksum = hasher.hexdigest()
            return actual_checksum.lower() == expected_checksum.lower()
            
        except Exception as e:
            logger.error(f"Failed to verify checksum for {file_path}: {e}")
            return False
    
    def cleanup(self):
        """Clean up resources."""
        if self.session:
            self.session.close()


class AsyncDownloader:
    """Async downloader using aiohttp for non-blocking I/O operations.
    
    This class provides async/await compatible methods for downloading files,
    which can be used with asyncio event loops. Falls back to threading if
    aiohttp is not available.
    """
    
    def __init__(self):
        """Initialize the async downloader."""
        self.session = None
        self.user_agent = "UNetbootin/" + self._get_version()
    
    def _get_version(self) -> str:
        """Get application version."""
        try:
            from unetbootin import APP_VERSION
            return APP_VERSION
        except ImportError:
            return "0.1.0"
    
    async def __aenter__(self):
        """Async context manager entry."""
        if HAS_AIOHTTP:
            self.session = aiohttp.ClientSession(headers={'User-Agent': self.user_agent})
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if HAS_AIOHTTP and self.session:
            await self.session.close()
    
    async def download_file_async(
        self,
        url: str,
        dest_path: str,
        min_size: int = 0,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> tuple:
        """Download a file asynchronously with progress tracking.
        
        Args:
            url: URL to download from
            dest_path: Destination file path
            min_size: Minimum expected file size
            progress_callback: Optional callback for progress (bytes_received, bytes_total)
            cancel_check: Optional callable to check for cancellation
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        logger.info(f"Async downloading {url} to {dest_path}")
        
        try:
            # Create destination directory
            os.makedirs(os.path.dirname(dest_path) or '.', exist_ok=True)
            
            if HAS_AIOHTTP:
                return await self._download_with_aiohttp(
                    url, dest_path, min_size, progress_callback, cancel_check
                )
            else:
                # Fallback: run sync download in executor
                loop = asyncio.get_event_loop()
                downloader = Downloader()
                return await loop.run_in_executor(
                    None,
                    lambda: downloader.download_file_sync(
                        url, dest_path, min_size,
                        progress_callback=progress_callback,
                        cancel_check=cancel_check
                    )
                )
        except Exception as e:
            logger.error(f"Async download failed: {e}")
            return False, str(e)
    
    async def _download_with_aiohttp(
        self,
        url: str,
        dest_path: str,
        min_size: int = 0,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> tuple:
        """Download using aiohttp."""
        try:
            # Get file size first
            async with aiohttp.ClientSession() as temp_session:
                async with temp_session.head(url, timeout=10) as response:
                    file_size = int(response.headers.get('content-length', 0))
                    if min_size > 0 and file_size < min_size:
                        return False, f"File size ({file_size}) is smaller than minimum required ({min_size})"
            
            # Download the file
            downloaded_bytes = 0
            chunk_size = 8192
            
            async with aiohttp.ClientSession(headers={'User-Agent': self.user_agent}) as temp_session:
                async with temp_session.get(url, timeout=30) as response:
                    response.raise_for_status()
                    
                    total_size = int(response.headers.get('content-length', file_size or 0))
                    
                    with open(dest_path, 'wb') as f:
                        while True:
                            if cancel_check and cancel_check():
                                return False, "Cancelled by user"
                            
                            chunk = await response.content.read(chunk_size)
                            if not chunk:
                                break
                            
                            f.write(chunk)
                            downloaded_bytes += len(chunk)
                            
                            if progress_callback:
                                progress_callback(downloaded_bytes, total_size)
            
            # Verify minimum size
            if min_size > 0 and downloaded_bytes < min_size:
                return False, f"Downloaded size ({downloaded_bytes}) is smaller than minimum required ({min_size})"
            
            return True, f"Downloaded {downloaded_bytes} bytes"
            
        except aiohttp.ClientError as e:
            logger.error(f"aiohttp download failed: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"aiohttp download failed with unexpected error: {e}")
            return False, str(e)
    
    async def get_remote_file_size_async(self, url: str) -> Optional[int]:
        """Get remote file size asynchronously."""
        try:
            if HAS_AIOHTTP:
                async with aiohttp.ClientSession() as session:
                    async with session.head(url, timeout=10) as response:
                        if response.status == 200:
                            content_length = response.headers.get('content-length')
                            if content_length:
                                return int(content_length)
            else:
                # Fallback to sync
                loop = asyncio.get_event_loop()
                downloader = Downloader()
                return await loop.run_in_executor(
                    None,
                    downloader.get_remote_file_size,
                    url
                )
        except Exception as e:
            logger.debug(f"Could not get remote file size: {e}")
        return None
    
    async def verify_checksum_async(
        self,
        file_path: str,
        expected_checksum: str,
        checksum_type: str = "sha256"
    ) -> bool:
        """Verify file checksum asynchronously."""
        loop = asyncio.get_event_loop()
        downloader = Downloader()
        return await loop.run_in_executor(
            None,
            downloader.verify_checksum,
            file_path, expected_checksum, checksum_type
        )
