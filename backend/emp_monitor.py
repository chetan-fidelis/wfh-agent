import os
import sys
import time
import json
import datetime as dt
import threading
import sqlite3
import subprocess
import platform
import re
import copy
import uuid
import socket
import ipaddress
import random
import shutil
import base64
import hashlib
import urllib.parse
from urllib.parse import urlparse
from typing import Dict, List, Tuple, Optional, Any, Set, Union
from dataclasses import dataclass, asdict
import warnings
import gc

# Import LocalStorage for SQLite with Postgres sync
try:
    from local_storage import LocalStorage
except ImportError:
    # Define a stub class if the module is not available
    class LocalStorage:
        def __init__(self, *args, **kwargs):
            pass
        def log(self, message):
            print(f"[LocalStorage-Stub] {message}")
        def insert_website_usage(self, *args, **kwargs):
            pass
        def insert_productivity(self, *args, **kwargs):
            pass
        def insert_timeline(self, *args, **kwargs):
            pass
        def insert_screenshot(self, *args, **kwargs):
            pass
        def update_screenshot_upload(self, *args, **kwargs):
            pass
        def insert_wellness(self, *args, **kwargs):
            pass

# Import API sync module
try:
    from api_sync import APISync
    API_SYNC_AVAILABLE = True
    print("[DEBUG] API sync module imported successfully")
except ImportError as e:
    API_SYNC_AVAILABLE = False
    print(f"[DEBUG] API sync import failed: {e}")
except Exception as e:
    API_SYNC_AVAILABLE = False
    print(f"[DEBUG] API sync import error: {e}")

# Import download monitor for Naukri file tracking (v2 - simplified, bulletproof)
try:
    from download_monitor_v2 import DownloadMonitorV2 as DownloadMonitor
    DOWNLOAD_MONITOR_AVAILABLE = True
except ImportError as e:
    print(f"[emp_monitor] Download monitor import failed: {e}")
    DOWNLOAD_MONITOR_AVAILABLE = False
    print(f"[DEBUG] Download monitor import failed: {e}")
except Exception as e:
    DOWNLOAD_MONITOR_AVAILABLE = False
    print(f"[DEBUG] Download monitor import error: {e}")

# Third-party deps
from flask import Flask, send_file, jsonify, Response, request
from werkzeug.utils import secure_filename
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
    # Suppress pkg_resources deprecation warning emitted by win10toast
    warnings.filterwarnings(
        'ignore',
        category=UserWarning,
        module=r'win10toast(\.|$)'
    )
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
# Default ingest URL fallback (can be overridden by env WFH_DEFAULT_INGEST_URL)
DEFAULT_INGEST_URL = os.environ.get('WFH_DEFAULT_INGEST_URL', 'http://20.197.8.101:5050').rstrip('/')
# Resolve config path with environment override and sensible fallbacks
CONFIG_PATH = os.environ.get('WFH_CONFIG_PATH')
if not CONFIG_PATH:
    candidates = [
        # Prefer per-user roaming data first (survives updates)
        os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming', 'wfh-agent-desktop', 'monitor_data', 'config.json'),
        # Then prefer current working directory (developer runs)
        os.path.join(os.getcwd(), 'monitor_data', 'config.json'),
        # Finally, fall back to bundled data next to the executable
        os.path.join(DATA_DIR, 'config.json'),
    ]
    for _p in candidates:
        try:
            if os.path.exists(_p):
                CONFIG_PATH = _p
                break
        except Exception:
            continue
if not CONFIG_PATH:
    CONFIG_PATH = os.path.join(DATA_DIR, 'config.json')
DEVICES_INFO_PATH = os.path.join(DATA_DIR, 'devices.json')
ALERTS_LOG = os.path.join(DATA_DIR, 'alerts.log')
LATEST_JPG = os.path.join(DATA_DIR, 'latest.jpg')
USAGE_JSON = os.path.join(DATA_DIR, 'usage.json')
WELLNESS_JSON = os.path.join(DATA_DIR, 'wellness.json')
TIMELINE_JSON = os.path.join(DATA_DIR, 'timeline.json')
WEBSITE_USAGE_JSON = os.path.join(DATA_DIR, 'website_usage.json')
WEBSITE_USAGE_BY_TAG_JSON = os.path.join(DATA_DIR, 'website_usage_by_tag.json')
WEBSITE_SESSIONS_JSON = os.path.join(DATA_DIR, 'website_sessions.json')
HEARTBEAT_DIR = os.path.join(DATA_DIR, 'heartbeats')
ITSM_TICKETS_JSON = os.path.join(DATA_DIR, 'itsm_tickets.json')
ESG_DIR = os.path.join(DATA_DIR, 'esg')
SHOTS_DIR = os.path.join(DATA_DIR, 'shots')
UPLOAD_BASE_DIR = os.environ.get('SCREENSHOT_UPLOAD_DIR', os.path.join(DATA_DIR, 'uploads'))

