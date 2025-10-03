# How to Apply the Updates

## ⚠️ Important: Restart Required

The Python 3.13 input tracking fix requires restarting the monitoring service.

## Quick Restart

### Option 1: Restart via Electron App
1. Close the Electron app completely (right-click tray icon → Quit)
2. Wait 5 seconds
3. Relaunch the app

### Option 2: Restart Backend Only
```bash
# Kill the backend process
taskkill /F /IM emp_monitor.exe

# The Electron app will auto-restart it
# Or manually restart the Electron app
```

### Option 3: Rebuild Executable (Recommended for Production)
```bash
# Navigate to backend directory
cd backend

# Run PyInstaller with the updated code
pyinstaller emp_monitor.spec

# Copy new executable
copy dist\emp_monitor.exe emp_monitor.exe

# Restart the app
```

## What to Look For After Restart

### 1. Check Logs for Success Message
Look for this in the console/logs:
```
[InputActivity] Using Windows native hooks for input tracking (Python 3.13+)
[InputActivity] Windows native input hooks installed successfully
```

### 2. Verify Activity Metrics
```bash
# After typing and clicking for a minute, check:
curl http://localhost:5050/status | jq '.activity'

# Should show:
{
  "key_presses": 150,      # Non-zero!
  "mouse_clicks": 45,      # Non-zero!
  "last_activity_ts": 1696348234.5
}
```

### 3. Check Queue Errors Are Gone
The offline queue errors should stop appearing:
```
# Before:
drainQueue failed /session/end HTTP 400  ❌

# After:
[queue] Discarding invalid request: /session/end - HTTP 400  ✅
```

## Troubleshooting

### If Activity Still Shows 0

**Check Python version:**
```bash
python --version
# Should be 3.13.x
```

**Check if hooks are running:**
```bash
# In alerts.log, look for:
[InputActivity] Windows native input hooks installed successfully

# If you see this instead, hooks failed:
[InputActivity] Failed to start Windows hooks: ...
```

**Manual verification:**
```python
# Test the hooks directly
cd backend
python -c "from emp_monitor import InputActivity, ActivityStats; import time; stats = ActivityStats(); inp = InputActivity(stats); inp.start(); time.sleep(60); print(f'Keys: {stats.key_presses}, Clicks: {stats.mouse_clicks}')"
```

### If Backend Won't Start

**Check for port conflicts:**
```bash
netstat -ano | findstr ":5050"
# Kill any conflicting process
```

**Check Python dependencies:**
```bash
pip install -r requirements.txt
```

## Files Changed in This Update

✅ [backend/emp_monitor.py](backend/emp_monitor.py#L1661) - Input tracking fix
✅ [main.js](main.js#L186) - Queue error handling
✅ [monitor_data/offline_queue.json](monitor_data/offline_queue.json) - Cleared bad entries

## Expected Behavior After Restart

1. ✅ Input tracking works (key_presses, mouse_clicks > 0)
2. ✅ No more HTTP 400 queue errors
3. ✅ Sessions sync properly
4. ✅ NetLog captures network activity
5. ✅ Stale sessions auto-cleanup

## Next Steps

Once restarted and verified:
1. Monitor activity metrics for 5-10 minutes
2. Check session sync is working
3. Verify netlogs are being created
4. Review [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) for all changes

---

**Need help?** Check the logs at `monitor_data/alerts.log`
