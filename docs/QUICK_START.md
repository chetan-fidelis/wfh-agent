# Download Monitor - Quick Start Guide

## 5-Minute Setup

### Step 1: Enable in Config (30 seconds)

Edit `monitor_data/config.json`:

```json
{
  "download_monitor": {
    "enabled": true,
    "api_url": "http://ats-tool.test/api"
  }
}
```

### Step 2: Set Auth Token (30 seconds)

**PowerShell:**
```powershell
$env:CV_CAPTURE_AUTH_TOKEN = "your-sanctum-token-here"
```

**Windows Command Prompt:**
```cmd
set CV_CAPTURE_AUTH_TOKEN=your-sanctum-token-here
```

**Permanent (Environment Variable):**
1. Press `Win + X` → System
2. Advanced system settings
3. Environment Variables
4. New User Variable:
   - Name: `CV_CAPTURE_AUTH_TOKEN`
   - Value: `your-token`
5. Click OK and restart app

### Step 3: Restart App (1 minute)

```powershell
Stop-Process -Name "wfh-agent-desktop" -Force
# Relaunch app
```

### Step 4: Verify (1 minute)

Check logs:
```powershell
Get-Content "monitor_data\alerts.log" -Tail 20
```

Look for:
```
[DownloadMonitor] Monitoring 5 download paths
[DownloadMonitor] Monitor thread started
```

### Step 5: Test (2 minutes)

1. Download a test file: `Naukri_Test_CV.pdf`
2. Check logs for: `Found new file: Naukri_Test_CV.pdf`
3. Verify upload: `Successfully uploaded: Naukri_Test_CV.pdf`

---

## Configuration Quick Reference

### Minimal Config
```json
{
  "download_monitor": {
    "enabled": true
  }
}
```

### Full Config
```json
{
  "download_monitor": {
    "enabled": true,
    "api_url": "http://ats-tool.test/api",
    "target_designations": [
      "manager - talent acquisition",
      "recruiter",
      "hr"
    ],
    "check_interval_sec": 30,
    "max_file_size_mb": 100,
    "allowed_extensions": ["pdf", "docx", "txt"],
    "naukri_pattern": "Naukri_",
    "monitor_naukri_only": true
  }
}
```

---

## Common Tasks

### Enable for Specific Employee

```json
{
  "emp_id": 123,
  "designation": "Manager - Talent Acquisition",
  "download_monitor": {
    "enabled": true
  }
}
```

### Disable Temporarily

```json
{
  "download_monitor": {
    "enabled": false
  }
}
```

### Change Scan Interval

```json
{
  "download_monitor": {
    "check_interval_sec": 60
  }
}
```

### Increase File Size Limit

```json
{
  "download_monitor": {
    "max_file_size_mb": 200
  }
}
```

---

## Troubleshooting Quick Fixes

### Monitor Not Starting

**Check 1: Is it enabled?**
```powershell
$config = Get-Content "monitor_data\config.json" | ConvertFrom-Json
$config.download_monitor.enabled  # Should be: true
```

**Check 2: Is auth token set?**
```powershell
$env:CV_CAPTURE_AUTH_TOKEN  # Should not be empty
```

**Check 3: Restart app**
```powershell
Stop-Process -Name "wfh-agent-desktop" -Force
```

### Files Not Being Detected

**Check 1: File naming**
- Must start with `Naukri_`
- Extension must be `.pdf`, `.docx`, or `.txt`
- Example: `Naukri_John_Doe.pdf` ✓

**Check 2: File is fully written**
- Wait 30 seconds after download completes
- Monitor scans every 30 seconds

**Check 3: File size**
- Must be under 100MB
- Check file properties

### Upload Failures

**Check 1: API reachable?**
```powershell
Test-NetConnection -ComputerName "ats-tool.test" -Port 80
```

**Check 2: Auth token valid?**
```powershell
# Token should be 40+ characters
$env:CV_CAPTURE_AUTH_TOKEN.Length
```

**Check 3: Review logs**
```powershell
Select-String "error|failed" "monitor_data\alerts.log" -i
```

---

## Monitoring

### Check Status

