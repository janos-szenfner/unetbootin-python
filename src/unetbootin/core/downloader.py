"""
Download functionality for UNetbootin.
"""

import os
import re
import time
import json
import ftplib
import logging
import asyncio
import requests
import hashlib
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# --- Tunable constants (previously scattered magic numbers) ---
# Size of each streamed download chunk / hash read, in bytes.
DOWNLOAD_CHUNK_SIZE = 8192
# Timeout (seconds) for streaming GET requests that transfer file bodies.
DOWNLOAD_TIMEOUT = 30
# Timeout (seconds) for lightweight metadata requests (HEAD, directory pages).
METADATA_TIMEOUT = 10
# Minimum interval (seconds) between download-speed recalculations.
SPEED_UPDATE_INTERVAL = 0.5

# Try to import aiohttp for async downloads
try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    logger.debug("aiohttp not available, async downloads will use threading")

# aiohttp is optional; when it is missing `aiohttp` is undefined, so guard
# exception handlers with this tuple (empty when aiohttp is unavailable, which
# is a valid "catch nothing" except target).
_AIOHTTP_ERRORS = (aiohttp.ClientError,) if HAS_AIOHTTP else ()


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
    """
    Information about a download mirror.
    
    Attributes:
        url: The hostname of the mirror (without protocol)
        name: Human-readable name of the mirror
        country: Country where the mirror is located
        priority: Priority level (higher = preferred)
        protocol: Protocol to use (http, https, ftp)
    """
    url: str
    name: str = ""
    country: str = ""
    priority: int = 0
    protocol: str = "https"
    
    def get_base_url(self) -> str:
        """
        Get the base URL for this mirror.
        
        Returns:
            The complete base URL with protocol and hostname
        """
        return f"{self.protocol}://{self.url}"


