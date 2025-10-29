# Data Collection Issues & Improvements - WFH Agent

## Executive Summary

Found **8 critical issues** in data collection:
1. 🔴 Screenshot "twice daily" not implemented correctly
2. 🔴 Screenshot upload failures (timeouts, no retry, no compression)
3. 🟡 Data sync issues (no offline queue, lock contention)
4. 🟡 No data validation before upload
5. 🟡 Missing screenshot metadata (context, thumbnails)
6. 🔴 Heartbeat data incomplete (network stats missing)
7. 🟡 Work session validation missing
8. 🟡 Website tracking issues (expensive, no sanitization)

---

## Critical Issues Details

### 1. Screenshot "Twice Daily" NOT Implemented Correctly

**Current Behavior**:
- Takes 2 screenshots at **random times** during work hours
- Could be 9:00 AM and 9:15 AM (both in morning)
- NOT guaranteed morning + afternoon distribution

**Code Location**: `emp_monitor.py` lines 1577-1594

**Problem**:
```python
# Picks 2 random times from entire work day
picks = sorted(random.sample(range(int(span_sec)), k=max(1, per_day)))
```

**Fix Needed**: Divide day into morning/afternoon windows

---

### 2. Screenshot Upload Failures

**Issue 2.1: Timeout (30s too short)**
- Line 1735: `timeout=30`
- Screenshots are 5-10 MB
- Slow networks will timeout
- **No retry mechanism**

**Issue 2.2: No Compression**
- Line 1616: Saves at quality=70 but full resolution
- No resizing before upload
- Wastes bandwidth

**Issue 2.3: Silent Failures**
- Lines 1761-1766: Errors only logged
- Failed uploads lost forever
- No user notification

**Issue 2.4: Three Upload Methods**
- API sync (line 1651)
- Direct Postgres (line 1663)
- Legacy HTTP (line 1702)
- Confusing fallback, can cause duplicates

---

### 3. Data Sync Issues

**Issue 3.1: No Persistent Offline Queue**
- If app crashes, unsent data lost
- No recovery mechanism

**Issue 3.2: Sync Lock Causes Skips**
- Line 846: `if not self.sync_lock.acquire(blocking=False): return`
- Long sync blocks new syncs
- Data accumulates

**Issue 3.3: No Sync Status**
- User can't see if data is syncing
- No progress indicator
- No error notifications

---

### 4. No Data Validation

**Missing Checks**:
- Valid employee ID
- Valid timestamps (not future, not too old)
- Data completeness
- Duplicate detection
- PII/sensitive data filtering

**Risk**: Invalid data breaks entire batch sync

---

### 5. Screenshot Metadata Missing

**Missing Context**:
- Active application name
- Window title
- Activity status (active/idle)
- Work session ID
- Mouse/keyboard activity

**Missing Features**:
- No thumbnail generation
- No cleanup of old files (if screenshots disabled)

---

### 6. Heartbeat Data Incomplete

**Line 150-151**: Network data hardcoded to 0
```python
'net_sent_mb': 0.0,
'net_recv_mb': 0.0,
```

**Line 138-143**: Geo parsing fails silently
```python
try:
    geo = json.loads(geo_json)
except:
    pass  # Silent failure
```

---

### 7. Work Session Issues

**No Validation For**:
- Session duration > 24 hours
- Overlapping sessions
- Future timestamps
- Negative durations

**No Auto-Recovery**:
- If app crashes during session
- Session never ends
- Data lost

---

### 8. Website Tracking Issues

**Issue 8.1**: URL extraction expensive (UI tree traversal every 2s)

**Issue 8.2**: No URL sanitization
- Stores query parameters
- Could contain tokens, passwords, API keys

**Issue 8.3**: Limited categorization
- Only 3 categories (productive/unproductive/neutral)
- No custom categories
- No learning

---

## Recommended Fixes (Priority Order)

### 🔴 CRITICAL - Fix Immediately

#### Fix 1: True "Twice Daily" Screenshots

**Implementation**: Divide day into morning/afternoon windows

