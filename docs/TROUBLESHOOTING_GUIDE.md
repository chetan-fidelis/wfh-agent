# Troubleshooting & Rollback Guide - Download Monitor

## Quick Diagnostics

### Check if Download Monitor is Running

1. **Check logs**
   ```powershell
   Get-Content "monitor_data\alerts.log" -Tail 50
   ```
   Look for: `[DownloadMonitor] Monitor thread started`

2. **Check process**
   ```powershell
   Get-Process | Where-Object {$_.Name -like "*emp_monitor*"}
   ```

3. **Check config**
   ```powershell
   Get-Content "monitor_data\config.json" | ConvertFrom-Json | Select-Object download_monitor
   ```

### Verify Configuration

```powershell
# Check if enabled
$config = Get-Content "monitor_data\config.json" | ConvertFrom-Json
$config.download_monitor.enabled  # Should be: true

# Check auth token
$env:CV_CAPTURE_AUTH_TOKEN  # Should not be empty

# Check API URL
$config.download_monitor.api_url  # Should be valid URL
```

---

## Common Issues & Solutions

### Issue 1: Download Monitor Not Starting

**Symptoms**:
- No "DownloadMonitor" lines in `alerts.log`
- Files not being detected

**Diagnosis**:
```powershell
# Check if enabled
$config = Get-Content "monitor_data\config.json" | ConvertFrom-Json
if ($config.download_monitor.enabled -eq $false) {
    Write-Host "Download monitor is disabled"
}

# Check auth token
if ([string]::IsNullOrEmpty($env:CV_CAPTURE_AUTH_TOKEN)) {
    Write-Host "Auth token not set"
}

# Check designation
Write-Host "Employee designation: $($config.designation)"
```

**Solutions**:

1. **Enable in config**
   ```json
   {
     "download_monitor": {
       "enabled": true
     }
   }
   ```

2. **Set auth token**
   ```powershell
   $env:CV_CAPTURE_AUTH_TOKEN = "your-token-here"
   ```

3. **Verify designation matches**
   ```powershell
   $config = Get-Content "monitor_data\config.json" | ConvertFrom-Json
   $designation = $config.designation.ToLower()
   $targets = $config.download_monitor.target_designations
   
   if ($targets -contains $designation) {
       Write-Host "Designation matches"
   } else {
       Write-Host "Designation does NOT match. Add to target_designations"
   }
   ```

---

### Issue 2: Files Not Being Detected

**Symptoms**:
- Monitor is running but files not found
- No "Found new file" messages in logs

**Diagnosis**:
```powershell
# Check download paths
$downloads = "$env:USERPROFILE\Downloads"
$desktop = "$env:USERPROFILE\Desktop"

Get-ChildItem $downloads -Filter "Naukri_*" -ErrorAction SilentlyContinue | 
    ForEach-Object { Write-Host "Found: $($_.Name)" }
```

**Solutions**:

1. **Verify file naming**
   - File must start with `Naukri_`
   - Extension must be `.pdf`, `.docx`, or `.txt`
   - Example: `Naukri_John_Doe.pdf` ✓
   - Example: `Resume_John.pdf` ✗

2. **Check file is fully written**
   ```powershell
   # File should not be locked
   $file = Get-Item "C:\Users\...\Downloads\Naukri_*.pdf"
   
   # Try to open it
   try {
       $stream = [System.IO.File]::Open($file.FullName, 'Open', 'Read', 'None')
       $stream.Close()
       Write-Host "File is ready"
   } catch {
       Write-Host "File is still being written"
   }
   ```

3. **Check file size**
   ```powershell
   $file = Get-Item "C:\Users\...\Downloads\Naukri_*.pdf"
   $sizeMB = $file.Length / 1MB
   
   if ($sizeMB -gt 100) {
       Write-Host "File exceeds 100MB limit"
   }
   ```

4. **Verify download paths are monitored**
   - Check `monitor_data/alerts.log` for: `Monitoring X download paths`
   - Ensure Downloads and Desktop folders exist

---

### Issue 3: Upload Failures

**Symptoms**:
- Files detected but not uploaded
- "Failed to upload" messages in logs

