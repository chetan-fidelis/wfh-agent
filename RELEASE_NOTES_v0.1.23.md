# Harmony Desktop v0.1.23 Release Notes

**Release Date:** November 21, 2025  
**Version:** 0.1.23  
**Platform:** Windows x64  
**Installer:** `Harmony Setup 0.1.23.exe` (155.72 MB)

---

## 🎯 Release Highlights

### Major Features & Improvements

#### 1. **Per-User Configuration Management** ✅
- **Issue Fixed:** Config changes were being ignored; all users saw bundled defaults
- **Solution:** Updated `loadConfig()` in `main.js` to prioritize per-user roaming config
  - Reads from: `%APPDATA%\Roaming\wfh-agent-desktop\monitor_data\config.json`
  - Falls back to bundled config if user config doesn't exist
- **Impact:** Each user now has persistent, independent configuration across updates

#### 2. **Dynamic Naukri File History (Per-User)** ✅
- **Issue Fixed:** Tray menu showed static, identical CV upload history across all machines
- **Solution:** Migrated `cv_uploads.json` to per-user Electron userData directory
  - Windows: `%APPDATA%\Roaming\wfh-agent-desktop\monitor_data\cv_uploads.json`
  - macOS: `~/Library/Application Support/wfh-agent-desktop/monitor_data/cv_uploads.json`
  - Linux: `~/.config/wfh-agent-desktop/monitor_data/cv_uploads.json`
- **Files Modified:**
  - `main.js` (lines 107-111, 1060-1068)
  - `backend/download_monitor_v2.py` (lines 337-356)
- **Impact:** Each user sees only their own CV upload history in the tray menu

#### 3. **System Info Display in Dashboard** ✅
- **Feature:** Added System Information as 3rd column in profile card
- **What's Displayed:**
  - Operating System (Windows, macOS, Linux)
  - Architecture (x64, arm64, etc.)
  - Harmony Version (v0.1.23)
- **Files Modified:**
  - `src/dashboard/index.html` (added System Info section)
  - `src/dashboard/renderer.js` (added `loadSystemInfo()` function)
  - `src/styles/global.css` (updated grid to 3 columns)
  - `preload.js` (exposed `getVersion()` and `getSystemInfo()` APIs)
  - `main.js` (added `system:info` IPC handler)
- **Responsive Design:**
  - Desktop (>1024px): 3 columns (Employee | Manager | System Info)
  - Tablet (768px-1024px): 2 columns
  - Mobile (<768px): 1 column (stacked)

#### 4. **Simplified Download Monitor Startup Logic** ✅
- **Issue Fixed:** Redundant checks in download monitor initialization
- **Solution:** Consolidated logic in `emp_monitor.py` (lines 3366-3384)
  - Now uses single condition: `if enabled OR is_recruitment_designation`
  - Removed unreachable code paths
- **Impact:** Cleaner, more reliable startup for Naukri file tracking

#### 5. **Installer Branding & Cleanup** ✅
- **Updated NSIS Configuration:**
  - Installer name: "Harmony Setup 0.1.23.exe"
  - Shortcut name: "Harmony"
  - Uninstall display name: "Harmony"
  - Added installer icons for professional appearance
- **Removed:** Old WFH Agent branding from installer
- **Note:** Future releases will include automatic uninstall of old WFH Agent

---

## 🔧 Technical Changes

### Backend (`backend/emp_monitor.py`)
- **Lines 3366-3384:** Simplified download monitor startup logic
  - Removed duplicate condition checks
  - Improved logging clarity

### Frontend (`src/dashboard/`)
- **index.html:** Added System Info profile section
- **renderer.js:** 
  - Added `loadSystemInfo()` async function
  - Integrated system info loading with profile load
- **styles/global.css:**
  - Updated `.profile-grid` from 2-column to 3-column layout
  - Added responsive breakpoint at 1024px for tablet view

### Electron Main Process (`main.js`)
- **Lines 28-31:** Added `os` module import
- **Lines 1019-1022:** Updated `loadConfig()` to check roaming config first
- **Lines 771-788:** Added `system:info` IPC handler
  - Returns: platform, arch, cpus, totalMemory, freeMemory, hostname, uptime

### IPC Bridge (`preload.js`)
- **Lines 39-40:** Exposed new APIs
  - `getVersion()` → calls `app:version` handler
  - `getSystemInfo()` → calls `system:info` handler

---

## 📋 Bug Fixes & Improvements

| Issue | Status | Details |
|-------|--------|---------|
| Static tray CV list | ✅ Fixed | Now per-user and dynamic |
| Config not persisting | ✅ Fixed | Reads from roaming config first |
| Redundant startup logic | ✅ Fixed | Simplified download monitor init |
| Missing system info display | ✅ Fixed | Added 3rd column in dashboard |
| NSIS build failure | ✅ Fixed | Removed problematic custom script |

---

## 🚀 Installation & Deployment

### For End Users
1. Download: `Harmony Setup 0.1.23.exe`
2. Run installer (one-click installation)
3. Desktop shortcut and Start Menu entry created automatically
4. First run: Config and history initialized in user's AppData

### For Administrators
- **Installer Size:** 155.72 MB
- **Installation Directory:** `C:\Program Files\Harmony` (default)
- **User Data Directory:** `%APPDATA%\Roaming\wfh-agent-desktop`
- **Silent Install:** `Harmony Setup 0.1.23.exe /S`

---

## ✅ Testing Checklist

- [x] Build succeeds without errors
- [x] Installer creates proper shortcuts
- [x] Per-user config loads correctly
- [x] CV upload history is per-user
- [x] System Info displays in dashboard
- [x] Responsive design works on all screen sizes
- [x] Backend download monitor starts correctly
- [x] No console errors on startup

---

## 📝 Known Limitations

- Automatic uninstall of old WFH Agent will be added in next release
- System Info is read-only (informational only)

---

## 🔄 Upgrade Path

**From v0.1.22 → v0.1.23:**
- No breaking changes
- Config automatically migrated to roaming directory on first run
- CV upload history preserved in new location

---

## 📞 Support

For issues or questions about this release:
1. Check `monitor_data/alerts.log` for error details
2. Verify config at `%APPDATA%\Roaming\wfh-agent-desktop\monitor_data\config.json`
3. Contact: support@fidelisgroup.in

---

**Build Info:**
- Electron: 31.7.7
- Node: v18.x
- Python Backend: 3.9+
- Target: Windows x64

**Checksum:** See `Harmony Setup 0.1.23.exe.blockmap` for integrity verification
