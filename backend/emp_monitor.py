import os
import sys
import time
import json
import copy
import threading
import queue
import shutil
import socket
import platform
import datetime as dt
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
import locale

# Third-party deps
from flask import Flask, send_file, jsonify, Response, request
import psutil
try:
    from waitress import serve
except Exception:
    serve = None
from PIL import Image
import mss
from pynput import keyboard, mouse
from urllib.parse import urlparse
import requests
try:
    from win10toast import ToastNotifier
except Exception:
    ToastNotifier = None
try:
    # Windows Runtime (WinRT) for Location API
    from winsdk.windows.devices.geolocation import Geolocator
except Exception:
    Geolocator = None
PSYCOPG_IMPORT_ERROR = None
try:
    import psycopg
    try:
        # Try different locations for execute_values in psycopg v3
        try:
            from psycopg.extras import execute_values
        except ImportError:
            try:
                from psycopg import sql
                execute_values = None  # Use fallback method
            except ImportError:
                execute_values = None
    except Exception as _e_execvals:
        execute_values = None
        PSYCOPG_IMPORT_ERROR = f"psycopg imported but execute_values missing: {_e_execvals}"
except Exception as _e_psycopg:
    psycopg = None
    execute_values = None
    PSYCOPG_IMPORT_ERROR = f"psycopg import failed: {_e_psycopg}"

try:
    import uiautomation as auto
except Exception:
    auto = None

try:
    import ctypes
    from ctypes import wintypes
except Exception:
    ctypes = None

try:
    import winreg as reg
except Exception:
    reg = None

try:
    import win32gui
    import win32process
    import win32con
except Exception:
    win32gui = None
    win32process = None
    win32con = None

# Constants & Config
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'monitor_data')
SESSIONS_DIR = os.path.join(DATA_DIR, 'sessions')
LOGS_DIR = os.path.join(DATA_DIR, 'logs')
CONFIG_PATH = os.path.join(DATA_DIR, 'config.json')
DEVICES_INFO_PATH = os.path.join(DATA_DIR, 'devices.json')
ALERTS_LOG = os.path.join(DATA_DIR, 'alerts.log')
LATEST_JPG = os.path.join(DATA_DIR, 'latest.jpg')
USAGE_JSON = os.path.join(DATA_DIR, 'usage.json')
WELLNESS_JSON = os.path.join(DATA_DIR, 'wellness.json')
TIMELINE_JSON = os.path.join(DATA_DIR, 'timeline.json')
WEBSITE_USAGE_JSON = os.path.join(DATA_DIR, 'website_usage.json')
WEBSITE_USAGE_BY_TAG_JSON = os.path.join(DATA_DIR, 'website_usage_by_tag.json')
HEARTBEAT_DIR = os.path.join(DATA_DIR, 'heartbeats')
ITSM_TICKETS_JSON = os.path.join(DATA_DIR, 'itsm_tickets.json')
ESG_DIR = os.path.join(DATA_DIR, 'esg')
SHOTS_DIR = os.path.join(DATA_DIR, 'shots')

SESSION_DURATION_SEC = 5 * 60  # 5 minutes
SCREEN_FPS = 1  # 1 frame per second
RETENTION_DAYS = 7
IDLE_THRESHOLD_SEC = 120  # if no keyboard/mouse activity for 2 minutes, consider idle
HOSTS_PATH = r"C:\\Windows\\System32\\drivers\\etc\\hosts"
HOSTS_MARKER_BEGIN = "# EMP_MONITOR BEGIN\n"
HOSTS_MARKER_END = "# EMP_MONITOR END\n"

DEFAULT_CONFIG = {
    "emp_id": 0,
    "work_hours": {"start": "09:30", "end": "18:30"},
    "blocked_domains": [
        # Add domains to block during work hours
        "facebook.com", "instagram.com", "twitter.com"
    ],
    "productivity_tags": {
        # process_name(lower): productive|unproductive|neutral
        "code.exe": "productive",
        "pycharm64.exe": "productive",
        "idea64.exe": "productive",
        "chrome.exe": "neutral",
        "msedge.exe": "neutral",
        "firefox.exe": "neutral",
        "spotify.exe": "unproductive",
        "steam.exe": "unproductive"
    },
    "website_tags": {
        # domain(lower) -> productive|unproductive|neutral
        # "stackoverflow.com": "productive",
        # "youtube.com": "unproductive"
    },
    "geo": {
        "mode": "ip",  # ip | ip_multi | windows | manual
        "manual": {
            # Example: fill these to override IP-based location
            # "ip": "",
            # "city": "Bengaluru",
            # "region": "Karnataka",
            # "country": "India",
            # "latitude": 12.9716,
            # "longitude": 77.5946,
            # "org": ""
        }
    },
    "wellness_thresholds": {
        "min_work_secs": 18000,           # 5 hours
        "overtime_secs": 32400,           # 9 hours
        "min_active_ratio": 0.5,          # >= 50% active
        "max_idle_ratio": 0.4,            # <= 40% idle
        "burnout_active_ratio": 0.7,      # > 70% active considered intense
        "bound_to_work_hours": True       # bound daily work secs to configured work hours
    },
    "break_window": {
        "start": "13:00",
        "duration_minutes": 60
    },
    "workdays": [1, 2, 3, 4, 5],  # Mon-Fri (isoweekday 1..7)
    "features": {
        "notifications": True,
        "itsm": True,
        "break": True,
        "domain_blocker": True,
        "screen_record": False,
        "usb_monitor": True,
        "website_tracking": True,
        "esg": True,
        "scheduled_shots": True
    }
    ,
    "itsm": {
        "enabled": True,
        "auto_heal": False,
        "high_cpu_threshold": 90,            # percent
        "high_cpu_duration_sec": 180,        # sustained duration
        "cooldowns": {                        # seconds to suppress duplicate tickets
            "high_cpu": 600,
            "network_disconnect": 600,
            "app_crash": 600
        },
        "network_check_urls": [
            "http://clients3.google.com/generate_204",
            "https://www.msftconnecttest.com/connecttest.txt"
        ],
        "watched_apps": ["code.exe"],       # critical apps to watch for crash
        "protected_processes": ["explorer.exe", "system", "wininit.exe"],
        "ticket_webhook": ""                # optional URL to POST new tickets
    },
    "esg": {
        # Simple model to estimate device energy and CO2e
        "power_watts_plugged": {  # on AC power
            "active": 28,
            "idle": 14
        },
        "power_watts_battery": {  # on battery saver profile
            "active": 22,
            "idle": 10
        },
        # Country-level kg CO2e per kWh (rough), fallback used if country unknown
        "co2_kg_per_kwh": {
            "default": 0.475,
            "India": 0.708
        }
    }
    ,
    "scheduled_shots": {
        "per_day": 2,
        "start": "09:30",
        "end": "18:30",
        "retention_days": 30
    }
    ,
    "ingestion": {
        "enabled": True,
        "mode": "postgres",             # file | postgres
        "file_retention_days": 30,       # how long to keep daily heartbeat files
        "batch_size": 200,               # max items per flush
        "flush_interval_sec": 5,         # flush cadence
        "sampling": {
            "state_change": True,        # emit on status/process/url change
            "periodic_sec": 60,          # periodic snapshot interval
            "active_burst_sec": 5,       # extra sampling during active
            "active_burst_cpu_percent": 50
        },
        "db": {
            "url_env": "EMP_DB_URL",    # environment var holding connection string
            "schema": "employee_monitor"
        }
    }
}

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(HEARTBEAT_DIR, exist_ok=True)
os.makedirs(ESG_DIR, exist_ok=True)
os.makedirs(SHOTS_DIR, exist_ok=True)
if not os.path.exists(ITSM_TICKETS_JSON):
    with open(ITSM_TICKETS_JSON, 'w', encoding='utf-8') as f:
        json.dump([], f)


@dataclass
class ActivityStats:
    key_presses: int = 0
    mouse_clicks: int = 0
    last_activity_ts: float = 0.0


class Alerts:
    lock = threading.Lock()

    @staticmethod
    def log(message: str):
        ts = dt.datetime.now().isoformat(timespec='seconds')
        line = f"[{ts}] {message}\n"
        with Alerts.lock:
            with open(ALERTS_LOG, 'a', encoding='utf-8') as f:
                f.write(line)
        print(line, end='')


def get_system_idle_seconds() -> Optional[float]:
    """Windows: seconds since last user input via GetLastInputInfo. Returns None if unavailable."""
    if ctypes is None:
        return None
    try:
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(lii)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return None
        tick_count = ctypes.windll.kernel32.GetTickCount()
        idle_ms = tick_count - lii.dwTime
        if idle_ms < 0:
            idle_ms = 0
        return idle_ms / 1000.0
    except Exception:
        return None


class Config:
    def __init__(self, path: str):
        self.path = path
        self.data = DEFAULT_CONFIG.copy()
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    on_disk = json.load(f)
                # merge shallow
                self.data.update(on_disk)
            except Exception as e:
                Alerts.log(f"Config load error: {e}")
        else:
            self.save()

    def save(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2)

    @property
    def work_hours(self) -> Tuple[dt.time, dt.time]:
        s = self.data.get('work_hours', {}).get('start', '09:00')
        e = self.data.get('work_hours', {}).get('end', '17:00')
        st = dt.datetime.strptime(s, '%H:%M').time()
        et = dt.datetime.strptime(e, '%H:%M').time()
        return st, et

    @property
    def blocked_domains(self) -> List[str]:
        return self.data.get('blocked_domains', [])

    @property
    def productivity_tags(self) -> Dict[str, str]:
        return self.data.get('productivity_tags', {})


