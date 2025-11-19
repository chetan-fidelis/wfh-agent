# Download Monitor v2 - Setup & Test Guide

## What Changed
- **Simplified v2 implementation** with explicit logging at every step.
- **No complex auth logic** - reads `api_key` or `auth_token` from config directly.
- **Bulletproof file detection** - logs every file found, checked, and uploaded.
- **All logs go to `monitor_data/alerts.log`** for easy debugging.

## Step 1: Configure

Edit `monitor_data/config.json`:

```json
{
  "emp_id": 18698,
  "designation": "Talent Acquisition",
  "download_monitor": {
    "enabled": true,
    "api_url": "https://nexoleats.fidelisam.in/api",
    "api_key": "YOUR_ATS_API_KEY_HERE",
    "check_interval_sec": 10,
    "max_file_size_mb": 100
  }
}
```

**Key points:**
- `enabled: true` - must be set
- `designation` - must be set (any value is OK for testing; for tray history to show, use a TA role like "Talent Acquisition")
- `api_key` - your ATS API key (or use `auth_token` for Bearer token)
- `check_interval_sec: 10` - scan every 10 seconds (faster for testing)

## Step 2: Restart App

```powershell
Stop-Process -Name "wfh-agent-desktop" -Force
# Then relaunch via npm start or your usual shortcut
```

## Step 3: Test File

Download a test file to `C:\Users\<you>\Downloads\`:

```
Naukri_Test_CV.pdf
```

Or any file matching:
- Starts with `Naukri_`
- Extension: `.pdf`, `.docx`, or `.txt`
- Size: < 100MB

## Step 4: Watch Logs

In PowerShell, tail the logs in real-time:

```powershell
Get-Content "monitor_data\alerts.log" -Wait | Select-String "\[DownloadMonitor\]"
```

**Expected output (within 10 seconds):**

```
[2025-11-06T17:00:00.000000] [DownloadMonitor] Init: enabled=True, api_url=https://nexoleats.fidelisam.in/api, paths=5
[2025-11-06T17:00:01.000000] [DownloadMonitor] Monitor loop started. Scanning 5 paths every 10s
[2025-11-06T17:00:11.000000] [DownloadMonitor] Found file: Naukri_Test_CV.pdf (0.5MB)
[2025-11-06T17:00:11.000000] [DownloadMonitor] Requesting presign for Naukri_Test_CV.pdf...
[2025-11-06T17:00:11.000000] [DownloadMonitor] Presign response: 200
[2025-11-06T17:00:11.000000] [DownloadMonitor] Uploading to S3...
[2025-11-06T17:00:12.000000] [DownloadMonitor] S3 upload response: 200
[2025-11-06T17:00:12.000000] [DownloadMonitor] Storing metadata...
[2025-11-06T17:00:12.000000] [DownloadMonitor] Metadata response: 200
[2025-11-06T17:00:12.000000] [DownloadMonitor] SUCCESS: Naukri_Test_CV.pdf
[2025-11-06T17:00:12.000000] [DownloadMonitor] History write error: ...
[2025-11-06T17:00:12.000000] Notify: CV Upload - Successfully uploaded Naukri_Test_CV.pdf
```

## Step 5: Verify Success

- **Toast notification**: A Windows toast should pop up saying "CV Upload - Successfully uploaded Naukri_Test_CV.pdf"
- **Tray history**: Right-click tray icon. If your `designation` is a TA role, you should see "Recent CV Uploads" with your file listed.
- **Upload history file**: Check `monitor_data\cv_uploads.json` - should have an entry.

## Troubleshooting

### Monitor not starting

```powershell
Get-Content "monitor_data\alerts.log" -Tail 50 | Select-String "\[DownloadMonitor\]"
```

Look for:
- `[DownloadMonitor] Init: enabled=True` - if not, check config `enabled: true`
- `[DownloadMonitor] Monitor loop started` - if not, check for errors above

### File not detected

```powershell
Get-Content "monitor_data\alerts.log" -Tail 100 | Select-String "\[DownloadMonitor\]"
```

Check:
- File is in a monitored path (Downloads, Desktop, Chrome/Edge/Firefox Downloads)
- File name starts with `Naukri_`
- Extension is `.pdf`, `.docx`, or `.txt`
- File size < 100MB
- Wait 10+ seconds after download completes

### Presign fails (401/403)

```
[DownloadMonitor] Presign response: 401
[DownloadMonitor] Presign failed: ...
```

**Fix:**
- Verify ATS API key is correct in config
- Test API key manually:
  ```powershell
  $api = "https://nexoleats.fidelisam.in/api/cv-capture/presign"
  $body = '{"file_name":"Naukri_Test.pdf","file_size":1000}'
  Invoke-WebRequest -Uri $api -Method POST `
    -Headers @{ "X-Api-Key"="YOUR_KEY"; "Accept"="application/json"; "Content-Type"="application/json" } `
    -Body $body
  ```
  Expect HTTP 200 with presigned URL.

### S3 upload fails

```
[DownloadMonitor] S3 upload response: 403
```

**Fix:**
- Verify presigned URL is valid and not expired
- Check S3 bucket permissions
- Verify Content-Type header is `application/octet-stream`

### Metadata store fails

```
[DownloadMonitor] Metadata response: 401
```

**Fix:**
- Same as presign - verify API key and ATS endpoint

### No toast notification

```powershell
Get-Content "monitor_data\alerts.log" -Tail 50 | Select-String "Notify:"
```

If you see `Notify:` lines but no toast:
- Ensure Electron is running (`npm start`)
- Windows notifications enabled for this app
- Check console for "Electron Notification failed"

### Tray history not showing

- Ensure `designation` in config is a TA role (e.g., "Talent Acquisition", "Manager - Talent Acquisition")
- Ensure at least one file has been successfully uploaded (check `cv_uploads.json`)
- Right-click tray icon and look for "Recent CV Uploads" section

## Full Test Scenario

```powershell
# 1. Set config
$cfg = Get-Content "monitor_data\config.json" | ConvertFrom-Json
$cfg.download_monitor.enabled = $true
$cfg.download_monitor.api_key = "YOUR_ATS_API_KEY"
$cfg.designation = "Talent Acquisition"
$cfg | ConvertTo-Json | Set-Content "monitor_data\config.json"

