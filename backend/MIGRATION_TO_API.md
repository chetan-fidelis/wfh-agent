# Migration Guide: PostgreSQL to API-Based Sync

## Overview

This guide explains the changes from direct PostgreSQL connection to secure API-based data ingestion.

---

## What Changed

### Before (v0.1.6 and earlier)
```
Employee Machine → PostgreSQL Database (Direct Connection)
❌ Database credentials on every machine
❌ Security risk
❌ Network exposure
```

### After (v0.1.7+)
```
Employee Machine → Ingestion API Server → PostgreSQL Database
✅ No database credentials on machines
✅ API key authentication
✅ Centralized security
```

---

## New Architecture

```
┌─────────────────────┐
│  Employee Machine   │
│  (WFH Agent)        │
│  ─────────────────  │
│  • Local SQLite     │
│  • API Key          │
│  • api_sync.py      │
└──────────┬──────────┘
           │ HTTPS + API Key
           ▼
┌─────────────────────┐
│  Ingestion Server   │
│  (Ubuntu/Cloud)     │
│  ─────────────────  │
│  • Flask API        │
│  • Authentication   │
│  • PostgreSQL       │
└─────────────────────┘
```

---

## Files Changed

### New Files Created

1. **`api_sync.py`** - API-based synchronization module
   - Replaces direct PostgreSQL sync
   - Uses REST API endpoints
   - Handles authentication

2. **`ingestion-server/`** - Server deployment
   - `ingestion_server.py` - Flask API server
   - `requirements.txt` - Dependencies
   - `deploy.sh` - Auto-deployment script
   - `README.md` - Full documentation
   - `QUICKSTART.md` - Quick setup guide

### Modified Files

1. **`config.json`** - Updated ingestion configuration
   ```json
   {
     "ingestion": {
       "enabled": true,
       "mode": "api",  // Changed from "postgres"
       "api": {
         "base_url": "https://ingest.your-domain.com",
         "auth_header": "X-Api-Key",
         "auth_env": "WFH_AGENT_API_KEY"
       }
     }
   }
   ```

2. **`emp_monitor.py`** - Needs integration with `api_sync.py`
   - Import API sync module
   - Replace `sync_to_postgres()` calls with API sync
   - Update periodic sync logic

---

## Integration Steps

### Step 1: Import API Sync Module

In `emp_monitor.py`, add at the top (around line 60):

```python
# Import API sync module
try:
    from api_sync import APISync
    API_SYNC_AVAILABLE = True
except ImportError:
    API_SYNC_AVAILABLE = False
```

### Step 2: Initialize API Sync

In `LocalStorage.__init__()` method (around line 436):

```python
# Initialize API sync if enabled
self.api_sync = None
if API_SYNC_AVAILABLE and self.app_ref:
    ing_cfg = self.app_ref.cfg.data.get('ingestion', {})
    if ing_cfg.get('mode') == 'api':
        try:
            self.api_sync = APISync(self.db_path, self.app_ref.cfg.data, self.app_ref)
            self.log("API sync initialized")
        except Exception as e:
            self.log(f"Failed to initialize API sync: {e}")
```

### Step 3: Update Sync Method

Replace `sync_to_postgres()` method (around line 738) with:

```python
def sync_to_postgres(self, tables_to_sync=None):
    """Sync data using configured method (API or direct PostgreSQL)"""

    # Check if we should use API sync
    if self.api_sync:
        return self._sync_via_api()

    # Otherwise use existing direct PostgreSQL sync
    return self._sync_direct_postgres(tables_to_sync)

def _sync_via_api(self):
    """Sync data via API server"""
    if not self.sync_lock.acquire(blocking=False):
        self.log("Sync already in progress, skipping")
        return

    try:
        emp_id = self.app_ref.cfg.data.get('emp_id', 0)
        if emp_id == 0:
            self.log("No employee ID configured, skipping sync")
            return

        # Get sessions file path
        sessions_file = os.path.join(self.data_dir, '..', 'monitor_data', 'work_sessions.json')

        # Sync all data
        results = self.api_sync.sync_all(emp_id, sessions_file)

        for data_type, count in results.items():
            if count > 0:
                self.log(f"API sync: {count} {data_type} records")

    except Exception as e:
        self.log(f"API sync error: {e}")
    finally:
        self.sync_lock.release()

def _sync_direct_postgres(self, tables_to_sync=None):
    """Original direct PostgreSQL sync method"""
    # ... existing sync_to_postgres code ...
```