class ScreenRecorder(threading.Thread):
    def __init__(self, activity: ActivityStats):
        super().__init__(daemon=True)
        self.activity = activity
        self.stop_event = threading.Event()
        self.sct = None  # initialize inside thread context to avoid cross-thread issues
        self.session_dir = None
        self.session_start = 0.0

    def rotate_session(self):
        now = time.time()
        if not self.session_dir or (now - self.session_start) >= SESSION_DURATION_SEC:
            # start new session folder
            self.session_start = now
            ts = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
            self.session_dir = os.path.join(SESSIONS_DIR, ts)
            os.makedirs(self.session_dir, exist_ok=True)
            Alerts.log(f"Started new screen session: {self.session_dir}")

    def capture_frame(self):
        frame_ts = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
        frame_path = os.path.join(self.session_dir, f"frame_{frame_ts}.jpg")
        # Lazily create MSS handle in this thread
        if self.sct is None:
            self.sct = mss.mss()
        img = self.sct.grab(self.sct.monitors[0])
        # Save via PIL for JPEG
        Image.frombytes('RGB', img.size, img.rgb).save(frame_path, 'JPEG', quality=70)
        # Update latest
        try:
            shutil.copyfile(frame_path, LATEST_JPG)
        except Exception:
            pass

    def cleanup_old_sessions(self):
        cutoff = time.time() - RETENTION_DAYS * 86400
        for name in os.listdir(SESSIONS_DIR):
            p = os.path.join(SESSIONS_DIR, name)
            try:
                if os.path.isdir(p):
                    ts = dt.datetime.strptime(name, '%Y%m%d_%H%M%S')
                    if ts.timestamp() < cutoff:
                        shutil.rmtree(p, ignore_errors=True)
                        Alerts.log(f"Deleted old session: {name}")
            except Exception:
                continue

    def run(self):
        next_frame = 0.0
        while not self.stop_event.is_set():
            try:
                self.rotate_session()
                now = time.time()
                if now >= next_frame:
                    self.capture_frame()
                    next_frame = now + 1.0 / max(1, SCREEN_FPS)
                # periodically cleanup
                if int(now) % 600 == 0:
                    self.cleanup_old_sessions()
            except Exception as e:
                Alerts.log(f"ScreenRecorder error: {e}")
            time.sleep(0.1)

    def stop(self):
        self.stop_event.set()
        # Ensure buffered records are flushed on shutdown
        try:
            self._buf.flush(force=True)
        except Exception:
            pass

class ScheduledShooter(threading.Thread):
    """Takes a small number of screenshots per day at random times within office hours when active and on workdays."""
    def __init__(self, app_ref: 'MonitorApp'):
        super().__init__(daemon=True)
        self.app = app_ref
        self.stop_event = threading.Event()
        self.targets: List[dt.datetime] = []
        self.captured_today = 0

    def _randomize_today(self):
        cfg = self.app.cfg.data.get('scheduled_shots', {})
        per_day = int(cfg.get('per_day', 2))
        start_s = cfg.get('start', '09:30')
        end_s = cfg.get('end', '18:30')
        today = dt.datetime.now().date()
        st = dt.datetime.combine(today, dt.datetime.strptime(start_s, '%H:%M').time())
        et = dt.datetime.combine(today, dt.datetime.strptime(end_s, '%H:%M').time())
        if et <= st:
            et = st + dt.timedelta(hours=9)
        # pick unique random minutes
        import random
        self.targets = []
        span_sec = (et - st).total_seconds()
        picks = sorted(random.sample(range(int(span_sec)), k=max(1, per_day)))
        for p in picks:
            self.targets.append(st + dt.timedelta(seconds=p))
        self.captured_today = 0

    def _cleanup_old(self):
        keep_before = time.time() - int(self.app.cfg.data.get('scheduled_shots', {}).get('retention_days', 30)) * 86400
        for name in os.listdir(SHOTS_DIR):
            p = os.path.join(SHOTS_DIR, name)
            try:
                if os.path.isfile(p) and os.path.getmtime(p) < keep_before:
                    os.remove(p)
            except Exception:
                pass

    def _capture_one(self):
        # Only if active
        sys_idle = get_system_idle_seconds()
        if sys_idle is not None and sys_idle > IDLE_THRESHOLD_SEC:
            return False
        try:
            with mss.mss() as sct:
                img = sct.grab(sct.monitors[0])
                ts = dt.datetime.now().strftime('%Y%m%d_%H%M%S')
                out_path = os.path.join(SHOTS_DIR, f"shot_{ts}.jpg")
                Image.frombytes('RGB', img.size, img.rgb).save(out_path, 'JPEG', quality=70)
                try:
                    shutil.copyfile(out_path, LATEST_JPG)
                except Exception:
                    pass

                # Upload screenshot to server if configured
                self._upload_screenshot(out_path, ts)

                Alerts.log(f"Scheduled shot captured: {out_path}")
                return True
        except Exception as e:
            Alerts.log(f"Scheduled shot error: {e}")
        return False

    def _upload_screenshot(self, file_path: str, timestamp: str):
        """Upload screenshot to server if configured"""
        try:
            upload_cfg = self.app.cfg.data.get('screenshot_upload', {})
            if not upload_cfg.get('enabled', False):
                return

            server_url = upload_cfg.get('server_url', '').strip()
            if not server_url:
                return

            emp_id = int(self.app.cfg.data.get('emp_id', 0))
            if not emp_id:
                return

            # Prepare upload data
            with open(file_path, 'rb') as f:
                files = {'screenshot': (f'shot_{timestamp}.jpg', f, 'image/jpeg')}
                data = {
                    'emp_id': emp_id,
                    'timestamp': timestamp,
                    'captured_at': dt.datetime.now().isoformat()
                }

                # Upload with timeout
                upload_url = f"{server_url.rstrip('/')}/api/upload/screenshot"
                response = requests.post(upload_url, files=files, data=data, timeout=30)

                if response.status_code == 200:
                    result = response.json()
                    if result.get('success'):
                        Alerts.log(f"Screenshot uploaded successfully: {result.get('url', 'N/A')}")
                    else:
                        Alerts.log(f"Screenshot upload failed: {result.get('error', 'Unknown error')}")
                else:
                    Alerts.log(f"Screenshot upload failed: HTTP {response.status_code}")

        except requests.exceptions.Timeout:
            Alerts.log("Screenshot upload timed out")
        except requests.exceptions.RequestException as e:
            Alerts.log(f"Screenshot upload network error: {e}")
        except Exception as e:
            Alerts.log(f"Screenshot upload error: {e}")

    def run(self):
        current_day = None
        self._randomize_today()
        while not self.stop_event.is_set():
            try:
                now = dt.datetime.now()
                if current_day != now.date():
                    current_day = now.date()
                    self._randomize_today()
                    self._cleanup_old()
                if not MonitorApp.is_workday_now(self.app.cfg):
                    time.sleep(30)
                    continue
                # take when past target and not yet captured all
                for tgt in list(self.targets):
                    if now >= tgt and self.captured_today < len(self.targets):
                        if self._capture_one():
                            self.captured_today += 1
                            self.targets.remove(tgt)
                time.sleep(20)
            except Exception as e:
                Alerts.log(f"ScheduledShooter loop error: {e}")
                time.sleep(60)

    def stop(self):
        self.stop_event.set()


class Heartbeat(threading.Thread):
    """Emits smart-sampled heartbeat events and ingests them in batches."""
    def __init__(self, app_ref: 'MonitorApp'):
        super().__init__(daemon=True)
        self.app_ref = app_ref
        self.stop_event = threading.Event()
        # Prime cpu_percent
        try:
            psutil.cpu_percent(interval=None)
        except Exception:
            pass
        self._current_date = None
        self._last_emitted: Dict = {}
        self._next_periodic_ts: float = 0.0
        self._next_burst_ts: float = 0.0
        self._buf = IngestionBuffer(app_ref)

    def run(self):
        while not self.stop_event.is_set():
            try:
                cur = self.app_ref.fg.current if self.app_ref and self.app_ref.fg else {}
                # battery info
                batt = None
                try:
                    b = psutil.sensors_battery()
                    if b:
                        batt = {"percent": b.percent, "power_plugged": b.power_plugged, "secsleft": b.secsleft}
                except Exception:
                    batt = None
                # geo info (cached via app)
                geo = self.app_ref.get_geo_info() if self.app_ref else {}
                hb = {
                    "ts": dt.datetime.now().isoformat(timespec='seconds'),
                    "current": cur,
                    "activity": asdict(self.app_ref.activity),
                    "cpu_percent": psutil.cpu_percent(interval=None),
                    "mem_percent": psutil.virtual_memory().percent,
                    "battery": batt,
                    "geo": geo,
                    "geo_source": geo.get('_source'),
                }
                # Smart sampling decision
                emit = False
                now_ts = time.time()
                cfg = self.app_ref.cfg.data.get('ingestion', {})
                samp = cfg.get('sampling', {})
                # state change
                if samp.get('state_change', True):
                    key_now = {
                        'status': (cur or {}).get('status'),
                        'process': (cur or {}).get('process'),
                        'url': (cur or {}).get('url')
                    }
                    if key_now != {k: self._last_emitted.get('current', {}).get(k) for k in ('status','process','url')}:
                        emit = True
                # periodic
                if not emit and now_ts >= self._next_periodic_ts:
                    emit = True
                # active burst when CPU high
                if not emit and (cur or {}).get('status') == 'active':
                    thr = int(samp.get('active_burst_cpu_percent', 50))
                    if hb['cpu_percent'] >= thr and now_ts >= self._next_burst_ts:
                        emit = True

                if emit:
                    # Update timers
                    self._last_emitted = hb
                    per = int(samp.get('periodic_sec', 60))
                    self._next_periodic_ts = now_ts + max(10, per)
                    burst = int(samp.get('active_burst_sec', 5))
                    self._next_burst_ts = now_ts + max(2, burst)
                    # Buffer for ingestion
                    self._buf.add(hb)
                # periodic flush/retention
                self._buf.maybe_flush()
                self._cleanup_old_heartbeats()
            except Exception as e:
                Alerts.log(f"Heartbeat error: {e}")
            time.sleep(1.0)

    def stop(self):
        self.stop_event.set()

    def _cleanup_old_heartbeats(self):
        """Delete old daily heartbeat files beyond retention days."""
        try:
            keep_days = int(self.app_ref.cfg.data.get('ingestion', {}).get('file_retention_days', 30))
            cutoff = (dt.datetime.now() - dt.timedelta(days=keep_days)).strftime('%Y-%m-%d')
            for name in os.listdir(HEARTBEAT_DIR):
                if not (name.startswith('heartbeat_') and name.endswith('.jsonl')):
                    continue
                day = name[len('heartbeat_'):-len('.jsonl')]
                if day < cutoff:
                    try:
                        os.remove(os.path.join(HEARTBEAT_DIR, name))
                    except Exception:
                        pass
        except Exception:
            pass

