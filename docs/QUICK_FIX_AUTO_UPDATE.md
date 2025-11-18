# Quick Fix: Auto-Update Not Working

## Problem
Users on v0.1.15 are not auto-updating to v0.1.17.

## Root Cause
**Missing `latest.yml` file** in the GitHub release.

electron-updater requires this file to detect new versions. Without it, the app thinks there are no updates available.

---

## Solution (5 minutes)

### Step 1: Generate latest.yml
```powershell
cd d:\tracking\v5\desktop
.\generate-latest-yml.ps1
```

This will create `dist\latest.yml` with the correct SHA512 hash and file size.

### Step 2: Upload to GitHub Release

1. **Go to**: https://github.com/chetan-fidelis/wfh-agent/releases/tag/v0.1.17
2. **Click**: "Edit release"
3. **Upload**: Drag `dist\latest.yml` to the assets section
4. **Click**: "Update release"

### Step 3: Verify

Test the URL in your browser:
```
https://github.com/chetan-fidelis/wfh-agent/releases/download/v0.1.17/latest.yml
```

Should download the yml file (not show 404).

---

## What Happens After Fix

1. **Within 4 hours**: All running v0.1.15 apps will check for updates
2. **Update detected**: App shows "Update available: 0.1.17"
3. **Auto-download**: Update downloads in background
4. **Auto-install**: App prompts to restart and install

Users can also manually check:
- Right-click tray icon → Check for Updates

---

## Verify It's Working

On a test machine with v0.1.15:

1. **Open**: `monitor_data\alerts.log`
2. **Look for**:
   ```
   auto-updater: checking for updates...
   auto-updater: update available -> 0.1.17
   auto-updater: download 100%
   auto-updater: update downloaded -> 0.1.17
   ```

---

## For Future Releases

To avoid this issue, always upload 3 files to GitHub releases:

1. ✅ `WFH-Agent-Setup-X.X.X.exe` (installer)
2. ✅ `WFH-Agent-Setup-X.X.X.exe.blockmap` (for delta updates)
3. ✅ `latest.yml` (for update detection) ← **CRITICAL**

### Automated Solution

Use electron-builder's publish feature:

```powershell
# Set GitHub token (one-time)
$env:GH_TOKEN = "your_github_personal_access_token"

# Build and auto-publish (uploads all 3 files)
npx electron-builder --win nsis --x64 --publish always
```

This automatically:
- Builds the installer
- Generates `latest.yml`
- Uploads all files to GitHub release

---

## Current Release Status

**Your release**: https://github.com/chetan-fidelis/wfh-agent/releases/tag/v0.1.17

**Current assets**:
- ✅ WFH-Agent-Setup-0.1.17.exe (156 MB)
- ✅ WFH-Agent-Setup-0.1.17.exe.blockmap (162 KB)
- ❌ latest.yml (MISSING - add this!)

**After fix**:
- ✅ WFH-Agent-Setup-0.1.17.exe
- ✅ WFH-Agent-Setup-0.1.17.exe.blockmap
- ✅ latest.yml ← Will enable auto-update

---

## Summary

**Fix**: Run `.\generate-latest-yml.ps1` and upload the generated file to GitHub release.

**Time**: 5 minutes

**Impact**: All v0.1.15 users will auto-update to v0.1.17 within 4 hours.

**Files created**:
- `generate-latest-yml.ps1` - Script to generate latest.yml
- `AUTO_UPDATE_FIX.md` - Detailed troubleshooting guide
- `QUICK_FIX_AUTO_UPDATE.md` - This quick reference