SESSION_DURATION_SEC = 5 * 60  # 5 minutes
SCREEN_FPS = 0.1  # 1 frame per 10 seconds (reduced from 1 FPS for performance)
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
        "high_memory_threshold": 90,         # percent
        "high_memory_duration_sec": 180,     # sustained duration
        "low_disk_threshold": 15,            # percent free space
        "min_uptime_for_reboot_detect": 300, # 5 minutes
        "battery_health_threshold": 60,      # percent
        "cooldowns": {                        # seconds to suppress duplicate tickets
            "high_cpu": 600,
            "high_memory": 600,
            "low_disk": 3600,
            "app_crash": 600,
            "unexpected_reboot": 3600,
            "service_stopped": 1800,
            "usb_device": 1800,
            "security_disabled": 1800,
            "repeated_crash": 1800,
            "battery_issue": 3600
        },
        "network_check_urls": [
            "http://clients3.google.com/generate_204",
            "https://www.msftconnecttest.com/connecttest.txt"
        ],
        "watched_apps": ["code.exe"],       # critical apps to watch for crash
        "watched_services": [                # critical services to monitor
            "Windefend",                     # Windows Defender
            "WinDefend",
            "SecurityHealthService"
        ],
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
    "download_monitor": {
        "enabled": False,                # Enable for recruitment-related employees
        "api_url": "https://nexoleats.fidelisam.in/api",
        "target_designations": [
            "recruiter", "hr", "hiring_manager",
            "manager - talent acquisition",
            "associate manager - talent acquisition",
            "senior executive - talent acquisition",
            "team lead - talent acquisition",
            "executive - talent acquisition",
            "associate manager – talent acquisition",
            "vice president - talent acquisition",
            "executive - talent acquisition",
            "trainee - talent acquisition",
            "senior executive - talent acquisition - rpo",
            "talent acquisition partner",
            "talent acquisition",
            "associate vice president - talent acquisition"
        ],
        "check_interval_sec": 30,        # Check downloads every 30 seconds
        "max_file_size_mb": 100,         # Max file size to upload
        "allowed_extensions": ["pdf", "docx", "txt"],  # Naukri-specific
        "naukri_pattern": "Naukri_",     # Filename pattern to match
        "monitor_naukri_only": True      # Only monitor Naukri_*.pdf files
    }
    ,
    "ingestion": {
        "enabled": True,
        "mode": "api",                   # api | postgres | file
        "file_retention_days": 30,       # how long to keep daily heartbeat files
        "batch_size": 200,               # max items per flush
        "flush_interval_sec": 30,        # flush cadence
        "heartbeat_sync_sec": 3600,      # how often to sync heartbeat (60 minutes)
        "full_sync_sec": 7200,           # how often to sync all data (120 minutes)
        "sampling": {
            "state_change": True,        # emit on status/process/url change
            "periodic_sec": 60,          # periodic snapshot interval
            "active_burst_sec": 5,       # extra sampling during active
            "active_burst_cpu_percent": 50
        },
        "screenshot": {
            "encrypt": True,             # Enable AES-256-GCM encryption for screenshots
            "encryption_key": None,      # Optional custom key (None = machine-derived)
            "compress": True,            # Compress before encryption
            "max_size": [1920, 1080],    # Maximum dimensions
            "quality": 75                # JPEG quality (1-100)
        },
        "api": {
            "base_url": "http://20.197.8.101:5050",
            "auth_header": "X-Api-Key",
            "auth_env": "WFH_AGENT_API_KEY",
            "api_key": ""                # Set during deployment
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


# Integrated LocalStorage class for SQLite with optimized Postgres sync
class LocalStorage:
    """Local SQLite storage with optimized periodic sync to Postgres"""
    
    def __init__(self, data_dir, app_ref=None):
        self.data_dir = data_dir
        self.db_path = os.path.join(data_dir, 'local_data.db')
        self.app_ref = app_ref
        self.last_sync = dt.datetime.now() - dt.timedelta(minutes=10)  # Force initial sync
        self.last_full_sync = dt.datetime.now() - dt.timedelta(minutes=15)  # Force initial full sync
        # Make sync intervals configurable
        if self.app_ref and hasattr(self.app_ref, 'cfg'):
            ing = self.app_ref.cfg.data.get('ingestion', {})
            self.sync_interval = int(ing.get('heartbeat_sync_sec', 1800))  # default 30 min
            self.full_sync_interval = int(ing.get('full_sync_sec', 3600))   # default 60 min
        else:
            # Safe defaults if config not available
            self.sync_interval = 3600  # 60 minutes
            self.full_sync_interval = 7200  # 120 minutes
        # Ensure a lock exists for sync
        self.sync_lock = threading.Lock()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create tables if they don't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS website_usage (
                emp_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                domain TEXT NOT NULL,
                duration_seconds REAL NOT NULL,
                tag TEXT NOT NULL,
                start_time TEXT,
                end_time TEXT,
                last_updated TEXT NOT NULL,
                synced INTEGER DEFAULT 0,
                PRIMARY KEY (emp_id, date, domain)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS website_usage_by_tag (
                emp_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                tag TEXT NOT NULL,
                duration_seconds REAL NOT NULL,
                last_updated TEXT NOT NULL,
                synced INTEGER DEFAULT 0,
                PRIMARY KEY (emp_id, date, tag)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS productivity (
                emp_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                process_name TEXT NOT NULL,
                tag TEXT NOT NULL,
                duration_seconds REAL NOT NULL,
                last_updated TEXT NOT NULL,
                synced INTEGER DEFAULT 0,
                PRIMARY KEY (emp_id, date, process_name, tag)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS productivity_by_tag (
                emp_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                tag TEXT NOT NULL,
                duration_seconds REAL NOT NULL,
                last_updated TEXT NOT NULL,
                synced INTEGER DEFAULT 0,
                PRIMARY KEY (emp_id, date, tag)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS timeline (
                emp_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                hour INTEGER NOT NULL,
                status TEXT NOT NULL,
                duration_seconds INTEGER NOT NULL,
                last_updated TEXT NOT NULL,
                synced INTEGER DEFAULT 0,
                PRIMARY KEY (emp_id, date, hour, status)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS screenshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                emp_id INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                captured_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                uploaded INTEGER DEFAULT 0,
                upload_url TEXT,
                last_updated TEXT,
                synced INTEGER DEFAULT 0,
                UNIQUE (emp_id, file_name)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS wellness (
                emp_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                active_secs INTEGER NOT NULL,
                idle_secs INTEGER NOT NULL,
                offline_secs INTEGER NOT NULL,
                work_secs INTEGER NOT NULL,
                active_ratio REAL NOT NULL,
                idle_ratio REAL NOT NULL,
                utilization_percent REAL NOT NULL,
                underutilized INTEGER NOT NULL,
                overburdened INTEGER NOT NULL,
                burnout_risk INTEGER NOT NULL,
                steady_performer INTEGER NOT NULL,
                last_updated TEXT NOT NULL,
                synced INTEGER DEFAULT 0,
                PRIMARY KEY (emp_id, date)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS heartbeat (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                emp_id INTEGER NOT NULL,
                ts TEXT NOT NULL,
                status TEXT NOT NULL,
                cpu_percent REAL NOT NULL,
                memory_percent REAL NOT NULL,
                process_name TEXT NOT NULL,
                window_title TEXT NOT NULL,
                domain TEXT,
                url TEXT,
                battery_level REAL,
                battery_plugged INTEGER,
                geo TEXT,
                synced INTEGER DEFAULT 0,
                UNIQUE (emp_id, ts)
            )
        ''')

        # Migration: Add last_updated column to screenshots if it doesn't exist
        try:
            cursor.execute("SELECT last_updated FROM screenshots LIMIT 1")
        except sqlite3.OperationalError:
            # Column doesn't exist, add it
            cursor.execute("ALTER TABLE screenshots ADD COLUMN last_updated TEXT")

        conn.commit()
        conn.close()

        # ALWAYS log this before anything else
        if self.app_ref and hasattr(self.app_ref, 'log'):
            self.app_ref.log(f"[INIT] API_SYNC_AVAILABLE={API_SYNC_AVAILABLE}, app_ref={self.app_ref is not None}")

        # Initialize API sync if enabled
        self.api_sync = None
        if API_SYNC_AVAILABLE and self.app_ref:
            ing_cfg = self.app_ref.cfg.data.get('ingestion', {})
            self.log(f"Ingestion mode: {ing_cfg.get('mode')}")
            if ing_cfg.get('mode') == 'api':
                try:
                    self.api_sync = APISync(self.db_path, self.app_ref.cfg.data, self.app_ref)
                    self.log("API sync initialized successfully!")
                except Exception as e:
                    self.log(f"Failed to initialize API sync: {e}")
        elif self.app_ref:
            self.log("API sync module import failed - using direct PostgreSQL mode")

        if self.app_ref:
            self.log("SQLite database initialized")
    
    def log(self, message):
        """Log message using app_ref if available"""
        if self.app_ref and hasattr(self.app_ref, 'log'):
            self.app_ref.log(message)
        else:
            print(f"[LocalStorage] {message}")
    
    def insert_heartbeat(self, emp_id, ts, status, cpu_percent, memory_percent, process_name, window_title, domain=None, url=None, battery_level=None, battery_plugged=None, geo=None):
        """Insert heartbeat data into local SQLite"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = dt.datetime.now().isoformat()
        # Normalize status to satisfy NOT NULL constraint
        try:
            status_norm = (status or '').strip() or 'unknown'
        except Exception:
            status_norm = 'unknown'
        
        try:
            cursor.execute('''
                INSERT INTO heartbeat (
                    emp_id, ts, status, cpu_percent, memory_percent, process_name, window_title,
                    domain, url, battery_level, battery_plugged, geo, synced
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT (emp_id, ts) DO UPDATE SET
                    status = ?,
                    cpu_percent = ?,
                    memory_percent = ?,
                    process_name = ?,
                    window_title = ?,
                    domain = ?,
                    url = ?,
                    battery_level = ?,
                    battery_plugged = ?,
                    geo = ?,
                    synced = 0
            ''', (
                emp_id, ts, status_norm, cpu_percent, memory_percent, process_name, window_title,
                domain, url, battery_level, battery_plugged, json.dumps(geo) if geo else None, 
                # For ON CONFLICT UPDATE
                status_norm, cpu_percent, memory_percent, process_name, window_title,
                domain, url, battery_level, battery_plugged, json.dumps(geo) if geo else None
            ))
            
            conn.commit()
            # Throttle verbose local DB logs
            if self.app_ref and self.app_ref.cfg.data.get('logging', {}).get('verbose_local', False):
                self.log(f"Heartbeat data saved to local DB: {ts} - {process_name}")
        except Exception as e:
            self.log(f"Error inserting heartbeat: {e}")
        finally:
            conn.close()
        
        # Sync heartbeat data immediately (but only heartbeat data)
        self.check_sync_needed(data_type='heartbeat')
    
    def insert_website_usage(self, emp_id, date, domain, duration, tag):
        """Insert website usage data into local SQLite"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = dt.datetime.now().isoformat()
        
        try:
            # Insert/update website usage
            cursor.execute('''
                INSERT INTO website_usage (emp_id, date, domain, duration_seconds, tag, last_updated, synced)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT (emp_id, date, domain) DO UPDATE SET
                    duration_seconds = duration_seconds + ?,
                    last_updated = ?,
                    synced = 0
            ''', (emp_id, date, domain, duration, tag, now, duration, now))
            
            # Insert/update website usage by tag
            cursor.execute('''
                INSERT INTO website_usage_by_tag (emp_id, date, tag, duration_seconds, last_updated, synced)
                VALUES (?, ?, ?, ?, ?, 0)
                ON CONFLICT (emp_id, date, tag) DO UPDATE SET
                    duration_seconds = duration_seconds + ?,
                    last_updated = ?,
                    synced = 0
            ''', (emp_id, date, tag, duration, now, duration, now))
            
            conn.commit()
            if self.app_ref and self.app_ref.cfg.data.get('logging', {}).get('verbose_local', False):
                self.log(f"Website usage data saved to local DB: {domain} - {duration} seconds")
        except Exception as e:
            self.log(f"Error inserting website usage: {e}")
        finally:
            conn.close()
        
        # Check if it's time for a full sync
        self.check_sync_needed()
    
    def insert_productivity(self, emp_id, date, process_name, tag, duration):
        """Insert productivity data into local SQLite"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = dt.datetime.now().isoformat()
        
        try:
            # Insert/update productivity
            cursor.execute('''
                INSERT INTO productivity (emp_id, date, process_name, tag, duration_seconds, last_updated, synced)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT (emp_id, date, process_name, tag) DO UPDATE SET
                    duration_seconds = duration_seconds + ?,
                    last_updated = ?,
                    synced = 0
            ''', (emp_id, date, process_name, tag, duration, now, duration, now))
            
            # Insert/update productivity by tag
            cursor.execute('''
                INSERT INTO productivity_by_tag (emp_id, date, tag, duration_seconds, last_updated, synced)
                VALUES (?, ?, ?, ?, ?, 0)
                ON CONFLICT (emp_id, date, tag) DO UPDATE SET
                    duration_seconds = duration_seconds + ?,
                    last_updated = ?,
                    synced = 0
            ''', (emp_id, date, tag, duration, now, duration, now))
            
            conn.commit()
            if self.app_ref and self.app_ref.cfg.data.get('logging', {}).get('verbose_local', False):
                self.log(f"Productivity data saved to local DB: {process_name} - {duration} seconds ({tag})")
        except Exception as e:
            self.log(f"Error inserting productivity: {e}")
        finally:
            conn.close()
        
        # Check if it's time for a full sync
        self.check_sync_needed()
    
    def insert_timeline(self, emp_id, date, hour, status, duration):
        """Insert timeline data into local SQLite"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = dt.datetime.now().isoformat()
        
        try:
            cursor.execute('''
                INSERT INTO timeline (emp_id, date, hour, status, duration_seconds, last_updated, synced)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT (emp_id, date, hour, status) DO UPDATE SET
                    duration_seconds = duration_seconds + ?,
                    last_updated = ?,
                    synced = 0
            ''', (emp_id, date, hour, status, duration, now, duration, now))
            
            conn.commit()
            if self.app_ref and self.app_ref.cfg.data.get('logging', {}).get('verbose_local', False):
                self.log(f"Timeline data saved to local DB: {date} hour {hour} - {status} {duration} seconds")
        except Exception as e:
            self.log(f"Error inserting timeline: {e}")
        finally:
            conn.close()
        
        # Check if it's time for a full sync
        self.check_sync_needed()
    
    def insert_screenshot(self, emp_id, file_name, file_path, file_size, captured_at):
        """Insert screenshot metadata into local SQLite"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = dt.datetime.now().isoformat()
        
        try:
            cursor.execute('''
                INSERT INTO screenshots (emp_id, file_name, file_path, file_size, captured_at, created_at, synced)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT (emp_id, file_name) DO UPDATE SET
                    file_path = ?,
                    file_size = ?,
                    captured_at = ?,
                    created_at = ?,
                    synced = 0
            ''', (emp_id, file_name, file_path, file_size, captured_at, now, file_path, file_size, captured_at, now))
            
            conn.commit()
            if self.app_ref and self.app_ref.cfg.data.get('logging', {}).get('verbose_local', False):
                self.log(f"Screenshot metadata saved to local DB: {file_name}")
        except Exception as e:
            self.log(f"Error inserting screenshot: {e}")
        finally:
            conn.close()
        
        # Sync screenshots immediately
        self.check_sync_needed(data_type='screenshot')
    
    def update_screenshot_upload(self, emp_id, file_name, upload_url):
        """Update screenshot upload status in local SQLite"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = dt.datetime.now().isoformat()
        
        try:
            cursor.execute('''
                UPDATE screenshots
                SET uploaded = 1, upload_url = ?, last_updated = ?, synced = 0
                WHERE emp_id = ? AND file_name = ?
            ''', (upload_url, now, emp_id, file_name))
            
            conn.commit()
            self.log(f"Screenshot upload status updated in local DB: {file_name}")
        except Exception as e:
            self.log(f"Error updating screenshot upload status: {e}")
        finally:
            conn.close()
        
        # Sync screenshots immediately
        self.check_sync_needed(data_type='screenshot')
    
    def insert_wellness(self, emp_id, date, data):
        """Insert wellness data into local SQLite"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        now = dt.datetime.now().isoformat()
        
        try:
            cursor.execute('''
                INSERT INTO wellness (
                    emp_id, date, active_secs, idle_secs, offline_secs, work_secs,
                    active_ratio, idle_ratio, utilization_percent,
                    underutilized, overburdened, burnout_risk, steady_performer,
                    last_updated, synced
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT (emp_id, date) DO UPDATE SET
                    active_secs = ?,
                    idle_secs = ?,
                    offline_secs = ?,
                    work_secs = ?,
                    active_ratio = ?,
                    idle_ratio = ?,
                    utilization_percent = ?,
                    underutilized = ?,
                    overburdened = ?,
                    burnout_risk = ?,
                    steady_performer = ?,
                    last_updated = ?,
                    synced = 0
            ''', (
                emp_id, date, 
                data['active_secs'], data['idle_secs'], data['offline_secs'], data['work_secs'],
                data['active_ratio'], data['idle_ratio'], data['utilization_percent'],
                1 if data['underutilized'] else 0, 
                1 if data['overburdened'] else 0,
                1 if data['burnout_risk'] else 0, 
                1 if data['steady_performer'] else 0,
                now,
                # For ON CONFLICT UPDATE
                data['active_secs'], data['idle_secs'], data['offline_secs'], data['work_secs'],
                data['active_ratio'], data['idle_ratio'], data['utilization_percent'],
                1 if data['underutilized'] else 0, 
                1 if data['overburdened'] else 0,
                1 if data['burnout_risk'] else 0, 
                1 if data['steady_performer'] else 0,
                now
            ))
            
            conn.commit()
            if self.app_ref and self.app_ref.cfg.data.get('logging', {}).get('verbose_local', False):
                self.log(f"Wellness data saved to local DB for date: {date}")
        except Exception as e:
            self.log(f"Error inserting wellness: {e}")
        finally:
            conn.close()
        
        # Check if it's time for a full sync
        self.check_sync_needed()
    def check_sync_needed(self, data_type=None):
        """Check if it's time to sync with Postgres
        
        Args:
            data_type: Optional type of data being inserted. If specified, may trigger
                      immediate sync for certain data types (e.g., screenshots)
        """
        now = dt.datetime.now()
        
        # For screenshots, sync immediately
        if data_type == 'screenshot':
            threading.Thread(target=self.sync_to_postgres, args=(['screenshots'],), daemon=True).start()
            return
            
        # For heartbeat data, sync every sync_interval seconds
        if data_type == 'heartbeat':
            if (now - self.last_sync).total_seconds() >= self.sync_interval:
                # Use a separate thread for sync to avoid blocking
                threading.Thread(target=self.sync_to_postgres, args=(['heartbeat'],), daemon=True).start()
                self.last_sync = now
            # DON'T return here - continue to check full sync

        # For all data types, sync everything every full_sync_interval seconds
        if (now - self.last_full_sync).total_seconds() >= self.full_sync_interval:
            threading.Thread(target=self.sync_to_postgres, daemon=True).start()
            self.last_full_sync = now
            self.last_sync = now
    
    def sync_to_postgres(self, tables_to_sync=None):
        """Sync data using configured method (API or direct PostgreSQL)

        Args:
            tables_to_sync: Optional list of tables to sync. If None, sync all tables.
        """
        # Check if we should use API sync
        if self.api_sync:
            return self._sync_via_api()

        # Otherwise use existing direct PostgreSQL sync
        return self._sync_direct_postgres(tables_to_sync)

    def _sync_via_api(self):
        """Sync data via API server using individual endpoint calls"""
        if not self.sync_lock.acquire(blocking=False):
            self.log("Sync already in progress, skipping")
            return

        try:
            emp_id = self.app_ref.cfg.data.get('emp_id', 0)
            if emp_id == 0:
                self.log("No employee ID configured, skipping sync")
                return

            # Get data file paths
            data_dir = os.path.join(self.data_dir, '..', 'monitor_data')
            sessions_file = os.path.join(data_dir, 'work_sessions.json')
            usage_file = os.path.join(data_dir, 'website_usage.json')
            productivity_file = os.path.join(data_dir, 'usage.json')
            wellness_file = os.path.join(data_dir, 'wellness.json')
            tickets_file = os.path.join(data_dir, 'itsm_tickets.json')
            timeline_file = os.path.join(data_dir, 'timeline.json')

            # Sync all data using individual endpoints (API expects separate calls)
            results = self.api_sync.sync_all(
                emp_id,
                sessions_file=sessions_file,
                usage_file=usage_file,
                productivity_file=productivity_file,
                wellness_file=wellness_file,
                tickets_file=tickets_file,
                timeline_file=timeline_file
            )

            for data_type, count in results.items():
                if count > 0:
                    self.log(f"API sync: {count} {data_type} records")

        except Exception as e:
            self.log(f"API sync error: {e}")
        finally:
            self.sync_lock.release()

    def _sync_direct_postgres(self, tables_to_sync=None):
        """Sync all unsynced data to Postgres (direct connection)

        Args:
            tables_to_sync: Optional list of tables to sync. If None, sync all tables.
        """
        # Use lock to prevent multiple syncs running simultaneously
        if not self.sync_lock.acquire(blocking=False):
            self.log("Sync already in progress, skipping")
            return

        try:
            # Get app reference for Postgres connection
            if not self.app_ref:
                self.log("No app reference available for Postgres sync")
                return

            # Check if Postgres is enabled
            ing = self.app_ref.cfg.data.get('ingestion', {})
            if ing.get('mode') != 'postgres':
                self.log("Postgres sync not enabled in config")
                return

            # Only log start after we've confirmed postgres mode is enabled
            self.log(f"Starting sync to Postgres... Tables: {tables_to_sync or 'ALL'}")
            
            # Import psycopg here to avoid circular imports
            try:
                import psycopg
            except ImportError:
                self.log("psycopg not available, skipping sync")
                return
            
            # Get Postgres connection details
            db_cfg = ing.get('db', {})
            dsn = (db_cfg.get('url') or '').strip() or os.environ.get(db_cfg.get('url_env', 'EMP_DB_URL'))
            if not dsn:
                self.log("No Postgres DSN available, skipping sync")
                return
            
            schema = db_cfg.get('schema', 'employee_monitor')
            
            # Connect to SQLite to get unsynced data
            sqlite_conn = sqlite3.connect(self.db_path)
            sqlite_cursor = sqlite_conn.cursor()
            
            # Connect to Postgres
            with psycopg.connect(dsn) as pg_conn:
                with pg_conn.cursor() as pg_cur:
                    # Determine which tables to sync
                    all_tables = [
                        'heartbeat', 'website_usage', 'website_usage_by_tag',
                        'productivity', 'productivity_by_tag', 'timeline',
                        'screenshots', 'wellness'
                    ]
                    
                    tables = tables_to_sync if tables_to_sync else all_tables
                    
                    # Sync each table
                    for table in tables:
                        if table == 'heartbeat':
                            self._sync_heartbeat(sqlite_cursor, pg_cur, schema)
                        elif table == 'website_usage':
                            self._sync_website_usage(sqlite_cursor, pg_cur, schema)
                        elif table == 'website_usage_by_tag':
                            self._sync_website_usage_by_tag(sqlite_cursor, pg_cur, schema)
                        elif table == 'productivity':
                            self._sync_productivity(sqlite_cursor, pg_cur, schema)
                        elif table == 'productivity_by_tag':
                            self._sync_productivity_by_tag(sqlite_cursor, pg_cur, schema)
                        elif table == 'timeline':
                            self._sync_timeline(sqlite_cursor, pg_cur, schema)
                        elif table == 'screenshots':
                            self._sync_screenshots(sqlite_cursor, pg_cur, schema)
                        elif table == 'wellness':
                            self._sync_wellness(sqlite_cursor, pg_cur, schema)
            
            sqlite_conn.close()
            self.log(f"Sync to Postgres completed successfully for tables: {tables}")
            
        except Exception as e:
            self.log(f"Error syncing to Postgres: {e}")
        finally:
            self.sync_lock.release()
    
    def _sync_heartbeat(self, sqlite_cursor, pg_cur, schema):
        """Sync heartbeat data to Postgres"""
        sqlite_cursor.execute("""
            SELECT emp_id, ts, status, cpu_percent, memory_percent, process_name, window_title,
                   domain, url, battery_level, battery_plugged, geo
            FROM heartbeat WHERE synced = 0
        """)
        records = sqlite_cursor.fetchall()
        
        if not records:
            return
        
        # Ensure table exists
        pg_cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {schema}.heartbeat (
                id SERIAL PRIMARY KEY,
                emp_id INTEGER NOT NULL,
                ts TIMESTAMPTZ NOT NULL,
                status VARCHAR(20) NOT NULL,
                cpu_percent REAL NOT NULL,
                memory_percent REAL NOT NULL,
                process_name VARCHAR(255) NOT NULL,
                window_title TEXT NOT NULL,
                domain VARCHAR(255),
                url TEXT,
                battery_level REAL,
                battery_plugged BOOLEAN,
                geo JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (emp_id, ts)
            )
        """)
        
        # Batch insert
        for record in records:
            (emp_id, ts, status, cpu_percent, memory_percent, process_name, window_title,
             domain, url, battery_level, battery_plugged, geo) = record
            if battery_plugged is not None:
                battery_plugged = bool(battery_plugged)
            
            pg_cur.execute(f"""
                INSERT INTO {schema}.heartbeat 
                (emp_id, ts, status, cpu_percent, memory_percent, process_name, window_title,
                 domain, url, battery_level, battery_plugged, geo)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (emp_id, ts) DO NOTHING
            """, (
                emp_id, ts, status, cpu_percent, memory_percent, process_name, window_title,
                domain, url, battery_level, battery_plugged, geo
            ))
        
        # Mark as synced
        sqlite_cursor.execute("UPDATE heartbeat SET synced = 1 WHERE synced = 0")
        sqlite_cursor.connection.commit()
        
        self.log(f"Synced {len(records)} heartbeat records to Postgres")
    def _sync_website_usage(self, sqlite_cursor, pg_cur, schema):
        """Sync website usage data to Postgres"""
        sqlite_cursor.execute("SELECT emp_id, date, domain, duration_seconds, tag FROM website_usage WHERE synced = 0")
        records = sqlite_cursor.fetchall()
        
        if not records:
            return
        
        # Ensure table exists
        pg_cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {schema}.website_usage (
                emp_id INTEGER NOT NULL,
                date DATE NOT NULL,
                domain VARCHAR(255) NOT NULL,
                duration_seconds FLOAT NOT NULL,
                tag VARCHAR(50) NOT NULL,
                start_time TIMESTAMPTZ,
                end_time TIMESTAMPTZ,
                last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (emp_id, date, domain)
            )
        """)
        
        # Batch insert
        for record in records:
            emp_id, date, domain, duration, tag = record
            pg_cur.execute(f"""
                INSERT INTO {schema}.website_usage 
                (emp_id, date, domain, duration_seconds, tag, last_updated)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (emp_id, date, domain) DO UPDATE SET
                    duration_seconds = website_usage.duration_seconds + EXCLUDED.duration_seconds,
                    last_updated = NOW()
            """, (emp_id, date, domain, duration, tag))
        
        # Mark as synced
        sqlite_cursor.execute("UPDATE website_usage SET synced = 1 WHERE synced = 0")
        sqlite_cursor.connection.commit()
        
        self.log(f"Synced {len(records)} website usage records to Postgres")
    
    def _sync_website_usage_by_tag(self, sqlite_cursor, pg_cur, schema):
        """Sync website usage by tag data to Postgres"""
        sqlite_cursor.execute("SELECT emp_id, date, tag, duration_seconds FROM website_usage_by_tag WHERE synced = 0")
        records = sqlite_cursor.fetchall()
        
        if not records:
            return
        
        # Ensure table exists
        pg_cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {schema}.website_usage_by_tag (
                emp_id INTEGER NOT NULL,
                date DATE NOT NULL,
                tag VARCHAR(50) NOT NULL,
                duration_seconds FLOAT NOT NULL,
                last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (emp_id, date, tag)
            )
        """)
        
        # Batch insert
        for record in records:
            emp_id, date, tag, duration = record
            pg_cur.execute(f"""
                INSERT INTO {schema}.website_usage_by_tag 
                (emp_id, date, tag, duration_seconds, last_updated)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (emp_id, date, tag) DO UPDATE SET
                    duration_seconds = website_usage_by_tag.duration_seconds + EXCLUDED.duration_seconds,
                    last_updated = NOW()
            """, (emp_id, date, tag, duration))
        
        # Mark as synced
        sqlite_cursor.execute("UPDATE website_usage_by_tag SET synced = 1 WHERE synced = 0")
        sqlite_cursor.connection.commit()
        
        self.log(f"Synced {len(records)} website usage by tag records to Postgres")
    
    def _sync_productivity(self, sqlite_cursor, pg_cur, schema):
        """Sync productivity data to Postgres"""
        sqlite_cursor.execute("SELECT emp_id, date, process_name, tag, duration_seconds FROM productivity WHERE synced = 0")
        records = sqlite_cursor.fetchall()
        
        if not records:
            return
        
        # Ensure table exists
        pg_cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {schema}.productivity (
                emp_id INTEGER NOT NULL,
                date DATE NOT NULL,
                process_name VARCHAR(255) NOT NULL,
                tag VARCHAR(50) NOT NULL,
                duration_seconds FLOAT NOT NULL,
                last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (emp_id, date, process_name, tag)
            )
        """)
        
        # Batch insert
        for record in records:
            emp_id, date, process_name, tag, duration = record
            pg_cur.execute(f"""
                INSERT INTO {schema}.productivity 
                (emp_id, date, process_name, tag, duration_seconds, last_updated)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (emp_id, date, process_name, tag) DO UPDATE SET
                    duration_seconds = productivity.duration_seconds + EXCLUDED.duration_seconds,
                    last_updated = NOW()
            """, (emp_id, date, process_name, tag, duration))
        
        # Mark as synced
        sqlite_cursor.execute("UPDATE productivity SET synced = 1 WHERE synced = 0")
        sqlite_cursor.connection.commit()
        
        self.log(f"Synced {len(records)} productivity records to Postgres")
    
    def _sync_productivity_by_tag(self, sqlite_cursor, pg_cur, schema):
        """Sync productivity by tag data to Postgres"""
        sqlite_cursor.execute("SELECT emp_id, date, tag, duration_seconds FROM productivity_by_tag WHERE synced = 0")
        records = sqlite_cursor.fetchall()
        
        if not records:
            return
        
        # Ensure table exists
        pg_cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {schema}.productivity_by_tag (
                emp_id INTEGER NOT NULL,
                date DATE NOT NULL,
                tag VARCHAR(50) NOT NULL,
                duration_seconds FLOAT NOT NULL,
                last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (emp_id, date, tag)
            )
        """)
        
        # Batch insert
        for record in records:
            emp_id, date, tag, duration = record
            pg_cur.execute(f"""
                INSERT INTO {schema}.productivity_by_tag 
                (emp_id, date, tag, duration_seconds, last_updated)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (emp_id, date, tag) DO UPDATE SET
                    duration_seconds = productivity_by_tag.duration_seconds + EXCLUDED.duration_seconds,
                    last_updated = NOW()
            """, (emp_id, date, tag, duration))
        
        # Mark as synced
        sqlite_cursor.execute("UPDATE productivity_by_tag SET synced = 1 WHERE synced = 0")
        sqlite_cursor.connection.commit()
        
        self.log(f"Synced {len(records)} productivity by tag records to Postgres")
    def _sync_timeline(self, sqlite_cursor, pg_cur, schema):
        """Sync timeline data to Postgres"""
        sqlite_cursor.execute("SELECT emp_id, date, hour, status, duration_seconds FROM timeline WHERE synced = 0")
        records = sqlite_cursor.fetchall()
        
        if not records:
            return
        
        # Ensure table exists
        pg_cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {schema}.timeline (
                emp_id INTEGER NOT NULL,
                date DATE NOT NULL,
                hour INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL,
                duration_seconds INTEGER NOT NULL,
                last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (emp_id, date, hour, status)
            )
        """)
        
        # Batch insert
        for record in records:
            emp_id, date, hour, status, duration = record
            pg_cur.execute(f"""
                INSERT INTO {schema}.timeline 
                (emp_id, date, hour, status, duration_seconds, last_updated)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (emp_id, date, hour, status) DO UPDATE SET
                    duration_seconds = timeline.duration_seconds + EXCLUDED.duration_seconds,
                    last_updated = NOW()
            """, (emp_id, date, int(hour), status, duration))
        
        # Mark as synced
        sqlite_cursor.execute("UPDATE timeline SET synced = 1 WHERE synced = 0")
        sqlite_cursor.connection.commit()
        
        self.log(f"Synced {len(records)} timeline records to Postgres")
    
    def _sync_screenshots(self, sqlite_cursor, pg_cur, schema):
        """Sync screenshots data to Postgres"""
        sqlite_cursor.execute("""
            SELECT emp_id, file_name, file_path, file_size, captured_at, created_at, uploaded, upload_url 
            FROM screenshots WHERE synced = 0
        """)
        records = sqlite_cursor.fetchall()
        
        if not records:
            return
        
        # Ensure table exists
        pg_cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {schema}.screenshots (
                id SERIAL PRIMARY KEY,
                emp_id INTEGER NOT NULL,
                file_name VARCHAR(255) NOT NULL,
                file_path VARCHAR(512) NOT NULL,
                file_size INTEGER NOT NULL,
                captured_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                uploaded BOOLEAN DEFAULT FALSE,
                upload_url VARCHAR(512),
                UNIQUE (emp_id, file_name)
            )
        """)
        
        # Batch insert
        for record in records:
            emp_id, file_name, file_path, file_size, captured_at, created_at, uploaded, upload_url = record
            pg_cur.execute(f"""
                INSERT INTO {schema}.screenshots 
                (emp_id, file_name, file_path, file_size, captured_at, created_at, uploaded, upload_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (emp_id, file_name) DO UPDATE SET
                    file_path = EXCLUDED.file_path,
                    file_size = EXCLUDED.file_size,
                    captured_at = EXCLUDED.captured_at,
                    created_at = EXCLUDED.created_at,
                    uploaded = EXCLUDED.uploaded,
                    upload_url = EXCLUDED.upload_url
            """, (emp_id, file_name, file_path, file_size, captured_at, created_at, bool(uploaded), upload_url))
        
        # Mark as synced
        sqlite_cursor.execute("UPDATE screenshots SET synced = 1 WHERE synced = 0")
        sqlite_cursor.connection.commit()
        
        self.log(f"Synced {len(records)} screenshot records to Postgres")
    
    def _sync_wellness(self, sqlite_cursor, pg_cur, schema):
        """Sync wellness data to Postgres"""
        sqlite_cursor.execute("""
            SELECT emp_id, date, active_secs, idle_secs, offline_secs, work_secs,
                   active_ratio, idle_ratio, utilization_percent,
                   underutilized, overburdened, burnout_risk, steady_performer
            FROM wellness WHERE synced = 0
        """)
        records = sqlite_cursor.fetchall()
        
        if not records:
            return
        
        # Ensure table exists
        pg_cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {schema}.wellness (
                emp_id INTEGER NOT NULL,
                date DATE NOT NULL,
                active_secs INTEGER NOT NULL,
                idle_secs INTEGER NOT NULL,
                offline_secs INTEGER NOT NULL,
                work_secs INTEGER NOT NULL,
                active_ratio FLOAT NOT NULL,
                idle_ratio FLOAT NOT NULL,
                utilization_percent FLOAT NOT NULL,
                underutilized BOOLEAN NOT NULL,
                overburdened BOOLEAN NOT NULL,
                burnout_risk BOOLEAN NOT NULL,
                steady_performer BOOLEAN NOT NULL,
                last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (emp_id, date)
            )
        """)
        
        # Batch insert
        for record in records:
            (emp_id, date, active_secs, idle_secs, offline_secs, work_secs,
             active_ratio, idle_ratio, utilization_percent,
             underutilized, overburdened, burnout_risk, steady_performer) = record
            
            pg_cur.execute(f"""
                INSERT INTO {schema}.wellness 
                (emp_id, date, active_secs, idle_secs, offline_secs, work_secs,
                 active_ratio, idle_ratio, utilization_percent,
                 underutilized, overburdened, burnout_risk, steady_performer, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (emp_id, date) DO UPDATE SET
                    active_secs = EXCLUDED.active_secs,
                    idle_secs = EXCLUDED.idle_secs,
                    offline_secs = EXCLUDED.offline_secs,
                    work_secs = EXCLUDED.work_secs,
                    active_ratio = EXCLUDED.active_ratio,
                    idle_ratio = EXCLUDED.idle_ratio,
                    utilization_percent = EXCLUDED.utilization_percent,
                    underutilized = EXCLUDED.underutilized,
                    overburdened = EXCLUDED.overburdened,
                    burnout_risk = EXCLUDED.burnout_risk,
                    steady_performer = EXCLUDED.steady_performer,
                    last_updated = NOW()
            """, (
                emp_id, date, active_secs, idle_secs, offline_secs, work_secs,
                active_ratio, idle_ratio, utilization_percent,
                bool(underutilized), bool(overburdened), bool(burnout_risk), bool(steady_performer)
            ))
        
        # Mark as synced
        sqlite_cursor.execute("UPDATE wellness SET synced = 1 WHERE synced = 0")
        sqlite_cursor.connection.commit()
        
        self.log(f"Synced {len(records)} wellness records to Postgres")

@dataclass
class ActivityStats:
    key_presses: int = 0
    mouse_clicks: int = 0
    last_activity_ts: float = 0.0


def activity_asdict(act) -> Dict[str, Any]:
    """Safely convert ActivityStats-like object to dict.
    Falls back gracefully if it's not a dataclass instance.
    """
    try:
        return asdict(act)  # works if dataclass instance
    except Exception:
        return {
            "key_presses": int(getattr(act, "key_presses", 0) or 0),
            "mouse_clicks": int(getattr(act, "mouse_clicks", 0) or 0),
            "last_activity_ts": float(getattr(act, "last_activity_ts", 0.0) or 0.0),
        }

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
        # Prefer user config if current path is the PyInstaller temp bundle
        appdata_cfg = os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming', 'wfh-agent-desktop', 'monitor_data', 'config.json')
        running_from_temp = bool(self.path and ('_MEI' in self.path or 'Temp' in self.path) and ('monitor_data' in self.path))
        try:
            if running_from_temp and os.path.exists(appdata_cfg):
                self.path = appdata_cfg
                Alerts.log(f"[CONFIG] Switched to user config at: {self.path}")
        except Exception:
            pass
        Alerts.log(f"[CONFIG] Loading config from: {self.path}")
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    on_disk = json.load(f)
                # merge shallow
                self.data.update(on_disk)
                # If base_url missing, try to derive via health check from screenshot_upload.server_url, env, or DEFAULT_INGEST_URL
                try:
                    ing = self.data.get('ingestion', {}) or {}
                    api = ing.get('api', {}) or {}
                    base_url = (api.get('base_url') or '').strip()
                    if not base_url:
                        candidates = []
                        su = self.data.get('screenshot_upload', {}) or {}
                        su_url = (su.get('server_url') or '').strip().rstrip('/')
                        if su_url:
                            candidates.append(su_url)
                        env_default = (os.environ.get('WFH_DEFAULT_INGEST_URL') or '').strip().rstrip('/')
                        if env_default:
                            candidates.append(env_default)
                        if DEFAULT_INGEST_URL:
                            candidates.append(DEFAULT_INGEST_URL)
                        for url in candidates:
                            try:
                                r = requests.get(url + '/health', timeout=2)
                                if r.ok:
                                    api['base_url'] = url
                                    ing['api'] = api
                                    ing['mode'] = 'api'
                                    self.data['ingestion'] = ing
                                    Alerts.log(f"[CONFIG] Auto-set ingestion.api.base_url from health check: {url}")
                                    break
                            except Exception:
                                continue
                except Exception:
                    pass
                # Force API mode automatically if API base_url is configured
                try:
                    ing = self.data.get('ingestion', {}) or {}
                    api = ing.get('api', {}) or {}
                    base_url = (api.get('base_url') or '').strip()
                    if base_url:
                        if ing.get('mode') != 'api':
                            ing['mode'] = 'api'
                            self.data['ingestion'] = ing
                            Alerts.log("[CONFIG] Detected ingestion.api.base_url; auto-forcing ingestion mode to 'api'")
                except Exception:
                    pass
                # If we are running from temp and AppData config does not exist, persist normalized config there for future runs
                try:
                    if running_from_temp and not os.path.exists(appdata_cfg):
                        os.makedirs(os.path.dirname(appdata_cfg), exist_ok=True)
                        with open(appdata_cfg, 'w', encoding='utf-8') as wf:
                            json.dump(self.data, wf, indent=2)
                        Alerts.log(f"[CONFIG] Created user config at: {appdata_cfg}")
                except Exception as e:
                    Alerts.log(f"[CONFIG] Failed to create user config at AppData: {e}")
                Alerts.log(f"[CONFIG] Config loaded successfully, ingestion mode: {self.data.get('ingestion', {}).get('mode', 'NOT SET')}")
            except Exception as e:
                Alerts.log(f"Config load error: {e}")
        else:
            Alerts.log(f"[CONFIG] Config file not found, creating default config")
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
            time.sleep(1.0)  # Reduced from 0.1 to 1.0 for performance

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
        mode = cfg.get('mode', 'twice_daily')  # 'twice_daily' or 'random'
        today = dt.datetime.now().date()
        import random
        self.targets = []
        
        if mode == 'twice_daily' and per_day == 2:
            # Guaranteed morning + afternoon distribution
            # Morning window: 9:30 AM - 12:30 PM
            morning_start = dt.datetime.combine(today, dt.time(9, 30))
            morning_end = dt.datetime.combine(today, dt.time(12, 30))
            morning_seconds = int((morning_end - morning_start).total_seconds())
            morning_offset = random.randint(0, morning_seconds)
            morning_time = morning_start + dt.timedelta(seconds=morning_offset)
            
            # Afternoon window: 2:00 PM - 5:30 PM
            afternoon_start = dt.datetime.combine(today, dt.time(14, 0))
            afternoon_end = dt.datetime.combine(today, dt.time(17, 30))
            afternoon_seconds = int((afternoon_end - afternoon_start).total_seconds())
            afternoon_offset = random.randint(0, afternoon_seconds)
            afternoon_time = afternoon_start + dt.timedelta(seconds=afternoon_offset)
            
            self.targets = [morning_time, afternoon_time]
            Alerts.log(f"Scheduled screenshots: Morning {morning_time.strftime('%H:%M')}, Afternoon {afternoon_time.strftime('%H:%M')}")
        else:
            # Legacy random mode - pick N random times across work hours
            start_s = cfg.get('start', '09:30')
            end_s = cfg.get('end', '18:30')
            st = dt.datetime.combine(today, dt.datetime.strptime(start_s, '%H:%M').time())
            et = dt.datetime.combine(today, dt.datetime.strptime(end_s, '%H:%M').time())
            if et <= st:
                et = st + dt.timedelta(hours=9)
            span_sec = (et - st).total_seconds()
            picks = sorted(random.sample(range(int(span_sec)), k=max(1, per_day)))
            for p in picks:
                self.targets.append(st + dt.timedelta(seconds=p))
            Alerts.log(f"Scheduled {per_day} random screenshots")
        
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
                
                # Convert to PIL Image for compression and resizing
                pil_img = Image.frombytes('RGB', img.size, img.rgb)
                
                # Get compression settings from config
                cfg = self.app.cfg.data.get('scheduled_shots', {})
                compression = cfg.get('compression', {})
                max_width = compression.get('max_width', 1920)
                max_height = compression.get('max_height', 1080)
                quality = compression.get('quality', 75)
                
                # Resize if too large (reduces file size significantly)
                original_size = pil_img.size
                if pil_img.width > max_width or pil_img.height > max_height:
                    pil_img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                    Alerts.log(f"Screenshot resized: {original_size} -> {pil_img.size}")
                
                # Save with optimized compression
                pil_img.save(out_path, 'JPEG', quality=quality, optimize=True)
                
                # Log file size
                file_size_kb = os.path.getsize(out_path) / 1024
                Alerts.log(f"Screenshot saved: {file_size_kb:.1f} KB")
                
                try:
                    shutil.copyfile(out_path, LATEST_JPG)
                except Exception:
                    pass

                # Upload screenshot to server with retry
                self._upload_screenshot_with_retry(out_path, ts)

                Alerts.log(f"Scheduled shot captured: {out_path}")
                return True
        except Exception as e:
            Alerts.log(f"Scheduled shot error: {e}")
        return False

    def _upload_screenshot_with_retry(self, file_path: str, timestamp: str, max_attempts: int = 3):
        """Upload screenshot with retry mechanism"""
        cfg = self.app.cfg.data.get('scheduled_shots', {}).get('upload', {})
        max_attempts = cfg.get('retry_attempts', 3)
        retry_delay = cfg.get('retry_delay_sec', 5)
        
        for attempt in range(max_attempts):
            try:
                success = self._upload_screenshot(file_path, timestamp)
                if success:
                    Alerts.log(f"Screenshot uploaded successfully on attempt {attempt + 1}")
                    return True
                if attempt < max_attempts - 1:
                    Alerts.log(f"Upload attempt {attempt + 1} failed, retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
            except Exception as e:
                Alerts.log(f"Upload attempt {attempt + 1} error: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(retry_delay)
        
        # All attempts failed - queue for later retry
        Alerts.log(f"All {max_attempts} upload attempts failed, queuing for later")
        self._queue_failed_upload(file_path, timestamp)
        return False
    
    def _queue_failed_upload(self, file_path: str, timestamp: str):
        """Queue failed upload for retry"""
        queue_file = os.path.join(DATA_DIR, 'screenshot_upload_queue.json')
        try:
            queue = []
            if os.path.exists(queue_file):
                with open(queue_file, 'r', encoding='utf-8') as f:
                    queue = json.load(f)
            
            queue.append({
                'file_path': file_path,
                'timestamp': timestamp,
                'queued_at': dt.datetime.now().isoformat(),
                'attempts': 0
            })
            
            with open(queue_file, 'w', encoding='utf-8') as f:
                json.dump(queue, f, indent=2)
            
            Alerts.log(f"Screenshot queued for retry: {os.path.basename(file_path)}")
        except Exception as e:
            Alerts.log(f"Failed to queue upload: {e}")
    
    def _upload_screenshot(self, file_path: str, timestamp: str) -> bool:
        """Upload screenshot to server if configured and store metadata in database"""
        try:
            emp_id = int(self.app.cfg.data.get('emp_id', 0))
            if not emp_id:
                return

            # Get file info
            file_size = os.path.getsize(file_path)
            file_name = os.path.basename(file_path)
            captured_at = dt.datetime.strptime(timestamp, '%Y%m%d_%H%M%S').isoformat()

            # Store metadata in local SQLite first
            if self.app.local_storage:
                self.app.local_storage.insert_screenshot(emp_id, file_name, file_path, file_size, captured_at)

            # Check ingestion mode for upload
            ing = self.app.cfg.data.get('ingestion', {})

            # If using API mode, upload via API sync
            if ing.get('mode') == 'api' and self.app.local_storage and self.app.local_storage.api_sync:
                try:
                    success = self.app.local_storage.api_sync.upload_screenshot(emp_id, file_path, captured_at)
                    if success and self.app.local_storage:
                        # Update upload status in local storage
                        self.app.local_storage.update_screenshot_upload(emp_id, file_name, f"api://{file_name}")
                    return success
                except Exception as e:
                    Alerts.log(f"API screenshot upload error: {e}")
                    # Fall through to legacy upload method if API fails
                    return False

            # Store in database if using direct Postgres
            if ing.get('mode') == 'postgres' and psycopg is not None:
                db_cfg = ing.get('db', {})
                dsn = (db_cfg.get('url') or '').strip() or os.environ.get(db_cfg.get('url_env', 'EMP_DB_URL'))
                if dsn:
                    schema = db_cfg.get('schema', 'employee_monitor')

                    with psycopg.connect(dsn) as conn:
                        with conn.cursor() as cur:
                            # Create screenshots table if not exists
                            cur.execute(f"""
                                CREATE TABLE IF NOT EXISTS {schema}.screenshots (
                                    id SERIAL PRIMARY KEY,
                                    emp_id INTEGER NOT NULL,
                                    file_name VARCHAR(255) NOT NULL,
                                    file_path VARCHAR(512) NOT NULL,
                                    file_size INTEGER NOT NULL,
                                    captured_at TIMESTAMPTZ NOT NULL,
                                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                    uploaded BOOLEAN DEFAULT FALSE,
                                    upload_url VARCHAR(512),
                                    UNIQUE (emp_id, file_name)
                                )
                            """)

                            # Insert screenshot metadata
                            cur.execute(f"""
                                INSERT INTO {schema}.screenshots
                                (emp_id, file_name, file_path, file_size, captured_at)
                                VALUES (%s, %s, %s, %s, %s)
                                ON CONFLICT (emp_id, file_name) DO UPDATE SET
                                    file_path = EXCLUDED.file_path,
                                    file_size = EXCLUDED.file_size,
                                    captured_at = EXCLUDED.captured_at,
                                    created_at = NOW()
                            """, (emp_id, file_name, file_path, file_size, captured_at))

                            conn.commit()
                            Alerts.log(f"Screenshot metadata saved to database: {file_name}")

            # Also upload to server if configured (legacy method)
            upload_cfg = self.app.cfg.data.get('screenshot_upload', {})
            if not upload_cfg.get('enabled', False):
                return

            server_url = upload_cfg.get('server_url', '').strip()
            if not server_url:
                return

            emp_id = int(self.app.cfg.data.get('emp_id', 0))
            if not emp_id:
                return

            # Prepare upload data with proper path structure: screenshot/empid/date/image.jpg
            file_name = os.path.basename(file_path)
            # Extract date from timestamp (format: YYYYMMDD_HHMMSS)
            date_str = timestamp.split('_')[0]  # YYYYMMDD
            date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"  # YYYY-MM-DD

            # Server path: screenshot/empid/date/filename.jpg
            server_path = f"screenshot/{emp_id}/{date_formatted}/{file_name}"

            with open(file_path, 'rb') as f:
                files = {'screenshot': (file_name, f, 'image/jpeg')}
                data = {
                    'emp_id': emp_id,
                    'timestamp': timestamp,
                    'captured_at': dt.datetime.now().isoformat(),
                    'server_path': server_path  # Desired server path
                }

                # Upload with timeout
                upload_url = f"{server_url.rstrip('/')}/api/upload/screenshot"
                response = requests.post(upload_url, files=files, data=data, timeout=30)

                if response.status_code == 200:
                    result = response.json()
                    if result.get('success'):
                        final_url = result.get('url', server_path)  # Use returned URL or fallback to expected path
                        Alerts.log(f"Screenshot uploaded successfully: {final_url}")

                        # Update database with upload status and server path if using Postgres
                        if ing.get('mode') == 'postgres' and psycopg is not None and dsn:
                            try:
                                with psycopg.connect(dsn) as conn:
                                    with conn.cursor() as cur:
                                        cur.execute(f"""
                                            UPDATE {schema}.screenshots
                                            SET uploaded = TRUE, upload_url = %s, file_path = %s
                                            WHERE emp_id = %s AND file_name = %s
                                        """, (final_url, server_path, emp_id, file_name))
                                        conn.commit()
                            except Exception as e:
                                Alerts.log(f"Failed to update screenshot upload status: {e}")
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
                time.sleep(60)  # Increased from 20 to 60 for performance
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
        # Performance optimization: Cache CPU reading
        self._cached_cpu = 0.0
        self._last_cpu_check = 0.0
        self._cpu_check_interval = 15.0  # Check CPU every 15 seconds for performance
        self._last_gc_ts = time.time()  # For periodic garbage collection
        self._gc_interval = 600.0  # Run garbage collection every 10 minutes for performance

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

                # Performance optimization: Update CPU reading only every 10 seconds
                now_ts = time.time()
                if now_ts - self._last_cpu_check >= self._cpu_check_interval:
                    self._cached_cpu = psutil.cpu_percent(interval=None)
                    self._last_cpu_check = now_ts

                hb = {
                    "ts": dt.datetime.now().isoformat(timespec='seconds'),
                    "current": cur,
                    "activity": activity_asdict(self.app_ref.activity),
                    "cpu_percent": self._cached_cpu,  # Use cached value instead of calling every second
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

                # Periodic garbage collection to prevent memory leaks
                if now_ts - self._last_gc_ts >= self._gc_interval:
                    collected = gc.collect()
                    self._last_gc_ts = now_ts
                    if collected > 0:
                        Alerts.log(f"Heartbeat GC: Collected {collected} objects")
            except Exception as e:
                Alerts.log(f"Heartbeat error: {e}")
            time.sleep(3.0)  # Increased from 1.0 to 3.0 for performance

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
    """Cross-platform input activity tracking with Python 3.13 support"""

    def __init__(self, stats: ActivityStats):
        self.stats = stats
        self.k_listener = None
        self.m_listener = None
        self.stop_event = threading.Event()
        self.windows_hook_thread = None
        self.use_windows_hooks = False

    def _on_key(self, key):
        self.stats.key_presses += 1
        self.stats.last_activity_ts = time.time()

    def _on_click(self, x, y, button, pressed):
        if pressed:
            self.stats.mouse_clicks += 1
            self.stats.last_activity_ts = time.time()

    def _windows_hook_worker(self):
        """Windows-native input tracking using ctypes (Python 3.13 compatible)"""
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            # Hook procedure types
            HOOKPROC = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

            # Hook IDs
            WH_KEYBOARD_LL = 13
            WH_MOUSE_LL = 14

            # Message types
            WM_KEYDOWN = 0x0100
            WM_SYSKEYDOWN = 0x0104
            WM_LBUTTONDOWN = 0x0201
            WM_RBUTTONDOWN = 0x0204
            WM_MBUTTONDOWN = 0x0207

            keyboard_hook = None
            mouse_hook = None

            def keyboard_hook_proc(nCode, wParam, lParam):
                if nCode >= 0 and wParam in [WM_KEYDOWN, WM_SYSKEYDOWN]:
                    self.stats.key_presses += 1
                    self.stats.last_activity_ts = time.time()
                return user32.CallNextHookEx(keyboard_hook, nCode, wParam, lParam)

            def mouse_hook_proc(nCode, wParam, lParam):
                if nCode >= 0 and wParam in [WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN]:
                    self.stats.mouse_clicks += 1
                    self.stats.last_activity_ts = time.time()
                return user32.CallNextHookEx(mouse_hook, nCode, wParam, lParam)

            # Create hook procedures
            kb_proc = HOOKPROC(keyboard_hook_proc)
            m_proc = HOOKPROC(mouse_hook_proc)

            # Set hooks
            keyboard_hook = user32.SetWindowsHookExA(WH_KEYBOARD_LL, kb_proc, None, 0)
            mouse_hook = user32.SetWindowsHookExA(WH_MOUSE_LL, m_proc, None, 0)

            if not keyboard_hook or not mouse_hook:
                Alerts.log("Failed to set Windows hooks")
                return

            Alerts.log("Windows native input hooks installed successfully (Python 3.13 compatible)")

            # Message loop
            msg = wintypes.MSG()
            while not self.stop_event.is_set():
                if user32.PeekMessageA(ctypes.byref(msg), None, 0, 0, 1):  # PM_REMOVE = 1
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageA(ctypes.byref(msg))
                time.sleep(0.01)

            # Unhook
            if keyboard_hook:
                user32.UnhookWindowsHookEx(keyboard_hook)
            if mouse_hook:
                user32.UnhookWindowsHookEx(mouse_hook)

            Alerts.log("Windows native input hooks uninstalled")

        except Exception as e:
            Alerts.log(f"Windows hook worker error: {e}")

    def start(self):
        # Try Windows native hooks first (Python 3.13+ compatible)
        if sys.platform == 'win32' and sys.version_info >= (3, 13) and os.environ.get('WFH_USE_WIN_HOOKS', '0') == '1':
            try:
                self.use_windows_hooks = True
                self.stop_event.clear()
                self.windows_hook_thread = threading.Thread(target=self._windows_hook_worker, daemon=True)
                self.windows_hook_thread.start()
                Alerts.log("Using Windows native hooks for input tracking (Python 3.13+)")
                return
            except Exception as e:
                Alerts.log(f"Failed to start Windows hooks: {e}")
                self.use_windows_hooks = False

        # Fallback to pynput for Python < 3.13. On Windows Python 3.13+, pynput is unstable; skip unless explicitly enabled.
        if sys.platform == 'win32' and sys.version_info >= (3, 13) and os.environ.get('WFH_USE_PYNPUT', '0') != '1':
            Alerts.log("Skipping pynput listeners on Windows Python 3.13+ (set WFH_USE_PYNPUT=1 to force enable)")
            return
        try:
            self.k_listener = keyboard.Listener(on_press=self._on_key)
            self.m_listener = mouse.Listener(on_click=self._on_click)
            self.k_listener.start()
            self.m_listener.start()
            Alerts.log("Keyboard/Mouse activity listeners started (pynput)")
        except NotImplementedError:
            Alerts.log("pynput listener not implemented on this platform/Python version; disabling input listeners.")
        except Exception as e:
            Alerts.log(f"Failed to start input listeners: {e}")

    def stop(self):
        if self.use_windows_hooks:
            self.stop_event.set()
            if self.windows_hook_thread:
                self.windows_hook_thread.join(timeout=2)
        else:
            if self.k_listener:
                self.k_listener.stop()
            if self.m_listener:
                self.m_listener.stop()


class ForegroundTracker(threading.Thread):
    def __init__(self, stats: ActivityStats, cfg: Config, app_ref: 'MonitorApp'):
        super().__init__(daemon=True)
        self.stats = stats
        self.cfg = cfg
        self.app_ref = app_ref
        self.stop_event = threading.Event()
        self.current: Dict = {}
        self.usage: Dict = {}  # {exe: {productive: secs, unproductive: secs, neutral: secs}}
        self.website_usage: Dict = {}  # {domain: total_secs}
        self.website_usage_by_tag: Dict = {}  # {tag: total_secs}
        self._agg_prod: Dict = {}  # {(exe, tag): secs} for batched SQLite writes
        self._agg_web: Dict = {}  # {(domain, tag): secs} for batched SQLite writes
        self._uia_initialized = False
        # Timeline tracking structures
        self.timeline: Dict = {}
        self._agg_timeline: Dict = {}  # {(date, hour, status): secs}
        
        # URL sanitization settings
        self.sanitize_urls = cfg.data.get('data_validation', {}).get('sanitize_urls', True)
        # URL extraction feature flag and throttling (lightweight defaults)
        self.enable_url_extract = bool(cfg.data.get('features', {}).get('website_url_extraction', False))
        self._last_url_extract_ts = 0.0
        try:
            self._url_extract_interval = int(cfg.data.get('features', {}).get('url_extract_interval_sec', 10))
        except Exception:
            self._url_extract_interval = 10
    
    def _sanitize_url(self, url: str) -> str:
        """Remove sensitive data from URLs"""
        if not url or not self.sanitize_urls:
            return url
        
        try:
            from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
            
            parsed = urlparse(url)
            
            # Remove sensitive query parameters
            sensitive_params = ['token', 'key', 'password', 'secret', 'api_key', 
                               'access_token', 'session', 'auth', 'credential', 'jwt',
                               'bearer', 'apikey', 'api-key', 'authorization']
            
            query_params = parse_qs(parsed.query)
            filtered_params = {
                k: v for k, v in query_params.items() 
                if not any(sensitive in k.lower() for sensitive in sensitive_params)
            }
            
            # Rebuild URL
            clean_query = urlencode(filtered_params, doseq=True)
            clean_url = urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                clean_query,
                ''  # Remove fragment
            ))
            
            return clean_url
            
        except Exception:
            # If parsing fails, return domain only
            try:
                return urlparse(url).netloc
            except:
                return ''
        self._agg_prod: Dict[Tuple[str, str], float] = {}            # (exe, tag) -> secs
        self._agg_timeline: Dict[Tuple[str, str, str], int] = {}     # (date, hour, status) -> secs
        self._agg_web: Dict[Tuple[str, str], float] = {}             # (domain, tag) -> secs
        self._flush_interval_sec = int(self.cfg.data.get('ingestion', {}).get('flush_interval_sec', 15))
        self._last_flush_ts = time.time()

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
        
        # Persist to file (legacy) - reduced frequency for performance
        if int(time.time()) % 60 == 0:
            with open(USAGE_JSON, 'w', encoding='utf-8') as f:
                json.dump(self.usage, f, indent=2)
        # Aggregate for batched SQLite writes
        key = (exe, tag)
        self._agg_prod[key] = self._agg_prod.get(key, 0.0) + secs
        
        # Optional: direct Postgres write (DISABLED for performance; use batched sync instead)
        try:
            ing = self.cfg.data.get('ingestion', {})
            if False and ing.get('mode') == 'postgres' and ing.get('direct_write', False) and psycopg is not None:
                db_cfg = ing.get('db', {})
                dsn = (db_cfg.get('url') or '').strip() or os.environ.get(db_cfg.get('url_env', 'EMP_DB_URL'))
                if dsn:
                    schema = db_cfg.get('schema', 'employee_monitor')
                    emp_id = self.cfg.data.get('emp_id', 0)
                    today = dt.datetime.now().strftime('%Y-%m-%d')
                    
                    with psycopg.connect(dsn) as conn:
                        with conn.cursor() as cur:
                            # Create productivity table if not exists
                            cur.execute(f"""
                                CREATE TABLE IF NOT EXISTS {schema}.productivity (
                                    emp_id INTEGER NOT NULL,
                                    date DATE NOT NULL,
                                    process_name VARCHAR(255) NOT NULL,
                                    tag VARCHAR(50) NOT NULL,
                                    duration_seconds FLOAT NOT NULL,
                                    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                    PRIMARY KEY (emp_id, date, process_name, tag)
                                )
                            """)
                            
                            # Insert/update productivity data
                            cur.execute(f"""
                                INSERT INTO {schema}.productivity 
                                (emp_id, date, process_name, tag, duration_seconds, last_updated)
                                VALUES (%s, %s, %s, %s, %s, NOW())
                                ON CONFLICT (emp_id, date, process_name, tag) DO UPDATE SET
                                    duration_seconds = productivity.duration_seconds + EXCLUDED.duration_seconds,
                                    last_updated = NOW()
                            """, (emp_id, today, exe, tag, secs))
                            
                            # Also create and update productivity summary table
                            cur.execute(f"""
                                CREATE TABLE IF NOT EXISTS {schema}.productivity_by_tag (
                                    emp_id INTEGER NOT NULL,
                                    date DATE NOT NULL,
                                    tag VARCHAR(50) NOT NULL,
                                    duration_seconds FLOAT NOT NULL,
                                    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                    PRIMARY KEY (emp_id, date, tag)
                                )
                            """)
                            
                            cur.execute(f"""
                                INSERT INTO {schema}.productivity_by_tag 
                                (emp_id, date, tag, duration_seconds, last_updated)
                                VALUES (%s, %s, %s, %s, NOW())
                                ON CONFLICT (emp_id, date, tag) DO UPDATE SET
                                    duration_seconds = productivity_by_tag.duration_seconds + EXCLUDED.duration_seconds,
                                    last_updated = NOW()
                            """, (emp_id, today, tag, secs))
                            
                            conn.commit()
                            Alerts.log(f"Productivity data saved to database: {exe} - {secs} seconds ({tag})")
        except Exception as e:
            Alerts.log(f"Productivity DB insert error: {e}")

    def _tick_timeline(self, status: str, secs: float):
        now = dt.datetime.now()
        date_key = now.strftime('%Y-%m-%d')
        hour_key = now.strftime('%H')
        self.timeline.setdefault(date_key, {})
        self.timeline[date_key].setdefault(hour_key, {"active": 0, "idle": 0, "offline": 0})
        self.timeline[date_key][hour_key][status] += int(secs)
        
        # Persist to file (legacy)
        if int(time.time()) % 30 == 0:
            with open(TIMELINE_JSON, 'w', encoding='utf-8') as f:
                json.dump(self.timeline, f, indent=2)
        
        # Aggregate for batched SQLite writes
        tkey = (date_key, hour_key, status)
        self._agg_timeline[tkey] = int(self._agg_timeline.get(tkey, 0)) + int(secs)
        
        # Save to database if using Postgres
        try:
            ing = self.cfg.data.get('ingestion', {})
            if ing.get('mode') == 'postgres' and psycopg is not None:
                db_cfg = ing.get('db', {})  
                dsn = (db_cfg.get('url') or '').strip() or os.environ.get(db_cfg.get('url_env', 'EMP_DB_URL'))
                if dsn:
                    schema = db_cfg.get('schema', 'employee_monitor')
                    emp_id = self.cfg.data.get('emp_id', 0)
                    
                    with psycopg.connect(dsn) as conn:
                        with conn.cursor() as cur:
                            # Create timeline table if not exists
                            cur.execute(f"""
                                CREATE TABLE IF NOT EXISTS {schema}.timeline (
                                    emp_id INTEGER NOT NULL,
                                    date DATE NOT NULL,
                                    hour INTEGER NOT NULL,
                                    status VARCHAR(20) NOT NULL,
                                    duration_seconds INTEGER NOT NULL,
                                    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                    PRIMARY KEY (emp_id, date, hour, status)
                                )
                            """)
                            
                            # Insert/update timeline data
                            cur.execute(f"""
                                INSERT INTO {schema}.timeline 
                                (emp_id, date, hour, status, duration_seconds, last_updated)
                                VALUES (%s, %s, %s, %s, %s, NOW())
                                ON CONFLICT (emp_id, date, hour, status) DO UPDATE SET
                                    duration_seconds = timeline.duration_seconds + EXCLUDED.duration_seconds,
                                    last_updated = NOW()
                            """, (emp_id, date_key, int(hour_key), status, int(secs)))
                            
                            conn.commit()
                            if self.cfg.data.get('logging', {}).get('verbose_db', False):
                                Alerts.log(f"Timeline data saved to database: {date_key} hour {hour_key} - {status} {int(secs)} seconds")
        except Exception as e:
            Alerts.log(f"Timeline DB insert error: {e}")

    def _extract_url_from_hwnd(self, exe: str, hwnd: Optional[int], title: str = "") -> str:
        if not getattr(self, 'enable_url_extract', False):
            return ""
        if not auto or not hwnd:
            return ""
        # Only attempt for known browsers
        if exe not in ("chrome.exe", "msedge.exe", "firefox.exe"):
            return ""
        # Throttle extraction frequency
        try:
            now_ts = time.time()
            if (now_ts - (self._last_url_extract_ts or 0)) < getattr(self, '_url_extract_interval', 10):
                return ""
            self._last_url_extract_ts = now_ts
        except Exception:
            pass
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
        
        # Save to file (legacy) - reduced frequency for performance
        if int(time.time()) % 60 == 0:
            with open(WEBSITE_USAGE_JSON, 'w', encoding='utf-8') as f:
                json.dump(self.website_usage, f, indent=2)
        
        # Aggregate by tag
        tag = self.cfg.data.get('website_tags', {}).get(dom, 'neutral')
        if tag not in self.website_usage_by_tag:
            self.website_usage_by_tag[tag] = 0.0
        self.website_usage_by_tag[tag] += secs
        
        # Save to file (legacy) - reduced frequency for performance
        if int(time.time()) % 60 == 0:
            with open(WEBSITE_USAGE_BY_TAG_JSON, 'w', encoding='utf-8') as f:
                json.dump(self.website_usage_by_tag, f, indent=2)
        
        # Aggregate for batched SQLite writes
        wkey = (dom, tag)
        self._agg_web[wkey] = self._agg_web.get(wkey, 0.0) + secs
        
        # Save to database if using Postgres (DISABLED for performance; use batched sync)
        try:
            ing = self.cfg.data.get('ingestion', {})
            if False and ing.get('mode') == 'postgres' and psycopg is not None:
                db_cfg = ing.get('db', {})
                dsn = (db_cfg.get('url') or '').strip() or os.environ.get(db_cfg.get('url_env', 'EMP_DB_URL'))
                if dsn:
                    schema = db_cfg.get('schema', 'employee_monitor')
                    emp_id = self.cfg.data.get('emp_id', 0)
                    today = dt.datetime.now().strftime('%Y-%m-%d')
                    
                    with psycopg.connect(dsn) as conn:
                        with conn.cursor() as cur:
                            # Force drop and recreate tables
                            try:
                                # First check if the table exists with wrong schema
                                cur.execute(f"""
                                    SELECT column_name FROM information_schema.columns 
                                    WHERE table_schema = '{schema}' AND table_name = 'website_usage'
                                """)
                                columns = [row[0] for row in cur.fetchall()]
                                
                                # If table exists but doesn't have the right columns, drop it
                                if columns and 'date' not in columns:
                                    cur.execute(f"DROP TABLE IF EXISTS {schema}.website_usage CASCADE")
                                    cur.execute(f"DROP TABLE IF EXISTS {schema}.website_usage_by_tag CASCADE")
                                    Alerts.log(f"Dropped existing website_usage tables with incorrect schema")
                            except Exception as e:
                                Alerts.log(f"Error checking/dropping tables: {e}")
                            
                            # Create tables with correct schema
                            cur.execute(f"""
                                CREATE TABLE IF NOT EXISTS {schema}.website_usage (
                                    emp_id INTEGER NOT NULL,
                                    date DATE NOT NULL,
                                    domain VARCHAR(255) NOT NULL,
                                    duration_seconds FLOAT NOT NULL,
                                    tag VARCHAR(50) NOT NULL,
                                    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                    PRIMARY KEY (emp_id, date, domain)
                                )
                            """)
                            
                            # Insert/update website usage
                            cur.execute(f"""
                                INSERT INTO {schema}.website_usage (emp_id, date, domain, duration_seconds, tag, last_updated)
                                VALUES (%s, %s, %s, %s, %s, NOW())
                                ON CONFLICT (emp_id, date, domain) DO UPDATE SET
                                    duration_seconds = website_usage.duration_seconds + EXCLUDED.duration_seconds,
                                    last_updated = NOW()
                            """, (emp_id, today, dom, secs, tag))
                            
                            # Also update tag summary table with the same approach
                            try:
                                # First check if the table exists with wrong schema
                                cur.execute(f"""
                                    SELECT column_name FROM information_schema.columns 
                                    WHERE table_schema = '{schema}' AND table_name = 'website_usage_by_tag'
                                """)
                                columns = [row[0] for row in cur.fetchall()]
                                
                                # If table exists but doesn't have the right columns, drop it
                                if columns and 'date' not in columns:
                                    cur.execute(f"DROP TABLE IF EXISTS {schema}.website_usage_by_tag CASCADE")
                                    Alerts.log(f"Dropped existing website_usage_by_tag table with incorrect schema")
                            except Exception as e:
                                Alerts.log(f"Error checking/dropping website_usage_by_tag table: {e}")
                                
                            # Create tag summary table
                            cur.execute(f"""
                                CREATE TABLE IF NOT EXISTS {schema}.website_usage_by_tag (
                                    emp_id INTEGER NOT NULL,
                                    date DATE NOT NULL,
                                    tag VARCHAR(50) NOT NULL,
                                    duration_seconds FLOAT NOT NULL,
                                    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                    PRIMARY KEY (emp_id, date, tag)
                                )
                            """)
                            
                            cur.execute(f"""
                                INSERT INTO {schema}.website_usage_by_tag (emp_id, date, tag, duration_seconds, last_updated)
                                VALUES (%s, %s, %s, %s, NOW())
                                ON CONFLICT (emp_id, date, tag) DO UPDATE SET
                                    duration_seconds = website_usage_by_tag.duration_seconds + EXCLUDED.duration_seconds,
                                    last_updated = NOW()
                            """, (emp_id, today, tag, secs))
                            
                            conn.commit()
                            if self.cfg.data.get('logging', {}).get('verbose_db', False):
                                Alerts.log(f"Website usage data saved to database: {dom} - {secs} seconds")
        except Exception as e:
            Alerts.log(f"Website usage DB insert error: {e}")

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
            url = ""
            if status == "active":
                url = self._extract_url_from_hwnd(exe, hwnd, title)
            if not url and exe in ("chrome.exe", "msedge.exe", "firefox.exe") and title:
                # Fallback: infer from title without needing browser flags
                url = self._infer_url_from_title(title)
            
            # Sanitize URL to remove sensitive data
            if url:
                url = self._sanitize_url(url)
            
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
            time.sleep(2.0)  # Increased from 1.0 to 2.0 for performance

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
                time.sleep(60)  # Increased from 30 to 60 for performance
            except Exception as e:
                Alerts.log(f"DomainBlocker loop error: {e}")
                time.sleep(120)  # Increased from 60 to 120 for performance

    def stop(self):
        self.stop_event.set()


# Standalone utility functions
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


def is_recruitment_designation(designation: Optional[str]) -> bool:
    """Check if designation is recruitment-related (for Naukri file monitoring)."""
    if not designation:
        return False
    
    # Normalize: lowercase, replace em-dash with hyphen, collapse whitespace
    d = str(designation).lower().replace('\u2013', '-').replace('\u2014', '-')
    # Collapse repeated whitespace
    try:
        d = re.sub(r'\s+', ' ', d).strip()
    except Exception:
        d = ' '.join(d.split()).strip()
    
    recruitment_keywords = [
        'recruiter',
        'hr',
        'hiring_manager',
        'hiring manager',
        'manager - talent acquisition',
        'associate manager - talent acquisition',
        'senior executive - talent acquisition',
        'team lead - talent acquisition',
        'executive - talent acquisition',
        'vice president - talent acquisition',
        'trainee - talent acquisition',
        'talent acquisition partner',
        'talent acquisition',
    ]
    
    return any(keyword in d for keyword in recruitment_keywords)


def send_admin_notification(event_type: str, data: Dict, cfg: Optional['Config'] = None):
    """Send admin notification via webhook or email"""
    try:
        if not cfg:
            return

        admin_notif = cfg.data.get('admin_notifications', {})
        if not admin_notif.get('enabled'):
            return

        # Check if this event type is enabled
        events = admin_notif.get('events', {})
        if not events.get(event_type):
            return

        emp_id = cfg.data.get('emp_id', 0)
        hostname = socket.gethostname()
        timestamp = dt.datetime.now().isoformat()

        payload = {
            "event": event_type,
            "employee_id": emp_id,
            "hostname": hostname,
            "timestamp": timestamp,
            "data": data
        }

        # Send webhook if configured
        webhook_url = admin_notif.get('webhook_url', '').strip()
        if webhook_url:
            try:
                resp = requests.post(webhook_url, json=payload, timeout=10)
                if resp.status_code >= 200 and resp.status_code < 300:
                    Alerts.log(f"Admin notification sent: {event_type}")
                else:
                    Alerts.log(f"Admin notification failed: HTTP {resp.status_code}")
            except Exception as e:
                Alerts.log(f"Webhook notification error: {e}")

        # Send email if configured
        email_cfg = admin_notif.get('email', {})
        if email_cfg.get('enabled'):
            try:
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart

                # Create email message
                msg = MIMEMultipart()
                msg['From'] = email_cfg.get('from_email', '')
                msg['To'] = ', '.join(email_cfg.get('to_emails', []))
                msg['Subject'] = f"[WFH Agent] {event_type.replace('_', ' ').title()} - Employee {emp_id}"

                body = f"""
Event: {event_type.replace('_', ' ').title()}
Employee ID: {emp_id}
Hostname: {hostname}
Time: {timestamp}

Details:
{json.dumps(data, indent=2)}
"""
                msg.attach(MIMEText(body, 'plain'))

                # Send email
                server = smtplib.SMTP(email_cfg.get('smtp_server', 'smtp.gmail.com'),
                                    email_cfg.get('smtp_port', 587))
                server.starttls()
                server.login(email_cfg.get('username', ''), email_cfg.get('password', ''))
                server.send_message(msg)
                server.quit()

                Alerts.log(f"Admin email notification sent: {event_type}")
            except Exception as e:
                Alerts.log(f"Email notification error: {e}")

    except Exception as e:
        Alerts.log(f"Admin notification error: {e}")


def compute_wellness(timeline_path: str = TIMELINE_JSON, cfg: Optional['Config'] = None) -> Dict:
    """Compute daily wellness with thresholds and flags; optionally bound to work hours."""
    # Load timeline
    timeline = {}
    if os.path.exists(timeline_path):
        # Robust loader: tolerate JSONL or partially written JSON
        try:
            with open(timeline_path, 'r', encoding='utf-8') as f:
                content = f.read()
            # First try strict JSON
            try:
                loaded = json.loads(content)
                if isinstance(loaded, dict):
                    timeline = loaded
                else:
                    timeline = {}
            except json.JSONDecodeError:
                # Fallback: parse line-by-line as JSONL and merge dicts
                merged: Dict[str, Dict] = {}
                for line in content.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if isinstance(k, str) and isinstance(v, dict):
                                    merged.setdefault(k, {}).update(v)
                    except Exception:
                        # Ignore bad line
                        continue
                timeline = merged
        except Exception:
            # On any error, fall back to empty to avoid crashing the agent
            timeline = {}
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

    # Save to file (legacy)
    with open(WELLNESS_JSON, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    
    # Save to local SQLite if config is available
    if cfg is not None and hasattr(cfg, "app_ref") and hasattr(cfg.app_ref, "local_storage"):
        try:
            emp_id = cfg.data.get("emp_id", 0)
            for day, data in summary.items():
                cfg.app_ref.local_storage.insert_wellness(emp_id, day, data)
        except Exception as e:
            print(f"Wellness local DB insert error: {e}")
    
    # Save to database if using Postgres and config is available
    if cfg is not None:
        try:
            ing = cfg.data.get('ingestion', {})
            if ing.get('mode') == 'postgres' and psycopg is not None:
                db_cfg = ing.get('db', {})
                dsn = (db_cfg.get('url') or '').strip() or os.environ.get(db_cfg.get('url_env', 'EMP_DB_URL'))
                if dsn:
                    schema = db_cfg.get('schema', 'employee_monitor')
                    emp_id = cfg.data.get('emp_id', 0)
                    
                    with psycopg.connect(dsn) as conn:
                        with conn.cursor() as cur:
                            # Create wellness table if not exists
                            cur.execute(f"""
                                CREATE TABLE IF NOT EXISTS {schema}.wellness (
                                    emp_id INTEGER NOT NULL,
                                    date DATE NOT NULL,
                                    active_secs INTEGER NOT NULL,
                                    idle_secs INTEGER NOT NULL,
                                    offline_secs INTEGER NOT NULL,
                                    work_secs INTEGER NOT NULL,
                                    active_ratio FLOAT NOT NULL,
                                    idle_ratio FLOAT NOT NULL,
                                    utilization_percent FLOAT NOT NULL,
                                    underutilized BOOLEAN NOT NULL,
                                    overburdened BOOLEAN NOT NULL,
                                    burnout_risk BOOLEAN NOT NULL,
                                    steady_performer BOOLEAN NOT NULL,
                                    last_updated TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                    PRIMARY KEY (emp_id, date)
                                )
                            """)
                            
                            # Insert/update wellness data for each day
                            for day, data in summary.items():
                                cur.execute(f"""
                                    INSERT INTO {schema}.wellness 
                                    (emp_id, date, active_secs, idle_secs, offline_secs, work_secs, 
                                    active_ratio, idle_ratio, utilization_percent, underutilized, 
                                    overburdened, burnout_risk, steady_performer, last_updated)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                                    ON CONFLICT (emp_id, date) DO UPDATE SET
                                        active_secs = EXCLUDED.active_secs,
                                        idle_secs = EXCLUDED.idle_secs,
                                        offline_secs = EXCLUDED.offline_secs,
                                        work_secs = EXCLUDED.work_secs,
                                        active_ratio = EXCLUDED.active_ratio,
                                        idle_ratio = EXCLUDED.idle_ratio,
                                        utilization_percent = EXCLUDED.utilization_percent,
                                        underutilized = EXCLUDED.underutilized,
                                        overburdened = EXCLUDED.overburdened,
                                        burnout_risk = EXCLUDED.burnout_risk,
                                        steady_performer = EXCLUDED.steady_performer,
                                        last_updated = NOW()
                                """, (
                                    emp_id, day, data['active_secs'], data['idle_secs'], 
                                    data['offline_secs'], data['work_secs'], data['active_ratio'], 
                                    data['idle_ratio'], data['utilization_percent'], data['underutilized'], 
                                    data['overburdened'], data['burnout_risk'], data['steady_performer']
                                ))
                            
                            conn.commit()
                            Alerts.log(f"Wellness data saved to database for {len(summary)} days")
        except Exception as e:
            Alerts.log(f"Wellness DB insert error: {e}")
    
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
    def log(self, message):
        """Log message to alerts log"""
        # Use the in-file Alerts class
        Alerts.log(message)

    def __init__(self):
        self.cfg = Config(CONFIG_PATH)
        self.activity = ActivityStats()
        
        # Try to load employee ID from session file
        self._load_emp_id_from_session()
        
        self.screen = ScreenRecorder(self.activity)
        self.inputs = InputActivity(self.activity)
        self.fg = ForegroundTracker(self.activity, self.cfg, self)
        self.usb = USBDetector()
        self.blocker = DomainBlocker(self.cfg)
        self.heartbeat = Heartbeat(self)
        self.flask_app: Optional[Flask] = None
        self.server_thread: Optional[threading.Thread] = None
        self._geo_cache: Dict[str, any] = {"ts": 0, "data": {}}
        # Defer geolocation network calls briefly after startup to avoid contention
        self._geo_ready_at: float = time.time() + 20.0
        self._notifier = NotificationManager(self)
        self.itsm = ITSMHelper(self)
        self.session_monitor: Optional['WorkSessionMonitor'] = None
        self.shooter: Optional[ScheduledShooter] = None

        # Initialize work session state
        self._work_session: Dict = {}

        # Initialize local storage with SQLite and Postgres sync
        self.local_storage = LocalStorage(DATA_DIR, self)
        # Initialize session watcher controls
        self._session_watch_stop = threading.Event()
        self._session_watch_thread = None
        
        # Initialize download monitor for Naukri file tracking
        self.download_monitor: Optional[DownloadMonitor] = None
        self._download_monitor_auth_token: Optional[str] = None
        
    def _load_emp_id_from_session(self):
        """Load employee ID from Electron session file if available"""
        try:
            # Session file is in Electron's userData directory
            # For Windows: %APPDATA%\wfh-agent-desktop\session.json
            app_name = 'wfh-agent-desktop'
            if sys.platform == 'win32':
                session_dir = os.path.join(os.environ.get('APPDATA', ''), app_name)
                session_path = os.path.join(session_dir, 'session.json')
            elif sys.platform == 'darwin':
                session_dir = os.path.join(os.path.expanduser('~/Library/Application Support'), app_name)
                session_path = os.path.join(session_dir, 'session.json')
            else:  # Linux
                session_dir = os.path.join(os.path.expanduser('~/.config'), app_name)
                session_path = os.path.join(session_dir, 'session.json')
            
            # Test if we can access the directory
            Alerts.log(f"Looking for session file at: {session_path}")
            test_file = os.path.join(session_dir, 'test_access.txt')
            try:
                if os.path.exists(session_dir):
                    with open(test_file, 'w') as f:
                        f.write('Test access to session directory')
                    Alerts.log(f"Successfully wrote test file to {test_file}")
                else:
                    Alerts.log(f"Session directory does not exist: {session_dir}")
            except Exception as e:
                Alerts.log(f"Failed to write test file: {e}")
                
            # Try alternate locations
            alt_paths = [
                os.path.join(os.environ.get('LOCALAPPDATA', ''), app_name, 'session.json'),
                os.path.join(os.path.dirname(DATA_DIR), 'session.json'),
                os.path.join(os.path.dirname(os.path.dirname(DATA_DIR)), 'session.json')
            ]
            for alt_path in alt_paths:
                if os.path.exists(alt_path):
                    Alerts.log(f"Found session file at alternate location: {alt_path}")
                    session_path = alt_path
                    break
            if os.path.exists(session_path):
                with open(session_path, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
                    if session_data and 'hrmsEmpId' in session_data and session_data['hrmsEmpId']:
                        emp_id = int(session_data['hrmsEmpId'])
                        if emp_id > 0:
                            self.cfg.data['emp_id'] = emp_id
                            Alerts.log(f"Loaded employee ID {emp_id} from session")
        except Exception as e:
            Alerts.log(f"Failed to read emp_id from session: {e}")
            # Continue with default/config emp_id

    def _watch_session_emp(self):
        """Background watcher to pick up emp_id changes from Electron session.json without restart."""
        last_emp = int(self.cfg.data.get('emp_id', 0) or 0)
        while not self._session_watch_stop.is_set():
            try:
                self._load_emp_id_from_session()
                cur_emp = int(self.cfg.data.get('emp_id', 0) or 0)
                if cur_emp and cur_emp != last_emp:
                    last_emp = cur_emp
                    try:
                        self.cfg.save()
                    except Exception:
                        pass
                    Alerts.log(f"Session watcher: emp_id updated to {cur_emp}")
            except Exception as e:
                Alerts.log(f"Session watcher error: {e}")
            # Sleep with event wait to allow fast shutdown
            try:
                self._session_watch_stop.wait(10.0)
            except Exception:
                time.sleep(10.0)

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
        if self.cfg.data.get('features', {}).get('screen_record', False):  # Changed default to False for performance
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
            # Guard against duplicate starts
            try:
                if not self.shooter or not getattr(self.shooter, 'is_alive', lambda: False)():
                    self.shooter = ScheduledShooter(self)
                    self.shooter.start()
                    Alerts.log("ScheduledShooter started")
                else:
                    Alerts.log("ScheduledShooter already running; skip starting a second instance")
            except Exception as e:
                Alerts.log(f"ScheduledShooter start guard error: {e}")
        # Start work session monitor for auto-stop limits
        try:
            self.session_monitor = WorkSessionMonitor(self)
            self.session_monitor.start()
            Alerts.log("Work session monitor started")
        except Exception as e:
            Alerts.log(f"Failed to start work session monitor: {e}")
        # Start session watcher to pick up emp_id from Electron login session
        try:
            if not self._session_watch_thread or not self._session_watch_thread.is_alive():
                self._session_watch_thread = threading.Thread(target=self._watch_session_emp, daemon=True)
                self._session_watch_thread.start()
        except Exception as e:
            Alerts.log(f"Failed to start session watcher: {e}")

        # Trigger initial full sync on startup
        try:
            Alerts.log("Triggering initial full data sync to PostgreSQL...")
            threading.Thread(target=self.local_storage.sync_to_postgres, daemon=True).start()
        except Exception as e:
            Alerts.log(f"Failed to trigger initial sync: {e}")
        
        # Start download monitor for recruitment employees (Naukri file tracking)
        try:
            if not DOWNLOAD_MONITOR_AVAILABLE:
                Alerts.log("[DownloadMonitor] Module not available")
            else:
                dm_cfg = self.cfg.data.get('download_monitor', {})
                emp_id = int(self.cfg.data.get('emp_id', 0))
                designation = self.cfg.data.get('designation', '')
                
                # Start if explicitly enabled via config OR if recruitment designation detected
                if dm_cfg.get('enabled', False) or is_recruitment_designation(designation):
                    Alerts.log(f"[DownloadMonitor] Starting: emp_id={emp_id}, designation={designation or ''}")
                    self.download_monitor = DownloadMonitor(self.cfg.data, emp_id)
                    self.download_monitor.start()
                    Alerts.log(f"[DownloadMonitor] Monitor started")
                else:
                    Alerts.log(f"[DownloadMonitor] Skipped: not enabled in config and designation '{designation}' is not recruitment-related")
        except Exception as e:
            Alerts.log(f"[DownloadMonitor] Start error: {e}")

        if enable_http:
            self._start_http(host, port)

    def stop(self):
        Alerts.log("Stopping Employee Monitor")
        try:
            self._session_watch_stop.set()
        except Exception:
            pass
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
        try:
            if self.download_monitor:
                self.download_monitor.stop()
        except Exception:
            pass

    def _start_http(self, host: str, port: int):
        app = Flask(__name__)
        # Ensure we bind to the expected host/port for Electron
        host = host or '127.0.0.1'
        port = port or 5050
        Alerts.log(f"Starting HTTP server on {host}:{port}")

        # Optional API key for server-side ingestion endpoints
        INGEST_API_KEY = os.environ.get('INGEST_API_KEY', '').strip()

        # Helpers for screenshot uploads
        ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}
        MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

        def _allowed_file(filename: str) -> bool:
            return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

        def _validate_file_size(file_storage) -> bool:
            try:
                pos = file_storage.stream.tell()
            except Exception:
                pos = 0
            try:
                file_storage.stream.seek(0, os.SEEK_END)
                size = file_storage.stream.tell()
                file_storage.stream.seek(pos)
                return size <= MAX_FILE_SIZE
            except Exception:
                # If we cannot determine size reliably, accept and rely on server limits
                return True

        def _require_api_key():
            if not INGEST_API_KEY:
                return True
            try:
                hdr = request.headers.get('X-Api-Key', '')
                return hdr == INGEST_API_KEY
            except Exception:
                return False

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
            # Make website usage human readable with start/end time and rounded minutes
            try:
                # Build first/last seen per domain from today's heartbeat
                first_last: Dict[str, Dict[str, str]] = {}
                day_key = dt.datetime.now().strftime('%Y-%m-%d')
                hb_path = os.path.join(HEARTBEAT_DIR, f'heartbeat_{day_key}.jsonl')
                if os.path.exists(hb_path):
                    with open(hb_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                rec = json.loads(line)
                            except Exception:
                                continue
                            ts = rec.get('ts') or rec.get('timestamp')
                            cur = rec.get('current') or {}
                            url = cur.get('url') or ''
                            # Extract domain
                            try:
                                p = urlparse(url)
                                dom = (p.netloc or '').split('@')[-1].split(':')[0].lower()
                                if dom.startswith('www.'):
                                    dom = dom[4:]
                            except Exception:
                                dom = ''
                            if not ts or not dom:
                                continue
                            ent = first_last.get(dom)
                            if not ent:
                                first_last[dom] = {'start_ts': ts, 'end_ts': ts}
                            else:
                                ent['end_ts'] = ts
                # Convert totals to minutes with 2 decimals and attach times when available
                human: Dict[str, Dict[str, object]] = {}
                if isinstance(web_usage, dict):
                    for dom, secs in web_usage.items():
                        mins = round(float(secs or 0.0) / 60.0, 2)
                        times = first_last.get(dom, {})
                        human[dom] = {
                            'duration_min': mins,
                            'start_ts': times.get('start_ts'),
                            'end_ts': times.get('end_ts')
                        }
                # Also include domains seen today even if no totals yet
                for dom, times in first_last.items():
                    if dom not in human:
                        human[dom] = {
                            'duration_min': 0.0,
                            'start_ts': times.get('start_ts'),
                            'end_ts': times.get('end_ts')
                        }
                # Add human-readable local times
                for dom, rec in human.items():
                    def _fmt(ts: Optional[str]) -> Optional[str]:
                        try:
                            return dt.datetime.fromisoformat(ts).strftime('%d %b %Y, %I:%M %p') if ts else None
                        except Exception:
                            return None
                    rec['start_time'] = _fmt(rec.get('start_ts'))
                    rec['end_time'] = _fmt(rec.get('end_ts'))
                web_usage = human
            except Exception as e:
                Alerts.log(f"/status website_usage humanize error: {e}")
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
                # Keep actual ingestion mode but hide DB credentials
                ing = cfg_copy.get('ingestion', {})
                if isinstance(ing, dict):
                    # Keep original mode (postgres/file) but hide credentials
                    db = ing.get('db', {})
                    if isinstance(db, dict):
                        # Ensure DB credentials are always blank
                        db['url'] = ''
                        db['url_env'] = ''
                        ing['db'] = db
                    cfg_copy['ingestion'] = ing
                # Use emp_id from login session if available (already loaded by _load_emp_id_from_session)
                # Just use the current emp_id from self.cfg.data which should be updated by the session watcher
                if self.cfg.data.get('emp_id', 0) > 0:
                    cfg_copy['emp_id'] = self.cfg.data.get('emp_id', 0)
            except Exception:
                cfg_copy = {"error": "config_unavailable"}
            # Get the actual employee ID for the response
            emp_id = self.cfg.data.get('emp_id', 0)
            
            return jsonify({
                "current": cur,
                "activity": activity_asdict(self.activity),
                "usage": usage,
                "website_usage": web_usage,
                "website_usage_by_tag": web_usage_by_tag,
                "wellness": wellness,
                "config": cfg_copy,
                "battery": battery,
                "geo": geo,
                "employee_id": emp_id  # Add employee ID as a separate field
            })

        @app.route('/health', methods=['GET'])
        def health():
            return jsonify({
                'status': 'healthy',
                'service': 'emp-monitor-api',
                'timestamp': dt.datetime.now().isoformat()
            })

        @app.route('/diagnostics', methods=['GET'])
        def diagnostics():
            """System diagnostics endpoint for troubleshooting"""
            try:
                from system_diagnostics import SystemDiagnostics

                diag = SystemDiagnostics()
                diag.collect_all()

                # Get format parameter (json or text)
                output_format = request.args.get('format', 'json').lower()

                if output_format == 'text':
                    summary = diag.get_summary()
                    return Response(summary, mimetype='text/plain')
                else:
                    return jsonify(diag.diagnostics)

            except Exception as e:
                return jsonify({'error': str(e)}), 500

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
        self._last_activity_ts: Optional[float] = None  # Track last system activity for shutdown detection

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

        def _sum_break_ms(breaks: List[Dict], session_start_ts: str, session_end_ts: str) -> int:
            """Sum break durations, clamped within the session window to avoid over-counting.
            Handles both closed breaks (with end_ts) and open breaks (without end_ts, using session_end_ts)."""
            try:
                ss = dt.datetime.fromisoformat(session_start_ts)
                se = dt.datetime.fromisoformat(session_end_ts)
            except Exception:
                # Fallback: no clamping if timestamps invalid
                ss, se = None, None
            total = 0
            for br in breaks or []:
                st, en = br.get('start_ts'), br.get('end_ts')
                # Skip breaks without start_ts
                if not st:
                    continue
                try:
                    bst = dt.datetime.fromisoformat(st)
                    # Use end_ts if available, otherwise use session_end_ts (for open breaks)
                    ben = dt.datetime.fromisoformat(en) if en else se
                    # If no session end time available, skip this break
                    if not ben:
                        continue
                    # Clamp to session window if available
                    if ss and se:
                        if bst < ss:
                            bst = ss
                        if ben > se:
                            ben = se
                    if ben > bst:
                        total += int((ben - bst).total_seconds() * 1000)
                except Exception:
                    continue
            return total

        def _auto_end_session(reason: str = "auto_stop") -> Dict:
            """Automatically end the current work session with a reason"""
            if not self._work_session or self._work_session.get('end_ts'):
                return {"ok": False, "error": "No active session"}

            # Close any open break
            brks = self._work_session.get('breaks') or []
            if brks and not brks[-1].get('end_ts'):
                brks[-1]['end_ts'] = _now_iso()

            self._work_session['end_ts'] = _now_iso()
            start_ts = self._work_session.get('start_ts')
            end_ts = self._work_session.get('end_ts')
            total_ms = _dur_ms(start_ts, end_ts)
            break_ms = _sum_break_ms(brks, start_ts, end_ts)

            work_ms = max(0, total_ms - break_ms)

            rec = {
                "emp_id": int(self.cfg.data.get('emp_id', 0)),
                "start_ts": start_ts,
                "end_ts": end_ts,
                "breaks": brks,
                "work_ms": work_ms,
                "break_ms": break_ms,
                "total_ms": total_ms,
                "auto_stop_reason": reason
            }
            _insert_session_db(rec)
            self._work_session = {}
            Alerts.log(f"Session auto-stopped: {reason}")
            return {"ok": True, "record": rec, "reason": reason}

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
                # Check if there's an existing active session
                if (self._work_session or {}).get('start_ts') and not self._work_session.get('end_ts'):
                    # Check if session is stale (older than 24 hours)
                    try:
                        start_ts = dt.datetime.fromisoformat(self._work_session.get('start_ts'))
                        now_utc = dt.datetime.now(dt.timezone.utc)
                        if start_ts.tzinfo is None:
                            start_ts_utc = start_ts.replace(tzinfo=dt.timezone.utc)
                        else:
                            start_ts_utc = start_ts.astimezone(dt.timezone.utc)
                        age_hours = (now_utc - start_ts_utc).total_seconds() / 3600

                        if age_hours > 24:
                            # Stale session - clear it
                            Alerts.log(f"Clearing stale session from {self._work_session.get('start_ts')} (age: {age_hours:.1f}h)")
                            self._work_session = {}
                        else:
                            # Recent active session - return existing
                            return jsonify({"ok": True, "state": self._work_session, "already_active": True})
                    except Exception as e:
                        Alerts.log(f"Error checking session age: {e}, creating new session")
                        self._work_session = {}

                # Optional payload to restore an existing timeline
                payload = {}
                try:
                    payload = request.get_json(force=False, silent=True) or {}
                except Exception:
                    payload = {}

                # Validate and normalize fields
                start_ts = payload.get('start_ts')
                status = (payload.get('status') or 'active')
                breaks = payload.get('breaks') or []

                # Default to now if invalid or missing
                def _is_iso(ts: str) -> bool:
                    try:
                        dt.datetime.fromisoformat(ts)
                        return True
                    except Exception:
                        return False

                if not (isinstance(start_ts, str) and _is_iso(start_ts)):
                    start_ts = _now_iso()

                # Clamp start to last 24h to avoid bogus timelines
                try:
                    st_dt = dt.datetime.fromisoformat(start_ts)
                    now_dt = dt.datetime.now(dt.timezone.utc) if st_dt.tzinfo else dt.datetime.now()
                    if (now_dt - st_dt).total_seconds() > 24 * 3600:
                        Alerts.log("/session/start: start_ts older than 24h, clamping to now-24h")
                        start_ts = (now_dt - dt.timedelta(hours=24)).isoformat()
                except Exception:
                    pass

                # Sanitize breaks: keep only well-formed items; ensure times within session..now
                sane_breaks = []
                try:
                    st_dt = dt.datetime.fromisoformat(start_ts)
                    now_dt = dt.datetime.now(dt.timezone.utc) if st_dt.tzinfo else dt.datetime.now()
                    for b in breaks:
                        if not isinstance(b, dict):
                            continue
                        bst, ben = b.get('start_ts'), b.get('end_ts')
                        if not (isinstance(bst, str) and _is_iso(bst)):
                            continue
                        try:
                            bst_dt = dt.datetime.fromisoformat(bst)
                            if bst_dt < st_dt:
                                bst_dt = st_dt
                            if ben and isinstance(ben, str) and _is_iso(ben):
                                ben_dt = dt.datetime.fromisoformat(ben)
                                if ben_dt > now_dt:
                                    ben_dt = now_dt
                                if ben_dt > bst_dt:
                                    sane_breaks.append({"start_ts": bst_dt.isoformat(), "end_ts": ben_dt.isoformat()})
                            else:
                                # open break
                                sane_breaks.append({"start_ts": bst_dt.isoformat(), "end_ts": None})
                        except Exception:
                            continue
                except Exception:
                    sane_breaks = []

                self._work_session = {"start_ts": start_ts, "end_ts": None, "breaks": sane_breaks, "status": status or 'active'}
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
                break_ms = _sum_break_ms(brks, start_ts, end_ts)

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
                # Determine default days from config if available
                try:
                    default_days = int((self.cfg.data.get('ui', {}) or {}).get('session_days_default', 7))
                except Exception:
                    default_days = 7
                days = int((request.args.get('days') if request else None) or default_days)
                # Debug flag
                dbg_flag = False
                try:
                    d = (request.args.get('debug') or '').strip().lower()
                    dbg_flag = d in ('1', 'true', 'yes')
                except Exception:
                    dbg_flag = False
                since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
                # Collect from DB (if configured) and file, then merge
                kpi = {"total_work_ms": 0, "total_break_ms": 0, "avg_work_ms": 0, "sessions_completed": 0}
                merged: Dict[str, Dict] = {}
                dbg = {
                    "work_file_path": None,
                    "file_exists": False,
                    "file_count": 0,
                    "filtered_count": 0,
                    "db_count": 0,
                    "final_row_count": 0,
                    "errors": []
                }
                # DB source
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
                                    try:
                                        dbg["db_count"] = len(recs or [])
                                    except Exception:
                                        pass
                                    for (st_ts, en_ts, br, wms, bms, tms) in recs:
                                        key = st_ts.isoformat()
                                        merged[key] = {"start_ts": key, "end_ts": (en_ts.isoformat() if en_ts else None), "breaks": br, "work_ms": int(wms or 0), "break_ms": int(bms or 0), "total_ms": int(tms or 0)}
                except Exception as e:
                    Alerts.log(f"work session summary db error: {e}")
                    try:
                        dbg["errors"].append(f"db: {e}")
                    except Exception:
                        pass
                # File source (always merge)
                try:
                    p = _work_file_path()
                    dbg["work_file_path"] = p
                    dbg["file_exists"] = os.path.exists(p)
                    if os.path.exists(p):
                        with open(p, 'r', encoding='utf-8') as f:
                            arr = json.load(f)
                            try:
                                dbg["file_count"] = len(arr or [])
                            except Exception:
                                pass
                            for r in arr:
                                try:
                                    st = r.get('start_ts')
                                    if not st:
                                        continue
                                    if dt.datetime.fromisoformat(st).replace(tzinfo=None) < since.replace(tzinfo=None):
                                        continue
                                    # counted as filtered candidate
                                    try:
                                        dbg["filtered_count"] += 1
                                    except Exception:
                                        pass
                                    key = st
                                    # Prefer DB entry when present; otherwise take file
                                    if key not in merged:
                                        merged[key] = {
                                            "start_ts": r.get('start_ts'),
                                            "end_ts": r.get('end_ts'),
                                            "breaks": r.get('breaks') or [],
                                            "work_ms": int(r.get('work_ms') or 0),
                                            "break_ms": int(r.get('break_ms') or 0),
                                            "total_ms": int(r.get('total_ms') or 0),
                                        }
                                except Exception:
                                    continue
                except Exception as e:
                    Alerts.log(f"work session summary file error: {e}")
                    try:
                        dbg["errors"].append(f"file: {e}")
                    except Exception:
                        pass
                # Finalize rows sorted by start_ts desc
                rows = sorted(merged.values(), key=lambda x: x.get('start_ts') or '', reverse=True)
                if rows:
                    kpi['sessions_completed'] = len(rows)
                    kpi['total_work_ms'] = sum(int(r.get('work_ms') or 0) for r in rows)
                    kpi['total_break_ms'] = sum(int(r.get('break_ms') or 0) for r in rows)
                    kpi['avg_work_ms'] = int(kpi['total_work_ms'] / max(1, kpi['sessions_completed']))
                try:
                    dbg["final_row_count"] = len(rows or [])
                except Exception:
                    pass
                # CamelCase KPI aliases for UI compatibility
                try:
                    kpi.update({
                        'totalWorkMs': kpi.get('total_work_ms', 0),
                        'totalBreakMs': kpi.get('total_break_ms', 0),
                        'avgWorkMs': kpi.get('avg_work_ms', 0),
                        'sessionsCompleted': kpi.get('sessions_completed', 0)
                    })
                except Exception:
                    pass
                resp = {"ok": True, "kpi": kpi, "rows": rows}
                if dbg_flag:
                    resp["debug"] = dbg
                return jsonify(resp)
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

        @app.post('/app/quit')
        def app_quit_notification():
            """Notify admin when employee quits the app"""
            try:
                data = request.get_json() or {}

                # Get current work session info
                work_info = {
                    "reason": data.get('reason', 'user_action'),
                    "work_session_active": False
                }

                # Check if there was an active work session
                work = self._work_session or {}
                if work and not work.get('end_ts'):
                    work_info["work_session_active"] = True
                    work_info["session_start"] = work.get('start_ts')
                    if work.get('start_ts'):
                        try:
                            work_info["session_duration_minutes"] = int(
                                (dt.datetime.now() - dt.datetime.fromisoformat(work.get('start_ts'))).total_seconds() / 60
                            )
                        except Exception:
                            work_info["session_duration_minutes"] = 0

                # Send admin notification
                send_admin_notification('app_quit', work_info, self.cfg)

                return jsonify({"ok": True})
            except Exception as e:
                Alerts.log(f"/app/quit notification error: {e}")
                return jsonify({"ok": False, "error": str(e)}), 500

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

        @app.post('/api/screenshot/capture')
        def trigger_screenshot():
            """Manually trigger a screenshot capture (for testing)"""
            try:
                if self.shooter:
                    if self.shooter._capture_one():
                        return jsonify({'success': True, 'message': 'Screenshot captured'}), 200
                    else:
                        return jsonify({'success': False, 'message': 'Failed to capture (system may be idle)'}), 400
                else:
                    return jsonify({'success': False, 'message': 'Screenshot feature not enabled'}), 400
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 500

        @app.post('/api/upload/screenshot')
        def upload_screenshot():
            """Receive screenshot image and store it under uploads/screenshot/<emp_id>/<date>/"""
            try:
                # Optional API key
                if not _require_api_key():
                    return jsonify({'success': False, 'error': 'Unauthorized'}), 401

                if 'screenshot' not in request.files:
                    return jsonify({'success': False, 'error': 'No screenshot file in request'}), 400
                file = request.files['screenshot']
                if file.filename == '':
                    return jsonify({'success': False, 'error': 'No file selected'}), 400
                if not _allowed_file(file.filename):
                    return jsonify({'success': False, 'error': f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"}), 400
                if not _validate_file_size(file):
                    return jsonify({'success': False, 'error': f'File too large. Max size: {MAX_FILE_SIZE / 1024 / 1024}MB'}), 400

                emp_id = request.form.get('emp_id')
                timestamp = request.form.get('timestamp')  # expected YYYYMMDD_HHMMSS
                captured_at = request.form.get('captured_at')
                if not emp_id:
                    return jsonify({'success': False, 'error': 'emp_id is required'}), 400
                if not timestamp:
                    return jsonify({'success': False, 'error': 'timestamp is required'}), 400

                filename = secure_filename(file.filename)
                # Derive date folder
                try:
                    date_str = timestamp.split('_')[0]
                    date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                except Exception:
                    date_formatted = dt.datetime.now().strftime('%Y-%m-%d')

                # Build path and save
                base_dir = os.path.join(UPLOAD_BASE_DIR, 'screenshot', str(emp_id), date_formatted)
                os.makedirs(base_dir, exist_ok=True)
                file_path = os.path.join(base_dir, filename)
                file.save(file_path)

                # Stats
                file_size = os.path.getsize(file_path)
                try:
                    md5 = hashlib.md5()
                    with open(file_path, 'rb') as fh:
                        for chunk in iter(lambda: fh.read(4096), b''):
                            md5.update(chunk)
                    file_hash = md5.hexdigest()
                except Exception:
                    file_hash = ''

                relative_path = os.path.join('screenshot', str(emp_id), date_formatted, filename).replace('\\', '/')
                Alerts.log(f"Screenshot uploaded: {relative_path} | Size: {file_size} bytes")
                return jsonify({
                    'success': True,
                    'url': relative_path,
                    'file_name': filename,
                    'file_size': file_size,
                    'file_hash': file_hash,
                    'emp_id': emp_id,
                    'timestamp': timestamp,
                    'captured_at': captured_at,
                    'stored_at': dt.datetime.now().isoformat(),
                }), 200
            except Exception as e:
                Alerts.log(f"upload_screenshot error: {e}")
                return jsonify({'success': False, 'error': f'Internal server error: {str(e)}'}), 500

        @app.post('/api/ingest/heartbeat')
        def ingest_heartbeat():
            """Ingest heartbeat batch into Postgres (server-side DSN via EMP_DB_URL)."""
            try:
                if not _require_api_key():
                    return jsonify({'ok': False, 'error': 'Unauthorized'}), 401

                payload = request.get_json(force=True, silent=False) or {}
                emp_id = int(payload.get('emp_id') or 0)
                items = payload.get('items') or []
                if emp_id <= 0 or not isinstance(items, list) or not items:
                    return jsonify({'ok': False, 'error': 'Invalid payload'}), 400

                # Resolve DSN and schema (server holds secret)
                ing = self.cfg.data.get('ingestion', {}) if self.cfg else {}
                db_cfg = ing.get('db', {}) if isinstance(ing, dict) else {}
                schema = db_cfg.get('schema', 'employee_monitor')
                dsn = os.environ.get(db_cfg.get('url_env', 'EMP_DB_URL'))
                if not dsn or psycopg is None:
                    return jsonify({'ok': False, 'error': 'Database unavailable on server'}), 503

                rows = []
                for rec in items:
                    cur = rec.get('current') or {}
                    url = cur.get('url') or ''
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
                        (cur.get('process') or 'unknown'),
                        (cur.get('window') or ''),
                        (dom or None),
                        (url or None),
                        batt.get('percent'),
                        batt.get('power_plugged'),
                        json.dumps(rec.get('geo') or {})
                    ))

                inserted = 0
                with psycopg.connect(dsn) as conn:
                    with conn.cursor() as cur:
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
                            inserted = cur.rowcount or 0
                        else:
                            sql = f"""
                                INSERT INTO {schema}.heartbeat
                                (emp_id, ts, status, cpu_percent, memory_percent, process_name, window_title, domain, url, battery_level, battery_plugged, geo)
                                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                ON CONFLICT (emp_id, ts) DO NOTHING
                            """
                            cur.executemany(sql, rows)
                            inserted = cur.rowcount or 0
                return jsonify({'ok': True, 'inserted': inserted})
            except Exception as e:
                Alerts.log(f"ingest_heartbeat error: {e}")
                return jsonify({'ok': False, 'error': str(e)}), 500

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
        # Defer network lookups during first seconds after startup to avoid contention
        try:
            if hasattr(self, '_geo_ready_at') and now < float(self._geo_ready_at):
                cached = self._geo_cache.get('data') or {}
                return cached
        except Exception:
            pass
        cache_ts = self._geo_cache.get('ts', 0)
        cached = self._geo_cache.get('data')

        # Check if we have valid cached data
        if cached and len(cached) > 0:
            # Successful data cached, honor 1 hour TTL
            if (now - cache_ts) < 3600:
                return cached
        elif cache_ts > 0:
            # Previous lookup failed (empty result), respect shorter TTL (10 min)
            if (now - cache_ts) < 600:
                return cached or {}

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
                # Default: Use ipwho.is only (ipapi.co is rate-limited and unreliable)
                Alerts.log(f"Fetching geolocation from ipwho.is...")
                try:
                    r = requests.get('https://ipwho.is/', timeout=5)
                    if r.ok:
                        j = r.json()
                        if j.get('success', True):
                            conn = j.get('connection') or {}
                            data = {
                                "ip": j.get('ip'),
                                "city": j.get('city'),
                                "region": j.get('region'),
                                "country": j.get('country') or j.get('country_name'),
                                "latitude": j.get('latitude'),
                                "longitude": j.get('longitude'),
                                "org": conn.get('org') or conn.get('isp'),
                            }
                            Alerts.log(f"Geolocation fetched: {data.get('city')}, {data.get('country')} (IP: {data.get('ip')})")
                    else:
                        Alerts.log(f"Geo API returned status: {r.status_code}")
                except Exception as e:
                    Alerts.log(f"Geo lookup failed: {e}")
        except Exception as e:
            Alerts.log(f"Geo lookup failed: {e}")
        # Always cache outcome (even if empty) to honor TTL/backoff above
        self._geo_cache = {"ts": now, "data": data}
        return data

    def _geo_from_multiple_providers(self) -> Dict:
        """Query IP geolocation provider (ipwho.is only).
        Note: ipapi.co removed due to rate limiting issues.
        """
        try:
            r = requests.get('https://ipwho.is/', timeout=3)
            if r.ok:
                j = r.json()
                if j.get('success', True):
                    conn = j.get('connection') or {}
                    return {
                        "ip": j.get('ip'),
                        "city": j.get('city'),
                        "region": j.get('region'),
                        "country": j.get('country') or j.get('country_name'),
                        "latitude": j.get('latitude'),
                        "longitude": j.get('longitude'),
                        "org": conn.get('org') or conn.get('isp'),
                    }
        except Exception as e:
            Alerts.log(f"Geo lookup failed: {e}")
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

        batch_size = int(cfg.get('batch_size', 200))
        # Prevent unbounded growth - force flush if buffer exceeds 2x batch size
        if len(self.buf) >= (batch_size * 2):
            Alerts.log(f"Force flushing oversized buffer: {len(self.buf)} records")
            self.flush()
            return

        if len(self.buf) >= batch_size or (time.time() - self.last_flush) >= int(cfg.get('flush_interval_sec', 5)):
            self.flush()

    def flush(self, force: bool = False):
        if not self.buf and not force:
            return
        ing_cfg = self.app.cfg.data.get('ingestion', {})
        mode = ing_cfg.get('mode', 'file')
        direct = bool(ing_cfg.get('direct_write', False))
        # If not direct_write, always fall back to file-based buffering; periodic sync will handle Postgres
        if mode == 'file' or (mode == 'postgres' and not direct):
            today = dt.datetime.now().strftime('%Y-%m-%d')
            hb_path = os.path.join(HEARTBEAT_DIR, f'heartbeat_{today}.jsonl')
            try:
                with open(hb_path, 'a', encoding='utf-8') as f:
                    for rec in self.buf:
                        f.write(json.dumps(rec) + "\n")
            except Exception as e:
                Alerts.log(f"Ingestion flush error: {e}")
            # Also insert into local SQLite so periodic sync can push to Postgres
            try:
                emp_id = int(self.app.cfg.data.get('emp_id', 0))
                for rec in self.buf:
                    cur = rec.get('current') or {}
                    url = cur.get('url') or ''
                    # derive domain similar to Postgres path
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
                    self.app.local_storage.insert_heartbeat(
                        emp_id=emp_id,
                        ts=rec.get('ts'),
                        status=(cur.get('status') or None),
                        cpu_percent=float(rec.get('cpu_percent') or 0.0),
                        memory_percent=float(rec.get('mem_percent') or 0.0),
                        process_name=(cur.get('process') or 'unknown'),
                        window_title=(cur.get('window') or ''),
                        domain=(dom or None),
                        url=(url or None),
                        battery_level=batt.get('percent'),
                        battery_plugged=batt.get('power_plugged'),
                        geo=rec.get('geo') or None,
                    )
            except Exception as e:
                Alerts.log(f"Local heartbeat insert error: {e}")
            # Trigger a single sync check for heartbeats after batch insert
            try:
                if hasattr(self.app, 'local_storage'):
                    self.app.local_storage.check_sync_needed(data_type='heartbeat')
            except Exception as e:
                Alerts.log(f"Heartbeat sync trigger error: {e}")
        elif mode == 'api':
            # For API mode: save to SQLite and let APISync handle remote sync
            try:
                emp_id = int(self.app.cfg.data.get('emp_id', 0))
                for rec in self.buf:
                    cur = rec.get('current') or {}
                    url = rec.get('url') or ''
                    # derive domain
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
                    self.app.local_storage.insert_heartbeat(
                        emp_id=emp_id,
                        ts=rec.get('ts'),
                        status=(cur.get('status') or None),
                        cpu_percent=float(rec.get('cpu_percent') or 0.0),
                        memory_percent=float(rec.get('mem_percent') or 0.0),
                        process_name=(cur.get('process') or 'unknown'),
                        window_title=(cur.get('window') or ''),
                        domain=(dom or None),
                        url=(url or None),
                        battery_level=batt.get('percent'),
                        battery_plugged=batt.get('power_plugged'),
                        geo=rec.get('geo') or None,
                    )
                # Trigger API sync via APISync (not direct API call)
                if hasattr(self.app, 'local_storage'):
                    self.app.local_storage.check_sync_needed(data_type='heartbeat')
            except Exception as e:
                Alerts.log(f"API mode heartbeat buffer error: {e}")
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
                            (cur.get('process') or 'unknown'),
                            (cur.get('window') or ''),
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
            time.sleep(120)  # Increased from 60 to 120 for performance

    def stop(self):
        self.stop_event.set()


class WorkSessionMonitor(threading.Thread):
    """Monitors active work sessions for automatic limits and shutdowns"""
    MAX_WORK_DURATION_MS = 24 * 60 * 60 * 1000  # 24 hours in milliseconds
    INACTIVITY_THRESHOLD_SEC = 300  # 5 minutes of inactivity treated as potential shutdown/sleep

    def __init__(self, app_ref: 'MonitorApp'):
        super().__init__(daemon=True)
        self.app = app_ref
        self.stop_event = threading.Event()
        self.last_day = dt.datetime.now().day
        self.last_activity_check = time.time()
        self.inactive_break_start = None

    def _notify(self, title: str, message: str):
        """Send notification to user"""
        try:
            if self.app._notifier:
                self.app._notifier._notify(title, message)
        except Exception as e:
            Alerts.log(f"Notification error: {e}")

    def run(self):
        while not self.stop_event.is_set():
            try:
                # Use UTC-aware timestamps consistently
                now = dt.datetime.now(dt.timezone.utc)
                session = self.app._work_session

                # Check if there's an active session
                if session and session.get('start_ts') and not session.get('end_ts'):
                    start_dt = dt.datetime.fromisoformat(session['start_ts'])
                    if start_dt.tzinfo is None:
                        start_dt = start_dt.replace(tzinfo=dt.timezone.utc)
                    duration_ms = int((now - start_dt).total_seconds() * 1000)

                    # Calculate work duration (total - breaks)
                    breaks = session.get('breaks', [])
                    break_ms = 0
                    for br in breaks:
                        if br.get('start_ts') and br.get('end_ts'):
                            br_start = dt.datetime.fromisoformat(br['start_ts'])
                            br_end = dt.datetime.fromisoformat(br['end_ts'])
                            if br_start.tzinfo is None:
                                br_start = br_start.replace(tzinfo=dt.timezone.utc)
                            if br_end.tzinfo is None:
                                br_end = br_end.replace(tzinfo=dt.timezone.utc)
                            # Clamp break within session window
                            br_start = max(br_start, start_dt)
                            br_end = min(br_end, now)
                            if br_end > br_start:
                                break_ms += int((br_end - br_start).total_seconds() * 1000)

                    work_ms = duration_ms - break_ms

                    # Check 1: 24-hour work limit exceeded
                    if work_ms >= self.MAX_WORK_DURATION_MS:
                        Alerts.log("Work session exceeded 24 hours, auto-stopping")
                        self._notify("Work Limit Reached",
                                   "Your work session has reached the 24-hour limit and has been automatically stopped.")
                        # Call the Flask app's auto-end function through direct method
                        # We need to invoke this through the app context
                        try:
                            with self.app.flask_app.app_context():
                                from flask import Flask, jsonify
                                # Import the _auto_end_session closure from start_server scope
                                # Since we can't access the closure, we'll call the endpoint internally
                                pass
                        except:
                            pass
                        # Instead, directly manipulate the session
                        self.app._work_session['end_ts'] = dt.datetime.now(dt.timezone.utc).isoformat()
                        self._notify("Timer Auto-Stopped", "Work timer stopped due to 24-hour work limit.")

                    # Check 2: Midnight rollover - auto-stop at midnight
                    if now.day != self.last_day and now.hour == 0 and now.minute < 1:
                        Alerts.log("Midnight detected, auto-stopping work session")
                        self._notify("Midnight Auto-Stop",
                                   "Your work session has been automatically stopped at midnight.")
                        self.app._work_session['end_ts'] = dt.datetime.now(dt.timezone.utc).isoformat()

                # Update last day tracker
                self.last_day = now.day

                # Check 3: Inactivity detection (shutdown/sleep) - auto-create break
                if session and session.get('start_ts') and not session.get('end_ts'):
                    # Prefer reliable system idle time over hook counters to avoid false breaks when hooks are disabled
                    idle_sec = None
                    try:
                        idle_sec = get_system_idle_seconds()
                    except Exception:
                        idle_sec = None

                    if idle_sec is not None:
                        if idle_sec >= self.INACTIVITY_THRESHOLD_SEC:
                            # Sustained OS-level idle detected
                            if not self.inactive_break_start:
                                self.inactive_break_start = now - dt.timedelta(seconds=self.INACTIVITY_THRESHOLD_SEC)
                                Alerts.log("Inactivity detected (OS idle) - starting automatic break")
                        else:
                            # Activity present
                            if self.inactive_break_start:
                                # End the automatic break
                                breaks = session.setdefault('breaks', [])
                                if not breaks or breaks[-1].get('end_ts'):
                                    br_start = max(self.inactive_break_start, start_dt)
                                    br_end = now
                                    if br_end > br_start:
                                        breaks.append({
                                            "start_ts": br_start.isoformat(),
                                            "end_ts": br_end.isoformat(),
                                            "reason": "auto_inactivity"
                                        })
                                    Alerts.log("Automatic break added for inactivity period (OS idle)")
                                self.inactive_break_start = None
                    else:
                        # Fallback to lightweight counters when OS idle not available
                        current_time = time.time()
                        if hasattr(self.app, 'activity'):
                            total_activity = self.app.activity.mouse_clicks + self.app.activity.key_presses
                            if not hasattr(self, 'last_total_activity'):
                                self.last_total_activity = total_activity
                                self.last_activity_check = current_time

                            time_since_check = current_time - self.last_activity_check
                            activity_delta = total_activity - self.last_total_activity

                            if activity_delta == 0 and time_since_check >= self.INACTIVITY_THRESHOLD_SEC:
                                if not self.inactive_break_start:
                                    self.inactive_break_start = now - dt.timedelta(seconds=self.INACTIVITY_THRESHOLD_SEC)
                                    Alerts.log("Inactivity detected (counters) - starting automatic break")
                            elif activity_delta > 0:
                                if self.inactive_break_start:
                                    breaks = session.setdefault('breaks', [])
                                    if not breaks or breaks[-1].get('end_ts'):
                                        br_start = max(self.inactive_break_start, start_dt)
                                        br_end = now
                                        if br_end > br_start:
                                            breaks.append({
                                                "start_ts": br_start.isoformat(),
                                                "end_ts": br_end.isoformat(),
                                                "reason": "auto_inactivity"
                                            })
                                        Alerts.log("Automatic break added for inactivity period (counters)")
                                    self.inactive_break_start = None

                                # Update tracking variables
                                self.last_total_activity = total_activity
                                self.last_activity_check = current_time

            except Exception as e:
                Alerts.log(f"WorkSessionMonitor error: {e}")

            # Check every 60 seconds (increased from 30 for performance)
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
        self.high_memory_since: Optional[float] = None
        self.prev_running: set = set()
        self.prev_usb_devices: set = set()
        self.crash_history: Dict[str, List[float]] = {}
        self.last_ticket_ts: Dict[str, float] = {}  # Track last ticket timestamp per issue type

    def _create_ticket(self, issue_type: str, severity: str, details: Dict, actions_taken: Optional[List[str]] = None):
        # Check cooldown to prevent duplicate tickets
        cfg = self.app.cfg.data.get('itsm', {})
        cooldowns = cfg.get('cooldowns', {})
        cooldown_sec = cooldowns.get(issue_type, 600)  # Default 10 min cooldown

        now = time.time()
        last_ts = self.last_ticket_ts.get(issue_type, 0)

        if (now - last_ts) < cooldown_sec:
            # Still in cooldown period, skip creating ticket
            Alerts.log(f"ITSM ticket suppressed (cooldown): {issue_type}")
            return

        # Create ticket
        ticket = {
            "id": f"TKT-{int(time.time())}",
            "ts": dt.datetime.now().isoformat(timespec='seconds'),
            "type": issue_type,
            "severity": severity,
            "details": details,
            "actions_taken": actions_taken or [],
            "status": "open"
        }

        # Save to JSON file
        try:
            with open(ITSM_TICKETS_JSON, 'r', encoding='utf-8') as f:
                tickets = json.load(f)
        except Exception:
            tickets = []
        tickets.append(ticket)
        with open(ITSM_TICKETS_JSON, 'w', encoding='utf-8') as f:
            json.dump(tickets, f, indent=2)

        # Save to PostgreSQL database
        try:
            ing = self.app.cfg.data.get('ingestion', {})
            if ing.get('mode') == 'postgres' and psycopg is not None:
                db_cfg = ing.get('db', {})
                dsn = (db_cfg.get('url') or '').strip() or os.environ.get(db_cfg.get('url_env', 'EMP_DB_URL'))
                if dsn:
                    schema = db_cfg.get('schema', 'employee_monitor')
                    emp_id = int(self.app.cfg.data.get('emp_id', 0))

                    with psycopg.connect(dsn) as conn:
                        with conn.cursor() as cur:
                            # Create ITSM tickets table if not exists
                            cur.execute(f"""
                                CREATE TABLE IF NOT EXISTS {schema}.itsm_tickets (
                                    id VARCHAR(50) PRIMARY KEY,
                                    emp_id INTEGER NOT NULL,
                                    ts TIMESTAMPTZ NOT NULL,
                                    type VARCHAR(50) NOT NULL,
                                    severity VARCHAR(20) NOT NULL,
                                    details JSONB,
                                    actions_taken JSONB,
                                    status VARCHAR(20) DEFAULT 'open',
                                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                                )
                            """)

                            # Insert ticket
                            cur.execute(f"""
                                INSERT INTO {schema}.itsm_tickets
                                (id, emp_id, ts, type, severity, details, actions_taken, status)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT (id) DO NOTHING
                            """, (
                                ticket['id'], emp_id, ticket['ts'], ticket['type'],
                                ticket['severity'], json.dumps(ticket['details']),
                                json.dumps(ticket['actions_taken']), ticket['status']
                            ))
                            conn.commit()
                            Alerts.log(f"ITSM ticket saved to database: {ticket['id']}")
        except Exception as e:
            Alerts.log(f"Failed to save ITSM ticket to database: {e}")

        # Update last ticket timestamp
        self.last_ticket_ts[issue_type] = now

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
                        # Removed sleep for performance - use cached values
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

    def _check_disk_space(self):
        """Check for low disk space on system drive"""
        cfg = self.app.cfg.data.get('itsm', {})
        thresh = int(cfg.get('low_disk_threshold', 15))
        try:
            usage = psutil.disk_usage('C:')
            free_percent = (usage.free / usage.total) * 100
            if free_percent < thresh:
                self._create_ticket(
                    issue_type="low_disk",
                    severity="major",
                    details={
                        "drive": "C:",
                        "free_percent": round(free_percent, 2),
                        "free_gb": round(usage.free / (1024**3), 2),
                        "total_gb": round(usage.total / (1024**3), 2)
                    },
                    actions_taken=[]
                )
        except Exception as e:
            Alerts.log(f"Disk space check error: {e}")

    def _check_memory_usage(self):
        """Check for sustained high memory usage"""
        cfg = self.app.cfg.data.get('itsm', {})
        thresh = int(cfg.get('high_memory_threshold', 90))
        dur = int(cfg.get('high_memory_duration_sec', 180))
        mem = psutil.virtual_memory().percent
        now = time.time()

        if mem >= thresh:
            if self.high_memory_since is None:
                self.high_memory_since = now
            elif (now - self.high_memory_since) >= dur:
                # sustained high memory
                actions = []
                if cfg.get('auto_heal', False):
                    # attempt to find top memory offender and terminate if not protected
                    try:
                        offenders = []
                        for p in psutil.process_iter(['pid', 'name', 'memory_percent']):
                            try:
                                mem_pct = p.info.get('memory_percent', 0)
                                if mem_pct:
                                    offenders.append((p, mem_pct))
                            except Exception:
                                continue
                        offenders.sort(key=lambda t: t[1], reverse=True)
                        for p, pct in offenders[:3]:
                            name = (p.info.get('name') or '').lower()
                            if name and name not in cfg.get('protected_processes', []):
                                try:
                                    p.terminate()
                                    actions.append(f"terminated {name} pid={p.pid} mem={pct:.1f}%")
                                    break
                                except Exception:
                                    continue
                    except Exception:
                        pass
                self._create_ticket(
                    issue_type="high_memory",
                    severity="major",
                    details={"memory_percent": mem, "duration_sec": dur},
                    actions_taken=actions
                )
                self.high_memory_since = None
        else:
            self.high_memory_since = None

    def _check_unexpected_reboot(self):
        """Detect unexpected system reboot based on low uptime"""
        cfg = self.app.cfg.data.get('itsm', {})
        min_uptime = int(cfg.get('min_uptime_for_reboot_detect', 300))
        try:
            uptime_sec = time.time() - psutil.boot_time()
            if uptime_sec < min_uptime and not hasattr(self, '_reboot_check_done'):
                self._create_ticket(
                    issue_type="unexpected_reboot",
                    severity="major",
                    details={
                        "uptime_seconds": round(uptime_sec, 2),
                        "boot_time": dt.datetime.fromtimestamp(psutil.boot_time()).isoformat()
                    },
                    actions_taken=[]
                )
                self._reboot_check_done = True
        except Exception as e:
            Alerts.log(f"Reboot check error: {e}")

    def _check_critical_services(self):
        """Monitor critical Windows services"""
        cfg = self.app.cfg.data.get('itsm', {})
        watched = cfg.get('watched_services', [])
        if not watched:
            return

        try:
            for service_name in watched:
                try:
                    service = psutil.win_service_get(service_name)
                    status = service.status()
                    if status != 'running':
                        self._create_ticket(
                            issue_type="service_stopped",
                            severity="critical",
                            details={
                                "service": service_name,
                                "status": status,
                                "display_name": service.display_name()
                            },
                            actions_taken=[]
                        )
                except psutil.NoSuchProcess:
                    self._create_ticket(
                        issue_type="service_stopped",
                        severity="critical",
                        details={
                            "service": service_name,
                            "status": "not_found"
                        },
                        actions_taken=[]
                    )
                except Exception:
                    continue
        except Exception as e:
            Alerts.log(f"Service check error: {e}")

    def _check_usb_devices(self):
        """Detect new USB/external storage devices"""
        try:
            current_devices = set()
            for part in psutil.disk_partitions(all=False):
                if 'removable' in part.opts.lower():
                    current_devices.add(part.device)

            if not hasattr(self, 'prev_usb_devices'):
                self.prev_usb_devices = current_devices
                return

            new_devices = current_devices - self.prev_usb_devices
            if new_devices:
                for device in new_devices:
                    self._create_ticket(
                        issue_type="usb_device",
                        severity="minor",
                        details={"device": device},
                        actions_taken=[]
                    )

            self.prev_usb_devices = current_devices
        except Exception as e:
            Alerts.log(f"USB device check error: {e}")

    def _check_security_status(self):
        """Check if Windows Defender or antivirus is disabled"""
        try:
            # Check Windows Defender status via registry or WMI
            import winreg
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Windows Defender\Real-Time Protection", 0,
                    winreg.KEY_READ)
                disabled, _ = winreg.QueryValueEx(key, "DisableRealtimeMonitoring")
                winreg.CloseKey(key)

                if disabled == 1:
                    self._create_ticket(
                        issue_type="security_disabled",
                        severity="critical",
                        details={"protection": "Windows Defender Real-Time", "status": "disabled"},
                        actions_taken=[]
                    )
            except FileNotFoundError:
                pass  # Key doesn't exist, might be using different AV
            except Exception:
                pass
        except Exception as e:
            Alerts.log(f"Security status check error: {e}")

    def _check_repeated_crashes(self):
        """Detect repeated crashes of the same application"""
        if not hasattr(self, 'crash_history'):
            self.crash_history = {}

        cfg = self.app.cfg.data.get('itsm', {})
        watch = [w.lower() for w in cfg.get('watched_apps', [])]
        if not watch:
            return

        now = time.time()
        # Clean old crash history (older than 1 hour)
        self.crash_history = {app: times for app, times in self.crash_history.items()
                             if any(t > now - 3600 for t in times)}

        running = set()
        for p in psutil.process_iter(['name']):
            try:
                nm = (p.info.get('name') or '').lower()
                if nm:
                    running.add(nm)
            except Exception:
                continue

        # Detect crashed apps
        crashed = [app for app in watch if (app in self.prev_running and app not in running)]
        for app in crashed:
            if app not in self.crash_history:
                self.crash_history[app] = []
            self.crash_history[app].append(now)

            # Check if crashed 3+ times in last hour
            recent_crashes = [t for t in self.crash_history[app] if t > now - 3600]
            if len(recent_crashes) >= 3:
                self._create_ticket(
                    issue_type="repeated_crash",
                    severity="critical",
                    details={
                        "app": app,
                        "crash_count": len(recent_crashes),
                        "time_window": "1 hour"
                    },
                    actions_taken=[]
                )
                # Reset to avoid duplicate tickets
                self.crash_history[app] = []

    def _check_battery_health(self):
        """Monitor battery health and charging issues (for laptops)"""
        try:
            battery = psutil.sensors_battery()
            if battery is None:
                return  # Not a laptop or no battery

            cfg = self.app.cfg.data.get('itsm', {})
            thresh = int(cfg.get('battery_health_threshold', 60))

            # Check battery percentage when not plugged in
            if not battery.power_plugged and battery.percent < 20:
                self._create_ticket(
                    issue_type="battery_issue",
                    severity="minor",
                    details={
                        "issue": "low_battery",
                        "percent": battery.percent,
                        "power_plugged": battery.power_plugged
                    },
                    actions_taken=[]
                )

            # Note: Actual battery health % requires WMI or additional tools
            # This is a simplified check based on available psutil data
        except Exception as e:
            Alerts.log(f"Battery health check error: {e}")

    def run(self):
        # Prime prev_running
        try:
            self.prev_running = { (p.info.get('name') or '').lower() for p in psutil.process_iter(['name']) }
        except Exception:
            self.prev_running = set()
        # Run reboot check once at startup
        self._check_unexpected_reboot()

        while not self.stop_event.is_set():
            try:
                self._check_high_cpu()
                self._check_memory_usage()
                self._check_disk_space()
                self._check_critical_services()
                self._check_usb_devices()
                self._check_security_status()
                self._check_app_crash()
                self._check_repeated_crashes()
                self._check_battery_health()
            except Exception as e:
                Alerts.log(f"ITSMHelper loop error: {e}")
            time.sleep(60)  # Increased from 30 to 60 for performance

    def stop(self):
        self.stop_event.set()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Employee Monitor System')
    parser.add_argument('--serve', action='store_true', help='Start HTTP livestream server')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=5050)
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