class InputActivity:
    def __init__(self, stats: ActivityStats):
        self.stats = stats
        self.k_listener = None
        self.m_listener = None

    def _on_key(self, key):
        self.stats.key_presses += 1
        self.stats.last_activity_ts = time.time()

    def _on_click(self, x, y, button, pressed):
        if pressed:
            self.stats.mouse_clicks += 1
            self.stats.last_activity_ts = time.time()

    def start(self):
        # pynput has issues on Python 3.13 on Windows; disable gracefully
        if sys.version_info >= (3, 13):
            Alerts.log("pynput is not compatible with Python 3.13 on Windows; disabling input listeners. Activity will rely on foreground usage and idle heuristics.")
            return
        try:
            self.k_listener = keyboard.Listener(on_press=self._on_key)
            self.m_listener = mouse.Listener(on_click=self._on_click)
            self.k_listener.start()
            self.m_listener.start()
            Alerts.log("Keyboard/Mouse activity listeners started")
        except NotImplementedError:
            Alerts.log("pynput listener not implemented on this platform/Python version; disabling input listeners.")
        except Exception as e:
            Alerts.log(f"Failed to start input listeners: {e}")

    def stop(self):
        if self.k_listener:
            self.k_listener.stop()
        if self.m_listener:
            self.m_listener.stop()


class ForegroundTracker(threading.Thread):
    def __init__(self, stats: ActivityStats, cfg: Config):
        super().__init__(daemon=True)
        self.stats = stats
        self.cfg = cfg
        self.stop_event = threading.Event()
        self.current: Dict[str, str] = {"window": "", "process": "", "status": "unknown", "url": ""}
        self.usage: Dict[str, Dict[str, float]] = {}  # process -> {productive|unproductive|neutral: seconds}
        self.timeline: Dict[str, Dict[str, int]] = {}  # date -> {hour -> active/idle/offline counts seconds}
        self.website_usage: Dict[str, float] = {}  # domain -> seconds
        self.website_usage_by_tag: Dict[str, float] = {"productive": 0.0, "unproductive": 0.0, "neutral": 0.0}
        self._uia_initialized = False
        self._is_on_break = False

    def _get_foreground(self) -> Tuple[str, str, Optional[int]]:
        if not win32gui:
            return ("Unknown", "Unknown", None)
        try:
            hwnd = win32gui.GetForegroundWindow()
            thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)
            title = win32gui.GetWindowText(hwnd)
            proc = psutil.Process(pid)
            exe = os.path.basename(proc.exe()).lower()
            return (title, exe, hwnd)
        except Exception:
            return ("Unknown", "Unknown", None)

    def _status(self) -> str:
        # Handle configured break window as a distinct status
        if self.cfg.data.get('features', {}).get('break', True) and MonitorApp.is_break_now(self.cfg):
            return "break"
        # Prefer system idle seconds on Windows; fallback to internal last_activity_ts
        sys_idle = get_system_idle_seconds()
        if sys_idle is not None:
            return "active" if sys_idle <= IDLE_THRESHOLD_SEC else "idle"
        last = self.stats.last_activity_ts or 0
        return "active" if time.time() - last <= IDLE_THRESHOLD_SEC else "idle"

    def _tick_usage(self, exe: str, secs: float):
        tag = self.cfg.productivity_tags.get(exe, 'neutral')
        self.usage.setdefault(exe, {"productive": 0.0, "unproductive": 0.0, "neutral": 0.0})
        self.usage[exe][tag] += secs
        # persist periodically
        if int(time.time()) % 15 == 0:
            with open(USAGE_JSON, 'w', encoding='utf-8') as f:
                json.dump(self.usage, f, indent=2)

    def _tick_timeline(self, status: str, secs: float):
        now = dt.datetime.now()
        date_key = now.strftime('%Y-%m-%d')
        hour_key = now.strftime('%H')
        self.timeline.setdefault(date_key, {})
        self.timeline[date_key].setdefault(hour_key, {"active": 0, "idle": 0, "offline": 0})
        self.timeline[date_key][hour_key][status] += int(secs)
        if int(time.time()) % 30 == 0:
            with open(TIMELINE_JSON, 'w', encoding='utf-8') as f:
                json.dump(self.timeline, f, indent=2)

    def _extract_url_from_hwnd(self, exe: str, hwnd: Optional[int], title: str = "") -> str:
        if not auto or not hwnd:
            return ""
        # Only attempt for known browsers
        if exe not in ("chrome.exe", "msedge.exe", "firefox.exe"):
            return ""
        try:
            root = auto.ControlFromHandle(hwnd)
            edit = None
            # Strategy per browser
            if exe in ("chrome.exe", "msedge.exe"):
                # Chrome/Edge typically expose an Edit named 'Address and search bar'
                try:
                    edit = auto.EditControl(searchFromControl=root, Name='Address and search bar')
                    if not edit.Exists(0, 0):
                        edit = None
                except Exception:
                    edit = None
                if edit is None:
                    # Fallback: regex name search
                    try:
                        edit = auto.EditControl(searchFromControl=root, RegexName='.*Address.*search.*bar.*')
                        if not edit.Exists(0, 0):
                            edit = None
                    except Exception:
                        edit = None
            elif exe == "firefox.exe":
                # Firefox may expose different names or AutomationId for url bar
                # Try common names
                try:
                    edit = auto.EditControl(searchFromControl=root, RegexName='.*(Search.*enter address|Address.*bar).*')
                    if not edit.Exists(0, 0):
                        edit = None
                except Exception:
                    edit = None
                if edit is None:
                    # Try AutomationId heuristics
                    try:
                        cand = root.GetFirstDescendant(lambda c: isinstance(c, auto.EditControl) and getattr(c, 'AutomationId', '') in ('urlbar-input', 'urlbar'))
                        edit = cand if cand and cand.Exists(0, 0) else None
                    except Exception:
                        edit = None

            if edit is None:
                # Generic fallback: first Edit descendant
                try:
                    cand = root.GetFirstDescendant(lambda c: isinstance(c, auto.EditControl))
                    edit = cand if cand and cand.Exists(0, 0) else None
                except Exception:
                    edit = None

            if edit is None:
                return ""

            val = ""
            try:
                val = edit.GetValuePattern().Value
            except Exception:
                try:
                    val = edit.CurrentValue() if hasattr(edit, 'CurrentValue') else ""
                except Exception:
                    val = ""
            if not val:
                return ""
            v = val.strip()
            # Heuristic: looks like URL/domain
            if (" " in v) or len(v) < 4:
                return ""
            if not (v.startswith("http://") or v.startswith("https://")):
                # Sometimes address bar omits scheme; add https by default
                if "." in v and "/" not in v.split(" ")[0]:
                    v = "https://" + v
                else:
                    return ""
            return v
        except Exception:
            return ""

    def _infer_url_from_title(self, title: str) -> str:
        # Try to find a domain-like string in the window title and return a synthetic https URL
        try:
            import re
            # Common browser title formats: "Page Title - Google Chrome"; domain may or may not be present.
            # Look for domain-like token anywhere in the title.
            m = re.search(r"\b([a-z0-9-]+\.)+[a-z]{2,}\b", title, flags=re.IGNORECASE)
            if not m:
                return ""
            host = m.group(0).lower()
            if host.startswith('www.'):
                host = host[4:]
            return f"https://{host}"
        except Exception:
            return ""

    @staticmethod
    def _to_domain(url: str) -> str:
        try:
            p = urlparse(url)
            host = (p.netloc or "").split('@')[-1]  # strip creds if any
            host = host.split(':')[0]
            if host.startswith('www.'):
                host = host[4:]
            return host.lower()
        except Exception:
            return ""

    def _tick_website(self, url: str, secs: float):
        dom = self._to_domain(url)
        if not dom:
            return
        self.website_usage.setdefault(dom, 0.0)
        self.website_usage[dom] += secs
        if int(time.time()) % 15 == 0:
            with open(WEBSITE_USAGE_JSON, 'w', encoding='utf-8') as f:
                json.dump(self.website_usage, f, indent=2)
        # Aggregate by tag
        tag = self.cfg.data.get('website_tags', {}).get(dom, 'neutral')
        if tag not in self.website_usage_by_tag:
            self.website_usage_by_tag[tag] = 0.0
        self.website_usage_by_tag[tag] += secs
        if int(time.time()) % 15 == 0:
            with open(WEBSITE_USAGE_BY_TAG_JSON, 'w', encoding='utf-8') as f:
                json.dump(self.website_usage_by_tag, f, indent=2)

    def run(self):
        last_title, last_exe = None, None
        # Initialize UI Automation for this thread if available
        uia_init = None
        if auto and not self._uia_initialized:
            try:
                uia_init = auto.UIAutomationInitializerInThread()
                self._uia_initialized = True
            except Exception as e:
                Alerts.log(f"UI Automation init failed in ForegroundTracker: {e}")
        last_ts = time.time()
        while not self.stop_event.is_set():
            title, exe, hwnd = self._get_foreground()
            status = self._status()
            url = self._extract_url_from_hwnd(exe, hwnd, title)
            if not url and exe in ("chrome.exe", "msedge.exe", "firefox.exe") and title:
                # Fallback: infer from title without needing browser flags
                url = self._infer_url_from_title(title)
            self.current = {"window": title, "process": exe, "status": status, "url": url}
            now = time.time()
            dt_secs = now - last_ts
            last_ts = now
            # Only record usage/timeline on working days and outside break
            if MonitorApp.is_workday_now(self.cfg):
                if status != "break":
                    if exe:
                        self._tick_usage(exe, dt_secs)
                    if url and self.cfg.data.get('features', {}).get('website_tracking', True):
                        self._tick_website(url, dt_secs)
                    self._tick_timeline(status, dt_secs)
            time.sleep(1.0)

    def stop(self):
        self.stop_event.set()


