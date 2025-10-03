# Employee Monitor - Improvements & Recommendations

## Current Issues

### 1. ⚠️ Activity Tracking Disabled (Python 3.13)
**Problem:** `key_presses` and `mouse_clicks` always show 0

**Root Cause:**
- Python 3.13.7 detected at [emp_monitor.py:1678](emp_monitor.py#L1678)
- `pynput` library incompatible with Python 3.13 on Windows
- Input listeners automatically disabled

**Current Workaround:**
- Uses Windows `GetLastInputInfo()` API for idle detection
- Works for active/idle status but no detailed metrics

**Solutions:**

#### A. Downgrade Python (Recommended for now)
```bash
# Install Python 3.12
winget install Python.Python.3.12

# Rebuild executable
pyinstaller emp_monitor.spec
```

#### B. Implement Windows Native Input Tracking
Replace `pynput` with `ctypes` + Windows API:

```python
import ctypes
from ctypes import wintypes

# Windows API for input hooks
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

class WindowsInputTracker:
    """Native Windows input tracking using SetWindowsHookEx"""

    def __init__(self):
        self.key_count = 0
        self.mouse_count = 0

    def keyboard_hook_proc(self, nCode, wParam, lParam):
        if nCode >= 0:
            if wParam in [0x100, 0x104]:  # WM_KEYDOWN, WM_SYSKEYDOWN
                self.key_count += 1
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    def mouse_hook_proc(self, nCode, wParam, lParam):
        if nCode >= 0:
            if wParam in [0x201, 0x204, 0x207]:  # WM_LBUTTONDOWN, etc
                self.mouse_count += 1
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    def start(self):
        # Install low-level hooks
        # WH_KEYBOARD_LL = 13, WH_MOUSE_LL = 14
        pass  # Implementation needed
```

#### C. Use `keyboard` + `mouse` libraries (Python 3.13 compatible)
```bash
pip install keyboard mouse
```

**Note:** May require elevated privileges

---

## Suggested Improvements

### 2. 🔄 Real-time Session Sync
**Current:** Sessions only sync when explicitly ended
**Improvement:** Auto-sync active sessions every 5 minutes

```javascript
// In main.js
setInterval(async () => {
  const work = loadWork();
  if (work.current && !work.current.end_ts) {
    // Sync active session to backend
    await backendPost('/session/update', {
      start_ts: work.current.start_ts,
      breaks: work.current.breaks,
      status: work.current.status
    });
  }
}, 5 * 60 * 1000); // Every 5 minutes
```

### 3. 📊 Enhanced Activity Metrics
Add more granular tracking:

```python
class EnhancedActivityStats:
    """Extended activity tracking"""

    # Current
    key_presses: int
    mouse_clicks: int
    last_activity_ts: float

    # New additions
    scroll_events: int          # Mouse wheel usage
    window_switches: int        # Focus changes
    active_window_time: Dict[str, float]  # Time per application
    typing_speed_wpm: float     # Words per minute
    mouse_distance_pixels: int  # Total mouse movement
    clipboard_operations: int   # Copy/paste count

    # Productivity indicators
    continuous_active_time: float  # No idle breaks
    multitask_score: float        # Window switch frequency
    focus_score: float            # Time in single app
```

### 4. 🎯 Smart Idle Detection
Current idle detection is binary (active/idle). Improve with:

```python
class SmartIdleDetector:
    """Multi-level activity classification"""

    ACTIVITY_LEVELS = {
        'highly_active': 0,      # < 30s idle, high input rate
        'active': 30,            # < 5min idle, moderate input
        'lightly_active': 300,   # < 15min idle, low input
        'idle': 900,             # < 30min idle
        'away': 1800,            # > 30min idle
    }

    def classify_activity(self, idle_secs, input_rate):
        """Return activity level based on idle time + input rate"""
        if idle_secs < 30 and input_rate > 10:  # 10+ inputs/min
            return 'highly_active'
        # ... more logic
```

### 5. 🔐 Privacy Mode
Add option to pause monitoring:

```python
class PrivacyMode:
    """Allow users to pause monitoring temporarily"""

    def __init__(self):
        self.paused = False
        self.pause_start = None

    def toggle_privacy_mode(self):
        """Toggle monitoring on/off"""
        self.paused = not self.paused
        if self.paused:
            self.pause_start = time.time()
            # Stop input listeners
            # Mark as 'privacy_mode' status
        else:
            # Resume monitoring
            # Create gap in timeline
            pass
```

### 6. 📸 Screenshot Optimization
**Current:** Fixed schedule (2/day at random times)
**Improvement:** Smart screenshot triggers

```python
class SmartScreenshotManager:
    """Intelligent screenshot capture"""

    TRIGGERS = {
        'scheduled': True,           # Keep existing schedule
        'activity_spike': True,      # High activity detected
        'new_application': True,     # App switch
        'productivity_change': True, # Productive -> Unproductive
        'meeting_detected': True,    # Teams/Zoom active
    }

    def should_capture(self, context):
        """Decide if screenshot needed based on triggers"""
        if self.scheduled_due():
            return True
        if context.activity_rate > threshold:
            return True
        # ... more logic
```

### 7. 🧠 AI-Powered Insights
Add ML-based analysis:

```python
class ProductivityInsights:
    """Machine learning for productivity patterns"""

    def analyze_patterns(self, history_days=30):
        """Identify productivity patterns"""
        return {
            'peak_hours': ['9-11 AM', '2-4 PM'],
            'distraction_triggers': ['social media after email'],
            'focus_apps': ['vscode', 'pycharm'],
            'break_patterns': 'regular 15min breaks',
            'recommendations': [
                'Block social media 9-11 AM',
                'Take breaks every 90 minutes',
            ]
        }
```

### 8. 📱 Mobile Integration
Add mobile app sync:

```python
# REST API endpoints for mobile app
@app.route('/api/mobile/status')
def mobile_status():
    """Get current work status for mobile app"""
    return jsonify({
        'is_working': session.is_active,
        'current_task': session.current_app,
        'time_worked_today': session.total_time,
        'productivity_score': calculate_score()
    })

@app.route('/api/mobile/remote-break', methods=['POST'])
def mobile_remote_break():
    """Start break from mobile device"""
    start_break_session()
    return jsonify({'ok': True})
```

### 9. 🔔 Smart Notifications
Replace basic alerts with intelligent notifications:

```python
class SmartNotificationEngine:
    """Context-aware notifications"""

    NOTIFICATION_TYPES = {
        'break_reminder': {
            'condition': 'continuous_work > 2 hours',
            'message': 'Take a 15-minute break',
            'priority': 'high'
        },
        'posture_reminder': {
            'condition': 'active_time > 30 min',
            'message': 'Stretch and adjust posture',
            'priority': 'medium'
        },
        'productivity_boost': {
            'condition': 'distraction_detected',
            'message': 'Focus time - minimize distractions',
            'priority': 'low'
        },
        'water_reminder': {
            'condition': 'time_since_last_break > 1 hour',
            'message': 'Stay hydrated',
            'priority': 'low'
        }
    }
```

### 10. 📈 Advanced Dashboard Features

#### A. Heatmap View
```javascript
// Show activity intensity by hour/day
{
  "monday": { "09:00": 85, "10:00": 92, ... },
  "tuesday": { "09:00": 78, "10:00": 88, ... }
}
```

#### B. Application Timeline
```javascript
// Visualize app switches throughout day
[
  { start: "09:00", end: "09:30", app: "chrome", url: "github.com" },
  { start: "09:30", end: "11:00", app: "vscode", productivity: "high" },
  { start: "11:00", end: "11:15", app: "break", type: "scheduled" }
]
```

#### C. Team Comparison (Anonymous)
```python
def get_team_metrics():
    """Compare your metrics with team averages"""
    return {
        'your_productivity': 78,
        'team_avg': 72,
        'your_hours': 7.5,
        'team_avg_hours': 8.2,
        'your_focus_time': 5.2,
        'team_avg_focus': 4.8
    }
```

---

## Performance Optimizations

### 11. 🚀 Database Optimization
**Current:** Frequent SQLite writes
**Improvement:** Batch operations

```python
class OptimizedLocalStorage:
    """Batched writes for better performance"""

    def __init__(self):
        self.write_buffer = []
        self.buffer_size = 100

    def queue_write(self, table, data):
        """Queue write operation"""
        self.write_buffer.append((table, data))

        if len(self.write_buffer) >= self.buffer_size:
            self.flush()

    def flush(self):
        """Batch execute all queued writes"""
        with sqlite3.connect(self.db_path) as conn:
            for table, data in self.write_buffer:
                # Single transaction for all writes
                pass
        self.write_buffer.clear()
```

### 12. 🎨 UI/UX Improvements

#### A. Quick Actions Tray Menu
```javascript
const trayMenu = [
  { label: '⏰ Start Work', click: startWork },
  { label: '☕ Take Break', click: takeBreak },
  { label: '🛑 End Work', click: endWork },
  { type: 'separator' },
  { label: '📊 Today: 6h 23m', enabled: false },
  { label: '🎯 Focus: 85%', enabled: false },
  { type: 'separator' },
  { label: '⚙️ Settings', click: openSettings },
  { label: '🔄 Sync Now', click: forceSyn },
  { label: '❌ Quit', click: quitApp }
]
```

#### B. Pomodoro Timer Integration
```javascript
class PomodoroTimer {
  constructor() {
    this.workDuration = 25 * 60; // 25 minutes
    this.breakDuration = 5 * 60; // 5 minutes
    this.longBreakDuration = 15 * 60; // 15 minutes
    this.sessionsUntilLongBreak = 4;
  }

  start() {
    // Integrate with work session tracking
    // Auto-start breaks after work intervals
  }
}
```

---

## Security Improvements

### 13. 🔒 Data Encryption
```python
from cryptography.fernet import Fernet

class EncryptedStorage:
    """Encrypt sensitive data at rest"""

    def __init__(self):
        self.key = self.load_or_generate_key()
        self.cipher = Fernet(self.key)

    def encrypt_screenshot(self, image_path):
        """Encrypt screenshots before upload"""
        with open(image_path, 'rb') as f:
            encrypted = self.cipher.encrypt(f.read())
        return encrypted
```

### 14. 🛡️ Audit Logging
```python
class AuditLogger:
    """Log all system events for compliance"""

    def log_event(self, event_type, details):
        """Append to audit log"""
        entry = {
            'timestamp': datetime.now().isoformat(),
            'event': event_type,
            'details': details,
            'user': os.getenv('USERNAME'),
            'ip': get_local_ip()
        }
        # Write to tamper-proof log
```

---

## Deployment Improvements

### 15. 🐳 Docker Deployment
```dockerfile
# Dockerfile for screenshot upload server
FROM python:3.12-slim

WORKDIR /app
COPY backend/screenshot_upload_server.py .
COPY backend/screenshot_server_requirements.txt .

RUN pip install -r screenshot_server_requirements.txt

EXPOSE 8080
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "screenshot_upload_server:app"]
```

### 16. 🔄 Auto-Update Improvements
- Delta updates (download only changed files)
- Rollback capability
- Update scheduling (only during off-hours)
- Staged rollout (test on subset first)

---

## Monitoring & Observability

### 17. 📊 System Health Dashboard
```python
class SystemHealth:
    """Monitor application health"""

    def get_health_metrics(self):
        return {
            'cpu_usage': psutil.cpu_percent(),
            'memory_usage': psutil.virtual_memory().percent,
            'disk_space': psutil.disk_usage('/').percent,
            'backend_status': 'healthy',
            'last_sync': '2 minutes ago',
            'errors_today': 0,
            'screenshot_queue': 3,
            'session_duration': '6h 23m'
        }
```

---

## Priority Implementation Order

### Phase 1 (Critical - This Week)
1. ✅ Fix Python 3.13 input tracking issue
2. ✅ Real-time session sync
3. Enhanced error handling

### Phase 2 (Important - Next Week)
4. Smart idle detection
5. Screenshot optimization
6. Privacy mode

### Phase 3 (Nice to Have - This Month)
7. AI-powered insights
8. Mobile integration
9. Advanced dashboard features

### Phase 4 (Future)
10. Team collaboration features
11. Custom reporting
12. Third-party integrations (Jira, Slack, etc.)

---

Would you like me to implement any of these improvements?