# 2. Restart app
Stop-Process -Name "wfh-agent-desktop" -Force
# Relaunch app

# 3. Wait 5 seconds for startup
Start-Sleep -Seconds 5

# 4. Create test file (or download one)
$testFile = "$env:USERPROFILE\Downloads\Naukri_Test_CV.pdf"
"test content" | Out-File $testFile

# 5. Watch logs
Get-Content "monitor_data\alerts.log" -Wait | Select-String "\[DownloadMonitor\]"

# 6. After success, check history
Get-Content "monitor_data\cv_uploads.json"

# 7. Check tray (right-click icon)
```

## API Key Setup (ATS Laravel)

If you haven't set up the ATS API key middleware yet:

```php
// app/Http/Middleware/ValidateApiKey.php
namespace App\Http\Middleware;
use Closure;
use Illuminate\Http\Request;

class ValidateApiKey
{
    public function handle(Request $request, Closure $next)
    {
        $key = $request->header('X-Api-Key');
        $valid = $key && hash_equals($key, config('cv_capture.api_key'));
        
        if (!$valid) {
            return response()->json(['message' => 'Unauthorized'], 401);
        }
        return $next($request);
    }
}

// app/Http/Kernel.php
protected $routeMiddleware = [
    'ats.api_key' => \App\Http\Middleware\ValidateApiKey::class,
];

// routes/api.php
Route::middleware('ats.api_key')->group(function () {
    Route::post('/cv-capture/presign', [CvCaptureController::class, 'presign']);
    Route::post('/cv-capture/metadata', [CvCaptureController::class, 'storeMetadata']);
});

// config/cv_capture.php
return [
    'api_key' => env('CV_CAPTURE_API_KEY'),
];

// .env
CV_CAPTURE_API_KEY=YOUR_ATS_API_KEY
```

## Summary

- **v2 is simpler**: no complex auth logic, just reads config.
- **All logs are explicit**: every step is logged to `alerts.log`.
- **Fast debugging**: tail logs and see exactly what's happening.
- **Bulletproof**: no silent failures, all errors logged.

If you follow these steps and still have issues, share the last 200 lines of `alerts.log` and I'll fix it immediately.
