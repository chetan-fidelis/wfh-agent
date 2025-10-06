# WFH Agent v0.1.8 Release Notes

## 🚀 Major Features

### Cloud Ingestion Server
- **NEW**: Complete cloud-based data ingestion system
- **NEW**: Centralized PostgreSQL database for multi-employee monitoring
- **NEW**: Secure API-based data synchronization
- Real-time data streaming from desktop clients to cloud server
- API key authentication for secure data transmission

### Data Sync Architecture
- **NEW**: Comprehensive sync for all data types:
  - ✅ Heartbeat monitoring (real-time activity tracking)
  - ✅ Website usage tracking with duration
  - ✅ Work sessions with break management
  - ✅ Productivity metrics by tag (productive/neutral/unproductive)
  - ✅ Wellness daily metrics and flags
  - ✅ Timeline hourly activity breakdown
  - ✅ ITSM ticket management
  - ✅ Screenshot upload to cloud storage

### Data Persistence
- **IMPROVED**: Data accumulation throughout the day
- **FIXED**: Data no longer clears after sync
- **NEW**: ON CONFLICT handling for upsert operations
- Continuous updates to cloud database with incremental data

## 🔧 Technical Improvements

### Backend Enhancements
- **NEW**: `api_sync.py` - Complete API synchronization module
- **NEW**: `ingestion_server.py` - Flask-based ingestion server
- **IMPROVED**: Column mapping to match PostgreSQL schema
- **FIXED**: Database field name mismatches (mem_percent → memory_percent, date → day, etc.)
- **NEW**: Batch ingestion endpoint with table whitelisting

### Server Infrastructure
- **NEW**: Systemd service configuration for ingestion server
- **NEW**: Nginx reverse proxy support
- **NEW**: SSL/HTTPS ready with certbot integration
- **NEW**: Connection pooling for database performance
- **NEW**: Waitress WSGI server for production deployment

### Data Schema Fixes
- Fixed heartbeat table column mapping
- Fixed website_usage duration field (duration_sec → duration_seconds)
- Fixed wellness_daily structure (date → day, added wellness_flags JSONB)
- Fixed productivity_by_tag schema (removed app_name, kept tag only)
- Fixed timeline structure (status-based rows with duration)
- Fixed ITSM tickets schema alignment

## 🐛 Bug Fixes

- Fixed duplicate key violations with ON CONFLICT clauses
- Fixed transaction abort errors during batch inserts
- Fixed data clearing issue (now accumulates throughout the day)
- Fixed column name mismatches across all tables
- Fixed JSON file handling for website_usage and productivity data

## 📁 New Files

### Ingestion Server
- `ingestion-server/ingestion_server.py` - Main ingestion server
- `ingestion-server/requirements.txt` - Python dependencies
- `ingestion-server/deploy.sh` - Automated deployment script
- `ingestion-server/README.md` - Setup documentation
- `ingestion-server/QUICKSTART.md` - 5-minute setup guide

### Backend
- `backend/api_sync.py` - API synchronization module
- `backend/MIGRATION_TO_API.md` - Migration documentation

## 🔐 Security

- API key-based authentication for all endpoints
- Environment variable storage for sensitive credentials
- Server-side credential management (no DB credentials on client)
- Configurable authentication headers

## 📊 Configuration

### New Config Options
```json
{
  "ingestion": {
    "enabled": true,
    "mode": "api",
    "batch_size": 200,
    "heartbeat_sync_sec": 30,
    "full_sync_sec": 60,
    "api": {
      "base_url": "http://your-server:5050",
      "auth_header": "X-Api-Key",
      "auth_env": "WFH_AGENT_API_KEY"
    }
  }
}
```

## 🚀 Deployment

### Server Requirements
- Ubuntu 20.04+ / Linux server
- PostgreSQL 12+ with TimescaleDB
- Python 3.8+
- Nginx (for reverse proxy)
- Certbot (for SSL)

### Client Requirements
- Updated WFH Agent desktop app (v0.1.8)
- API key environment variable configured
- Network access to ingestion server

## 📈 Performance

- Efficient batch processing (up to 1000 records per batch)
- Connection pooling (2-10 concurrent connections)
- Optimized ON CONFLICT upserts for incremental updates
- Minimal client-side resource usage

## 🔄 Migration Notes

### From v0.1.7 to v0.1.8

1. **Update package.json version** to 0.1.8
2. **Deploy ingestion server** on cloud infrastructure
3. **Configure client** with API credentials
4. **Set environment variable**: `WFH_AGENT_API_KEY`
5. **Update config.json** with ingestion settings

### Breaking Changes
- Data sync now requires ingestion server deployment
- Direct PostgreSQL connection mode deprecated (still supported)
- API authentication now mandatory for cloud sync

## 🎯 What's Next (v0.1.9 Roadmap)

- Web dashboard for data visualization
- Enhanced screenshot analysis
- Real-time notifications
- Mobile companion app
- Advanced analytics and reporting

## 📞 Support

- **Documentation**: See `ingestion-server/README.md` and `QUICKSTART.md`
- **Issues**: Report at https://github.com/chetan-fidelis/wfh-agent/issues
- **Email**: support@fidelisgroup.in

---

**Release Date**: October 6, 2025
**Build**: v0.1.8
**License**: MIT
