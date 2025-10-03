# WFH Agent 🏠💼

> **Enterprise Employee Monitoring & Productivity Analytics Platform**

A comprehensive desktop application for monitoring employee productivity, wellness, and system metrics in work-from-home environments. Built with Electron and Python, featuring real-time analytics, PostgreSQL integration, and intelligent notification systems.

[![Version](https://img.shields.io/badge/version-0.1.6-blue.svg)](https://github.com/chetan-fidelis/wfh-agent/releases)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)](https://www.microsoft.com/windows)

---

## 📋 Table of Contents

- [Features](#-features)
- [Screenshots](#-screenshots)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Architecture](#-architecture)
- [Development](#-development)
- [Usage](#-usage)
- [API Reference](#-api-reference)
- [Roadmap](#-roadmap)
- [Contributing](#-contributing)
- [License](#-license)

---

## ✨ Features

### 📊 Productivity Tracking
- **Application Usage Monitoring** - Track time spent on applications with productivity tagging
- **Website Activity Tracking** - Monitor website usage with categorization (productive/neutral/unproductive)
- **Activity Metrics** - Real-time keyboard and mouse activity tracking
- **Timeline Visualization** - Hourly breakdown of work patterns and productivity

### 👤 Work Session Management
- **Smart Tray Menu** - Live countdown timer showing work duration
- **Visual Status Indicators** - Clear display of work/break status
- **Context-Aware Actions** - Dynamic menu based on current work state
- **Session Analytics** - Comprehensive work session summaries

### 🔔 Intelligent Notifications
- **Milestone Celebrations** - Achievements at 4h, 6h, 8h work milestones
- **Break Reminders** - Automatic reminders every 2 hours
- **Long Break Alerts** - Notifications for breaks exceeding 30 minutes
- **Battery Optimization** - Reminders to unplug at 80%+ charge
- **Wellness Alerts** - Burnout risk and overburden notifications

### 🏥 Wellness Monitoring
- **Daily Wellness Scores** - Comprehensive health metrics tracking
- **Work-Life Balance** - Overtime detection and alerts
- **Activity Analysis** - Active/idle ratio monitoring
- **Burnout Prevention** - Risk assessment based on work patterns

### 🌍 ESG & Sustainability
- **Carbon Footprint Tracking** - Real-time CO2e calculations
- **Energy Consumption Monitoring** - Power usage analytics
- **Country-Specific Metrics** - Location-based carbon intensity
- **Battery vs. AC Power Analysis** - Environmental impact tracking

### 🎫 IT Service Management (ITSM)
- **Auto-Ticket Generation** - Automatic incident creation
- **High CPU Monitoring** - Performance issue detection
- **Network Disconnect Alerts** - Connectivity monitoring
- **Application Crash Detection** - Critical app monitoring
- **Webhook Integration** - External system notifications

### 📧 Admin Management
- **App Quit Notifications** - Email alerts when employees quit
- **Webhook Support** - Integration with monitoring systems
- **Configurable Events** - Customizable notification triggers
- **SMTP Integration** - Email notifications via Office 365, Gmail, etc.

### 📸 Screenshot Capabilities
- **Scheduled Screenshots** - Configurable daily captures
- **Remote Storage** - Upload to external server
- **Screenshot Gallery** - Built-in viewer with metadata
- **Retention Policies** - Automatic cleanup based on retention days

### 🔒 Security & Compliance
- **Domain Blocking** - Work-hours website restrictions
- **USB Monitoring** - Device connection tracking
- **Geo-Location Tracking** - IP-based location detection
- **Office vs. Remote Detection** - Location-aware features

### 💾 Data Management
- **PostgreSQL Integration** - Enterprise-grade database storage
- **Local SQLite Backup** - Offline data persistence
- **Automatic Sync** - Real-time database synchronization
- **Data Export** - JSON file exports for analytics

---

## 📸 Screenshots

### Dashboard
![Dashboard](docs/screenshots/dashboard.png)
*Real-time productivity metrics and work session overview*

### Tray Menu
![Tray Menu](docs/screenshots/tray-menu.png)
*Smart tray menu with live countdown timer*

### Analytics
![Analytics](docs/screenshots/analytics.png)
*Detailed productivity and wellness analytics*

---

## 🚀 Installation

### Prerequisites
- **Windows 10/11** (64-bit)
- **PostgreSQL** (for production deployment)
- **Internet Connection** (for initial setup)

### Quick Install

1. **Download the latest release**
   ```
   Download: WFH Agent Setup 0.1.6.exe
   ```

2. **Run the installer**
   - Double-click `WFH Agent Setup 0.1.6.exe`
   - Follow the installation wizard
   - Choose installation directory

3. **Configure database** (Optional - for production)
   - Edit `monitor_data/config.json`
   - Update PostgreSQL connection details
   - Restart the application

### First Run

1. **Login** with your credentials
2. **Configure** work hours and preferences
3. **Start Work** session from tray menu
4. Monitor productivity in real-time

---

## ⚙️ Configuration

### Database Configuration

Edit `monitor_data/config.json`:

```json
{
  "ingestion": {
    "enabled": true,
    "mode": "postgres",
    "db": {
      "schema": "employee_monitor",
      "url": "postgresql://user:password@host:5432/database"
    }
  }
}
```

### Work Hours

```json
{
  "work_hours": {
    "start": "09:30",
    "end": "18:30"
  },
  "workdays": [1, 2, 3, 4, 5],
  "break_window": {
    "start": "13:00",
    "duration_minutes": 60
  }
}
```

### Features Toggle

```json
{
  "features": {
    "itsm": true,
    "notifications": true,
    "website_tracking": true,
    "esg": true,
    "scheduled_shots": true
  }
}
```

### Admin Notifications

```json
{
  "admin_notifications": {
    "enabled": true,
    "webhook_url": "https://your-webhook.com/endpoint",
    "email": {
      "enabled": true,
      "smtp_server": "smtp.office365.com",
      "smtp_port": 587,
      "from_email": "monitor@company.com",
      "to_emails": ["admin@company.com"]
    },
    "events": {
      "app_quit": true,
      "policy_violation": true
    }
  }
}
```

---

## 🏗️ Architecture

### Technology Stack

**Frontend (Electron)**
- Electron 31.x
- HTML5/CSS3/JavaScript
- IPC Communication
- Auto-updater

**Backend (Python)**
- Python 3.13
- Flask REST API
- psutil (System Metrics)
- psycopg (PostgreSQL)
- Pillow (Screenshots)
- Windows Hooks (Input Tracking)

**Database**
- PostgreSQL (Production)
- SQLite (Local Backup)

### System Design

```
┌─────────────────┐
│  Electron App   │
│   (Frontend)    │
└────────┬────────┘
         │ IPC
┌────────▼────────┐
│  Python Backend │
│  (Flask API)    │
└────────┬────────┘
         │
    ┌────▼─────┬──────────┬──────────┐
    │          │          │          │
┌───▼───┐ ┌───▼───┐ ┌───▼───┐ ┌───▼────┐
│ SQLite│ │Postgres│ │ Files │ │Webhooks│
└───────┘ └────────┘ └───────┘ └────────┘
```

---

## 🛠️ Development

### Setup Development Environment

1. **Clone the repository**
   ```bash
   git clone https://github.com/chetan-fidelis/wfh-agent.git
   cd wfh-agent
   ```

2. **Install Node dependencies**
   ```bash
   npm install
   ```

3. **Install Python dependencies**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

4. **Run in development mode**
   ```bash
   npm run dev
   ```

### Build for Production

```bash
# Build backend executable
npm run build:backend

# Build Electron installer
npm run build:single

# Output: dist/WFH Agent Setup 0.1.6.exe
```

### Project Structure

```
wfh-agent/
├── src/                    # Frontend source
│   ├── dashboard/         # Dashboard UI
│   ├── login/            # Login UI
│   └── styles/           # CSS styles
├── backend/               # Python backend
│   ├── emp_monitor.py    # Main backend script
│   ├── local_storage.py  # Database layer
│   └── requirements.txt  # Python deps
├── monitor_data/          # Data storage
│   ├── config.json       # Configuration
│   ├── timeline.json     # Activity timeline
│   └── shots/           # Screenshots
├── assets/               # App assets
│   └── icon.png         # App icon
├── main.js              # Electron main process
├── preload.js           # Preload script
└── package.json         # Node dependencies
```

---

## 📖 Usage

### Starting Work Session

**Via Tray Menu:**
1. Right-click tray icon
2. Click "▶️ Start Work"
3. Monitor timer in tray menu

**Via Dashboard:**
1. Open dashboard
2. Click "Start Work" button
3. View real-time metrics

### Taking Breaks

**Via Tray Menu:**
1. Right-click tray icon
2. Click "☕ Take Break"
3. Click "▶️ Resume Work" when ready

### Viewing Analytics

1. Click "📊 Show Dashboard" in tray menu
2. Navigate to different tabs:
   - **Overview** - Current session stats
   - **Timeline** - Hourly activity
   - **Wellness** - Health metrics
   - **ESG** - Environmental impact
   - **ITSM** - IT incidents

---

## 🔌 API Reference

### REST Endpoints

#### Session Management

```http
POST /session/start
GET  /session/state
POST /session/break/start
POST /session/break/end
POST /session/end
GET  /session/summary?days=7
```

#### Monitoring

```http
GET  /status
GET  /heartbeat?n=100&date=2025-10-03
GET  /latest.jpg
```

#### Analytics

```http
GET  /esg?month=2025-10
GET  /itsm/tickets
GET  /api/screenshots
```

#### Admin

```http
POST /app/quit
POST /geo/refresh
```

### IPC Handlers (Electron)

```javascript
// Work session
ipcMain.handle('work:start')
ipcMain.handle('work:breakToggle')
ipcMain.handle('work:end')
ipcMain.handle('work:state')
ipcMain.handle('work:summary', { days: 7 })

// Configuration
ipcMain.handle('config:get')
ipcMain.handle('session:get')
```

---

## 🗺️ Roadmap

### v0.2.0 (Planned)
- [ ] Multi-platform support (macOS, Linux)
- [ ] Advanced AI-powered productivity insights
- [ ] Team collaboration features
- [ ] Mobile companion app
- [ ] Video call detection
- [ ] Focus mode with Pomodoro timer

### v0.3.0 (Future)
- [ ] Cloud dashboard
- [ ] Manager portal
- [ ] Custom report builder
- [ ] Integration with JIRA/Slack
- [ ] Advanced ML analytics

---

## 🤝 Contributing

We welcome contributions! Please follow these guidelines:

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Commit your changes** (`git commit -m 'Add amazing feature'`)
4. **Push to the branch** (`git push origin feature/amazing-feature`)
5. **Open a Pull Request**

### Development Guidelines

- Follow existing code style
- Write meaningful commit messages
- Add tests for new features
- Update documentation

---

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🏢 About

**WFH Agent** is developed and maintained by **Fidelis Technology Services Pvt. Ltd.**

- **Website**: https://fidelisam.in
- **Email**: support@fidelisgroup.in
- **GitHub**: https://github.com/chetan-fidelis/wfh-agent

---

## 📞 Support

For support, please:

1. Check the [Documentation](docs/)
2. Search [Issues](https://github.com/chetan-fidelis/wfh-agent/issues)
3. Create a [New Issue](https://github.com/chetan-fidelis/wfh-agent/issues/new)
4. Email: support@fidelisgroup.in

---

## 🙏 Acknowledgments

- Built with [Electron](https://www.electronjs.org/)
- Powered by [Python](https://www.python.org/)
- Icons from [Heroicons](https://heroicons.com/)
- Inspired by modern remote work challenges

---

<div align="center">

**[⬆ Back to Top](#wfh-agent-)**

Made with ❤️ by Fidelis Technology Services

</div>
