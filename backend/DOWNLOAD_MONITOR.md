# Download Monitor - Naukri File Tracking

## Overview

The Download Monitor is a lightweight feature that automatically detects and uploads Naukri CV files downloaded by recruitment-related employees to a Laravel API endpoint (`https://fhq.fidelisam.in/api`).

## Features

- **Lightweight**: Minimal CPU/memory footprint; runs in background thread
- **Targeted**: Only monitors employees with recruitment-related designations
- **Naukri-specific**: Monitors files matching pattern `Naukri_*.pdf`, `Naukri_*.docx`, `Naukri_*.txt`
- **Smart Upload**: Avoids re-uploading same files (SHA256 hash tracking)
- **Presigned URLs**: Uses S3 presigned URLs for secure uploads
- **Metadata Tracking**: Stores file metadata in Laravel database

## Configuration

Add to `monitor_data/config.json`:

```json
{
  "download_monitor": {
    "enabled": false,
    "api_url": "https://fhq.fidelisam.in/api",
    "target_designations": ["recruiter", "hr", "hiring_manager"],
    "check_interval_sec": 30,
    "max_file_size_mb": 100,
    "allowed_extensions": ["pdf", "docx", "txt"],
    "naukri_pattern": "Naukri_",
    "monitor_naukri_only": true
  }
}
```

### Configuration Fields

- **enabled** (bool): Enable/disable the download monitor
- **api_url** (str): Base URL of the Laravel CV Capture API
- **target_designations** (list): Employee designations to monitor (case-insensitive, whitespace-normalized)
- **check_interval_sec** (int): How often to scan download folders (default: 30s)
- **max_file_size_mb** (int): Maximum file size to upload (default: 100MB)
- **allowed_extensions** (list): File types to monitor (default: pdf, docx, txt)
- **naukri_pattern** (str): Filename prefix to match (default: "Naukri_")
- **monitor_naukri_only** (bool): Only upload files matching the pattern (default: true)

### Supported Talent Acquisition Designations

The monitor automatically activates for employees with these designations:

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

**Note**: Designation matching is case-insensitive and handles both regular hyphens (`-`) and em-dashes (`–`).

## Authentication

The monitor requires a Bearer token for API authentication. Provide it via:

1. **Environment variable** (recommended):
   ```powershell
   $env:CV_CAPTURE_AUTH_TOKEN = "your-bearer-token"
   ```

2. **Config file** (less secure):
   ```json
   {
     "download_monitor": {
       "auth_token": "your-bearer-token"
     }
   }
   ```

## Monitored Paths

The monitor scans these locations for downloads:

- `%USERPROFILE%\Downloads`
- `%USERPROFILE%\Desktop`
- Chrome default downloads folder
- Edge default downloads folder
- Firefox default downloads folder

## API Workflow

### 1. Request Presigned URL
```
POST /api/cv-capture/presign
Authorization: Bearer {token}
Content-Type: application/json

{
  "file_name": "Naukri_John_Doe.pdf",
  "file_size": 245000
}

Response:
{
  "url": "https://s3-bucket.s3.amazonaws.com/...",
  "id": "metadata-id-123"
}
```

### 2. Upload to S3
```
PUT {presigned_url}
Content-Type: application/octet-stream

[binary file data]
```

### 3. Store Metadata
```
POST /api/cv-capture/metadata
Authorization: Bearer {token}
Content-Type: application/json

{
  "file_name": "Naukri_John_Doe.pdf",
  "file_size": 245000,
  "file_hash": "sha256-hash",
  "download_path": "C:\\Users\\...",
  "uploaded_at": "2025-11-06T16:30:00",
  "emp_id": 123
}
```

## Logging

Monitor activity is logged to `monitor_data/alerts.log`:

```
[2025-11-06T16:30:00.123456] [DownloadMonitor] Monitoring 5 download paths
[2025-11-06T16:30:30.456789] [DownloadMonitor] Found new file: Naukri_John_Doe.pdf
[2025-11-06T16:30:31.789012] [DownloadMonitor] Successfully uploaded: Naukri_John_Doe.pdf (245.0KB)
```

## File Ready Detection

The monitor uses platform-specific checks to ensure files are fully written before upload:

- **Windows**: Attempts exclusive file lock; waits if file is still being written
- **Other**: Reads first byte to verify accessibility

## Duplicate Prevention

Files are tracked by SHA256 hash. If the same file (by hash) is detected again, it's skipped to avoid re-uploads.

## Performance Impact

- **CPU**: Negligible; runs every 30 seconds in background thread
- **Memory**: ~5-10MB for monitor instance
- **Network**: Only uploads on new file detection; presigned URLs expire after 15 minutes

## Troubleshooting

### Monitor not starting
- Check `enabled: true` in config
- Verify `CV_CAPTURE_AUTH_TOKEN` environment variable is set
- Check employee designation matches `target_designations`
- Review `monitor_data/alerts.log` for errors

### Files not being uploaded
- Ensure file matches `Naukri_*.{pdf,docx,txt}` pattern
- Check file size is under `max_file_size_mb`
- Verify API endpoint is reachable
- Check auth token is valid

### Upload failures
- Verify S3 bucket is accessible
- Check API presign endpoint returns valid URL
- Ensure network connectivity to `api_url`

## Example: Enable for Specific Employees

```json
{
  "emp_id": 123,
  "designation": "recruiter",
  "download_monitor": {
    "enabled": true,
    "api_url": "https://fhq.fidelisam.in/api",
    "target_designations": ["recruiter", "hr", "hiring_manager"],
    "check_interval_sec": 30
  }
}
```

Then set the auth token:
```powershell
$env:CV_CAPTURE_AUTH_TOKEN = "your-sanctum-token"
```

## Integration with Electron App

The download monitor is automatically started by the backend when:
1. Config has `download_monitor.enabled: true`
2. Employee designation is in `target_designations`
3. Auth token is available via env var or config

No UI changes required; monitoring happens silently in background.

## Security Notes

- **Auth tokens**: Store in environment variables, never in config files
- **File hashing**: SHA256 ensures file integrity
- **Presigned URLs**: Expire automatically; no long-lived credentials
- **Local tracking**: Processed file hashes stored locally only

## Future Enhancements

- [ ] Support for other job portals (LinkedIn, Indeed, etc.)
- [ ] Configurable file naming patterns
- [ ] Webhook notifications on upload
- [ ] Bulk upload retry logic
- [ ] File quarantine/scanning before upload
