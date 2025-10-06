# Ingestion Server Consolidation - Change Log

## Overview
Consolidated `screenshot_upload_server.py` functionality into `ingestion_server.py` to create a unified data ingestion server.

## Changes Made

### 1. Combined Server Functionality
- **Merged** screenshot upload server into main ingestion server
- **Removed** separate `screenshot_upload_server.py` file
- **Unified** all endpoints under single Flask application

### 2. Enhanced Screenshot Upload Endpoint
**Endpoint:** `POST /api/upload/screenshot`

**Features Added:**
- File system storage with organized directory structure: `uploads/screenshot/{emp_id}/{date}/`
- MD5 hash generation for file verification
- Database metadata storage (PostgreSQL)
- Support for both `file` and `screenshot` form field names
- Automatic date extraction from timestamp format (YYYYMMDD_HHMMSS)
- Secure filename sanitization using `secure_filename()`

**Response Format:**
```json
{
  "success": true,
  "id": 123,
  "url": "screenshot/123/2025-10-04/filename.jpg",
  "file_name": "filename.jpg",
  "file_size": 45678,
  "file_hash": "abc123..."
}
```

### 3. New Endpoints Added

#### List Screenshots
**Endpoint:** `GET /api/screenshots/<emp_id>`

**Query Parameters:**
- `date` (optional): Filter by date (YYYY-MM-DD format)
- `limit` (optional): Max results (default: 100)

**Features:**
- List all screenshots for an employee
- Date filtering support
- File metadata (size, timestamps)
- Reverse chronological order

#### Screenshot Statistics
**Endpoint:** `GET /api/screenshots/stats`

**Features:**
- Total screenshot count across all employees
- Total storage size (bytes and MB)
- Employee count
- Upload directory path

### 4. Requirements Consolidation
- **Removed:** `screenshot_server_requirements.txt`
- **Updated:** `requirements.txt` with combined dependencies:
  ```
  flask>=3.0.0
  werkzeug>=3.0.0
  psycopg[binary]>=3.1.0
  waitress>=2.1.2
  ```

### 5. Environment Variables
**Added:**
- `SCREENSHOT_UPLOAD_DIR`: Upload directory path (default: `./uploads`)

**Updated Configuration:**
```bash
export SCREENSHOT_UPLOAD_DIR="/home/wfhagent/uploads"
```

### 6. Documentation Updates

#### README.md
- Added detailed screenshot endpoint documentation
- Added list screenshots endpoint with examples
- Added screenshot statistics endpoint
- Updated environment variables section

#### QUICKSTART.md
- Added `SCREENSHOT_UPLOAD_DIR` to environment setup
- Updated deployment instructions

#### deploy.sh
- Added automatic creation of uploads directory
- Added `SCREENSHOT_UPLOAD_DIR` to .env configuration
- Set proper permissions for uploads directory

### 7. Database Schema
**Table:** `screenshots`

```sql
CREATE TABLE IF NOT EXISTS screenshots (
    id SERIAL PRIMARY KEY,
    emp_id INTEGER NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    file_size INTEGER NOT NULL,
    file_hash VARCHAR(32),
    captured_at TIMESTAMPTZ,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (emp_id, file_name)
);
```

## Benefits

1. **Simplified Deployment**
   - Single server to deploy and maintain
   - Single port configuration
   - Unified systemd service

2. **Better Security**
   - All endpoints behind single API key authentication
   - Consistent security middleware
   - Centralized access control

3. **Easier Monitoring**
   - Single log stream for all operations
   - Unified health check endpoint
   - Consolidated error handling

4. **Reduced Overhead**
   - One Python process instead of two
   - Shared database connection pool
   - Lower memory footprint

## Migration Path

### For Existing Deployments

1. **Backup** existing screenshot upload server data
2. **Stop** old screenshot upload server service
3. **Update** ingestion server with new code
4. **Set** `SCREENSHOT_UPLOAD_DIR` environment variable
5. **Restart** ingestion server
6. **Remove** old screenshot upload server files

### For New Deployments

1. Use updated `deploy.sh` script - automatically configures everything
2. Or manually follow QUICKSTART.md with new environment variables

## API Compatibility

- ✅ **Backward compatible** with existing screenshot upload clients
- ✅ Supports both `file` and `screenshot` form field names
- ✅ Same response format maintained
- ✅ All existing endpoints preserved

## Testing

**Syntax Check:**
```bash
python -m py_compile ingestion_server.py  # ✅ Passed
```

**Server Start:**
```bash
python ingestion_server.py  # ✅ Starts successfully (requires env vars)
```

## Files Modified

- ✅ `ingestion-server/ingestion_server.py` - Enhanced with screenshot endpoints
- ✅ `ingestion-server/requirements.txt` - Combined dependencies
- ✅ `ingestion-server/README.md` - Updated documentation
- ✅ `ingestion-server/QUICKSTART.md` - Updated quick start guide
- ✅ `ingestion-server/deploy.sh` - Added upload directory setup

## Files Removed

- ❌ `ingestion-server/screenshot_upload_server.py` - Merged into main server
- ❌ `ingestion-server/screenshot_server_requirements.txt` - Consolidated

## Version
- **Ingestion Server:** v2.0 (Consolidated)
- **Date:** October 4, 2025