class USBDetector(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.stop_event = threading.Event()
        self.prev_devices = set()

    def _current_removable(self) -> set:
        devs = set()
        for p in psutil.disk_partitions(all=False):
            if 'removable' in p.opts.lower() or p.device.lower().startswith('\\\\.\\physicaldrive'):
                devs.add((p.device, p.mountpoint))
        return devs

    def run(self):
        self.prev_devices = self._current_removable()
        while not self.stop_event.is_set():
            try:
                now_devs = self._current_removable()
                for d in now_devs - self.prev_devices:
                    Alerts.log(f"USB connected: {d}")
                for d in self.prev_devices - now_devs:
                    Alerts.log(f"USB disconnected: {d}")
                self.prev_devices = now_devs
            except Exception as e:
                Alerts.log(f"USBDetector error: {e}")
            time.sleep(5)

    def stop(self):
        self.stop_event.set()


class DomainBlocker(threading.Thread):
    def __init__(self, cfg: Config):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.stop_event = threading.Event()

    def _within_work_hours(self) -> bool:
        # Only Mon-Fri per config workdays
        if not MonitorApp.is_workday_now(self.cfg):
            return False
        st, et = self.cfg.work_hours
        now = dt.datetime.now().time()
        return st <= now <= et

    def _render_rules(self) -> str:
        lines = [HOSTS_MARKER_BEGIN]
        for d in self.cfg.blocked_domains:
            lines.append(f"127.0.0.1 {d}\n")
            lines.append(f"0.0.0.0 {d}\n")
            if not d.startswith('www.'):
                lines.append(f"127.0.0.1 www.{d}\n")
                lines.append(f"0.0.0.0 www.{d}\n")
        lines.append(HOSTS_MARKER_END)
        return ''.join(lines)

    def _apply_hosts(self, enable: bool):
        try:
            if not os.path.exists(HOSTS_PATH):
                Alerts.log(f"Hosts file not found: {HOSTS_PATH}")
                return
            with open(HOSTS_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            # remove our block first
            start = content.find(HOSTS_MARKER_BEGIN)
            end = content.find(HOSTS_MARKER_END)
            if start != -1 and end != -1 and end >= start:
                end += len(HOSTS_MARKER_END)
                content = content[:start] + content[end:]
            if enable and self.cfg.blocked_domains:
                content = content.rstrip() + '\n' + self._render_rules()
            with open(HOSTS_PATH, 'w', encoding='utf-8') as f:
                f.write(content)
        except PermissionError:
            Alerts.log("Permission denied updating hosts. Run as Administrator to enable Domain Blocking.")
        except Exception as e:
            Alerts.log(f"DomainBlocker error: {e}")

    def run(self):
        last_state = None
        while not self.stop_event.is_set():
            try:
                state = self._within_work_hours()
                if state != last_state:
                    self._apply_hosts(enable=state)
                    last_state = state
                time.sleep(30)
            except Exception as e:
                Alerts.log(f"DomainBlocker loop error: {e}")
                time.sleep(60)

    def stop(self):
        self.stop_event.set()


def collect_devices_info():
    info = {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "processor": platform.processor(),
        "python": sys.version,
        "users": [u.name for u in psutil.users()],
        "boot_time": dt.datetime.fromtimestamp(psutil.boot_time()).isoformat(),
    }
    try:
        batt = psutil.sensors_battery()
        if batt:
            info["battery"] = {
                "percent": batt.percent,
                "power_plugged": batt.power_plugged,
                "secsleft": batt.secsleft,
            }
    except Exception:
        pass
    with open(DEVICES_INFO_PATH, 'w', encoding='utf-8') as f:
        json.dump(info, f, indent=2)
    return info


def compute_wellness(timeline_path: str = TIMELINE_JSON, cfg: Optional['Config'] = None) -> Dict:
    """Compute daily wellness with thresholds and flags; optionally bound to work hours."""
    # Load timeline
    timeline = {}
    if os.path.exists(timeline_path):
        with open(timeline_path, 'r', encoding='utf-8') as f:
            timeline = json.load(f)
    # Load thresholds
    thresholds = DEFAULT_CONFIG.get('wellness_thresholds', {}).copy()
    work_hours = (DEFAULT_CONFIG['work_hours']['start'], DEFAULT_CONFIG['work_hours']['end'])
    if cfg is None:
        # try reading from disk config if present
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    cfg_data = json.load(f)
                thresholds.update(cfg_data.get('wellness_thresholds', {}))
                if 'work_hours' in cfg_data:
                    work_hours = (cfg_data['work_hours'].get('start', work_hours[0]), cfg_data['work_hours'].get('end', work_hours[1]))
        except Exception:
            pass
    else:
        thresholds.update(cfg.data.get('wellness_thresholds', {}))
        wh = cfg.data.get('work_hours', {})
        work_hours = (wh.get('start', work_hours[0]), wh.get('end', work_hours[1]))

    def _within(day_hour: Tuple[str, str]) -> bool:
        # day_hour: (day 'YYYY-MM-DD', hour 'HH') -> check if within configured work hours if bounding enabled
        if not thresholds.get('bound_to_work_hours', True):
            return True
        try:
            st = dt.datetime.strptime(work_hours[0], '%H:%M').time()
            et = dt.datetime.strptime(work_hours[1], '%H:%M').time()
            h = int(day_hour[1])
            hour_time = dt.time(hour=h)
            return st <= hour_time <= et
        except Exception:
            return True

    summary: Dict[str, Dict] = {}
    for day, hours in timeline.items():
        # sum within bounds if configured
        active = 0
        idle = 0
        offline = 0
        for hour, vals in hours.items():
            if _within((day, hour)):
                active += int(vals.get('active', 0))
                idle += int(vals.get('idle', 0))
                offline += int(vals.get('offline', 0))
        work_secs = active + idle
        total = active + idle + offline
        active_ratio = (active / work_secs) if work_secs else 0.0
        idle_ratio = (idle / work_secs) if work_secs else 0.0
        utilization = (active / total) * 100 if total else 0

        underutilized = (work_secs < thresholds.get('min_work_secs', 18000)) or (active_ratio < thresholds.get('min_active_ratio', 0.5))
        overburdened = work_secs > thresholds.get('overtime_secs', 32400)
        burnout_risk = overburdened and (active_ratio > thresholds.get('burnout_active_ratio', 0.7))
        steady_performer = not underutilized and not overburdened and (idle_ratio <= thresholds.get('max_idle_ratio', 0.4))

        summary[day] = {
            "active_secs": active,
            "idle_secs": idle,
            "offline_secs": offline,
            "work_secs": work_secs,
            "active_ratio": round(active_ratio, 3),
            "idle_ratio": round(idle_ratio, 3),
            "utilization_percent": round(utilization, 1),
            "underutilized": underutilized,
            "overburdened": overburdened,
            "burnout_risk": burnout_risk,
            "steady_performer": steady_performer,
        }

    with open(WELLNESS_JSON, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    return summary


def compute_esg(cfg: Optional['Config'] = None, country_override: Optional[str] = None, battery_plugged: Optional[bool] = None) -> Dict:
    """Compute Environmental, Social, Governance daily metrics.
    - Environmental: estimate energy (kWh) and CO2e (kg) using power model and country factors.
    - Social: mirror wellness flags/ratios.
    - Governance: show feature/policy adherence snapshot.
    """
    wellness = compute_wellness(cfg=cfg)
    try:
        with open(TIMELINE_JSON, 'r', encoding='utf-8') as f:
            timeline = json.load(f)
    except Exception:
        timeline = {}
    # Config
    data = (cfg.data if cfg else DEFAULT_CONFIG)
    esg_cfg = data.get('esg', {})
    # Determine power model depending on battery state
    if battery_plugged is None:
        try:
            b = psutil.sensors_battery()
            battery_plugged = bool(b.power_plugged) if b else True
        except Exception:
            battery_plugged = True
    pw = esg_cfg.get('power_watts_plugged' if battery_plugged else 'power_watts_battery', {"active": 25, "idle": 12})
    co2_map = esg_cfg.get('co2_kg_per_kwh', {"default": 0.475})
    # Country from caller (status.geo.country). Fallback to default.
    default_co2 = co2_map.get('default', 0.475)
    country = (country_override or '').strip() or 'default'

    out: Dict[str, Dict] = {}
    for day, hours in timeline.items():
        active = sum(int(v.get('active', 0)) for v in hours.values())
        idle = sum(int(v.get('idle', 0)) for v in hours.values())
        # Energy (Wh) = seconds * W / 3600
        wh = (active * pw.get('active', 25) + idle * pw.get('idle', 12)) / 3600.0
        kwh = round(wh / 1000.0, 4)
        co2_factor = co2_map.get(country, default_co2)
        co2_kg = round(kwh * co2_factor, 4)
        w = wellness.get(day, {})
        out[day] = {
            "environmental": {"energy_kwh": kwh, "co2_kg": co2_kg},
            "social": {
                "work_secs": w.get('work_secs', 0),
                "active_ratio": w.get('active_ratio', 0),
                "idle_ratio": w.get('idle_ratio', 0),
                "underutilized": w.get('underutilized', False),
                "overburdened": w.get('overburdened', False),
                "burnout_risk": w.get('burnout_risk', False),
                "steady_performer": w.get('steady_performer', False)
            },
            "governance": {
                "domain_blocker": bool(data.get('features', {}).get('domain_blocker', True)),
                "usb_monitor": bool(data.get('features', {}).get('usb_monitor', True)),
                "website_tracking": bool(data.get('features', {}).get('website_tracking', True)),
                "workdays": data.get('workdays', [1,2,3,4,5])
            }
        }
    # Rotate by month: write only current month entries to esg/esg_YYYY-MM.json
    try:
        month_key = dt.datetime.now().strftime('%Y-%m')
        month_path = os.path.join(ESG_DIR, f'esg_{month_key}.json')
        month_data = {}
        if os.path.exists(month_path):
            with open(month_path, 'r', encoding='utf-8') as f:
                month_data = json.load(f)
        # Filter current month from out
        for day, v in out.items():
            if day.startswith(month_key):
                month_data[day] = v
        with open(month_path, 'w', encoding='utf-8') as f:
            json.dump(month_data, f, indent=2)
    except Exception:
        pass
    return out


class MonitorApp:
    def __init__(self):
        self.cfg = Config(CONFIG_PATH)
        self.activity = ActivityStats()
        self.screen = ScreenRecorder(self.activity)
        self.inputs = InputActivity(self.activity)
        self.fg = ForegroundTracker(self.activity, self.cfg)
        self.usb = USBDetector()
        self.blocker = DomainBlocker(self.cfg)
        self.heartbeat = Heartbeat(self)
        self.flask_app: Optional[Flask] = None
        self.server_thread: Optional[threading.Thread] = None
        self._geo_cache: Dict[str, any] = {"ts": 0, "data": {}}
        self._notifier = NotificationManager(self)
        self.itsm = ITSMHelper(self)
        self.shooter: Optional[ScheduledShooter] = None

    def start(self, enable_http: bool = False, host: str = '127.0.0.1', port: int = 5000):
        Alerts.log("Starting Employee Monitor")
        # Log psycopg availability for diagnostics
        try:
            ver = getattr(psycopg, '__version__', None) if psycopg else None
            Alerts.log(f"psycopg_available={bool(psycopg)} version={ver} exec_values={'yes' if execute_values else 'no'} err={PSYCOPG_IMPORT_ERROR}")
        except Exception:
            pass
        collect_devices_info()
        self.inputs.start()
        if self.cfg.data.get('features', {}).get('screen_record', True):
            self.screen.start()
        self.fg.start()
        if self.cfg.data.get('features', {}).get('usb_monitor', True):
            self.usb.start()
        if self.cfg.data.get('features', {}).get('domain_blocker', True):
            self.blocker.start()
        self.heartbeat.start()
        if self.cfg.data.get('features', {}).get('notifications', True):
            self._notifier.start()
        if self.cfg.data.get('features', {}).get('itsm', True) and self.cfg.data.get('itsm', {}).get('enabled', True):
            self.itsm.start()
        if self.cfg.data.get('features', {}).get('scheduled_shots', True):
            self.shooter = ScheduledShooter(self)
            self.shooter.start()
        if enable_http:
            self._start_http(host, port)

    def stop(self):
        Alerts.log("Stopping Employee Monitor")
        self.screen.stop()
        self.fg.stop()
        self.usb.stop()
        self.blocker.stop()
        self.inputs.stop()
        self.heartbeat.stop()
        if self.cfg.data.get('features', {}).get('notifications', True):
            self._notifier.stop()
        try:
            self.itsm.stop()
        except Exception:
            pass
        try:
            if self.shooter:
                self.shooter.stop()
        except Exception:
            pass

    def _start_http(self, host: str, port: int):
        app = Flask(__name__)
        # Ensure we bind to the expected host/port for Electron
        host = host or '127.0.0.1'
        port = port or 5050
        Alerts.log(f"Starting HTTP server on {host}:{port}")

        @app.route('/status', methods=['GET'])
        def status():
            wellness = compute_wellness(cfg=self.cfg)
            # geo for country-sensitive CO2 and battery state for power profile
            geo = self.get_geo_info()
            try:
                b = psutil.sensors_battery()
                plugged = bool(b.power_plugged) if b else True
            except Exception:
                plugged = True
            esg = compute_esg(cfg=self.cfg, country_override=geo.get('country'), battery_plugged=plugged) if self.cfg.data.get('features', {}).get('esg', True) else {}
            cur = self.fg.current
            try:
                with open(USAGE_JSON, 'r', encoding='utf-8') as f:
                    usage = json.load(f)
            except Exception:
                usage = {}
            try:
                with open(WEBSITE_USAGE_JSON, 'r', encoding='utf-8') as f:
                    web_usage = json.load(f)
            except Exception:
                web_usage = {}
            try:
                with open(WEBSITE_USAGE_BY_TAG_JSON, 'r', encoding='utf-8') as f:
                    web_usage_by_tag = json.load(f)
            except Exception:
                web_usage_by_tag = {}
            # battery & geo
            battery = None
            try:
                b = psutil.sensors_battery()
                if b:
                    battery = {"percent": b.percent, "power_plugged": b.power_plugged, "secsleft": b.secsleft}
            except Exception:
                battery = None
            geo = self.get_geo_info()
            # Redact sensitive config fields before exposing in /status
            try:
                cfg_copy = copy.deepcopy(self.cfg.data)
                ing = cfg_copy.get('ingestion') or {}
                db = ing.get('db') or {}
                if isinstance(db, dict):
                    db['url'] = ''
                    db['url_env'] = ''
                    ing['db'] = db
                cfg_copy['ingestion'] = ing
            except Exception:
                cfg_copy = {"error": "config_unavailable"}
            return jsonify({
                "current": cur,
                "activity": asdict(self.activity),
                "usage": usage,
                "website_usage": web_usage,
                "website_usage_by_tag": web_usage_by_tag,
                "wellness": wellness,
                "config": cfg_copy,
                "battery": battery,
                "geo": geo,
            })

        @app.route('/latest.jpg', methods=['GET'])
        def latest():
            if os.path.exists(LATEST_JPG):
                return send_file(LATEST_JPG, mimetype='image/jpeg', max_age=0)
            return Response(status=404)

        @app.route('/heartbeat', methods=['GET'])
        def heartbeat():
            # Return last N records as JSON array
            N = int((request.args.get('n') if request else None) or 100)
            date_q = request.args.get('date')  # YYYY-MM-DD
            if not date_q:
                date_q = dt.datetime.now().strftime('%Y-%m-%d')
            try:
                from collections import deque
                dq = deque(maxlen=max(1, min(N, 1000)))
                hb_path = os.path.join(HEARTBEAT_DIR, f'heartbeat_{date_q}.jsonl')
                if os.path.exists(hb_path):
                    with open(hb_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            dq.append(json.loads(line))
                return jsonify(list(dq))
            except Exception as e:
                Alerts.log(f"/heartbeat error: {e}")
                return jsonify([])

        # ---------------- Work Session API (server-side) ----------------
        # In-memory current session; persisted on end. Fallback to file if Postgres not available.
        self._work_session: Dict = getattr(self, '_work_session', {}) or {}

        def _now_iso() -> str:
            return dt.datetime.now(dt.timezone.utc).isoformat()

        def _work_file_path() -> str:
            return os.path.join(DATA_DIR, 'work_sessions.json')

        def _save_file_session(rec: Dict):
            try:
                p = _work_file_path()
                arr = []
                if os.path.exists(p):
                    with open(p, 'r', encoding='utf-8') as f:
                        arr = json.load(f)
                arr.append(rec)
                with open(p, 'w', encoding='utf-8') as f:
                    json.dump(arr, f, indent=2)
            except Exception as e:
                Alerts.log(f"work session file save error: {e}")

        def _dur_ms(a: str, b: str) -> int:
            try:
                return max(0, int((dt.datetime.fromisoformat(b) - dt.datetime.fromisoformat(a)).total_seconds() * 1000))
            except Exception:
                return 0

        def _sum_break_ms(breaks: List[Dict]) -> int:
            total = 0
            for br in breaks or []:
                st, en = br.get('start_ts'), br.get('end_ts')
                if st and en:
                    total += _dur_ms(st, en)
            return total

        def _insert_session_db(rec: Dict):
            try:
                ing = self.cfg.data.get('ingestion', {})
                if ing.get('mode') != 'postgres' or psycopg is None:
                    _save_file_session(rec)
                    return
                db_cfg = ing.get('db', {})
                dsn = (db_cfg.get('url') or '').strip() or os.environ.get(db_cfg.get('url_env', 'EMP_DB_URL'))
                if not dsn:
                    _save_file_session(rec)
                    return
                schema = db_cfg.get('schema', 'employee_monitor')
                try:
                    Alerts.log(f"Attempting PostgreSQL connection to: {dsn[:30]}...")
                    with psycopg.connect(dsn) as conn:
                        with conn.cursor() as cur:
                            cur.execute(f"""
                                CREATE TABLE IF NOT EXISTS {schema}.work_sessions (
                                    emp_id INTEGER NOT NULL,
                                    start_ts TIMESTAMPTZ NOT NULL,
                                    end_ts TIMESTAMPTZ,
                                    breaks JSONB,
                                    work_ms BIGINT,
                                    break_ms BIGINT,
                                    total_ms BIGINT,
                                    PRIMARY KEY (emp_id, start_ts)
                                );
                            """)
                            cur.execute(f"SET search_path TO {schema}, public;")
                            cur.execute(f"""
                                INSERT INTO {schema}.work_sessions(emp_id,start_ts,end_ts,breaks,work_ms,break_ms,total_ms)
                                VALUES (%s,%s,%s,%s,%s,%s,%s)
                                ON CONFLICT (emp_id, start_ts) DO UPDATE SET
                                    end_ts = EXCLUDED.end_ts,
                                    breaks = EXCLUDED.breaks,
                                    work_ms = EXCLUDED.work_ms,
                                    break_ms = EXCLUDED.break_ms,
                                    total_ms = EXCLUDED.total_ms;
                            """, (
                                int(self.cfg.data.get('emp_id', 0)),
                                rec.get('start_ts'), rec.get('end_ts'), json.dumps(rec.get('breaks') or []),
                                int(rec.get('work_ms') or 0), int(rec.get('break_ms') or 0), int(rec.get('total_ms') or 0)
                            ))
                            Alerts.log(f"PostgreSQL session saved successfully for emp_id {self.cfg.data.get('emp_id', 0)}")
                except Exception as e:
                    Alerts.log(f"work session db insert error: {e}")
                    _save_file_session(rec)
            except Exception as e:
                Alerts.log(f"Session insert function error: {e}")
                _save_file_session(rec)

        @app.post('/session/start')
        def api_session_start():
            try:
                if (self._work_session or {}).get('start_ts') and not self._work_session.get('end_ts'):
                    return jsonify({"ok": False, "error": "Session already active"}), 400
                self._work_session = {"start_ts": _now_iso(), "end_ts": None, "breaks": [], "status": "active"}
                return jsonify({"ok": True, "state": self._work_session})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500

        @app.post('/session/break/start')
        def api_session_break_start():
            try:
                if not self._work_session or self._work_session.get('end_ts'):
                    return jsonify({"ok": False, "error": "No active session"}), 400
                brks = self._work_session.setdefault('breaks', [])
                # if already on break, ignore
                if brks and not brks[-1].get('end_ts'):
                    return jsonify({"ok": True, "state": self._work_session})
                brks.append({"start_ts": _now_iso(), "end_ts": None})
                self._work_session['status'] = 'break'
                return jsonify({"ok": True, "state": self._work_session})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500

        @app.post('/session/break/end')
        def api_session_break_end():
            try:
                if not self._work_session or self._work_session.get('end_ts'):
                    return jsonify({"ok": False, "error": "No active session"}), 400
                brks = self._work_session.setdefault('breaks', [])
                if brks and not brks[-1].get('end_ts'):
                    brks[-1]['end_ts'] = _now_iso()
                self._work_session['status'] = 'active'
                return jsonify({"ok": True, "state": self._work_session})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500

        @app.post('/session/end')
        def api_session_end():
            try:
                if not self._work_session or self._work_session.get('end_ts'):
                    return jsonify({"ok": False, "error": "No active session"}), 400
                # close any open break
                brks = self._work_session.get('breaks') or []
                if brks and not brks[-1].get('end_ts'):
                    brks[-1]['end_ts'] = _now_iso()
                self._work_session['end_ts'] = _now_iso()
                start_ts = self._work_session.get('start_ts')
                end_ts = self._work_session.get('end_ts')
                total_ms = _dur_ms(start_ts, end_ts)
                break_ms = _sum_break_ms(brks)
                work_ms = max(0, total_ms - break_ms)
                rec = {
                    "emp_id": int(self.cfg.data.get('emp_id', 0)),
                    "start_ts": start_ts,
                    "end_ts": end_ts,
                    "breaks": brks,
                    "work_ms": work_ms,
                    "break_ms": break_ms,
                    "total_ms": total_ms,
                }
                _insert_session_db(rec)
                self._work_session = {}
                return jsonify({"ok": True, "record": rec})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500

        @app.route('/session/state', methods=['GET'])
        def api_session_state():
            try:
                st = self._work_session or {}
                # derive status
                status = 'idle'
                if st.get('start_ts') and not st.get('end_ts'):
                    if (st.get('breaks') and not st['breaks'][-1].get('end_ts')):
                        status = 'break'
                    else:
                        status = 'active'
                out = {"ok": True, "state": {**st, "status": status}}
                return jsonify(out)
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500

        @app.route('/session/summary', methods=['GET'])
        def api_session_summary():
            try:
                days = int((request.args.get('days') if request else None) or 7)
                since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
                # try DB first
                kpi = {"total_work_ms": 0, "total_break_ms": 0, "avg_work_ms": 0, "sessions_completed": 0}
                rows = []
                used_db = False
                try:
                    ing = self.cfg.data.get('ingestion', {})
                    if ing.get('mode') == 'postgres' and psycopg is not None:
                        db_cfg = ing.get('db', {})
                        dsn = (db_cfg.get('url') or '').strip() or os.environ.get(db_cfg.get('url_env', 'EMP_DB_URL'))
                        if dsn:
                            schema = db_cfg.get('schema', 'employee_monitor')
                            with psycopg.connect(dsn) as conn:
                                with conn.cursor() as cur:
                                    cur.execute(f"SET search_path TO {schema}, public;")
                                    cur.execute(f"""
                                        SELECT start_ts, end_ts, breaks, work_ms, break_ms, total_ms
                                        FROM {schema}.work_sessions
                                        WHERE emp_id = %s AND start_ts >= %s
                                        ORDER BY start_ts DESC
                                    """, (int(self.cfg.data.get('emp_id', 0)), since))
                                    recs = cur.fetchall()
                                    for (st_ts, en_ts, br, wms, bms, tms) in recs:
                                        rows.append({"start_ts": st_ts.isoformat(), "end_ts": (en_ts.isoformat() if en_ts else None), "breaks": br, "work_ms": wms or 0, "break_ms": bms or 0, "total_ms": tms or 0})
                                    used_db = True
                except Exception as e:
                    Alerts.log(f"work session summary db error: {e}")
                    used_db = False
                if not used_db:
                    # file fallback
                    try:
                        p = _work_file_path()
                        if os.path.exists(p):
                            with open(p, 'r', encoding='utf-8') as f:
                                arr = json.load(f)
                                for r in arr:
                                    try:
                                        if dt.datetime.fromisoformat(r.get('start_ts')).replace(tzinfo=None) >= since.replace(tzinfo=None):
                                            rows.append(r)
                                    except Exception:
                                        continue
                    except Exception:
                        pass
                # aggregate
                if rows:
                    kpi['sessions_completed'] = len(rows)
                    kpi['total_work_ms'] = sum(int(r.get('work_ms') or 0) for r in rows)
                    kpi['total_break_ms'] = sum(int(r.get('break_ms') or 0) for r in rows)
                    kpi['avg_work_ms'] = int(kpi['total_work_ms'] / max(1, kpi['sessions_completed']))
                return jsonify({"ok": True, "kpi": kpi, "rows": rows})
            except Exception as e:
                return jsonify({"ok": False, "error": str(e)}), 500

        @app.route('/esg', methods=['GET'])
        def esg_api():
            try:
                # support month=YYYY-MM to return a rotated monthly file
                month_q = request.args.get('month') if request else None
                if month_q:
                    month_path = os.path.join(ESG_DIR, f'esg_{month_q}.json')
                    if os.path.exists(month_path):
                        with open(month_path, 'r', encoding='utf-8') as f:
                            return jsonify(json.load(f))
                        
                # default: compute with current geo + battery profile
                geo = self.get_geo_info()
                b = psutil.sensors_battery()
                plugged = bool(b.power_plugged) if b else True
                esg = compute_esg(cfg=self.cfg, country_override=geo.get('country'), battery_plugged=plugged)
                return jsonify(esg)
            except Exception as e:
                Alerts.log(f"/esg error: {e}")
                return jsonify({})

        @app.route('/itsm/tickets', methods=['GET'])
        def itsm_tickets():
            try:
                with open(ITSM_TICKETS_JSON, 'r', encoding='utf-8') as f:
                    tickets = json.load(f)
                return jsonify(tickets)
            except Exception as e:
                Alerts.log(f"/itsm/tickets error: {e}")
                return jsonify([])

        @app.post('/geo/refresh')
        def geo_refresh():
            # clear cached geo so next call refreshes
            try:
                self._geo_cache = {"ts": 0, "data": {}}
                return jsonify({"ok": True})
            except Exception as e:
                Alerts.log(f"/geo/refresh error: {e}")
                return jsonify({"ok": False}), 500

        @app.route('/api/screenshots', methods=['GET'])
        def api_screenshots():
            """Get list of available screenshots with URLs"""
            try:
                screenshots = []
                if os.path.exists(SHOTS_DIR):
                    for filename in os.listdir(SHOTS_DIR):
                        if filename.endswith('.jpg') and filename.startswith('shot_'):
                            filepath = os.path.join(SHOTS_DIR, filename)
                            try:
                                # Extract timestamp from filename (shot_YYYYMMDD_HHMMSS.jpg)
                                timestamp_str = filename.replace('shot_', '').replace('.jpg', '')
                                timestamp = dt.datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')

                                stat = os.stat(filepath)
                                screenshots.append({
                                    'filename': filename,
                                    'timestamp': timestamp.isoformat(),
                                    'url': f'/screenshots/{filename}',
                                    'size': stat.st_size,
                                    'captured_at': timestamp.strftime('%Y-%m-%d %H:%M:%S')
                                })
                            except Exception as e:
                                Alerts.log(f"Error processing screenshot {filename}: {e}")

                # Sort by timestamp (newest first)
                screenshots.sort(key=lambda x: x['timestamp'], reverse=True)

                return jsonify({
                    'success': True,
                    'screenshots': screenshots,
                    'count': len(screenshots)
                })
            except Exception as e:
                Alerts.log(f"/api/screenshots error: {e}")
                return jsonify({"success": False, "error": str(e)}), 500

        @app.route('/screenshots/<filename>', methods=['GET'])
        def get_screenshot(filename):
            """Serve individual screenshot files"""
            try:
                # Security: only allow jpg files with shot_ prefix
                if not filename.endswith('.jpg') or not filename.startswith('shot_'):
                    return jsonify({"error": "Invalid filename"}), 400

                filepath = os.path.join(SHOTS_DIR, filename)
                if not os.path.exists(filepath):
                    return jsonify({"error": "Screenshot not found"}), 404

                return send_file(filepath, mimetype='image/jpeg')
            except Exception as e:
                Alerts.log(f"/screenshots/{filename} error: {e}")
                return jsonify({"error": str(e)}), 500

        @app.get('/')
        def home():
            return Response(
                f"""
                <html>
                <head><title>Emp Monitor - Livestream</title></head>
                <body style='font-family:Segoe UI,Arial,sans-serif;'>
                  <h2>Live View</h2>
                  <div>
                    <img src='/latest.jpg?ts={{int(Date.now()/1000)}}' style='max-width:98vw;border:1px solid #ccc' onerror="this.src='';this.alt='No frame yet'"/>
                  </div>
                  <h3>Status</h3>
                  <pre id='status'>Loading...</pre>
                  <script>
                    async function refresh() {{
                      try {{
                        const r = await fetch('/status');
                        const j = await r.json();
                        document.getElementById('status').innerText = JSON.stringify(j, null, 2);
                      }} catch(e) {{
                        document.getElementById('status').innerText = 'Status unavailable';
                      }}
                    }}
                    setInterval(refresh, 2000);
                    refresh();
                    setInterval(()=>{{
                      const img = document.querySelector('img');
                      if (img && img.src) img.src = '/latest.jpg?ts=' + Date.now();
                    }}, 1000);
                  </script>
                </body>
                </html>
                """,
                mimetype='text/html'
            )

        def run_server():
            try:
                server_host = host or '127.0.0.1'
                server_port = port or 5050
                if serve:
                    # Use waitress production WSGI server
                    Alerts.log(f"Starting production WSGI server on {server_host}:{server_port}")
                    serve(app, host=server_host, port=server_port, threads=6)
                else:
                    # Fallback to Flask dev server
                    Alerts.log(f"Waitress not available, using Flask dev server on {server_host}:{server_port}")
                    app.run(host=server_host, port=server_port, debug=False, use_reloader=False, threaded=True)
            except OSError as e:
                Alerts.log(f"HTTP server failed to start on {host}:{port}: {e}. Try a different --port (e.g., 5050) or check firewall/permissions.")

        self.flask_app = app
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        Alerts.log(f"HTTP server started at http://{host}:{port}")

    def get_geo_info(self) -> Dict:
        # Cache geo lookup: 1 hour on success; 10 minutes on failure to avoid spam
        now = time.time()
        cache_ts = self._geo_cache.get('ts', 0)
        cached = self._geo_cache.get('data') or {}
        if cached:
            # Successful data cached, honor 1 hour TTL
            if (now - cache_ts) < 3600:
                return cached
        else:
            # No data (likely failure) but still respect a shorter TTL (10 min)
            if (now - cache_ts) < 600:
                return cached
        # Check config for manual override
        geo_cfg = self.cfg.data.get('geo', {}) if self.cfg else {}
        if geo_cfg.get('mode') == 'manual':
            manual = geo_cfg.get('manual') or {}
            self._geo_cache = {"ts": now, "data": manual}
            return manual
        mode = geo_cfg.get('mode', 'ip')
        data = {}
        try:
            if mode == 'ip_multi':
                data = self._geo_from_multiple_providers()
            else:
                # Default single provider (ipapi.co)
                r = requests.get('https://ipapi.co/json/', timeout=5)
                if r.ok:
                    j = r.json()
                    data = {
                        "ip": j.get('ip'),
                        "city": j.get('city'),
                        "region": j.get('region'),
                        "country": j.get('country_name') or j.get('country'),
                        "latitude": j.get('latitude'),
                        "longitude": j.get('longitude'),
                        "org": j.get('org') or j.get('asn'),
                    }
        except Exception as e:
            Alerts.log(f"Geo lookup failed: {e}")
        # Always cache outcome (even if empty) to honor TTL/backoff above
        self._geo_cache = {"ts": now, "data": data}
        return data

    def _geo_from_multiple_providers(self) -> Dict:
        """Query multiple IP geolocation providers and choose a consensus city.
        Providers: ipapi.co, ipwho.is. Returns first non-empty on failure.
        """
        results: List[Dict] = []
        # Provider 1: ipapi.co
        try:
            r1 = requests.get('https://ipapi.co/json/', timeout=3)
            if r1.ok:
                j = r1.json()
                results.append({
                    "ip": j.get('ip'),
                    "city": j.get('city'),
                    "region": j.get('region'),
                    "country": j.get('country_name') or j.get('country'),
                    "latitude": j.get('latitude'),
                    "longitude": j.get('longitude'),
                    "org": j.get('org') or j.get('asn'),
                    "src": "ipapi.co"
                })
        except Exception as e:
            Alerts.log(f"Geo ipapi.co failed: {e}")
        # Provider 2: ipwho.is
        try:
            r2 = requests.get('https://ipwho.is/', timeout=3)
            if r2.ok:
                j = r2.json()
                if j.get('success', True):
                    conn = j.get('connection') or {}
                    results.append({
                        "ip": j.get('ip'),
                        "city": j.get('city'),
                        "region": j.get('region'),
                        "country": j.get('country') or j.get('country_name'),
                        "latitude": j.get('latitude'),
                        "longitude": j.get('longitude'),
                        "org": conn.get('org') or conn.get('isp'),
                        "src": "ipwho.is"
                    })
        except Exception as e:
            Alerts.log(f"Geo ipwho.is failed: {e}")

        # Choose consensus by city (case-insensitive)
        if results:
            from collections import Counter
            cities = [ (r.get('city') or '').strip().lower() for r in results if r.get('city') ]
            if cities:
                counts = Counter(cities)
                top_city, _ = counts.most_common(1)[0]
                # pick first result matching the top city
                for r in results:
                    if (r.get('city') or '').strip().lower() == top_city:
                        r.pop('src', None)
                        return r
            # fallback to first
            first = results[0]
            first.pop('src', None)
            return first
        return {}

    @staticmethod
    def is_workday_now(cfg: 'Config') -> bool:
        try:
            workdays = cfg.data.get('workdays', [1,2,3,4,5])
            today = dt.datetime.now().isoweekday()
            return today in workdays
        except Exception:
            return True

    @staticmethod
    def is_break_now(cfg: 'Config') -> bool:
        try:
            bw = cfg.data.get('break_window', {"start": "13:00", "duration_minutes": 60})
            start = dt.datetime.strptime(bw.get('start', '13:00'), '%H:%M').time()
            dur = int(bw.get('duration_minutes', 60))
            now = dt.datetime.now()
            start_dt = now.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
            end_dt = start_dt + dt.timedelta(minutes=dur)
            return start_dt.time() <= now.time() <= end_dt.time()
        except Exception:
            return False


class IngestionBuffer:
    """Simple batching buffer for heartbeats. Currently writes to daily JSONL files.
    Designed to be extended for Postgres/Timescale ingestion in future.
    """
    def __init__(self, app_ref: 'MonitorApp'):
        self.app = app_ref
        self.buf: List[Dict] = []
        self.last_flush = time.time()

    def add(self, record: Dict):
        self.buf.append(record)

    def maybe_flush(self):
        cfg = self.app.cfg.data.get('ingestion', {})
        if not cfg.get('enabled', True):
            self.buf.clear()
            return
        if len(self.buf) >= int(cfg.get('batch_size', 200)) or (time.time() - self.last_flush) >= int(cfg.get('flush_interval_sec', 5)):
            self.flush()

    def flush(self, force: bool = False):
        if not self.buf and not force:
            return
        mode = self.app.cfg.data.get('ingestion', {}).get('mode', 'file')
        if mode == 'file':
            today = dt.datetime.now().strftime('%Y-%m-%d')
            hb_path = os.path.join(HEARTBEAT_DIR, f'heartbeat_{today}.jsonl')
            try:
                with open(hb_path, 'a', encoding='utf-8') as f:
                    for rec in self.buf:
                        f.write(json.dumps(rec) + "\n")
            except Exception as e:
                Alerts.log(f"Ingestion flush error: {e}")
        elif mode == 'postgres':
            if psycopg is None:
                Alerts.log(f"psycopg (v3) not installed; cannot ingest to Postgres. Falling back to file. detail={PSYCOPG_IMPORT_ERROR}")
            else:
                db_cfg = self.app.cfg.data.get('ingestion', {}).get('db', {})
                url_env = db_cfg.get('url_env', 'EMP_DB_URL')
                dsn = (db_cfg.get('url') or '').strip() or os.environ.get(url_env)
                if not dsn:
                    Alerts.log(f"Environment variable {url_env} not set; cannot ingest to Postgres.")
                else:
                    schema = db_cfg.get('schema', 'employee_monitor')
                    emp_id = int(self.app.cfg.data.get('emp_id', 0))
                    rows = []
                    for rec in self.buf:
                        cur = rec.get('current') or {}
                        url = cur.get('url') or ''
                        # domain
                        try:
                            p = urlparse(url)
                            dom = (p.netloc or '').split('@')[-1]
                            dom = dom.split(':')[0]
                            dom = dom.lower()
                            if dom.startswith('www.'):
                                dom = dom[4:]
                        except Exception:
                            dom = ''
                        batt = rec.get('battery') or {}
                        rows.append((
                            emp_id,
                            rec.get('ts'),
                            (cur.get('status') or None),
                            float(rec.get('cpu_percent') or 0.0),
                            float(rec.get('mem_percent') or 0.0),
                            (cur.get('process') or None),
                            (cur.get('window') or None),
                            (dom or None),
                            (url or None),
                            batt.get('percent'),
                            batt.get('power_plugged'),
                            json.dumps(rec.get('geo') or {})
                        ))
                    if rows:
                        try:
                            Alerts.log(f"Heartbeat: attempting PostgreSQL batch insert of {len(rows)} records")
                            with psycopg.connect(dsn) as conn:
                                with conn.cursor() as cur:
                                    # Ensure schema is in search_path for the session
                                    cur.execute("SET search_path TO %s, public;" % schema)
                                    if execute_values is not None:
                                        tpl = "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                                        sql = f"""
                                        INSERT INTO {schema}.heartbeat
                                        (emp_id, ts, status, cpu_percent, memory_percent, process_name, window_title, domain, url, battery_level, battery_plugged, geo)
                                        VALUES %s
                                        ON CONFLICT (emp_id, ts) DO NOTHING
                                        """
                                        execute_values(cur, sql, rows, template=tpl)
                                    else:
                                        # Fallback to executemany if execute_values unavailable
                                        sql = f"""
                                        INSERT INTO {schema}.heartbeat
                                        (emp_id, ts, status, cpu_percent, memory_percent, process_name, window_title, domain, url, battery_level, battery_plugged, geo)
                                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                        ON CONFLICT (emp_id, ts) DO NOTHING
                                        """
                                        cur.executemany(sql, rows)
                                    Alerts.log(f"Heartbeat: PostgreSQL batch insert successful ({len(rows)} records)")
                        except Exception as e:
                            Alerts.log(f"Postgres ingestion error: {e}")
        else:
            Alerts.log(f"Unknown ingestion mode: {mode}")
        self.buf.clear()
        self.last_flush = time.time()

    @staticmethod
    def is_workday_now(cfg: 'Config') -> bool:
        try:
            workdays = cfg.data.get('workdays', [1,2,3,4,5])
            today = dt.datetime.now().isoweekday()
            return today in workdays
        except Exception:
            return True

    @staticmethod
    def is_break_now(cfg: 'Config') -> bool:
        try:
            bw = cfg.data.get('break_window', {"start": "13:00", "duration_minutes": 60})
            start = dt.datetime.strptime(bw.get('start', '13:00'), '%H:%M').time()
            dur = int(bw.get('duration_minutes', 60))
            now = dt.datetime.now()
            start_dt = now.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
            end_dt = start_dt + dt.timedelta(minutes=dur)
            return start_dt.time() <= now.time() <= end_dt.time()
        except Exception:
            return False


class NotificationManager(threading.Thread):
    """Sends Windows notifications for break and wellness events."""
    def __init__(self, app_ref: 'MonitorApp'):
        super().__init__(daemon=True)
        self.app = app_ref
        self.stop_event = threading.Event()
        self.toast = ToastNotifier() if ToastNotifier else None
        self.prev_break = False
        self.prev_overburdened = False
        self.prev_burnout = False
        # Battery notification state (simple hysteresis)
        self.prev_batt_high_on_charge = False
        self.prev_batt_low_no_charge = False

    def _notify(self, title: str, msg: str, duration: int = 5):
        Alerts.log(f"Notify: {title} - {msg}")
        if self.toast:
            try:
                self.toast.show_toast(title, msg, duration=duration, threaded=True)
            except Exception:
                pass

    def run(self):
        while not self.stop_event.is_set():
            try:
                # Break notifications (Mon-Fri only)
                on_break = MonitorApp.is_workday_now(self.app.cfg) and MonitorApp.is_break_now(self.app.cfg)
                if on_break and not self.prev_break:
                    self._notify("Break Time", "Your 1-hour break has started.")
                if not on_break and self.prev_break:
                    self._notify("Break Over", "Break finished. Welcome back!")
                self.prev_break = on_break

                # Wellness alerts once per change
                wellness = compute_wellness(cfg=self.app.cfg)
                today_key = dt.datetime.now().strftime('%Y-%m-%d')
                w = wellness.get(today_key, {})
                over = bool(w.get('overburdened'))
                burn = bool(w.get('burnout_risk'))
                if over and not self.prev_overburdened:
                    self._notify("Wellness Alert", "Overburdened: long working hours today.")
                if burn and not self.prev_burnout:
                    self._notify("Wellness Alert", "Burnout risk: long hours with high activity.")
                self.prev_overburdened = over
                self.prev_burnout = burn
                # Battery notifications: >80% while charging -> unplug; <25% and not charging -> plug in
                try:
                    b = psutil.sensors_battery()
                except Exception:
                    b = None
                if b is not None:
                    percent = int(b.percent or 0)
                    plugged = bool(b.power_plugged)
                    # High battery and charging
                    if plugged and percent >= 80:
                        if not self.prev_batt_high_on_charge:
                            self._notify("Battery", "Battery above 80% while charging. Please unplug to save electricity.")
                            self.prev_batt_high_on_charge = True
                    else:
                        # Reset when unplugged or sufficient drop
                        if (not plugged) or percent < 78:
                            self.prev_batt_high_on_charge = False

                    # Low battery and not charging
                    if (not plugged) and percent <= 25:
                        if not self.prev_batt_low_no_charge:
                            self._notify("Battery", "Battery below 25%. Please plug in the charger.")
                            self.prev_batt_low_no_charge = True
                    else:
                        if plugged or percent > 28:
                            self.prev_batt_low_no_charge = False
            except Exception as e:
                Alerts.log(f"Notification loop error: {e}")
            time.sleep(60)

    def stop(self):
        self.stop_event.set()

class ITSMHelper(threading.Thread):
    """Monitors system health and performs AI-inspired ITSM assistance and self-healing."""
    def __init__(self, app_ref: 'MonitorApp'):
        super().__init__(daemon=True)
        self.app = app_ref
        self.stop_event = threading.Event()
        self.high_cpu_since: Optional[float] = None
        self.prev_running: set = set()

    def _create_ticket(self, issue_type: str, severity: str, details: Dict, actions_taken: Optional[List[str]] = None):
        ticket = {
            "id": f"TKT-{int(time.time())}",
            "ts": dt.datetime.now().isoformat(timespec='seconds'),
            "type": issue_type,
            "severity": severity,
            "details": details,
            "actions_taken": actions_taken or [],
            "status": "open"
        }
        try:
            with open(ITSM_TICKETS_JSON, 'r', encoding='utf-8') as f:
                tickets = json.load(f)
        except Exception:
            tickets = []
        tickets.append(ticket)
        with open(ITSM_TICKETS_JSON, 'w', encoding='utf-8') as f:
            json.dump(tickets, f, indent=2)
        # optional webhook
        try:
            wh = self.app.cfg.data.get('itsm', {}).get('ticket_webhook')
            if wh:
                requests.post(wh, json=ticket, timeout=3)
        except Exception:
            pass
        Alerts.log(f"ITSM ticket created: {ticket['id']} {issue_type} {severity}")

    def _check_high_cpu(self):
        cfg = self.app.cfg.data.get('itsm', {})
        thresh = int(cfg.get('high_cpu_threshold', 90))
        dur = int(cfg.get('high_cpu_duration_sec', 180))
        cpu = psutil.cpu_percent(interval=None)
        now = time.time()
        if cpu >= thresh:
            if self.high_cpu_since is None:
                self.high_cpu_since = now
            elif (now - self.high_cpu_since) >= dur:
                # sustained high CPU
                actions = []
                if cfg.get('auto_heal', False):
                    # attempt to find top offender and terminate if not protected
                    try:
                        # prime per-process cpu stats
                        for p in psutil.process_iter(['pid', 'name']):
                            try:
                                p.cpu_percent(None)
                            except Exception:
                                pass
                        time.sleep(1.0)
                        offenders = []
                        for p in psutil.process_iter(['pid', 'name']):
                            try:
                                offenders.append((p, p.cpu_percent(None)))
                            except Exception:
                                continue
                        offenders.sort(key=lambda t: t[1], reverse=True)
                        for p, pct in offenders[:3]:
                            name = (p.info.get('name') or '').lower()
                            if name and name not in cfg.get('protected_processes', []):
                                try:
                                    p.terminate()
                                    actions.append(f"terminated {name} pid={p.pid} cpu={pct}")
                                    break
                                except Exception:
                                    continue
                    except Exception:
                        pass
                self._create_ticket(
                    issue_type="high_cpu",
                    severity="major",
                    details={"cpu_percent": cpu, "duration_sec": dur},
                    actions_taken=actions
                )
                self.high_cpu_since = None
        else:
            self.high_cpu_since = None

    def _check_network(self):
        cfg = self.app.cfg.data.get('itsm', {})
        urls: List[str] = cfg.get('network_check_urls', [])
        if not urls:
            return
        ok = False
        for u in urls:
            try:
                r = requests.get(u, timeout=3)
                if r.ok:
                    ok = True
                    break
            except Exception:
                continue
        if not ok:
            actions = []
            if cfg.get('auto_heal', False):
                # attempt lightweight heals: flush DNS
                try:
                    os.system('ipconfig /flushdns')
                    actions.append('ipconfig /flushdns')
                except Exception:
                    pass
            self._create_ticket(
                issue_type="network_disconnect",
                severity="critical",
                details={"probe_urls": urls},
                actions_taken=actions
            )

    def _check_app_crash(self):
        cfg = self.app.cfg.data.get('itsm', {})
        watch = [w.lower() for w in cfg.get('watched_apps', [])]
        if not watch:
            return
        running = set()
        for p in psutil.process_iter(['name']):
            try:
                nm = (p.info.get('name') or '').lower()
                if nm:
                    running.add(nm)
            except Exception:
                continue
        # detect watched apps previously running but no longer present
        crashed = [app for app in watch if (app in self.prev_running and app not in running)]
        if crashed:
            for app in crashed:
                actions = []
                if cfg.get('auto_heal', False):
                    # best effort: try to relaunch if found in PATH via startfile (may not work for all)
                    try:
                        os.startfile(app)  # may raise
                        actions.append(f"relaunch attempted for {app}")
                    except Exception:
                        pass
                self._create_ticket(
                    issue_type="app_crash",
                    severity="major",
                    details={"app": app},
                    actions_taken=actions
                )
        self.prev_running = running

    def run(self):
        # Prime prev_running
        try:
            self.prev_running = { (p.info.get('name') or '').lower() for p in psutil.process_iter(['name']) }
        except Exception:
            self.prev_running = set()
        while not self.stop_event.is_set():
            try:
                self._check_high_cpu()
                self._check_network()
                self._check_app_crash()
            except Exception as e:
                Alerts.log(f"ITSMHelper loop error: {e}")
            time.sleep(30)

    def stop(self):
        self.stop_event.set()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Employee Monitor System')
    parser.add_argument('--serve', action='store_true', help='Start HTTP livestream server')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=5000)
    args = parser.parse_args()

    app = MonitorApp()
    app.start(enable_http=args.serve, host=args.host, port=args.port)
    Alerts.log('Monitor running. Press Ctrl+C to stop.')
    try:
        while True:
            time.sleep(2)
            # periodic wellness computation
            if int(time.time()) % 60 == 0:
                compute_wellness()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()
        Alerts.log('Monitor stopped.')


if __name__ == '__main__':
    main()
