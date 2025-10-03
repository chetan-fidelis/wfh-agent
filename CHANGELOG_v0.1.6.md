# WFH Agent v0.1.6 - Release Notes

## 🎉 What's New

### Enhanced User Experience
- **Smart Tray Menu with Live Countdown Timer** ⏱️
  - Real-time work duration display (e.g., "2h 30m")
  - Visual status indicators ("⏱️ Working", "☕ On Break", "Not Working")
  - Context-aware action buttons
  - Auto-updates every minute
  - Synchronized with backend session data

- **Intelligent Work Notifications** 🔔
  - Milestone celebrations (4h, 6h, 8h work achievements)
  - Break reminders every 2 hours
  - Long break alerts (30+ minutes)
  - Battery saver reminders (80%+ while charging)
  - Encouragement messages for better employee engagement

### Admin Management Features
- **App Quit Notifications** 📧
  - Email alerts when employees quit the application
  - Webhook support for system integrations
  - Includes work session status and duration
  - Configurable notification events (app_quit, policy_violation)

### Bug Fixes & Improvements
- ✅ Fixed tray menu not updating when starting work from dashboard
- ✅ Fixed session start HTTP 400 errors (stale session handling)
- ✅ Fixed admin notification HTTP 500 errors
- ✅ Fixed disconnect between tray menu and dashboard data
- ✅ Tray menu now fetches live session data from backend
- ✅ Auto-clear stale sessions (>24 hours old)
- ✅ Improved session synchronization between Electron and backend
- ✅ Fixed auto-updater compatibility issues

### Technical Improvements
- Backend session management enhancements
- Better error handling for offline queue
- Smart HTTP 400/404 error discarding
- Session validation and cleanup
- Real-time bidirectional sync

## 📋 Configuration

### New Config Options

**Admin Notifications** (`config.json`):
```json
"admin_notifications": {
  "enabled": true,
  "webhook_url": "",
  "email": {
    "enabled": true,
    "smtp_server": "smtp.office365.com",
    "smtp_port": 587,
    "from_email": "your-email@company.com",
    "to_emails": ["admin@company.com"],
    "username": "your-email@company.com",
    "password": "your-password"
  },
  "events": {
    "app_quit": true,
    "session_end": false,
    "policy_violation": true
  }
}
```

**Notifications Feature** (must be enabled):
```json
"features": {
  "notifications": true
}
```

## 🔧 Installation

1. Close any running WFH Agent instances
2. Run `WFH Agent Setup 0.1.6.exe`
3. Follow the installation wizard
4. Launch the application

## 📊 Database Schema

No database changes in this release.

## 🐛 Known Issues

- Domain blocking requires administrator privileges (expected behavior)
- Battery notifications only show when battery is charging and above 80%

## 🙏 Credits

Developed by **Fidelis Technology Services Pvt. Ltd.**

---

**Full Changelog**: v0.1.5...v0.1.6
