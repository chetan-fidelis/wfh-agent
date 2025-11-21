"""
Download Monitor v2 - Simplified, bulletproof implementation.
Monitors Naukri downloads and uploads to ATS API with explicit debugging.
"""

import os
import sys
import time
import json
import threading
import hashlib
from pathlib import Path
from typing import Dict, Optional, Set
from datetime import datetime
import requests
import urllib3

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class DownloadMonitorV2:
    """Simplified, bulletproof download monitor with explicit debugging."""
    
    def __init__(self, config: Dict, emp_id: int):
        """Initialize monitor."""
        self.config = config
        self.emp_id = emp_id
        self.stop_event = threading.Event()
        self.thread = None
        self.processed_hashes: Set[str] = set()
        
        # Config
        dm = config.get('download_monitor', {})
        self.enabled = dm.get('enabled', False)
        api_url = dm.get('api_url', 'https://nexoleats.fidelisam.in/api')
        # Remove trailing /api if present, then remove trailing slash
        if api_url.endswith('/api'):
            self.api_url = api_url[:-4]  # Remove '/api'
        else:
            self.api_url = api_url.rstrip('/')
        self.api_key = dm.get('api_key', '')
        self.auth_token = dm.get('auth_token', '')
        self.check_interval = int(dm.get('check_interval_sec', 30))
        self.max_size_mb = int(dm.get('max_file_size_mb', 100))
        # Extensions (normalized to dot-lowercase)
        cfg_ext = dm.get('extensions') or []
        if isinstance(cfg_ext, str):
            cfg_ext = [cfg_ext]
        self.extensions = set([e.lower() if e.startswith('.') else f'.{e.lower()}' for e in cfg_ext])
        if not self.extensions:
            self.extensions = {'.pdf', '.docx', '.doc', '.txt'}
        
        # Paths to monitor
        self.download_paths = self._get_download_paths(dm)
        self.log(f"Init: enabled={self.enabled}, api_url={self.api_url}, paths={len(self.download_paths)}")
    
    def log(self, msg: str):
        """Log to console and alerts.log."""
        ts = datetime.now().isoformat()
        line = f"[{ts}] [DownloadMonitor] {msg}"
        print(line)
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'monitor_data'))
            os.makedirs(base_dir, exist_ok=True)
            with open(os.path.join(base_dir, 'alerts.log'), 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except Exception as e:
            print(f"[DownloadMonitor] Log write failed: {e}")
    
    def _get_download_paths(self, dm_cfg: Dict) -> Set[str]:
        """Get all download paths to monitor (merge user system defaults with config)."""
        paths = set()
        if sys.platform != 'win32':
            return paths
        
        try:
            home = os.path.expanduser('~')
            candidates = [
                os.path.join(home, 'Downloads'),
                os.path.join(home, 'Desktop'),
                os.path.join(home, 'AppData', 'Local', 'Google', 'Chrome', 'User Data', 'Default', 'Downloads'),
                os.path.join(home, 'AppData', 'Local', 'Microsoft', 'Edge', 'User Data', 'Default', 'Downloads'),
            ]
            for p in candidates:
                if os.path.exists(p):
                    paths.add(p)
            # Merge config-defined paths (string or list)
            cfg_paths = dm_cfg.get('paths')
            if isinstance(cfg_paths, str):
                cfg_paths = [cfg_paths]
            if isinstance(cfg_paths, (list, tuple)):
                for p in cfg_paths:
                    if not p:
                        continue
                    pp = str(p)
                    if os.path.exists(pp):
                        paths.add(pp)
        except Exception as e:
            self.log(f"Error getting download paths: {e}")
        
        return paths
    
    def start(self):
        """Start monitor thread."""
        if not self.enabled:
            self.log("Monitor disabled, not starting")
            return
        
        if self.thread and self.thread.is_alive():
            self.log("Monitor already running")
            return
        
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.log("Monitor thread started")
    
    def stop(self):
        """Stop monitor thread."""
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        self.log("Monitor stopped")
    
    def _run(self):
        """Main monitor loop."""
        self.log(f"Monitor loop started. Scanning {len(self.download_paths)} paths every {self.check_interval}s")
        while not self.stop_event.is_set():
            try:
                self._scan_and_upload()
            except Exception as e:
                self.log(f"Scan error: {e}")
            
            self.stop_event.wait(self.check_interval)
    
    def _scan_and_upload(self):
        """Scan paths and upload matching files."""
        for path in self.download_paths:
            if not os.path.exists(path):
                continue
            
            try:
                for entry in os.listdir(path):
                    if not entry.startswith('Naukri_'):
                        continue
                    
                    ext = os.path.splitext(entry)[1].lower()
                    if ext not in self.extensions:
                        continue
                    
                    full_path = os.path.join(path, entry)
                    if not os.path.isfile(full_path):
                        continue
                    
                    # Check file size
                    size_mb = os.path.getsize(full_path) / (1024 * 1024)
                    if size_mb > self.max_size_mb:
                        self.log(f"File too large: {entry} ({size_mb:.1f}MB > {self.max_size_mb}MB)")
                        continue
                    
                    # Compute hash
                    file_hash = self._hash_file(full_path)
                    if file_hash in self.processed_hashes:
                        self.log(f"Already processed: {entry}")
                        continue
                    
                    # Check if file is ready (not being written)
                    if not self._is_file_ready(full_path):
                        self.log(f"File not ready (still writing): {entry}")
                        continue
                    
                    # Detected qualifying file
                    self.log(f"Found file: {entry} ({size_mb:.1f}MB)")
                    # Emit immediate detection notice for UI toast
                    try:
                        self._emit_detect_notify(entry)
                    except Exception:
                        pass
                    # Mark as processed on detection to avoid repeated notifications in same run
                    self.processed_hashes.add(file_hash)
                    # Attempt upload (best-effort)
                    if self._upload_file(full_path, entry):
                        self.log(f"SUCCESS: {entry}")
                    else:
                        self.log(f"FAILED: {entry}")
            
            except Exception as e:
                self.log(f"Scan path error ({path}): {e}")
    
    def _hash_file(self, path: str) -> str:
        """Compute SHA256 hash of file."""
        try:
            sha = hashlib.sha256()
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    sha.update(chunk)
            return sha.hexdigest()
        except Exception as e:
            self.log(f"Hash error: {e}")
            return ""
    
    def _is_file_ready(self, path: str) -> bool:
        """Check if file is fully written."""
        try:
            with open(path, 'rb'):
                pass
            return True
        except Exception:
            return False
    
    def _get_mime_type(self, file_path: str) -> str:
        """Get MIME type for file."""
        ext = os.path.splitext(file_path)[1].lower()
        mime_types = {
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.txt': 'text/plain',
            '.rtf': 'text/rtf',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        }
        return mime_types.get(ext, 'application/octet-stream')
    
    def _upload_file(self, file_path: str, file_name: str) -> bool:
        """Upload file to ATS API."""
        try:
            file_size = os.path.getsize(file_path)
            file_hash = self._hash_file(file_path)
            file_type = self._get_mime_type(file_path)
            
            # Get auth header
            headers = {'Accept': 'application/json'}
            if self.auth_token:
                headers['Authorization'] = f'Bearer {self.auth_token}'
                self.log(f"Using Bearer token auth")
            elif self.api_key:
                headers['X-Api-Key'] = self.api_key
                self.log(f"Using API key auth")
            else:
                self.log(f"No auth token or API key configured")
                return False
            
            # Step 1: Get presigned URL with all required fields
            self.log(f"Requesting presign for {file_name}...")
            presign_url = f"{self.api_url.rstrip('/')}/api/cv-capture/presign"
            self.log(f"Presign URL: {presign_url}")
            presign_payload = {
                "file_name": file_name,
                "file_size": file_size,
                "file_type": file_type,
                "sha256": file_hash,
                "source": "download"
            }
            presign_resp = requests.post(
                presign_url,
                json=presign_payload,
                headers=headers,
                timeout=30,
                verify=False,  # Disable SSL verification for self-signed certs
                allow_redirects=False  # Don't follow redirects that might convert POST to GET
            )
            
            self.log(f"Presign response: {presign_resp.status_code}")
            self.log(f"Presign response headers: {dict(presign_resp.headers)}")
            if presign_resp.status_code != 200:
                self.log(f"Presign failed: {presign_resp.text[:500]}")
                return False
            
            presign_data = presign_resp.json()
            if not presign_data.get('success'):
                self.log(f"Presign error: {presign_data.get('error', {}).get('message', 'Unknown error')}")
                return False
            
            s3_url = presign_data.get('data', {}).get('url')
            s3_key = presign_data.get('data', {}).get('key')
            if not s3_url:
                self.log(f"No S3 URL in presign response")
                return False
            
            # Step 2: Upload to S3
            self.log(f"Uploading to S3...")
            with open(file_path, 'rb') as f:
                s3_resp = requests.put(
                    s3_url,
                    data=f,
                    headers={'Content-Type': file_type},
                    timeout=30
                )
            
            self.log(f"S3 upload response: {s3_resp.status_code}")
            if s3_resp.status_code not in [200, 204]:
                self.log(f"S3 upload failed: {s3_resp.text}")
                return False
            
            # Step 3: Store metadata with all required fields
            self.log(f"Storing metadata...")
            meta_url = f"{self.api_url.rstrip('/')}/api/cv-capture/metadata"
            metadata = {
                "s3_key": s3_key,
                "file_name": file_name,
                "file_size": file_size,
                "file_type": file_type,
                "sha256": file_hash,
                "source": "download"
            }
            meta_resp = requests.post(
                meta_url,
                json=metadata,
                headers=headers,
                timeout=30,
                verify=False,  # Disable SSL verification for self-signed certs
                allow_redirects=False  # Don't follow redirects that might convert POST to GET
            )
            
            self.log(f"Metadata response: {meta_resp.status_code}")
            if meta_resp.status_code not in [200, 201]:
                self.log(f"Metadata store failed: {meta_resp.text}")
                return False
            
            meta_data = meta_resp.json()
            if not meta_data.get('success'):
                self.log(f"Metadata error: {meta_data.get('error', {}).get('message', 'Unknown error')}")
                return False
            
            # Success - write history and notify
            self._write_history(file_name, file_size)
            self._emit_notify(file_name)
            return True
        
        except Exception as e:
            self.log(f"Upload error: {e}")
            return False
    
    def _write_history(self, file_name: str, file_size: int):
        """Write to cv_uploads.json in per-user Electron userData directory."""
        try:
            # Use Electron's userData directory for per-user history
            # Windows: %APPDATA%\wfh-agent-desktop\monitor_data\cv_uploads.json
            # macOS: ~/Library/Application Support/wfh-agent-desktop/monitor_data/cv_uploads.json
            # Linux: ~/.config/wfh-agent-desktop/monitor_data/cv_uploads.json
            if sys.platform == 'win32':
                app_name = 'wfh-agent-desktop'
                user_data = os.path.join(os.environ.get('APPDATA', ''), app_name)
            elif sys.platform == 'darwin':
                app_name = 'wfh-agent-desktop'
                user_data = os.path.join(os.path.expanduser('~/Library/Application Support'), app_name)
            else:  # Linux
                app_name = 'wfh-agent-desktop'
                user_data = os.path.join(os.path.expanduser('~/.config'), app_name)
            
            base_dir = os.path.join(user_data, 'monitor_data')
            os.makedirs(base_dir, exist_ok=True)
            hist_path = os.path.join(base_dir, 'cv_uploads.json')
            
            data = []
            if os.path.exists(hist_path):
                try:
                    with open(hist_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:
                            data = json.loads(content) or []
                        else:
                            data = []
                except Exception:
                    # Corrupted or partial file; start fresh
                    data = []
            
            data.append({
                'ts': datetime.now().isoformat(),
                'file_name': file_name,
                'file_size': file_size,
                'emp_id': self.emp_id
            })
            data = data[-50:]  # Keep last 50
            
            with open(hist_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.log(f"History write error: {e}")
    
    def _emit_notify(self, file_name: str):
        """Write Notify line for Electron toast."""
        return

    def _emit_detect_notify(self, file_name: str):
        """Write detection Notify line so the Electron app can toast immediately."""
        return
