# Fix Auto-Update: v0.1.16 → v0.1.17

## 🔴 Problem Identified

**v0.1.17 is NOT published as a GitHub release**, so electron-updater cannot find it.

### Why Auto-Update Fails:
1. ✅ `latest.yml` exists locally in `dist/` folder
2. ✅ Installer `WFH-Agent-Setup-0.1.17.exe` exists locally
3. ❌ **GitHub release v0.1.17 does NOT exist**
4. ❌ **Files not uploaded to GitHub**

electron-updater checks: `https://github.com/chetan-fidelis/wfh-agent/releases/latest`  
Result: **404 Not Found**

---

## ✅ Solution: Publish v0.1.17 to GitHub

### Step 1: Create GitHub Release

1. **Go to GitHub**:
   ```
   https://github.com/chetan-fidelis/wfh-agent/releases/new
   ```

2. **Fill in Release Details**:
   - **Tag**: `v0.1.17`
   - **Release title**: `WFH Agent v0.1.17 - Critical Data Collection Fixes`
   - **Description**:
   ```markdown
   ## What's New in v0.1.17
   
   ### Critical Fixes
   - ✅ Screenshot "twice daily" now guaranteed (morning + afternoon)
   - ✅ Screenshot compression (60-70% smaller files)
   - ✅ Upload retry mechanism (3x retry + queue)
   - ✅ Data validation before sync
   - ✅ URL sanitization (remove sensitive data)
   
   ### Improvements
   - Faster screenshot uploads
   - Better data quality
   - Enhanced privacy protection
   - Zero data loss with persistent queue
   
   ### Files
   - `WFH-Agent-Setup-0.1.17.exe` - Windows installer (156 MB)
   - `latest.yml` - Auto-update metadata
   - `WFH-Agent-Setup-0.1.17.exe.blockmap` - Delta update support
   
   **Full Changelog**: See CRITICAL_FIXES_APPLIED.md
   ```

3. **Upload Files** (REQUIRED):
   - ✅ `dist/WFH-Agent-Setup-0.1.17.exe`
   - ✅ `dist/latest.yml`
   - ✅ `dist/WFH-Agent-Setup-0.1.17.exe.blockmap` (if exists)

4. **Publish Release**:
   - ✅ Check "Set as the latest release"
   - ✅ Click "Publish release"

---

### Step 2: Verify Release

After publishing, verify:

1. **Check release exists**:
   ```
   https://github.com/chetan-fidelis/wfh-agent/releases/tag/v0.1.17
   ```

2. **Check latest.yml is accessible**:
   ```
   https://github.com/chetan-fidelis/wfh-agent/releases/download/v0.1.17/latest.yml
   ```

3. **Check installer is accessible**:
   ```
   https://github.com/chetan-fidelis/wfh-agent/releases/download/v0.1.17/WFH-Agent-Setup-0.1.17.exe
   ```

All URLs should return **200 OK** (not 404).

---

### Step 3: Test Auto-Update

1. **Install v0.1.16** on test machine

2. **Wait 5 minutes** (auto-update checks every 5 min)

3. **Check logs** in `monitor_data/alerts.log`:
   ```
   auto-updater: checking for updates...
   auto-updater: update available -> 0.1.17
   auto-updater: downloading update...
   auto-updater: update downloaded
   ```

4. **Restart app** when prompted

5. **Verify version** in About dialog: Should show `v0.1.17`

---

## 🚀 Quick Fix Commands

### Option A: Use PowerShell Script (Recommended)

Run the existing script to regenerate `latest.yml`:

```powershell
cd d:\tracking\v5\desktop
.\generate-latest-yml.ps1
```

Then upload the 3 files to GitHub release.

---

### Option B: Manual Upload

1. **Locate files**:
   ```
   d:\tracking\v5\desktop\dist\WFH-Agent-Setup-0.1.17.exe
   d:\tracking\v5\desktop\dist\latest.yml
   d:\tracking\v5\desktop\dist\WFH-Agent-Setup-0.1.17.exe.blockmap
   ```

2. **Create release on GitHub**

3. **Upload all 3 files**

4. **Publish release**

---

## 📋 Checklist

### Before Publishing
- [ ] Verify `package.json` version is `0.1.17`
- [ ] Verify `latest.yml` version is `0.1.17`
- [ ] Verify installer file exists: `WFH-Agent-Setup-0.1.17.exe`
- [ ] Verify SHA512 hash in `latest.yml` matches installer
- [ ] Verify file size in `latest.yml` matches installer

### Publishing
- [ ] Create GitHub release with tag `v0.1.17`
- [ ] Upload `WFH-Agent-Setup-0.1.17.exe`
- [ ] Upload `latest.yml`
- [ ] Upload `WFH-Agent-Setup-0.1.17.exe.blockmap` (if exists)
- [ ] Set as "latest release"
- [ ] Publish release

### After Publishing
- [ ] Verify release URL accessible
- [ ] Verify `latest.yml` downloadable
- [ ] Verify installer downloadable
- [ ] Test auto-update from v0.1.16
- [ ] Verify v0.1.17 installs correctly

---

## 🔍 Troubleshooting

### Issue: "No updates available" in v0.1.16

**Cause**: GitHub release not published  
**Fix**: Follow Step 1 above

---

### Issue: "404 Not Found" in logs

**Cause**: Files not uploaded to release  
**Fix**: Upload all 3 files to GitHub release

---

### Issue: "Update downloaded but won't install"

**Cause**: SHA512 mismatch  
**Fix**: Regenerate `latest.yml` with correct hash:
```powershell
.\generate-latest-yml.ps1
```
Then re-upload `latest.yml` to GitHub release.

---

### Issue: "Update available but download fails"

**Cause**: Installer file missing from release  
**Fix**: Upload `WFH-Agent-Setup-0.1.17.exe` to release

---

## 📝 Important Notes

### 1. GitHub Release is REQUIRED
electron-updater **only works with GitHub releases**. Local files are not enough.

### 2. File Names Must Match
- Release tag: `v0.1.17`
- Installer: `WFH-Agent-Setup-0.1.17.exe`
- Metadata: `latest.yml`

### 3. latest.yml Must Be Correct
The SHA512 hash and file size in `latest.yml` must match the actual installer file.

### 4. Set as Latest Release
Make sure to check "Set as the latest release" when publishing.

---

## 🎯 Expected Behavior After Fix

### On v0.1.16 Client:
1. App checks for updates every 5 minutes
2. Finds v0.1.17 on GitHub
3. Downloads update in background
4. Shows notification: "Update available"
5. User clicks "Restart to Update"
6. App restarts with v0.1.17

### Logs in alerts.log:
```
auto-updater: checking for updates...
auto-updater: update available -> 0.1.17
auto-updater: downloading update...
auto-updater: update downloaded
auto-updater: installing update...
```

---

## 🔄 Alternative: Use electron-builder publish

For future releases, automate the process:

```bash
# Build and publish in one command
npm run build:electron -- --publish always
```

This requires:
1. `GH_TOKEN` environment variable set
2. GitHub personal access token with repo permissions

---

## 📞 Support

If auto-update still doesn't work after following these steps:

1. **Check GitHub release exists**: Visit the release URL
2. **Check files are uploaded**: All 3 files present
3. **Check logs**: `monitor_data/alerts.log` for errors
4. **Manual update**: Download and install v0.1.17 manually

---

## Summary

**Root Cause**: v0.1.17 not published to GitHub  
**Fix**: Create GitHub release and upload files  
**Time**: 5-10 minutes  
**Impact**: Auto-update will work immediately after publishing
