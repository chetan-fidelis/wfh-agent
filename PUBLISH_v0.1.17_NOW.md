# 🚀 Publish v0.1.17 to GitHub - Quick Guide

## ⚠️ ISSUE FOUND

**v0.1.16 cannot update to v0.1.17 because v0.1.17 is NOT published on GitHub!**

---

## ✅ Files Ready to Upload

All files are built and ready in `dist/` folder:

1. ✅ `WFH-Agent-Setup-0.1.17.exe` (156 MB)
2. ✅ `latest.yml` (metadata)
3. ✅ `WFH-Agent-Setup-0.1.17.exe.blockmap` (delta updates)

---

## 📤 Upload Steps (5 minutes)

### Step 1: Go to GitHub Releases
```
https://github.com/chetan-fidelis/wfh-agent/releases/new
```

### Step 2: Fill Release Form

**Tag version**: `v0.1.17`

**Release title**: `WFH Agent v0.1.17 - Critical Data Collection Fixes`

**Description**:
```markdown
## 🎯 Critical Fixes in v0.1.17

### Data Collection Improvements
- ✅ Screenshot "twice daily" - guaranteed morning + afternoon
- ✅ Screenshot compression - 60-70% smaller files
- ✅ Upload retry mechanism - 3x retry with queue
- ✅ Data validation - prevent invalid data sync
- ✅ URL sanitization - remove sensitive parameters

### Benefits
- Faster uploads (smaller files)
- Better data quality (validation)
- Zero data loss (retry + queue)
- Enhanced privacy (URL sanitization)

### Installation
Download and run `WFH-Agent-Setup-0.1.17.exe`

### Auto-Update
Users on v0.1.16 will automatically receive this update.
```

### Step 3: Upload Files

**Drag and drop these 3 files**:
```
d:\tracking\v5\desktop\dist\WFH-Agent-Setup-0.1.17.exe
d:\tracking\v5\desktop\dist\latest.yml
d:\tracking\v5\desktop\dist\WFH-Agent-Setup-0.1.17.exe.blockmap
```

### Step 4: Publish

- ✅ Check "Set as the latest release"
- ✅ Click "Publish release"

---

## ✅ Verify After Publishing

1. **Release page loads**:
   ```
   https://github.com/chetan-fidelis/wfh-agent/releases/tag/v0.1.17
   ```

2. **Files are downloadable**:
   - Click on each file to verify download starts

3. **Auto-update will work**:
   - v0.1.16 clients will detect update within 5 minutes

---

## 🎉 Done!

After publishing:
- ✅ v0.1.16 users will auto-update to v0.1.17
- ✅ New users can download v0.1.17 directly
- ✅ All critical fixes will be deployed

---

## 🔧 If You Need to Regenerate latest.yml

If the SHA512 hash doesn't match:

```powershell
cd d:\tracking\v5\desktop
.\generate-latest-yml.ps1
```

Then re-upload the new `latest.yml` to the release.

---

## 📞 Questions?

See `FIX_AUTO_UPDATE_v0.1.17.md` for detailed troubleshooting.