**Diagnosis**:
```powershell
# Check API connectivity
$apiUrl = "https://fhq.fidelisam.in/api/cv-capture/presign"
$token = $env:CV_CAPTURE_AUTH_TOKEN

try {
    $response = Invoke-WebRequest -Uri $apiUrl `
        -Method POST `
        -Headers @{"Authorization" = "Bearer $token"} `
        -Body '{"file_name":"test.pdf","file_size":1000}' `
        -ContentType "application/json" `
        -ErrorAction Stop
    
    Write-Host "API is reachable: $($response.StatusCode)"
} catch {
    Write-Host "API error: $($_.Exception.Message)"
}
```

**Solutions**:

1. **Verify API endpoint**
   ```powershell
   # Test presign endpoint
   $apiUrl = "https://fhq.fidelisam.in/api/cv-capture/presign"
   
   # Should return 200 with presigned URL
   Invoke-WebRequest -Uri $apiUrl -Method OPTIONS -Verbose
   ```

2. **Check auth token**
   ```powershell
   # Token should be valid Sanctum token
   $token = $env:CV_CAPTURE_AUTH_TOKEN
   
   # Verify format (usually long alphanumeric string)
   if ($token.Length -lt 40) {
       Write-Host "Token looks invalid (too short)"
   }
   ```

3. **Check network connectivity**
   ```powershell
   # Ping API server
   Test-NetConnection -ComputerName "ats-tool.test" -Port 80
   
   # Check DNS resolution
   Resolve-DnsName "ats-tool.test"
   ```

4. **Review error logs**
   ```powershell
   # Check for specific error messages
   Select-String "error|failed|exception" "monitor_data\alerts.log" -i
   ```

---

### Issue 4: Duplicate Uploads

**Symptoms**:
- Same file uploaded multiple times
- Duplicate entries in database

**Diagnosis**:
```powershell
# Check processed files cache
# (This is in-memory, so check logs for hash tracking)

Select-String "Successfully uploaded" "monitor_data\alerts.log" | 
    ForEach-Object { Write-Host $_ }
```

**Solutions**:

1. **Verify hash tracking**
   - Monitor should track SHA256 hash of each file
   - Same hash should not be re-uploaded
   - Check logs for: `file_hash` entries

2. **Clear processed files cache** (if needed)
   - Restart the app
   - Cache is in-memory only

3. **Check database for duplicates**
   ```sql
   -- Find duplicate uploads
   SELECT file_hash, COUNT(*) as count
   FROM cv_capture_metadata
   GROUP BY file_hash
   HAVING count > 1;
   ```

---

### Issue 5: High CPU/Memory Usage

**Symptoms**:
- App running slow
- High CPU usage during scan
- Memory usage increasing

**Diagnosis**:
```powershell
# Monitor resource usage
$process = Get-Process -Name "wfh-agent-desktop" -ErrorAction SilentlyContinue

if ($process) {
    Write-Host "CPU: $($process.CPU)%"
    Write-Host "Memory: $($process.WorkingSet / 1MB)MB"
}
```

**Solutions**:

1. **Increase scan interval**
   ```json
   {
     "download_monitor": {
       "check_interval_sec": 60
     }
   }
   ```

2. **Reduce download paths**
   - Monitor only essential folders
   - Exclude network drives

3. **Limit file size**
   ```json
   {
     "download_monitor": {
       "max_file_size_mb": 50
     }
   }
   ```

4. **Restart app**
   ```powershell
   Stop-Process -Name "wfh-agent-desktop" -Force
   Start-Sleep -Seconds 2
   # Relaunch app
   ```

---

### Issue 6: API Rate Limiting

**Symptoms**:
- "429 Too Many Requests" errors
- Upload failures during bulk operations

**Solutions**:

1. **Increase scan interval**
   ```json
   {
     "download_monitor": {
       "check_interval_sec": 60
     }
   }
   ```

2. **Implement backoff strategy**
   - Monitor already retries on failure
   - Check logs for retry attempts

3. **Contact API admin**
   - Request higher rate limit
   - Provide emp_id and use case

---

### Issue 7: S3 Upload Failures

**Symptoms**:
- Presign succeeds but S3 upload fails
- "403 Forbidden" or "400 Bad Request" errors

**Diagnosis**:
```powershell
# Test S3 presigned URL
$presignedUrl = "https://s3-bucket.s3.amazonaws.com/..."

# Create test file
$testFile = "C:\temp\test.pdf"
"test content" | Out-File $testFile

