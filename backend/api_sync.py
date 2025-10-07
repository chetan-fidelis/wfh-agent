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
        self.timeout = 30  # seconds

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

                heartbeat_records.append({
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
                    'country': geo.get('country') if geo else None,
                    'ip_address': geo.get('ip') if geo else None
                })
                record_ids.append(rec_id)

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
        """Sync work sessions from JSON file to API"""
        if not os.path.exists(sessions_file):
            return 0

        try:
            with open(sessions_file, 'r', encoding='utf-8') as f:
                sessions = json.load(f)

            if not sessions:
                return 0

            # Prepare sessions for API
            session_records = []
            for session in sessions:
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

                session_records.append({
                    'emp_id': emp_id,
                    'start_ts': session['start_ts'],
                    'end_ts': session['end_ts'],
                    'breaks': json.dumps(session.get('breaks', [])),
                    'work_ms': work_ms,
                    'break_ms': break_ms,
                    'total_ms': total_ms
                })

            if not session_records:
                return 0

            # Send to API
            if self._make_request('/api/ingest/work_sessions', {
                'emp_id': emp_id,
                'records': session_records
            }):
                self.log(f"Synced {len(session_records)} work sessions to API")

                # Clear synced sessions from file
                with open(sessions_file, 'w', encoding='utf-8') as f:
                    json.dump([], f)

                return len(session_records)
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

    def _upload_screenshot_file(self, file_path: str, file_name: str, emp_id: int, captured_at: str) -> bool:
        """Upload a single screenshot file to the API"""
        try:
            with open(file_path, 'rb') as f:
                files = {'file': (file_name, f, 'image/jpeg')}
                data = {
                    'emp_id': emp_id,
                    'timestamp': captured_at,
                    'captured_at': captured_at
                }

                response = requests.post(
                    f"{self.base_url}/api/upload/screenshot",
                    files=files,
                    data=data,
                    headers={'X-Api-Key': self.api_key},
                    timeout=self.timeout
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
