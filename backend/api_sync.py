"""
API-based data synchronization for WFH Agent
Syncs local SQLite data to remote ingestion server via REST API
"""

import os
import json
import sqlite3
import threading
import requests
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any


class APISync:
    """Syncs local SQLite data to remote API server"""

    def __init__(self, db_path: str, config: Dict, app_ref=None):
        self.db_path = db_path
        self.config = config
        self.app_ref = app_ref
        self.sync_lock = threading.Lock()
        
        # Data validation settings
        self.validation_enabled = config.get('data_validation', {}).get('enabled', True)
        self.max_timestamp_age_days = config.get('data_validation', {}).get('max_timestamp_age_days', 7)

        # Get API configuration
        ing_cfg = config.get('ingestion', {})
        api_cfg = ing_cfg.get('api', {})

        self.base_url = api_cfg.get('base_url', '').rstrip('/')
        self.auth_header = api_cfg.get('auth_header', 'X-Api-Key')
        self.auth_env = api_cfg.get('auth_env', 'WFH_AGENT_API_KEY')

        # Try environment variable first, then config fallback
        env_key = os.environ.get(self.auth_env, '')
        config_key = api_cfg.get('api_key', '')
        self.api_key = env_key or config_key

        self.batch_size = ing_cfg.get('batch_size', 200)
        self.timeout = 30  # seconds for API requests
        self.screenshot_timeout = 90  # seconds for screenshot uploads (larger files)

        # Validate and log configuration
        if not self.base_url:
            self.log("Warning: API base_url not configured")

        if self.api_key:
            key_source = "environment" if env_key else "config"
            key_preview = self.api_key[:8] + "..." if len(self.api_key) > 8 else "***"
            self.log(f"API key loaded from {key_source}: {key_preview}")
        else:
            self.log(f"ERROR: API key not found in environment variable {self.auth_env} or config")

    def log(self, message: str):
        """Log message"""
        if self.app_ref and hasattr(self.app_ref, 'log'):
            self.app_ref.log(message)
        else:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{timestamp}] [APISync] {message}")
    
    def validate_heartbeat_record(self, record: Dict) -> bool:
        """Validate heartbeat record before sync"""
        if not self.validation_enabled:
            return True
        
        try:
            # Check required fields
            required_fields = ['emp_id', 'ts', 'cpu_percent', 'mem_percent']
            for field in required_fields:
                if field not in record:
                    self.log(f"Validation failed: Missing field '{field}'")
                    return False
            
            # Validate emp_id
            if not isinstance(record['emp_id'], int) or record['emp_id'] <= 0:
                self.log(f"Validation failed: Invalid emp_id {record.get('emp_id')}")
                return False
            
            # Validate timestamp
            try:
                ts = datetime.fromisoformat(record['ts'].replace('Z', '+00:00'))
                now = datetime.now(ts.tzinfo or None)
                
                # Check timestamp is not in future
                if ts > now:
                    self.log(f"Validation failed: Future timestamp {record['ts']}")
                    return False
                
                # Check timestamp is not too old
                age_days = (now - ts).days
                if age_days > self.max_timestamp_age_days:
                    self.log(f"Validation failed: Timestamp too old ({age_days} days)")
                    return False
            except Exception as e:
                self.log(f"Validation failed: Invalid timestamp format {record['ts']}: {e}")
                return False
            
            # Validate percentages
            if not (0 <= record.get('cpu_percent', -1) <= 100):
                self.log(f"Validation failed: Invalid cpu_percent {record.get('cpu_percent')}")
                return False
            if not (0 <= record.get('mem_percent', -1) <= 100):
                self.log(f"Validation failed: Invalid mem_percent {record.get('mem_percent')}")
                return False
            
            return True
            
        except Exception as e:
            self.log(f"Validation error: {e}")
            return False

    def _make_request(self, endpoint: str, data: Dict) -> bool:
        """Make API request with authentication"""
        if not self.base_url:
            self.log(f"ERROR: No base_url configured")
            return False

        if not self.api_key:
            self.log(f"ERROR: No API key available for request to {endpoint}")
            return False

        url = f"{self.base_url}{endpoint}"
        headers = {
            self.auth_header: self.api_key,
            'Content-Type': 'application/json'
        }

        # Debug log
        key_preview = self.api_key[:12] + "..." if len(self.api_key) > 12 else self.api_key
        self.log(f"Sending to {url} with {self.auth_header}: {key_preview}")

        try:
            response = requests.post(
                url,
                json=data,
                headers=headers,
                timeout=self.timeout
            )

            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    return True
                else:
                    self.log(f"API error: {result.get('error', 'Unknown error')}")
                    return False
            else:
                try:
                    error_detail = response.json()
                    self.log(f"API ingest failed: HTTP {response.status_code} {error_detail}")
                except:
                    self.log(f"API ingest failed: HTTP {response.status_code}")
                return False

        except requests.exceptions.RequestException as e:
            self.log(f"API request error: {e}")
            return False

    def sync_heartbeat(self, emp_id: int) -> int:
        """Sync unsynced heartbeat data to API"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Get unsynced records
            cursor.execute("""
                SELECT id, emp_id, ts, status, cpu_percent, memory_percent,
                       process_name, window_title, domain, url, battery_level,
                       battery_plugged, geo
                FROM heartbeat
                WHERE emp_id = ? AND synced = 0
                ORDER BY ts DESC
                LIMIT ?
            """, (emp_id, self.batch_size))

            records = cursor.fetchall()
            if not records:
                return 0

            # Prepare payload
            heartbeat_records = []
            record_ids = []

            for row in records:
                (rec_id, emp_id, ts, status, cpu_percent, memory_percent,
                 process_name, window_title, domain, url, battery_level,
                 battery_plugged, geo_json) = row

                # Parse geo JSON if present
                geo = None
                if geo_json:
                    try:
                        geo = json.loads(geo_json) if isinstance(geo_json, str) else geo_json
                    except:
                        pass

                record_data = {
                    'emp_id': emp_id,
                    'ts': ts,
                    'cpu_percent': cpu_percent or 0.0,
                    'mem_percent': memory_percent or 0.0,
                    'net_sent_mb': 0.0,  # Not stored in SQLite
                    'net_recv_mb': 0.0,  # Not stored in SQLite
                    'fg_app': process_name or '',
                    'fg_title': window_title or '',
                    'idle_sec': 0 if status == 'active' else 60,
                    'active': status == 'active',
                    'day_active_sec': 0,  # Calculated on server
                    'day_idle_sec': 0,    # Calculated on server
                    'work_location': 'remote',  # Default
                    'battery_percent': battery_level,
                    'battery_plugged': bool(battery_plugged) if battery_plugged is not None else None,
                    'geo': geo_json if geo_json else None  # Send geo as JSON string
                }
                
                # Validate record before adding
                if self.validate_heartbeat_record(record_data):
                    heartbeat_records.append(record_data)
                    record_ids.append(rec_id)
                else:
                    self.log(f"Skipping invalid heartbeat record id={rec_id}")

            # Send to API
            if self._make_request('/api/ingest/heartbeat', {
                'emp_id': emp_id,
                'records': heartbeat_records
            }):
                # Mark as synced
                placeholders = ','.join('?' * len(record_ids))
                cursor.execute(f"UPDATE heartbeat SET synced = 1 WHERE id IN ({placeholders})", record_ids)
                conn.commit()

                self.log(f"Synced {len(records)} heartbeat records to API")
                return len(records)
            else:
                self.log("Failed to sync heartbeat records")
                return 0

        except Exception as e:
            self.log(f"Error syncing heartbeat: {e}")
            return 0
        finally:
            conn.close()

    def sync_website_usage(self, emp_id: int, usage_file: str = None) -> int:
        """Sync website usage data to API from JSON file or SQLite"""

        # Try JSON file first (current implementation)
        if usage_file and os.path.exists(usage_file):
            try:
                with open(usage_file, 'r', encoding='utf-8') as f:
                    usage_data = json.load(f)

                if not usage_data or not isinstance(usage_data, dict):
                    return 0

                # Prepare records from JSON format
                usage_records = []
                today = datetime.now().strftime('%Y-%m-%d')

                for domain, duration_sec in usage_data.items():
                    if duration_sec > 0:
                        usage_records.append({
                            'emp_id': emp_id,
                            'date': today,
                            'domain': domain,
                            'duration_sec': int(duration_sec),
                            'visit_count': 1,
                            'tag': 'neutral'  # Default tag, can be enhanced later
                        })

                if not usage_records:
                    return 0

                # Send to API
                if self._make_request('/api/ingest/website_usage', {
                    'emp_id': emp_id,
                    'records': usage_records
                }):
                    # Don't clear file - let data accumulate throughout the day
                    # Server will handle updates via ON CONFLICT
                    self.log(f"Synced {len(usage_records)} website usage records (accumulated)")
                    return len(usage_records)
                else:
                    return 0

            except Exception as e:
                self.log(f"Error syncing website usage from JSON: {e}")
                return 0

        # Fallback to SQLite (legacy mode)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT emp_id, date, domain, duration_seconds, tag
                FROM website_usage
                WHERE emp_id = ? AND synced = 0
                LIMIT ?
            """, (emp_id, self.batch_size))

            records = cursor.fetchall()
            if not records:
                return 0

            # Prepare payload
            usage_records = []
            for row in records:
                emp_id, date, domain, duration, tag = row
                usage_records.append({
                    'emp_id': emp_id,
                    'date': date,
                    'domain': domain,
                    'duration_sec': int(duration),
                    'visit_count': 1,
                    'tag': tag or 'neutral'
                })

            # Send to API
            if self._make_request('/api/ingest/website_usage', {
                'emp_id': emp_id,
                'records': usage_records
            }):
                # Mark as synced
                cursor.execute("""
                    UPDATE website_usage
                    SET synced = 1
                    WHERE emp_id = ? AND synced = 0
                """, (emp_id,))
                conn.commit()

                self.log(f"Synced {len(records)} website usage records to API")
                return len(records)
            else:
                return 0

        except Exception as e:
            self.log(f"Error syncing website usage: {e}")
            return 0
        finally:
            conn.close()

    def sync_work_sessions(self, emp_id: int, sessions_file: str) -> int:
        """Sync work sessions from JSON file to API.
        Marks synced sessions in-place instead of clearing the file, so the UI can show history.
        """
        if not os.path.exists(sessions_file):
            return 0

        try:
            with open(sessions_file, 'r', encoding='utf-8') as f:
                sessions = json.load(f) or []

            # Filter unsynced, valid sessions
            to_send = []
            for session in sessions:
                if session.get('synced'):
                    continue
                if not session.get('start_ts') or not session.get('end_ts'):
                    continue

                # Calculate durations
                start_ts = datetime.fromisoformat(session['start_ts'].replace('Z', '+00:00'))
                end_ts = datetime.fromisoformat(session['end_ts'].replace('Z', '+00:00'))
                total_ms = int((end_ts - start_ts).total_seconds() * 1000)

                # Calculate break duration
                break_ms = 0
                for brk in session.get('breaks', []):
                    if brk.get('start_ts') and brk.get('end_ts'):
                        brk_start = datetime.fromisoformat(brk['start_ts'].replace('Z', '+00:00'))
                        brk_end = datetime.fromisoformat(brk['end_ts'].replace('Z', '+00:00'))
                        break_ms += int((brk_end - brk_start).total_seconds() * 1000)

                work_ms = max(0, total_ms - break_ms)

                to_send.append({
                    'emp_id': emp_id,
                    'start_ts': session['start_ts'],
                    'end_ts': session['end_ts'],
                    'breaks': json.dumps(session.get('breaks', [])),
                    'work_ms': work_ms,
                    'break_ms': break_ms,
                    'total_ms': total_ms
                })

            if not to_send:
                return 0

            # Send to API
            if self._make_request('/api/ingest/work_sessions', {
                'emp_id': emp_id,
                'records': to_send
            }):
                self.log(f"Synced {len(to_send)} work sessions to API")

                # Mark those entries as synced and write back
                start_set = {rec['start_ts'] for rec in to_send}
                for s in sessions:
                    if s.get('start_ts') in start_set and s.get('end_ts'):
                        s['synced'] = True

                with open(sessions_file, 'w', encoding='utf-8') as f:
                    json.dump(sessions, f, indent=2)

                return len(to_send)
            else:
                return 0

        except Exception as e:
            self.log(f"Error syncing work sessions: {e}")
            return 0

    def upload_screenshot(self, emp_id: int, screenshot_path: str, timestamp: str) -> bool:
        """Upload screenshot to API server"""
        if not self.base_url or not self.api_key:
            return False

        if not os.path.exists(screenshot_path):
            self.log(f"Screenshot not found: {screenshot_path}")
            return False

        url = f"{self.base_url}/api/upload/screenshot"
        headers = {
            self.auth_header: self.api_key
        }

        try:
            with open(screenshot_path, 'rb') as f:
                files = {'file': f}
                data = {
                    'emp_id': emp_id,
                    'timestamp': timestamp
                }

                response = requests.post(
                    url,
                    files=files,
                    data=data,
                    headers=headers,
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    self.log(f"Screenshot uploaded successfully: {os.path.basename(screenshot_path)}")
                    return True
                else:
                    self.log(f"Screenshot upload failed: HTTP {response.status_code}")
                    return False

        except Exception as e:
            self.log(f"Screenshot upload error: {e}")
            return False

    def sync_productivity(self, emp_id: int, productivity_file: str = None) -> int:
        """Sync productivity by tag data from JSON"""
        if not productivity_file or not os.path.exists(productivity_file):
            return 0

        try:
            with open(productivity_file, 'r', encoding='utf-8') as f:
                productivity_data = json.load(f)

            if not productivity_data or not isinstance(productivity_data, dict):
                return 0

            # Prepare records - DB schema: emp_id, date, tag, duration_seconds
            # Note: DB doesn't have app_name column, only tag
            records = []
            today = datetime.now().strftime('%Y-%m-%d')

            for app, tags in productivity_data.items():
                for tag, duration_sec in tags.items():
                    if duration_sec > 0:
                        records.append({
                            'emp_id': emp_id,
                            'date': today,
                            'tag': tag,
                            'duration_seconds': int(duration_sec)
                        })

            if not records:
                return 0

            # Send to API
            if self._make_request('/api/ingest/batch', {
                'table': 'productivity_by_tag',
                'records': records
            }):
                # Don't clear file - let data accumulate throughout the day
                # Server will handle updates via ON CONFLICT
                self.log(f"Synced {len(records)} productivity records (accumulated)")
                return len(records)

            return 0

        except Exception as e:
            self.log(f"Error syncing productivity: {e}")
            return 0

    def sync_wellness(self, emp_id: int, wellness_file: str = None) -> int:
        """Sync wellness daily data from JSON"""
        if not wellness_file or not os.path.exists(wellness_file):
            return 0

        try:
            with open(wellness_file, 'r', encoding='utf-8') as f:
                wellness_data = json.load(f)

            if not wellness_data or not isinstance(wellness_data, dict):
                return 0

            # Prepare records - DB schema: emp_id, day, work_seconds, active_seconds, idle_seconds, break_seconds, utilization_ratio, wellness_flags, esg_metrics
            records = []
            for date, metrics in wellness_data.items():
                # Build wellness flags JSON
                wellness_flags = {
                    'underutilized': metrics.get('underutilized', False),
                    'overburdened': metrics.get('overburdened', False),
                    'burnout_risk': metrics.get('burnout_risk', False),
                    'steady_performer': metrics.get('steady_performer', False)
                }

                records.append({
                    'emp_id': emp_id,
                    'day': date,  # Column is 'day', not 'date'
                    'work_seconds': metrics.get('work_secs', 0),
                    'active_seconds': metrics.get('active_secs', 0),
                    'idle_seconds': metrics.get('idle_secs', 0),
                    'break_seconds': metrics.get('offline_secs', 0),  # Map offline to breaks
                    'utilization_ratio': metrics.get('utilization_percent', 0) / 100.0,  # Convert percent to ratio
                    'wellness_flags': json.dumps(wellness_flags),
                    'esg_metrics': json.dumps({})  # Empty for now
                })

            if not records:
                return 0

            # Send to API
            if self._make_request('/api/ingest/batch', {
                'table': 'wellness_daily',
                'records': records
            }):
                # Don't clear file - let data accumulate throughout the day
                # Server will handle updates via ON CONFLICT
                self.log(f"Synced {len(records)} wellness records (accumulated)")
                return len(records)

            return 0

        except Exception as e:
            self.log(f"Error syncing wellness: {e}")
            return 0

    def sync_itsm_tickets(self, emp_id: int, tickets_file: str = None) -> int:
        """Sync ITSM tickets from JSON"""
        if not tickets_file or not os.path.exists(tickets_file):
            return 0

        try:
            with open(tickets_file, 'r', encoding='utf-8') as f:
                tickets = json.load(f)

            if not tickets or not isinstance(tickets, list):
                return 0

            # Prepare records - DB schema: ticket_id, emp_id, created_at, ticket_type, severity, status, details, resolved_at
            records = []
            for ticket in tickets:
                records.append({
                    'ticket_id': ticket.get('id'),
                    'emp_id': emp_id,
                    'created_at': ticket.get('ts'),
                    'ticket_type': ticket.get('type'),
                    'severity': ticket.get('severity'),
                    'status': ticket.get('status', 'open'),
                    'details': json.dumps(ticket.get('details', {})),
                    'resolved_at': None  # Not in source data
                })

            if not records:
                return 0

            # Send to API
            if self._make_request('/api/ingest/batch', {
                'table': 'itsm_tickets',
                'records': records
            }):
                # Clear file after sync
                with open(tickets_file, 'w', encoding='utf-8') as f:
                    json.dump([], f)

                self.log(f"Synced {len(records)} ITSM tickets")
                return len(records)

            return 0

        except Exception as e:
            self.log(f"Error syncing ITSM tickets: {e}")
            return 0

    def sync_timeline(self, emp_id: int, timeline_file: str = None) -> int:
        """Sync timeline data from JSON"""
        if not timeline_file or not os.path.exists(timeline_file):
            return 0

        try:
            with open(timeline_file, 'r', encoding='utf-8') as f:
                timeline_data = json.load(f)

            if not timeline_data or not isinstance(timeline_data, dict):
                return 0

            # Prepare records - DB schema: emp_id, date, hour, status, duration_seconds
            # Need to transform from {date: {hour: {active, idle, offline}}} to separate rows per status
            records = []
            for date, hours in timeline_data.items():
                for hour, metrics in hours.items():
                    # Create separate records for each status type
                    if metrics.get('active', 0) > 0:
                        records.append({
                            'emp_id': emp_id,
                            'date': date,
                            'hour': int(hour),
                            'status': 'active',
                            'duration_seconds': metrics.get('active', 0)
                        })
                    if metrics.get('idle', 0) > 0:
                        records.append({
                            'emp_id': emp_id,
                            'date': date,
                            'hour': int(hour),
                            'status': 'idle',
                            'duration_seconds': metrics.get('idle', 0)
                        })
                    if metrics.get('offline', 0) > 0:
                        records.append({
                            'emp_id': emp_id,
                            'date': date,
                            'hour': int(hour),
                            'status': 'offline',
                            'duration_seconds': metrics.get('offline', 0)
                        })

            if not records:
                return 0

            # Send to API
            if self._make_request('/api/ingest/batch', {
                'table': 'timeline',
                'records': records
            }):
                # Don't clear file - let data accumulate throughout the day
                # Server will handle updates via ON CONFLICT
                self.log(f"Synced {len(records)} timeline records (accumulated)")
                return len(records)

            return 0

        except Exception as e:
            self.log(f"Error syncing timeline: {e}")
            return 0

    def sync_screenshots(self, emp_id: int) -> int:
        """Sync unsynced screenshot files to API"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Get unsynced screenshots
            cursor.execute("""
                SELECT id, emp_id, file_name, file_path, file_size, captured_at
                FROM screenshots
                WHERE emp_id = ? AND synced = 0
                ORDER BY captured_at DESC
                LIMIT ?
            """, (emp_id, self.batch_size))

            records = cursor.fetchall()
            if not records:
                return 0

            uploaded = 0

            for row in records:
                (rec_id, emp_id, file_name, file_path, file_size, captured_at) = row

                # Check if file exists locally
                if not os.path.exists(file_path):
                    self.log(f"Screenshot file not found: {file_path}")
                    continue

                # Upload file to API
                if self._upload_screenshot_file(file_path, file_name, emp_id, captured_at):
                    # Update synced status
                    cursor.execute("""
                        UPDATE screenshots
                        SET synced = 1
                        WHERE id = ?
                    """, (rec_id,))
                    uploaded += 1
                else:
                    self.log(f"Failed to upload screenshot: {file_name}")

            conn.commit()
            self.log(f"Uploaded {uploaded}/{len(records)} screenshot files")
            return uploaded

        except Exception as e:
            self.log(f"Error syncing screenshots: {e}")
            return 0
        finally:
            conn.close()

    def _upload_screenshot_file(self, file_path: str, file_name: str, emp_id: int, captured_at: str,
                                encrypt: bool = True) -> bool:
        """Upload a single screenshot file to the API with compression and optional encryption"""
        try:
            # Check if encryption is enabled in config
            ing_cfg = self.config.get('ingestion', {})
            screenshot_cfg = ing_cfg.get('screenshot', {})
            encrypt_enabled = screenshot_cfg.get('encrypt', True) and encrypt

            if encrypt_enabled:
                # Import encryption module
                try:
                    from screenshot_crypto import ScreenshotCrypto

                    # Get encryption key from config or use default
                    master_key = screenshot_cfg.get('encryption_key', None)
                    crypto = ScreenshotCrypto(master_key)

                    # Encrypt to memory with compression
                    encrypted_data, metadata = crypto.encrypt_to_memory(
                        file_path,
                        compress=True,
                        max_size=(1920, 1080),
                        quality=75
                    )

                    original_size = metadata.get('original_size', 0)
                    encrypted_size = metadata.get('encrypted_size', 0)

                    self.log(f"Screenshot encrypted & compressed: {original_size/1024:.1f}KB -> {encrypted_size/1024:.1f}KB")

                    # Upload encrypted data
                    import io
                    buffer = io.BytesIO(encrypted_data)
                    files = {'file': (file_name + '.enc', buffer, 'application/octet-stream')}
                    data = {
                        'emp_id': emp_id,
                        'timestamp': captured_at,
                        'captured_at': captured_at,
                        'encrypted': True,
                        'encryption_version': metadata.get('encryption_version', '1.0.0'),
                        'metadata': json.dumps(metadata)
                    }

                except ImportError:
                    self.log("Encryption module not available, falling back to compression only")
                    encrypt_enabled = False

            # Fallback to compression only (original behavior)
            if not encrypt_enabled:
                import io
                from PIL import Image

                # Compress image before upload to reduce size and prevent timeouts
                img = Image.open(file_path)

                # Convert RGBA to RGB if necessary
                if img.mode == 'RGBA':
                    img = img.convert('RGB')

                # Resize if too large (max 1920x1080)
                max_width, max_height = 1920, 1080
                if img.width > max_width or img.height > max_height:
                    img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

                # Compress to JPEG with quality 75 (good balance between size and quality)
                buffer = io.BytesIO()
                img.save(buffer, format='JPEG', quality=75, optimize=True)
                buffer.seek(0)

                original_size = os.path.getsize(file_path)
                compressed_size = buffer.getbuffer().nbytes
                compression_ratio = (1 - compressed_size / original_size) * 100

                self.log(f"Screenshot compressed: {original_size/1024:.1f}KB -> {compressed_size/1024:.1f}KB ({compression_ratio:.1f}% reduction)")

                files = {'file': (file_name, buffer, 'image/jpeg')}
                data = {
                    'emp_id': emp_id,
                    'timestamp': captured_at,
                    'captured_at': captured_at,
                    'encrypted': False
                }

            # Upload to API
            response = requests.post(
                f"{self.base_url}/api/upload/screenshot",
                files=files,
                data=data,
                headers={'X-Api-Key': self.api_key},
                timeout=self.screenshot_timeout  # Use longer timeout for uploads
            )

            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    return True
                else:
                    self.log(f"Screenshot upload failed: {result.get('error', 'Unknown error')}")
                    return False
            else:
                self.log(f"Screenshot upload HTTP error: {response.status_code}")
                return False

        except Exception as e:
            self.log(f"Screenshot file upload error: {e}")
            return False

    def sync_all(self, emp_id: int, sessions_file: str = None, usage_file: str = None,
                 productivity_file: str = None, wellness_file: str = None,
                 tickets_file: str = None, timeline_file: str = None) -> Dict[str, int]:
        """Sync all data types"""
        # Acquire lock to prevent concurrent syncs
        if not self.sync_lock.acquire(blocking=False):
            self.log("Sync already in progress, skipping")
            return {}

        try:
            results = {}

            # Sync heartbeat
            results['heartbeat'] = self.sync_heartbeat(emp_id)

            # Sync website usage (from JSON file or SQLite)
            results['website_usage'] = self.sync_website_usage(emp_id, usage_file)

            # Sync work sessions if file provided
            if sessions_file:
                results['work_sessions'] = self.sync_work_sessions(emp_id, sessions_file)

            # Sync productivity by tag
            if productivity_file:
                results['productivity'] = self.sync_productivity(emp_id, productivity_file)

            # Sync wellness daily
            if wellness_file:
                results['wellness'] = self.sync_wellness(emp_id, wellness_file)

            # Sync ITSM tickets
            if tickets_file:
                results['itsm_tickets'] = self.sync_itsm_tickets(emp_id, tickets_file)

            # Sync timeline
            if timeline_file:
                results['timeline'] = self.sync_timeline(emp_id, timeline_file)

            # Sync screenshots
            results['screenshots'] = self.sync_screenshots(emp_id)

            return results

        finally:
            self.sync_lock.release()

    def sync_heartbeat_incremental(self, emp_id: int, cursor_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Incremental sync for heartbeat data using cursor-based pagination
        Prevents memory issues with large datasets

        Args:
            emp_id: Employee ID
            cursor_id: Last synced record ID (None = start from beginning)

        Returns:
            Dict with 'synced_count', 'last_cursor', 'has_more'
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Get records after cursor
            if cursor_id is None:
                cursor.execute("""
                    SELECT id, emp_id, ts, status, cpu_percent, memory_percent,
                           process_name, window_title, domain, url, battery_level,
                           battery_plugged, geo
                    FROM heartbeat
                    WHERE emp_id = ? AND synced = 0
                    ORDER BY id ASC
                    LIMIT ?
                """, (emp_id, self.batch_size))
            else:
                cursor.execute("""
                    SELECT id, emp_id, ts, status, cpu_percent, memory_percent,
                           process_name, window_title, domain, url, battery_level,
                           battery_plugged, geo
                    FROM heartbeat
                    WHERE emp_id = ? AND synced = 0 AND id > ?
                    ORDER BY id ASC
                    LIMIT ?
                """, (emp_id, cursor_id, self.batch_size))

            records = cursor.fetchall()
            if not records:
                return {'synced_count': 0, 'last_cursor': cursor_id, 'has_more': False}

            # Prepare payload
            heartbeat_records = []
            record_ids = []
            last_id = cursor_id

            for row in records:
                (rec_id, emp_id, ts, status, cpu_percent, memory_percent,
                 process_name, window_title, domain, url, battery_level,
                 battery_plugged, geo_json) = row

                # Parse geo JSON if present
                geo = None
                if geo_json:
                    try:
                        geo = json.loads(geo_json) if isinstance(geo_json, str) else geo_json
                    except:
                        pass

                heartbeat_records.append({
                    'emp_id': emp_id,
                    'ts': ts,
                    'cpu_percent': cpu_percent or 0.0,
                    'mem_percent': memory_percent or 0.0,
                    'net_sent_mb': 0.0,
                    'net_recv_mb': 0.0,
                    'fg_app': process_name or '',
                    'fg_title': window_title or '',
                    'idle_sec': 0 if status == 'active' else 60,
                    'active': status == 'active',
                    'day_active_sec': 0,
                    'day_idle_sec': 0,
                    'work_location': 'remote',
                    'battery_percent': battery_level,
                    'battery_plugged': bool(battery_plugged) if battery_plugged is not None else None,
                    'geo': geo_json if geo_json else None
                })
                record_ids.append(rec_id)
                last_id = rec_id

            # Send to API
            if self._make_request('/api/ingest/heartbeat', {
                'emp_id': emp_id,
                'records': heartbeat_records
            }):
                # Mark as synced
                placeholders = ','.join('?' * len(record_ids))
                cursor.execute(f"UPDATE heartbeat SET synced = 1 WHERE id IN ({placeholders})", record_ids)
                conn.commit()

                # Check if more records exist
                cursor.execute("""
                    SELECT COUNT(*) FROM heartbeat
                    WHERE emp_id = ? AND synced = 0 AND id > ?
                """, (emp_id, last_id))
                has_more = cursor.fetchone()[0] > 0

                self.log(f"Incremental sync: {len(records)} heartbeat records, cursor={last_id}, has_more={has_more}")

                return {
                    'synced_count': len(records),
                    'last_cursor': last_id,
                    'has_more': has_more
                }
            else:
                return {'synced_count': 0, 'last_cursor': cursor_id, 'has_more': False, 'error': 'API request failed'}

        except Exception as e:
            self.log(f"Error in incremental heartbeat sync: {e}")
            return {'synced_count': 0, 'last_cursor': cursor_id, 'has_more': False, 'error': str(e)}
        finally:
            conn.close()

    def sync_all_incremental(self, emp_id: int) -> Dict[str, Any]:
        """
        Sync all unsynced data using incremental cursor-based approach
        Better for large datasets - prevents memory issues

        Returns:
            Dict with sync results for each data type
        """
        results = {}

        # Heartbeat sync with cursor
        cursor_id = None
        total_heartbeat = 0
        while True:
            result = self.sync_heartbeat_incremental(emp_id, cursor_id)
            total_heartbeat += result.get('synced_count', 0)
            cursor_id = result.get('last_cursor')

            if not result.get('has_more', False):
                break

        results['heartbeat'] = total_heartbeat
        self.log(f"Total heartbeat records synced incrementally: {total_heartbeat}")

        # Other syncs use existing methods (already optimized)
        results['screenshots'] = self.sync_screenshots(emp_id)

        return results

    def sync_all_consolidated(self, emp_id: int, sessions_file: str = None, usage_file: str = None,
                            productivity_file: str = None, wellness_file: str = None,
                            tickets_file: str = None, timeline_file: str = None) -> Dict[str, int]:
        """Sync all data types in a single consolidated batch API call to reduce server load.
        
        Instead of making 5+ separate API calls, this consolidates all data into one batch request.
        """
        results = {}
        
        try:
            # Collect all data types into a single payload
            batch_payload = {'emp_id': emp_id, 'data': {}}
            
            # Collect heartbeat data
            heartbeat_count = 0
            try:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT emp_id, ts, status, cpu_percent, memory_percent,
                           process_name, window_title, domain, url, battery_level,
                           battery_plugged, geo
                    FROM heartbeat
                    WHERE emp_id = ? AND synced = 0
                    ORDER BY ts DESC
                    LIMIT ?
                """, (emp_id, self.batch_size))
                
                records = cursor.fetchall()
                if records:
                    heartbeat_records = []
                    record_ids = []
                    for row in records:
                        (emp_id_rec, ts, status, cpu_percent, memory_percent,
                         process_name, window_title, domain, url, battery_level,
                         battery_plugged, geo_json) = row
                        
                        record_data = {
                            'ts': ts,
                            'cpu_percent': cpu_percent or 0.0,
                            'mem_percent': memory_percent or 0.0,
                            'fg_app': process_name or '',
                            'fg_title': window_title or '',
                            'idle_sec': 0 if status == 'active' else 60,
                            'active': status == 'active',
                            'battery_percent': battery_level,
                            'battery_plugged': bool(battery_plugged) if battery_plugged is not None else None,
                            'geo': geo_json if geo_json else None
                        }
                        heartbeat_records.append(record_data)
                        record_ids.append(row[0])
                    
                    if heartbeat_records:
                        batch_payload['data']['heartbeat'] = heartbeat_records
                        heartbeat_count = len(heartbeat_records)
                        # Mark as synced
                        placeholders = ','.join('?' * len(record_ids))
                        cursor.execute(f"UPDATE heartbeat SET synced = 1 WHERE rowid IN ({placeholders})", record_ids)
                        conn.commit()
                
                conn.close()
            except Exception as e:
                self.log(f"Error collecting heartbeat data: {e}")
            
            # Collect website usage data
            website_usage_count = 0
            if usage_file and os.path.exists(usage_file):
                try:
                    with open(usage_file, 'r', encoding='utf-8') as f:
                        usage_data = json.load(f)
                    if usage_data and isinstance(usage_data, dict):
                        usage_records = []
                        today = datetime.now().strftime('%Y-%m-%d')
                        for domain, duration_sec in usage_data.items():
                            if duration_sec > 0:
                                usage_records.append({
                                    'date': today,
                                    'domain': domain,
                                    'duration_sec': int(duration_sec),
                                    'tag': 'neutral'
                                })
                        if usage_records:
                            batch_payload['data']['website_usage'] = usage_records
                            website_usage_count = len(usage_records)
                except Exception as e:
                    self.log(f"Error collecting website usage: {e}")
            
            # Collect productivity data
            productivity_count = 0
            if productivity_file and os.path.exists(productivity_file):
                try:
                    with open(productivity_file, 'r', encoding='utf-8') as f:
                        productivity_data = json.load(f)
                    if productivity_data and isinstance(productivity_data, dict):
                        prod_records = []
                        today = datetime.now().strftime('%Y-%m-%d')
                        for app, tags in productivity_data.items():
                            for tag, duration_sec in tags.items():
                                if duration_sec > 0:
                                    prod_records.append({
                                        'date': today,
                                        'tag': tag,
                                        'duration_seconds': int(duration_sec)
                                    })
                        if prod_records:
                            batch_payload['data']['productivity'] = prod_records
                            productivity_count = len(prod_records)
                except Exception as e:
                    self.log(f"Error collecting productivity data: {e}")
            
            # Collect wellness data
            wellness_count = 0
            if wellness_file and os.path.exists(wellness_file):
                try:
                    with open(wellness_file, 'r', encoding='utf-8') as f:
                        wellness_data = json.load(f)
                    if wellness_data and isinstance(wellness_data, dict):
                        wellness_records = []
                        for date, data in wellness_data.items():
                            wellness_records.append({
                                'date': date,
                                'active_secs': data.get('active', 0),
                                'idle_secs': data.get('idle', 0),
                                'offline_secs': data.get('offline', 0),
                                'utilization_percent': data.get('utilization', 0)
                            })
                        if wellness_records:
                            batch_payload['data']['wellness'] = wellness_records
                            wellness_count = len(wellness_records)
                except Exception as e:
                    self.log(f"Error collecting wellness data: {e}")
            
            # Collect timeline data
            timeline_count = 0
            if timeline_file and os.path.exists(timeline_file):
                try:
                    with open(timeline_file, 'r', encoding='utf-8') as f:
                        timeline_data = json.load(f)
                    if timeline_data and isinstance(timeline_data, dict):
                        timeline_records = []
                        for date, hours in timeline_data.items():
                            for hour, data in hours.items():
                                timeline_records.append({
                                    'date': date,
                                    'hour': int(hour),
                                    'active': data.get('active', 0),
                                    'idle': data.get('idle', 0),
                                    'offline': data.get('offline', 0)
                                })
                        if timeline_records:
                            batch_payload['data']['timeline'] = timeline_records
                            timeline_count = len(timeline_records)
                except Exception as e:
                    self.log(f"Error collecting timeline data: {e}")
            
            # Send consolidated batch in single API call
            if batch_payload['data']:
                if self._make_request('/api/ingest/batch', batch_payload):
                    results['heartbeat'] = heartbeat_count
                    results['website_usage'] = website_usage_count
                    results['productivity'] = productivity_count
                    results['wellness'] = wellness_count
                    results['timeline'] = timeline_count
                    self.log(f"Consolidated batch sync: {sum(results.values())} total records in 1 API call")
                else:
                    self.log("Consolidated batch sync failed")
            else:
                self.log("No data to sync")
        
        except Exception as e:
            self.log(f"Error in consolidated sync: {e}")
        
        return results