# Try upload
try {
    $response = Invoke-WebRequest -Uri $presignedUrl `
        -Method PUT `
        -InFile $testFile `
        -ContentType "application/octet-stream" `
        -ErrorAction Stop
    
    Write-Host "S3 upload successful: $($response.StatusCode)"
} catch {
    Write-Host "S3 upload failed: $($_.Exception.Message)"
}
```

**Solutions**:

1. **Verify S3 bucket permissions**
   - Check IAM role has `s3:PutObject` permission
   - Verify bucket policy allows uploads

2. **Check presigned URL expiration**
   - URL should be valid for 15 minutes
   - If expired, request new presigned URL

3. **Verify Content-Type header**
   - Should be `application/octet-stream`
   - Check presign response includes correct headers

---

## Rollback Procedures

### Immediate Rollback (Emergency)

**If critical issues occur:**

1. **Disable download monitor immediately**
   ```json
   {
     "download_monitor": {
       "enabled": false
     }
   }
   ```

2. **Restart app**
   ```powershell
   Stop-Process -Name "wfh-agent-desktop" -Force
   Start-Sleep -Seconds 2
   # Relaunch app
   ```

3. **Verify disabled**
   ```powershell
   # Check logs for: "Download monitor disabled"
   Select-String "Download monitor" "monitor_data\alerts.log" -Tail 5
   ```

### Rollback to Previous Version

**If code changes caused issues:**

1. **Revert to v0.1.18**
   ```powershell
   # Download previous version
   # Replace executable and DLLs
   # Restart app
   ```

2. **Remove download monitor files**
   ```powershell
   Remove-Item "backend\download_monitor.py"
   Remove-Item "backend\test_download_monitor.py"
   ```

3. **Revert config**
   ```json
   {
     "download_monitor": {
       "enabled": false
     }
   }
   ```

### Database Cleanup (if needed)

**If corrupted data:**

```sql
-- Backup first
BACKUP TABLE cv_capture_metadata TO 'backup_location';

-- Delete failed uploads
DELETE FROM cv_capture_metadata 
WHERE status = 'failed' 
AND uploaded_at < DATE_SUB(NOW(), INTERVAL 24 HOUR);

-- Reset metadata for re-upload
UPDATE cv_capture_metadata 
SET status = 'pending' 
WHERE status = 'failed';
```

---

## Performance Tuning

### Optimize for Large Download Folders

```json
{
  "download_monitor": {
    "check_interval_sec": 60,
    "max_file_size_mb": 100,
    "allowed_extensions": ["pdf", "docx", "txt"],
    "monitor_naukri_only": true
  }
}
```

### Optimize for Slow Network

```json
{
  "download_monitor": {
    "check_interval_sec": 120,
    "max_file_size_mb": 50
  }
}
```

### Optimize for High-Volume Uploads

```json
{
  "download_monitor": {
    "check_interval_sec": 30,
    "max_file_size_mb": 100
  }
}
```

---

## Logging & Debugging

### Enable Verbose Logging

```powershell
# Set environment variable for debug mode
$env:WFH_DEBUG = "1"

# Restart app
Stop-Process -Name "wfh-agent-desktop" -Force
Start-Sleep -Seconds 2
# Relaunch app
```

### Analyze Logs

```powershell
# Find all download monitor entries
Select-String "\[DownloadMonitor\]" "monitor_data\alerts.log"

# Find errors
Select-String "error|failed|exception" "monitor_data\alerts.log" -i

# Find successful uploads
Select-String "Successfully uploaded" "monitor_data\alerts.log"

# Count uploads by day
Select-String "Successfully uploaded" "monitor_data\alerts.log" | 
    Group-Object { $_.Line.Substring(0, 10) } | 
    Select-Object Name, Count
```

### Export Logs for Analysis

```powershell
# Export last 1000 lines
Get-Content "monitor_data\alerts.log" -Tail 1000 | 
    Out-File "download_monitor_logs_$(Get-Date -Format 'yyyyMMdd_HHmmss').txt"
```

---

## Support & Escalation

### When to Contact Support

- **API errors**: Contact backend team
- **S3 failures**: Contact DevOps/AWS team
- **Database issues**: Contact DBA
- **User issues**: Contact HR/Recruitment team

### Information to Provide

1. **Employee ID and designation**
2. **File name and size**
3. **Timestamp of failure**
4. **Error message from logs**
5. **Config settings (sanitized)**
6. **Network connectivity status**

### Support Contact Template

```
Subject: Download Monitor Issue - [EMP_ID]

Employee ID: 123
Designation: Manager - Talent Acquisition
File: Naukri_John_Doe.pdf
Size: 245KB
Timestamp: 2025-11-06 16:30:00
Error: [Copy from alerts.log]

Steps taken:
- Verified config is enabled
- Checked auth token
- Verified file naming
- Tested API connectivity

Logs attached: [alerts.log excerpt]
```

---

## Monitoring Checklist

- [ ] Monitor upload success rate (target: >95%)
- [ ] Monitor API response times (target: <5s)
- [ ] Monitor S3 upload failures (target: <1%)
- [ ] Monitor app CPU usage (target: <5%)
- [ ] Monitor app memory usage (target: <50MB)
- [ ] Check logs daily for errors
- [ ] Verify auth tokens are refreshing
- [ ] Track file upload volume trends
