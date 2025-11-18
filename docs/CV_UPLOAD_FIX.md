# CV Upload Issue - Root Cause & Fix

## Problem
- Notification "CV Upload xxxxx" appeared but file was NOT in S3 browser
- No entries in Laravel `cv-capture-*.log` or `laravel.log`
- Upload was failing silently

## Root Cause
The download monitor was sending **incomplete data** to the ATS API endpoints:

### Presign Endpoint Issue
**Expected by `/api/cv-capture/presign`:**
```json
{
  "file_name": "Naukri_Resume.pdf",
  "file_size": 245000,
  "file_type": "application/pdf",        // ← MISSING
  "sha256": "abc123...",                 // ← MISSING
  "source": "download"                   // ← MISSING
}
```

**What was being sent:**
```json
{
  "file_name": "Naukri_Resume.pdf",
  "file_size": 245000
}
```

### Metadata Endpoint Issue
**Expected by `/api/cv-capture/metadata`:**
```json
{
  "s3_key": "resumes/production/ats/3/2025/11/abc123_naukri-resume.pdf",
  "file_name": "Naukri_Resume.pdf",
  "file_size": 245000,
  "file_type": "application/pdf",        // ← MISSING
  "sha256": "abc123...",                 // ← MISSING
  "source": "download"                   // ← MISSING
}
```

**What was being sent:**
```json
{
  "file_name": "Naukri_Resume.pdf",
  "file_size": 245000,
  "file_hash": "abc123...",              // ← Wrong field name
  "download_path": "C:\\Users\\...",
  "uploaded_at": "2025-11-06T...",
  "emp_id": 123
}
```

## Laravel Validation Failures
The presign endpoint validation failed silently because:
1. Missing `file_type` → validation error
2. Missing `sha256` → validation error  
3. Missing `source` → validation error

The metadata endpoint validation failed because:
1. Missing `s3_key` → validation error
2. Wrong field name `file_hash` instead of `sha256` → validation error
3. Missing `source` → validation error

## Solution Applied

### Fixed Files
1. **`download_monitor.py`** - Updated `_upload_file()` method
2. **`download_monitor_v2.py`** - Updated `_upload_file()` method

### Changes Made

#### Step 1: Presign Request (Correct)
```python
presign_payload = {
    "file_name": file_name,
    "file_size": file_size,
    "file_type": file_type,           # ✓ Added
    "sha256": file_hash,              # ✓ Added
    "source": "download"              # ✓ Added
}
```

#### Step 2: S3 Upload (Correct)
```python
s3_resp = requests.put(
    s3_url,
    data=f,
    headers={"Content-Type": file_type},  # ✓ Use actual MIME type
    timeout=60
)
```

#### Step 3: Metadata Storage (Correct)
```python
metadata = {
    "s3_key": s3_key,                 # ✓ From presign response
    "file_name": file_name,
    "file_size": file_size,
    "file_type": file_type,           # ✓ Added
    "sha256": file_hash,              # ✓ Renamed from file_hash
    "source": "download"              # ✓ Added
}
```

## Expected Behavior After Fix

### Successful Upload Flow
```
1. Request presign with complete payload
   ✓ Presign endpoint validates and returns S3 URL + key
   
2. Upload file to S3 with correct Content-Type
   ✓ S3 accepts file
   
3. Store metadata with all required fields
   ✓ Laravel creates CVCapture record
   ✓ File appears in S3 browser
   ✓ Entry logged in cv-capture-*.log
   ✓ Notification toast shown
```

### Log Output
```
[2025-11-10T...] Requesting presign for Naukri_Resume.pdf...
[2025-11-10T...] Uploading to S3...
[2025-11-10T...] S3 upload successful
[2025-11-10T...] Storing metadata...
[2025-11-10T...] Successfully uploaded: Naukri_Resume.pdf (245.0KB)
```

### Laravel Log Entry
```
[2025-11-10 17:30:00] local.INFO: CV uploaded {"user_id":3,"cv_capture_id":4,"file_name":"Naukri_Resume.pdf","source":"download","ip_address":"127.0.0.1"}
```

## Verification Steps

1. **Restart backend:**
   ```
   py -3 D:\tracking\v5\desktop\backend\emp_monitor.py --serve --port 5050
   ```

2. **Create test file:**
   ```
   C:\Users\techs\Downloads\Naukri_TestResume.pdf
   ```

3. **Check logs:**
   - `d:\tracking\v5\desktop\monitor_data\alerts.log` → Should show upload success
   - `d:\ATS\ats-tool\storage\logs\cv-capture-*.log` → Should show CV uploaded entry
   - S3 browser → File should appear in `resumes/production/ats/3/2025/11/` folder

4. **Verify notification:**
   - Toast notification should appear: "CV Uploaded - Naukri_TestResume.pdf"

## Files Modified
- `d:\tracking\v5\desktop\backend\download_monitor.py` (lines 172-327)
- `d:\tracking\v5\desktop\backend\download_monitor_v2.py` (lines 202-302)
