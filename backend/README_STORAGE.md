# Optimized Data Storage with SQLite + Postgres Sync

This implementation provides a robust data storage solution that combines local SQLite storage with periodic Postgres synchronization to optimize performance and reduce server load.

## Key Features

1. **Local SQLite Storage**
   - All data is stored locally in SQLite first
   - Ensures data persistence even when offline
   - Fast local writes with minimal overhead

2. **Selective Postgres Sync**
   - Heartbeat data: Synced every 5 minutes (one record at a time)
   - Screenshots: Synced immediately when captured
   - Other data (website usage, productivity, timeline, wellness): Synced every 15 minutes

3. **Reduced Server Load**
   - Batched database operations
   - Fewer network connections
   - Optimized sync frequency based on data importance

## Data Types and Sync Strategy

| Data Type | Local Storage | Sync Frequency | Sync Trigger |
|-----------|---------------|----------------|--------------|
| Heartbeat | SQLite | Every 5 minutes | Time-based |
| Screenshots | SQLite | Immediate | Event-based |
| Website Usage | SQLite | Every 15 minutes | Time-based |
| Productivity | SQLite | Every 15 minutes | Time-based |
| Timeline | SQLite | Every 15 minutes | Time-based |
| Wellness | SQLite | Every 15 minutes | Time-based |

## Implementation Details

### LocalStorage Class

The `LocalStorage` class provides methods for:
- Initializing SQLite database with required tables
- Inserting data into SQLite tables
- Syncing data to Postgres based on configurable intervals
- Handling sync failures gracefully

### Sync Process

1. Data is inserted into SQLite
2. Based on data type and timing, sync may be triggered:
   - For screenshots: Immediate sync
   - For heartbeat: Every 5 minutes
   - For other data: Every 15 minutes
3. Sync process runs in a separate thread to avoid blocking
4. Only unsynced records are sent to Postgres
5. After successful sync, records are marked as synced

## Benefits

1. **Reliability**
   - No data loss during network outages
   - Graceful handling of server unavailability

2. **Performance**
   - Reduced network traffic
   - Lower server load
   - Faster local operations

3. **Scalability**
   - Can handle large amounts of data
   - Efficient use of server resources

## Usage

```python
# Initialize local storage
storage = LocalStorage(DATA_DIR, app_ref)

# Insert heartbeat data (syncs every 5 minutes)
storage.insert_heartbeat(emp_id, ts, status, cpu_percent, memory_percent, 
                         process_name, window_title, domain, url, 
                         battery_level, battery_plugged, geo)

# Insert screenshot metadata (syncs immediately)
storage.insert_screenshot(emp_id, file_name, file_path, file_size, captured_at)

# Insert website usage data (syncs every 15 minutes)
storage.insert_website_usage(emp_id, date, domain, duration, tag)
```

## Installation

1. Replace the existing `local_storage.py` with the optimized version
2. Update `emp_monitor.py` to use the new storage methods
3. Restart the application

You can use the provided `update_monitor.py` script to automate this process.