### Step 4: Update Screenshot Upload

Add screenshot upload support (in emp_monitor.py around screenshot capture code):

```python
# After screenshot is saved
if self.app_ref and hasattr(self.app_ref, 'local_storage'):
    storage = self.app_ref.local_storage
    if storage.api_sync:
        emp_id = self.app_ref.cfg.data.get('emp_id', 0)
        timestamp = dt.datetime.now().isoformat()
        storage.api_sync.upload_screenshot(emp_id, screenshot_path, timestamp)
```

---

## Configuration Update

### Old Config (Direct PostgreSQL)
```json
{
  "ingestion": {
    "mode": "postgres",
    "db": {
      "url": "postgresql://user:pass@host:5432/db",
      "schema": "employee_monitor"
    }
  }
}
```

### New Config (API-Based)
```json
{
  "ingestion": {
    "mode": "api",
    "api": {
      "base_url": "https://ingest.your-domain.com",
      "auth_header": "X-Api-Key",
      "auth_env": "WFH_AGENT_API_KEY"
    },
    "db": {
      "schema": "employee_monitor",
      "url": "",
      "url_env": ""
    }
  }
}
```

---

## Environment Variables

### Employee Machines

Set the API key on each employee machine:

**Windows:**
```cmd
setx WFH_AGENT_API_KEY "your-api-key-from-server"
```

**Or via System Properties:**
1. Search "Environment Variables"
2. System Variables → New
3. Variable name: `WFH_AGENT_API_KEY`
4. Variable value: (paste API key)
5. Restart WFH Agent

---

## Testing

### 1. Test API Connection
```python
python -c "
from api_sync import APISync
import os

config = {
    'ingestion': {
        'api': {
            'base_url': 'https://ingest.your-domain.com',
            'auth_header': 'X-Api-Key',
            'auth_env': 'WFH_AGENT_API_KEY'
        },
        'batch_size': 200
    }
}

sync = APISync('/path/to/local_data.db', config)
print('API Sync initialized successfully!')
"
```

### 2. Check Server Health
```bash
curl https://ingest.your-domain.com/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "wfh-agent-ingestion",
  "database": "connected"
}
```

### 3. Test Data Sync

Start WFH Agent and check logs for:
```
[LocalStorage] API sync initialized
[LocalStorage] API sync: 10 heartbeat records
[LocalStorage] API sync: 5 website_usage records
```

---

## Rollback Plan

If you need to rollback to direct PostgreSQL:

1. **Update config.json**:
   ```json
   {
     "ingestion": {
       "mode": "postgres"
     }
   }
   ```

2. **Restore database credentials**:
   ```json
   {
     "ingestion": {
       "db": {
         "url": "postgresql://user:pass@host:5432/db"
       }
     }
   }
   ```

3. **Restart WFH Agent**

The app will automatically use direct PostgreSQL sync.

---

## Benefits of API-Based Sync

✅ **Security**
- No database credentials on employee machines
- API key can be easily rotated
- Centralized access control

✅ **Scalability**
- Single ingestion point
- Easy to add rate limiting
- Better monitoring

✅ **Flexibility**
- Easy to switch databases
- Can add data transformations
- Simplified client updates

✅ **Maintenance**
- One place to update logic
- Easier debugging
- Better error handling

---

## Troubleshooting

### API Sync Not Working

1. **Check API key**:
   ```cmd
   echo %WFH_AGENT_API_KEY%
   ```

2. **Check server connectivity**:
   ```cmd
   curl https://ingest.your-domain.com/health
   ```

3. **Check logs**:
   Look for `[APISync]` messages in WFH Agent logs

### No Data in Database

1. **Check ingestion server logs**:
   ```bash
   sudo journalctl -u wfh-ingestion -f
   ```

2. **Verify API key matches** between client and server

3. **Check PostgreSQL connection** on server

---

## Support

For issues or questions:
- Email: support@fidelisgroup.in
- Check server logs: `sudo journalctl -u wfh-ingestion -f`
- Check client config: `monitor_data/config.json`