```powershell
# Is monitor running?
Select-String "\[DownloadMonitor\]" "monitor_data\alerts.log" -Tail 5

# How many files uploaded?
(Select-String "Successfully uploaded" "monitor_data\alerts.log").Count

# Any errors?
Select-String "error|failed|exception" "monitor_data\alerts.log" -i
```

### View Recent Activity

```powershell
# Last 20 monitor entries
Select-String "\[DownloadMonitor\]" "monitor_data\alerts.log" -Tail 20

# Export to file
Select-String "\[DownloadMonitor\]" "monitor_data\alerts.log" | 
    Out-File "download_monitor_activity.txt"
```

---

## File Naming Examples

### ✅ Correct
- `Naukri_John_Doe.pdf`
- `Naukri_Resume_2025.docx`
- `Naukri_CV.txt`
- `Naukri_123456.pdf`

### ❌ Incorrect
- `Resume_John.pdf` (wrong prefix)
- `Naukri_John.exe` (wrong extension)
- `john_naukri.pdf` (wrong position)
- `NAUKRI_John.pdf` (uppercase OK, but pattern must match)

---

## API Endpoints

### Presign URL
```
POST /api/cv-capture/presign
Authorization: Bearer {token}
Content-Type: application/json

{
  "file_name": "Naukri_John_Doe.pdf",
  "file_size": 245000
}
```

### Upload to S3
```
PUT {presigned_url}
Content-Type: application/octet-stream

[binary file data]
```

### Store Metadata
```
POST /api/cv-capture/metadata
Authorization: Bearer {token}
Content-Type: application/json

{
  "file_name": "Naukri_John_Doe.pdf",
  "file_size": 245000,
  "file_hash": "sha256-hash",
  "uploaded_at": "2025-11-06T16:30:00Z",
  "emp_id": 123
}
```

---

## Environment Variables

### Required
```powershell
$env:CV_CAPTURE_AUTH_TOKEN = "your-token"
```

### Optional
```powershell
$env:CV_CAPTURE_API_URL = "http://ats-tool.test/api"
$env:WFH_DEBUG = "1"  # Enable debug logging
```

---

## Performance Tips

### For Large Download Folders
```json
{
  "download_monitor": {
    "check_interval_sec": 60,
    "monitor_naukri_only": true
  }
}
```

### For Slow Network
```json
{
  "download_monitor": {
    "check_interval_sec": 120,
    "max_file_size_mb": 50
  }
}
```

### For High-Volume Uploads
```json
{
  "download_monitor": {
    "check_interval_sec": 30,
    "max_file_size_mb": 100
  }
}
```

---

## Support

### Getting Help

1. **Check logs first**
   ```powershell
   Get-Content "monitor_data\alerts.log" -Tail 50
   ```

2. **Review troubleshooting guide**
   - See: `TROUBLESHOOTING_GUIDE.md`

3. **Contact support with**
   - Employee ID
   - File name and size
   - Error message from logs
   - Config settings (sanitized)

### Documentation

- **Feature Overview**: `DOWNLOAD_MONITOR.md`
- **API Specification**: `LARAVEL_API_INTEGRATION.md`
- **Deployment Guide**: `DEPLOYMENT_CHECKLIST.md`
- **Troubleshooting**: `TROUBLESHOOTING_GUIDE.md`
- **Implementation Details**: `IMPLEMENTATION_SUMMARY.md`

---

## Supported Designations

The monitor automatically activates for:
- Manager - Talent Acquisition
- Associate Manager - Talent Acquisition
- Senior Executive - Talent Acquisition
- Team Lead - Talent Acquisition
- Executive - Talent Acquisition
- Vice President - Talent Acquisition
- Trainee - Talent Acquisition
- Senior Executive - Talent Acquisition - RPO
- Talent Acquisition Partner
- Talent Acquisition
- Associate Vice President - Talent Acquisition

---

## Next Steps

1. ✅ Enable in config
2. ✅ Set auth token
3. ✅ Restart app
4. ✅ Verify in logs
5. ✅ Test with sample file
6. ✅ Monitor uploads

**You're ready to go!** 🚀