```python
def _randomize_today_fixed(self):
    today = dt.datetime.now().date()
    
    # Morning: 9:30 AM - 12:30 PM
    morning_start = dt.datetime.combine(today, dt.time(9, 30))
    morning_end = dt.datetime.combine(today, dt.time(12, 30))
    morning_offset = random.randint(0, int((morning_end - morning_start).total_seconds()))
    morning_time = morning_start + dt.timedelta(seconds=morning_offset)
    
    # Afternoon: 2:00 PM - 5:30 PM
    afternoon_start = dt.datetime.combine(today, dt.time(14, 0))
    afternoon_end = dt.datetime.combine(today, dt.time(17, 30))
    afternoon_offset = random.randint(0, int((afternoon_end - afternoon_start).total_seconds()))
    afternoon_time = afternoon_start + dt.timedelta(seconds=afternoon_offset)
    
    self.targets = [morning_time, afternoon_time]
    self.captured_today = 0
```

#### Fix 2: Screenshot Compression & Retry

**Changes**:
1. Resize to max 1920x1080 before upload
2. Compress to quality=75
3. Retry 3 times on failure
4. Queue failed uploads for later

#### Fix 3: Data Validation

**Add validation before sync**:
- Check required fields
- Validate emp_id > 0
- Validate timestamps (not future, not > 7 days old)
- Validate percentages (0-100)

---

### 🟡 HIGH PRIORITY - Fix Soon

#### Fix 4: Sync Status UI

**Add status tracking**:
- Pending records count
- Synced records count
- Failed records count
- Last sync timestamp
- Display in dashboard

#### Fix 5: Screenshot Context

**Add metadata**:
- Active app/window
- Activity status
- Work session ID
- Mouse/keyboard activity
- Save as JSON alongside image

#### Fix 6: URL Sanitization

**Remove sensitive data**:
- Strip query parameters with: token, key, password, secret, auth
- Keep only scheme, domain, path
- Log sanitized URLs only

---

### 🟢 MEDIUM PRIORITY - Nice to Have

#### Fix 7: Network Usage Tracking

**Use psutil to track**:
- Bytes sent/received
- Calculate MB per interval
- Include in heartbeat data

#### Fix 8: Session Recovery

**Auto-recover crashed sessions**:
- Detect stale sessions (> 2 hours)
- Auto-end with reasonable time
- Close open breaks
- Sync to server

---

## Implementation Plan

### Phase 1: Critical Fixes (Week 1)
- [ ] Fix screenshot "twice daily" logic
- [ ] Add screenshot compression
- [ ] Add upload retry mechanism
- [ ] Add data validation

### Phase 2: High Priority (Week 2)
- [ ] Add sync status UI
- [ ] Add screenshot metadata
- [ ] Add URL sanitization
- [ ] Add offline queue persistence

### Phase 3: Medium Priority (Week 3)
- [ ] Add network usage tracking
- [ ] Add session recovery
- [ ] Add thumbnail generation
- [ ] Add custom productivity categories

---

## Testing Checklist

### Screenshot Tests
- [ ] Verify 1 morning + 1 afternoon screenshot
- [ ] Test upload on slow network (simulate 1 Mbps)
- [ ] Test retry mechanism (disconnect network)
- [ ] Verify compression reduces file size
- [ ] Test metadata JSON created

### Sync Tests
- [ ] Test offline queue (disconnect network)
- [ ] Test sync status updates in UI
- [ ] Test data validation rejects invalid records
- [ ] Test sync doesn't skip during long operations

### Session Tests
- [ ] Test session recovery after crash
- [ ] Test stale session auto-end
- [ ] Test session validation
- [ ] Test break tracking

---

## Configuration Changes Needed

### Add to config.json

```json
{
  "scheduled_shots": {
    "per_day": 2,
    "mode": "twice_daily",
    "morning_window": {
      "start": "09:30",
      "end": "12:30"
    },
    "afternoon_window": {
      "start": "14:00",
      "end": "17:30"
    },
    "compression": {
      "max_width": 1920,
      "max_height": 1080,
      "quality": 75
    },
    "upload": {
      "timeout_sec": 60,
      "retry_attempts": 3,
      "retry_delay_sec": 5
    },
    "retention_days": 30
  },
  "data_validation": {
    "enabled": true,
    "max_timestamp_age_days": 7,
    "sanitize_urls": true,
    "filter_pii": true
  },
  "sync": {
    "show_status": true,
    "offline_queue_enabled": true,
    "max_queue_size_mb": 100
  }
}
```

---

## Summary

**Total Issues**: 8  
**Critical**: 3  
**High Priority**: 3  
**Medium Priority**: 2  

**Estimated Effort**: 2-3 weeks  
**Impact**: Significantly improves data reliability and user experience

**Next Steps**:
1. Review and prioritize fixes
2. Implement Phase 1 (critical fixes)
3. Test thoroughly
4. Deploy to pilot users
5. Monitor and iterate
