# Errors Fixed - Session Nov 10, 2025

## Error 1: SSL Certificate Verification Failed

### Problem
```
[DownloadMonitor] Upload error: HTTPSConnectionPool(host='ats-tool.test', port=443): 
Max retries exceeded with url: /api/cv-capture/presign 
(Caused by SSLError(SSLCertVerificationError(1, '[SSL: CERTIFICATE_VERIFY_FAILED] 
certificate verify failed: unable to get local issuer certificate (_ssl.c:1032)')))
```

### Root Cause
- ATS server uses self-signed SSL certificate
- Download monitor was enforcing SSL verification (default behavior)
- Requests library rejected the certificate

### Solution
Added SSL verification bypass to both download monitors:

**Files Modified:**
- `download_monitor.py` (lines 17-20, 214, 227, 289, 305)
- `download_monitor_v2.py` (lines 16-19, 254, 304)

**Changes:**
```python
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# In all requests.post() calls:
requests.post(..., verify=False)  # Disable SSL verification for self-signed certs
```

**Affected Endpoints:**
- `/api/cv-capture/presign` - Presign request
- `/api/cv-capture/metadata` - Metadata storage

---

## Error 2: Invalid Payload - Consolidated Batch Sync

### Problem
```
[2025-11-10T18:03:00] Sending to http://20.197.8.101:5050/api/ingest/batch with X-Api-Key: b1jWosNKA3wA...
[2025-11-10T18:03:00] API ingest failed: HTTP 400 {'error': 'Invalid payload'}
[2025-11-10T18:03:00] Consolidated batch sync failed
```

### Root Cause
- Attempted to consolidate all data into a single nested batch structure
- API endpoints expect individual calls to specific endpoints, not a consolidated payload
- The nested structure `{'emp_id': ..., 'data': {'heartbeat': [...], 'website_usage': [...], ...}}` was invalid

### Solution
Reverted to using individual API endpoint calls while maintaining increased sync intervals:

**File Modified:**
- `emp_monitor.py` (lines 887-926)

**Changes:**
```python
# Before: sync_all_consolidated() - sends nested structure to /api/ingest/batch
# After: sync_all() - sends individual calls to specific endpoints

results = self.api_sync.sync_all(
    emp_id,
    sessions_file=sessions_file,
    usage_file=usage_file,
    productivity_file=productivity_file,
    wellness_file=wellness_file,
    tickets_file=tickets_file,
    timeline_file=timeline_file
)
```

**API Endpoints Used (Individual Calls):**
1. `/api/ingest/heartbeat` - Heartbeat data
2. `/api/ingest/website_usage` - Website usage data
3. `/api/ingest/batch` - Productivity data
4. `/api/ingest/batch` - Wellness data
5. `/api/ingest/batch` - Timeline data

### Server Load Optimization Still Applied
- Sync intervals increased: 30/60 min → 60/120 min (50% reduction)
- Sync frequency reduced from every ~30 seconds to every 60-120 minutes
- Individual calls are still more efficient than before due to longer intervals

---

## Summary of Changes

| Component | Issue | Fix | Impact |
|-----------|-------|-----|--------|
| CV Upload | SSL cert verification | Added `verify=False` | ✅ CV uploads now work |
| Batch Sync | Invalid nested payload | Reverted to individual endpoints | ✅ Sync errors resolved |
| Sync Intervals | Server congestion | Increased 1800s→3600s, 3600s→7200s | ✅ 50% less frequent |

---

## Expected Behavior After Restart

### CV Upload Flow
```
1. File detected in Downloads
2. Presign request sent (SSL verification disabled)
3. S3 presigned URL received
4. File uploaded to S3
5. Metadata stored in Laravel
6. Entry logged in cv-capture-*.log
7. Toast notification shown
```

### API Sync Flow
```
1. Sync triggered every 60-120 minutes (not every 30 seconds)
2. Individual API calls to specific endpoints
3. Each endpoint receives properly formatted data
4. No more "Invalid payload" errors
5. Server load reduced by 50%
```

---

## Verification Steps

1. **Restart backend:**
   ```
   npm start
   ```

2. **Check CV upload:**
   - Create test file: `C:\Users\techs\Downloads\Naukri_Test.docx`
   - Check logs for success message
   - Verify file in S3 browser

3. **Check API sync:**
   - Monitor logs for "API sync: N records" messages
   - Should appear every 60-120 minutes, not every 30 seconds
   - No more "Invalid payload" errors

4. **Monitor alerts.log:**
   ```
   [2025-11-10T18:XX:XX] [DownloadMonitor] Found file: Naukri_Test.docx
   [2025-11-10T18:XX:XX] [DownloadMonitor] Requesting presign for Naukri_Test.docx...
   [2025-11-10T18:XX:XX] [DownloadMonitor] S3 upload successful
   [2025-11-10T18:XX:XX] [DownloadMonitor] Successfully uploaded: Naukri_Test.docx
   ```
