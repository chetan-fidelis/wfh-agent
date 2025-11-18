"""
Lightweight file download monitor for Electron app.
Monitors browser downloads (Chrome, Edge, Firefox) and file explorer.
Uploads files to Laravel API endpoint for recruitment-related employees.
"""

import os
import sys
import time
import json
import threading
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Set
from datetime import datetime
import requests
import urllib3

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Platform-specific imports
if sys.platform == 'win32':
    import winreg
    from pathlib import WindowsPath


class DownloadMonitor:
    """Monitors downloads from browsers and file explorer, uploads to API."""
    
    def __init__(self, config: Dict, emp_id: int, auth_token: Optional[str] = None):
        """
        Initialize download monitor.
        
        Args:
            config: Config dict with download_monitor settings
            emp_id: Employee ID
            auth_token: Bearer token for API auth
        """
        self.config = config
        self.emp_id = emp_id
        self.auth_token = auth_token
        # Initialize logger early, before any other init that may log
        self.logger = self._get_logger()
        self.stop_event = threading.Event()
        self.thread = None
        
        # API config
        dm_cfg = config.get('download_monitor', {})
        api_url = dm_cfg.get('api_url', 'http://ats-tool.test/api')
        # Remove trailing /api if present, then remove trailing slash
        if api_url.endswith('/api'):
            self.api_base = api_url[:-4]  # Remove '/api'
        else:
            self.api_base = api_url.rstrip('/')
        self.enabled = dm_cfg.get('enabled', False)
        self.target_designations = dm_cfg.get('target_designations', ['recruiter', 'hr', 'hiring_manager'])
        # Check cadence (seconds) - coerce to int, fallback to 30 on invalid
        try:
            self.check_interval = int(dm_cfg.get('check_interval_sec', 30))
        except Exception:
            self.check_interval = 30
        
        # Download paths to monitor
        self.download_paths: Set[str] = set()
        self._init_download_paths()
        
        # Track processed files to avoid re-uploads
        self.processed_files: Dict[str, str] = {}  # {file_path: file_hash}
        self.max_file_size_mb = dm_cfg.get('max_file_size_mb', 100)
        
        # Supported extensions for upload (Naukri-specific: pdf, docx, txt)
        self.allowed_extensions = dm_cfg.get('allowed_extensions', [
            'pdf', 'docx', 'txt'
        ])
        
        # Naukri-specific monitoring
        self.naukri_pattern = dm_cfg.get('naukri_pattern', 'Naukri_')
        self.monitor_naukri_only = dm_cfg.get('monitor_naukri_only', True)
        
        # logger already initialized above
    
    def _get_logger(self):
        """Return a simple logger function."""
        def log(msg: str):
            ts = datetime.now().isoformat()
            print(f"[{ts}] [DownloadMonitor] {msg}")
        return log
    
    def _init_download_paths(self):
        """Initialize browser and file explorer download paths."""
        if sys.platform != 'win32':
            self.logger("Download monitor only supports Windows")
            return
        
        username = os.getenv('USERNAME', 'User')
        user_home = os.path.expanduser('~')
        
        # Common browser download locations
        paths = [
            os.path.join(user_home, 'Downloads'),
            os.path.join(user_home, 'Desktop'),
            # Chrome
            os.path.join(user_home, 'AppData', 'Local', 'Google', 'Chrome', 'User Data', 'Default', 'Downloads'),
            # Edge
            os.path.join(user_home, 'AppData', 'Local', 'Microsoft', 'Edge', 'User Data', 'Default', 'Downloads'),
            # Firefox
            os.path.join(user_home, 'AppData', 'Roaming', 'Mozilla', 'Firefox', 'Profiles'),
        ]
        
        for path in paths:
            if os.path.exists(path):
                self.download_paths.add(path)
        
        self.logger(f"Monitoring {len(self.download_paths)} download paths")
    
    def _get_file_hash(self, file_path: str) -> str:
        """Compute SHA256 hash of file."""
        try:
            sha256 = hashlib.sha256()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    sha256.update(chunk)
            return sha256.hexdigest()
        except Exception as e:
            self.logger(f"Error hashing {file_path}: {e}")
            return ""
    
    def _is_file_ready(self, file_path: str) -> bool:
        """Check if file is ready (not being written to)."""
        try:
            # Try to open file exclusively; if it fails, it's still being written
            if sys.platform == 'win32':
                import msvcrt
                with open(file_path, 'rb') as f:
                    try:
                        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                        return True
                    except OSError:
                        return False
            else:
                # On non-Windows, assume ready if we can read it
                with open(file_path, 'rb') as f:
                    f.read(1)
                return True
        except Exception:
            return False
    
    def _should_upload(self, file_path: str) -> bool:
        """Check if file should be uploaded."""
        try:
            file_name = os.path.basename(file_path)
            
            # Check extension
            ext = os.path.splitext(file_path)[1].lstrip('.').lower()
            if ext not in self.allowed_extensions:
                return False
            
            # Naukri-specific: check if filename matches pattern (e.g., Naukri_*.pdf)
            if self.monitor_naukri_only:
                if not file_name.startswith(self.naukri_pattern):
                    return False
            
            # Check file size
            size_mb = os.path.getsize(file_path) / (1024 * 1024)
            if size_mb > self.max_file_size_mb:
                self.logger(f"File {file_path} exceeds max size ({size_mb:.1f}MB > {self.max_file_size_mb}MB)")
                return False
            
            # Check if already processed
            file_hash = self._get_file_hash(file_path)
            if file_path in self.processed_files and self.processed_files[file_path] == file_hash:
                return False
            
            return True
        except Exception as e:
            self.logger(f"Error checking file {file_path}: {e}")
            return False
    
    def _upload_file(self, file_path: str) -> bool:
        """Upload file to API."""
        try:
            if not os.path.exists(file_path):
                return False
            
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            file_hash = self._get_file_hash(file_path)
            file_type = self._get_mime_type(file_path)
            
            # Get auth credentials
            token = os.environ.get('CV_CAPTURE_AUTH_TOKEN') or self.auth_token or self._read_auth_token_from_config()
            api_key = os.environ.get('CV_CAPTURE_API_KEY') or self._read_api_key_from_config()
            headers = { 'Accept': 'application/json' }
            if token:
                headers['Authorization'] = f'Bearer {token}'
            elif api_key:
                headers['X-Api-Key'] = api_key
            else:
                self.logger(f"No auth token or API key available")
                return False
            
            # Step 1: Get presigned URL with required fields
            presign_payload = {
                "file_name": file_name,
                "file_size": file_size,
                "file_type": file_type,
                "sha256": file_hash,
                "source": "download"
            }
            
            self.logger(f"Requesting presign for {file_name}...")
            presign_url = f"{self.api_base.rstrip('/')}/api/cv-capture/presign"
            self.logger(f"Presign URL: {presign_url}")
            presign_resp = requests.post(
                presign_url,
                json=presign_payload,
                headers=headers,
                timeout=30,
                verify=False,  # Disable SSL verification for self-signed certs
                allow_redirects=False  # Don't follow redirects that might convert POST to GET
            )
            
            # If bearer token was used and unauthorized, retry with API key if available
            if presign_resp.status_code in (401, 403) and token and api_key:
                try:
                    self.logger("Presign unauthorized with Bearer, retrying with API key")
                    headers_retry = { 'Accept': 'application/json', 'X-Api-Key': api_key }
                    presign_resp = requests.post(
                        presign_url,
                        json=presign_payload,
                        headers=headers_retry,
                        timeout=30,
                        verify=False,  # Disable SSL verification for self-signed certs
                        allow_redirects=False  # Don't follow redirects that might convert POST to GET
                    )
                except Exception:
                    pass
            
            if presign_resp.status_code != 200:
                self.logger(f"Presign failed for {file_name}: {presign_resp.status_code} - {presign_resp.text}")
                return False
            
            presign_data = presign_resp.json()
            if not presign_data.get('success'):
                self.logger(f"Presign error: {presign_data.get('error', {}).get('message', 'Unknown error')}")
                return False
            
            s3_url = presign_data.get('data', {}).get('url')
            s3_key = presign_data.get('data', {}).get('key')
            
            if not s3_url:
                self.logger(f"No S3 URL in presign response")
                return False
            
            # Step 2: Upload to S3
            self.logger(f"Uploading to S3...")
            with open(file_path, 'rb') as f:
                s3_resp = requests.put(
                    s3_url,
                    data=f,
                    headers={"Content-Type": file_type},
                    timeout=60
                )
            
            if s3_resp.status_code not in [200, 204]:
                self.logger(f"S3 upload failed for {file_name}: {s3_resp.status_code}")
                return False
            
            self.logger(f"S3 upload successful")
            
            # Step 3: Store metadata with required fields
            metadata = {
                "s3_key": s3_key,
                "file_name": file_name,
                "file_size": file_size,
                "file_type": file_type,
                "sha256": file_hash,
                "source": "download"
            }
            
            meta_headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
            if token:
                meta_headers['Authorization'] = f'Bearer {token}'
            elif api_key:
                meta_headers['X-Api-Key'] = api_key
            
            self.logger(f"Storing metadata...")
            meta_url = f"{self.api_base.rstrip('/')}/api/cv-capture/metadata"
            self.logger(f"Metadata URL: {meta_url}")
            meta_resp = requests.post(
                meta_url,
                json=metadata,
                headers=meta_headers,
                timeout=30,
                verify=False,  # Disable SSL verification for self-signed certs
                allow_redirects=False  # Don't follow redirects that might convert POST to GET
            )
            
            if meta_resp.status_code in (401, 403) and token and api_key:
                try:
                    self.logger("Metadata unauthorized with Bearer, retrying with API key")
                    meta_headers_retry = {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'X-Api-Key': api_key
                    }
                    meta_resp = requests.post(
                        meta_url,
                        json=metadata,
                        headers=meta_headers_retry,
                        timeout=30,
                        verify=False,  # Disable SSL verification for self-signed certs
                        allow_redirects=False  # Don't follow redirects that might convert POST to GET
                    )
                except Exception:
                    pass
            
            if meta_resp.status_code not in [200, 201]:
                self.logger(f"Metadata store failed for {file_name}: {meta_resp.status_code} - {meta_resp.text}")
                return False
            
            meta_data = meta_resp.json()
            if not meta_data.get('success'):
                self.logger(f"Metadata error: {meta_data.get('error', {}).get('message', 'Unknown error')}")
                return False
            
            # Mark as processed
            self.processed_files[file_path] = file_hash
            self.logger(f"Successfully uploaded: {file_name} ({file_size / 1024:.1f}KB)")
            # Record for tray history and emit Notify line for Electron toast
            try:
                self._record_upload_history(file_name, file_size, file_path)
                self._emit_notify(f"CV Uploaded - {file_name}")
            except Exception as _e_hist:
                self.logger(f"Upload history/notify error: {_e_hist}")
            return True
        
        except requests.exceptions.RequestException as e:
            self.logger(f"Network error uploading {file_path}: {e}")
            return False
        except Exception as e:
            self.logger(f"Error uploading {file_path}: {e}")
            return False

    def _read_auth_token_from_config(self) -> Optional[str]:
        """Read auth_token from monitor_data/config.json if present."""
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'monitor_data'))
            cfg_path = os.path.join(base_dir, 'config.json')
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f) or {}
                dm = (cfg or {}).get('download_monitor', {})
                tok = dm.get('auth_token')
                return tok
        except Exception:
            return None
        return None

    def _read_api_key_from_config(self) -> Optional[str]:
        """Read api_key from monitor_data/config.json if present."""
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'monitor_data'))
            cfg_path = os.path.join(base_dir, 'config.json')
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f) or {}
                dm = (cfg or {}).get('download_monitor', {})
                key = dm.get('api_key')
                return key
        except Exception:
            return None
        return None

    def _record_upload_history(self, file_name: str, file_size: int, file_path: str):
        """Append upload entry to monitor_data/cv_uploads.json (retain last 50)."""
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'monitor_data'))
        os.makedirs(base_dir, exist_ok=True)
        hist_path = os.path.join(base_dir, 'cv_uploads.json')
        try:
            data: List[Dict] = []
            if os.path.exists(hist_path):
                with open(hist_path, 'r', encoding='utf-8') as f:
                    data = json.load(f) or []
            entry = {
                'ts': datetime.now().isoformat(),
                'file_name': file_name,
                'file_size': file_size,
                'path': file_path,
                'emp_id': self.emp_id
            }
            data.append(entry)
            # Keep only last 50
            data = data[-50:]
            with open(hist_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger(f"Failed to write upload history: {e}")

    def _emit_notify(self, message: str):
        """Emit notification via alerts.log and Windows toast."""
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'monitor_data'))
            os.makedirs(base_dir, exist_ok=True)
            alerts_path = os.path.join(base_dir, 'alerts.log')
            ts = datetime.now().isoformat()
            line = f"[{ts}] Notify: CV Upload - {message}\n"
            with open(alerts_path, 'a', encoding='utf-8') as f:
                f.write(line)
            
            # Also try to show Windows toast notification
            try:
                from win10toast import ToastNotifier
                toaster = ToastNotifier()
                toaster.show_toast(
                    "Naukri File Detected",
                    message,
                    duration=10,
                    threaded=True
                )
            except Exception:
                pass  # Toast notification is optional
        except Exception as e:
            # Fallback to stdout
            self.logger(f"Notify write failed: {e}")
    
    def _scan_downloads(self):
        """Scan download paths for new files."""
        try:
            for download_path in self.download_paths:
                if not os.path.exists(download_path):
                    continue
                
                try:
                    for entry in os.listdir(download_path):
                        file_path = os.path.join(download_path, entry)
                        
                        # Skip directories and hidden files
                        if os.path.isdir(file_path) or entry.startswith('.'):
                            continue
                        
                        # Check if file is ready and should be uploaded
                        if self._is_file_ready(file_path) and self._should_upload(file_path):
                            self.logger(f"Found new file: {entry}")
                            # Emit immediate detection notification (independent of upload)
                            try:
                                self._emit_notify(f"Detected Naukri file: {entry}")
                            except Exception:
                                pass
                            # Mark as processed for this run to avoid repeated notifications
                            try:
                                fhash = self._get_file_hash(file_path)
                                if fhash:
                                    self.processed_files[file_path] = fhash
                            except Exception:
                                pass
                            # Attempt upload (may fail if no auth; that's OK)
                            self._upload_file(file_path)
                
                except PermissionError:
                    pass
                except Exception as e:
                    self.logger(f"Error scanning {download_path}: {e}")
        
        except Exception as e:
            self.logger(f"Scan error: {e}")
    
    def run(self):
        """Main monitoring loop."""
        if not self.enabled:
            self.logger("Download monitor disabled in config")
            return
        
        # Auth token is optional - can be read from config or environment
        if not self.auth_token:
            self.auth_token = self._read_auth_token_from_config() or os.environ.get('CV_CAPTURE_AUTH_TOKEN')
        
        if not self.auth_token:
            self.logger("Warning: No auth token found. File uploads will fail, but scanning continues.")
        
        self.logger(f"Starting download monitor (interval: {self.check_interval}s)")
        
        while not self.stop_event.is_set():
            try:
                self._scan_downloads()
            except Exception as e:
                self.logger(f"Monitor error: {e}")
            
            # Sleep in small chunks to allow quick stop
            for _ in range(self.check_interval):
                if self.stop_event.is_set():
                    break
                time.sleep(1)
    
    def start(self):
        """Start monitoring in background thread."""
        if self.thread and self.thread.is_alive():
            return
        
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        self.logger("Monitor thread started")
    
    def stop(self):
        """Stop monitoring."""
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        self.logger("Monitor stopped")