class DownloadResumeManager:
    """
    Manages download resume functionality using partial downloads and checksums.
    
    This class handles the storage and retrieval of partial download state, allowing
    interrupted downloads to be resumed from where they left off.
    """
    
    def __init__(self, dest_path: str):
        """
        Initialize the resume manager.
        
        Args:
            dest_path: The final destination path for the downloaded file
        """
        self.dest_path = dest_path
        self.temp_path = f"{dest_path}.part"
        self.checksum_path = f"{dest_path}.checksum"
        self.resume_info_path = f"{dest_path}.resume"
    
    def get_resume_info(self) -> Dict[str, Any]:
        """
        Get saved resume information.
        
        Returns:
            Dictionary containing resume information (URL, bytes downloaded, etc.)
            or empty dict if no resume info exists
        """
        try:
            if os.path.exists(self.resume_info_path):
                with open(self.resume_info_path, 'r') as f:
                    import json
                    return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
        return {}
    
    def save_resume_info(self, info: Dict[str, Any]):
        """
        Save resume information.
        
        Args:
            info: Dictionary containing resume state to save
        """
        try:
            os.makedirs(os.path.dirname(self.resume_info_path) or '.', exist_ok=True)
            with open(self.resume_info_path, 'w') as f:
                json.dump(info, f)
        except (OSError, TypeError) as e:
            logger.error(f"Failed to save resume info: {e}")
    
    def get_partial_file_size(self) -> int:
        """
        Get the size of the partial download file.
        
        Returns:
            Size in bytes of the partial file, or 0 if it doesn't exist
        """
        if os.path.exists(self.temp_path):
            return os.path.getsize(self.temp_path)
        return 0
    
    def get_partial_file_checksum(self) -> Optional[str]:
        """
        Get the checksum of the partial file.
        
        Returns:
            The stored checksum, or None if not available
        """
        if os.path.exists(self.checksum_path):
            try:
                with open(self.checksum_path, 'r') as f:
                    return f.read().strip()
            except OSError:
                pass
        return None
    
    def save_partial_file_checksum(self, checksum: str, checksum_type: str = "sha256"):
        """
        Save the checksum of the partial file.
        
        Args:
            checksum: The checksum value to save
            checksum_type: The type of checksum (sha256, sha1, md5)
        """
        try:
            with open(self.checksum_path, 'w') as f:
                f.write(f"{checksum_type}:{checksum}")
        except OSError as e:
            logger.error(f"Failed to save partial checksum: {e}")
    
    def cleanup(self):
        """
        Clean up temporary files.
        
        Removes all temporary files created during the download process.
        """
        for path in [self.temp_path, self.checksum_path, self.resume_info_path]:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError as e:
                logger.error(f"Failed to clean up {path}: {e}")
    
    def rename_partial_to_final(self) -> bool:
        """
        Rename partial file to final destination.
        
        Finalizes the download by moving the temporary file to its final location.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if os.path.exists(self.temp_path):
                if os.path.exists(self.dest_path):
                    os.remove(self.dest_path)
                os.rename(self.temp_path, self.dest_path)
                self.cleanup()
                return True
        except OSError as e:
            logger.error(f"Failed to rename partial to final: {e}")
        return False


class MirrorManager:
    """
    Manages a list of download mirrors and selects the best one.
    
    This class handles mirror selection logic, allowing users to choose between
    built-in mirrors and custom mirrors for faster or more reliable downloads.
    """
    
    def __init__(self):
        """Initialize the mirror manager."""
        self.mirrors: List[MirrorInfo] = []
        self.custom_mirrors: List[str] = []
    
    def add_mirror(self, mirror: MirrorInfo):
        """
        Add a mirror to the list.
        
        Args:
            mirror: MirrorInfo object to add
        """
        self.mirrors.append(mirror)
        # Sort by priority (higher priority first)
        self.mirrors.sort(key=lambda m: m.priority, reverse=True)
    
    def add_mirrors(self, mirrors: List[MirrorInfo]):
        """
        Add multiple mirrors.
        
        Args:
            mirrors: List of MirrorInfo objects to add
        """
        for mirror in mirrors:
            self.add_mirror(mirror)
    
    def set_custom_mirrors(self, urls: List[str]):
        """
        Set custom mirror URLs.
        
        Args:
            urls: List of custom mirror base URLs
        """
        self.custom_mirrors = urls
    
    def get_all_mirrors(self) -> List[str]:
        """
        Get all mirror base URLs.
        
        Returns:
            List of all available mirror URLs (built-in + custom)
        """
        urls = [m.get_base_url() for m in self.mirrors]
        urls.extend(self.custom_mirrors)
        return urls
    
    def get_best_mirror(self, base_url: str) -> str:
        """
        Get the best mirror for a given base URL.
        
        Args:
            base_url: The original base URL as fallback
            
        Returns:
            The best available mirror URL
        """
        # If we have custom mirrors, prefer them
        if self.custom_mirrors:
            return self.custom_mirrors[0]
        
        # Return the first built-in mirror or the original URL
        if self.mirrors:
            return self.mirrors[0].get_base_url()
        
        return base_url
    
    def replace_url_base(self, url: str, new_base: str) -> str:
        """
        Replace the base URL of a URL with a new base.
        
        Args:
            url: Original URL to modify
            new_base: New base URL to use
            
        Returns:
            URL with the new base but preserving path, query, and fragment
        """
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


class Downloader:
    """Handles file downloads with progress tracking."""
    
    def __init__(self):
        """Initialize the downloader with a requests session."""
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
    
    def download_file_sync_threaded(self, url: str, dest_path: str, 
                                   min_size: int = 0,
                                   progress_callback: Optional[Callable[[
                                       int, int], None]] = None,
                                   progress_estimated_callback: Optional[Callable[[
                                       int, int, int], None]] = None,
                                   cancel_check: Optional[Callable[[], bool]] = None,
                                   enable_resume: bool = True,
                                   resume_info: Optional[Dict[str, Any]] = None,
                                   resume_manager: Optional['DownloadResumeManager'] = None) -> tuple:
        """Download a file in a separate thread (for use with PySimpleGUI).
        
        This method runs the synchronous download to avoid blocking the PySimpleGUI event loop.
        
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
            
        Returns:
            Tuple of (success: bool, message: str)
        """
        import threading
        
        result = [None, None]
        exception = [None]
        
        def download_wrapper():
            """Wrapper function to run download in a thread."""
            try:
                result[0], result[1] = self.download_file_sync(
                    url, dest_path, min_size,
                    progress_callback=progress_callback,
                    progress_estimated_callback=progress_estimated_callback,
                    cancel_check=cancel_check,
                    enable_resume=enable_resume,
                    resume_info=resume_info,
                    resume_manager=resume_manager
                )
            except Exception as e:  # noqa: BLE001 - transparently re-raised on caller thread
                exception[0] = e
        
        thread = threading.Thread(target=download_wrapper, daemon=True)
        thread.start()
        thread.join()
        
        if exception[0]:
            raise exception[0]
        
        return result[0], result[1]
    
    def download_file_sync(self, url: str, dest_path: str,
                           min_size: int = 0,
                           progress_callback: Optional[Callable[[
                               int, int], None]] = None,
                           progress_estimated_callback: Optional[Callable[[
                               int, int, int], None]] = None,
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
                return False, (f"File size ({file_size}) is smaller than "
                               f"minimum required ({min_size})")
            
            # Check if we can resume a partial download
            partial_size = 0
            if enable_resume and resume_manager:
                partial_size = resume_manager.get_partial_file_size()
                logger.info(f"Found partial download of {partial_size} bytes")
            
            # Download with progress
            downloaded_bytes = partial_size if enable_resume and partial_size > 0 else 0
            chunk_size = DOWNLOAD_CHUNK_SIZE
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
            
            with self.session.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT,
                                  headers=headers) as response:
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', file_size or 0))
                
                # If we're resuming, adjust total_size
                if is_resuming and total_size > 0:
                    total_size += partial_size
                
                if total_size < min_size and min_size > 0:
                    return False, (
                        f"Downloaded file size ({total_size}) is smaller "
                        f"than minimum required ({min_size})")
                
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
                            # recalc speed at most this often
                            if elapsed > SPEED_UPDATE_INTERVAL:
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
                                    percentage = min(
                                        int((downloaded_bytes / total_size) * 100), 100)
                                    progress_estimated_callback(
                                        percentage, downloaded_bytes, int(eta_seconds or 0))
                                else:
                                    # No total size, emit speed instead
                                    progress_estimated_callback(-1,
                                                                downloaded_bytes, int(last_speed))
            
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
                return False, (
                    f"Downloaded file size ({actual_size}) is smaller "
                    f"than minimum required ({min_size})")
            
            return True, f"Downloaded {actual_size} bytes"
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Download failed: {e}")
            # Clean up on failure
            if enable_resume and resume_manager:
                # Don't cleanup on failure - keep partial download for resume
                pass
            return False, f"Download failed: {str(e)}"
        except (OSError, ValueError) as e:
            logger.error(f"Download failed: {e}")
            return False, str(e)
    
    def get_remote_file_size(self, url: str) -> Optional[int]:
        """Get the size of a remote file."""
        try:
            response = self.session.head(
    url, timeout=METADATA_TIMEOUT, allow_redirects=True)
            if response.status_code == 200:
                content_length = response.headers.get('content-length')
                if content_length:
                    return int(content_length)
        except (requests.exceptions.RequestException, ValueError) as e:
            logger.debug(f"Failed to get file size for {url}: {e}")
        
        return None
    
    def get_download_speed(self, bytes_received: int, elapsed_time: float) -> float:
        """Calculate download speed in bytes/second."""
        if elapsed_time <= 0:
            return 0
        return bytes_received / elapsed_time
    
    def format_size(self, size_bytes: int) -> str:
        """Format a byte size to a human readable string.

        Thin wrapper around utils.format_size so callers holding a
        Downloader instance don't need a separate import.
        """
        from unetbootin.core.utils import format_size
        return format_size(size_bytes)

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
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download page {url}: {e}")
            return None
    
    def list_ftp_directory(self, url: str, min_size: int = 0,
                           max_size: int = 0) -> List[str]:
        """List files in an FTP directory.

        SECURITY: plain FTP transmits everything (including credentials, if
        ever used) in cleartext and is vulnerable to tampering in transit.
        Prefer HTTPS mirrors. FTPS is attempted first; plain FTP is only
        used as a last resort, with a warning.
        """
        files = []
        try:
            if not url.startswith('ftp://'):
                url = 'ftp://' + url

            parsed = urlparse(url)

            # Try FTPS (explicit TLS) first, fall back to plain FTP.
            # ftplib.all_errors covers ftplib.Error, OSError (incl. ssl.SSLError)
            # and EOFError.
            try:
                ftp = ftplib.FTP_TLS(parsed.hostname)
                ftp.login()
                ftp.prot_p()  # encrypt the data channel too
                logger.info(f"Connected to {parsed.hostname} using FTPS (TLS)")
            except ftplib.all_errors:
                logger.warning(
                    f"SECURITY: falling back to unencrypted FTP for "
                    f"{parsed.hostname}; the directory listing can be "
                    f"observed or tampered with in transit. Prefer an "
                    f"HTTPS mirror if one is available."
                )
                ftp = ftplib.FTP(parsed.hostname)
                ftp.login()
            
            # Change to directory
            directory = parsed.path or '/'
            try:
                ftp.cwd(directory)
            except ftplib.all_errors:
                pass
            
            # List files (max_size <= 0 means "no upper bound")
            upper = max_size if max_size > 0 else float('inf')
            for name, facts in ftp.mlsd():
                if facts.get('type') == 'file':
                    size = int(facts.get('size', 0))
                    if min_size <= size <= upper:
                        files.append(name)
            
            ftp.quit()

        except (*ftplib.all_errors, ValueError) as e:
            logger.error(f"Failed to list FTP directory {url}: {e}")
        
        return files
    
    def list_http_directory(self, url: str) -> List[str]:
        """List files in an HTTP directory."""
        files = []
        try:
            if not url.endswith('/'):
                url += '/'
            
            response = self.session.get(url, timeout=DOWNLOAD_TIMEOUT)
            if response.status_code == 200:
                # Parse HTML to find file links
                from bs4 import BeautifulSoup
                try:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    for link in soup.find_all('a'):
                        href = link.get('href', '')
                        if href and not href.startswith(
                            '?') and not href.startswith('#'):
                            files.append(href)
                except ImportError:
                    # Fallback: simple regex parsing
                    import re
                    pattern = re.compile(r'href=["\']([^"\']+)["\']')
                    for match in pattern.finditer(response.text):
                        href = match.group(1)
                        if href and not href.startswith(
                            '?') and not href.startswith('#'):
                            files.append(href)
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to list HTTP directory {url}: {e}")
        
        return files
    
    def list_directory(self, url: str, min_size: int = 0,
                       max_size: int = 0) -> List[str]:
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
            response = self.session.head(
                url, allow_redirects=True, timeout=METADATA_TIMEOUT)
            return response.url
        except requests.exceptions.RequestException as e:
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
                    chunk = f.read(DOWNLOAD_CHUNK_SIZE)
                    if not chunk:
                        break
                    hasher.update(chunk)
            
            actual_checksum = hasher.hexdigest()
            return actual_checksum.lower() == expected_checksum.lower()

        except OSError as e:
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
            self.session = aiohttp.ClientSession(
                headers={'User-Agent': self.user_agent})
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
        except (*_AIOHTTP_ERRORS, asyncio.TimeoutError, OSError,
                ValueError, RuntimeError) as e:
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
                async with temp_session.head(url, timeout=METADATA_TIMEOUT) as response:
                    file_size = int(response.headers.get('content-length', 0))
                    if min_size > 0 and file_size < min_size:
                        return False, (
                            f"File size ({file_size}) is smaller than "
                            f"minimum required ({min_size})")
            
            # Download the file
            downloaded_bytes = 0
            chunk_size = DOWNLOAD_CHUNK_SIZE
            
            async with aiohttp.ClientSession(headers={'User-Agent': self.user_agent}) as temp_session:
                async with temp_session.get(url, timeout=DOWNLOAD_TIMEOUT) as response:
                    response.raise_for_status()
                    
                    total_size = int(
    response.headers.get(
        'content-length',
         file_size or 0))
                    
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
                return False, (
                    f"Downloaded size ({downloaded_bytes}) is smaller "
                    f"than minimum required ({min_size})")
            
            return True, f"Downloaded {downloaded_bytes} bytes"
            
        except aiohttp.ClientError as e:
            logger.error(f"aiohttp download failed: {e}")
            return False, str(e)
        except (OSError, ValueError, asyncio.TimeoutError) as e:
            logger.error(f"aiohttp download failed with unexpected error: {e}")
            return False, str(e)
    
    async def get_remote_file_size_async(self, url: str) -> Optional[int]:
        """Get remote file size asynchronously."""
        try:
            if HAS_AIOHTTP:
                async with aiohttp.ClientSession() as session:
                    async with session.head(url, timeout=METADATA_TIMEOUT) as response:
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
        except (*_AIOHTTP_ERRORS, asyncio.TimeoutError, OSError,
                ValueError) as e:
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
