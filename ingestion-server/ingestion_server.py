"""
WFH Agent - Data Ingestion Server
Secure PostgreSQL ingestion endpoint for employee monitoring data
No database credentials exposed to clients
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from flask import Flask, request, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix

# Try to import psycopg (PostgreSQL driver)
try:
    import psycopg
    from psycopg_pool import ConnectionPool
    PSYCOPG_AVAILABLE = True
except ImportError:
    PSYCOPG_AVAILABLE = False
    ConnectionPool = None
    print("Warning: psycopg not available. Install with: pip install psycopg[binary] psycopg-pool")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Configuration
API_KEY = os.environ.get('WFH_AGENT_API_KEY', '')
DB_URL = os.environ.get('EMP_DB_URL', '')
DB_SCHEMA = os.environ.get('DB_SCHEMA', 'employee_monitor')
MAX_BATCH_SIZE = 1000

# Validate configuration
if not API_KEY:
    logger.error("WFH_AGENT_API_KEY environment variable not set!")
    sys.exit(1)

if not DB_URL:
    logger.error("EMP_DB_URL environment variable not set!")
    sys.exit(1)

if not PSYCOPG_AVAILABLE:
    logger.error("psycopg not available. Install with: pip install 'psycopg[binary]'")
    sys.exit(1)


# Authentication middleware
def require_api_key(f):
    """Decorator to require API key authentication"""
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-Api-Key')

        # Debug logging
        received_preview = (api_key[:12] + "...") if api_key and len(api_key) > 12 else api_key
        expected_preview = (API_KEY[:12] + "...") if len(API_KEY) > 12 else API_KEY
        logger.info(f"Auth check - Received: {received_preview}, Expected: {expected_preview}, Match: {api_key == API_KEY}")

        if not api_key or api_key != API_KEY:
            logger.warning(f"Unauthorized access attempt from {request.remote_addr} to {request.path}")
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function


# Database connection pool
_db_pool = None

def get_db_pool():
    """Get or create database connection pool"""
    global _db_pool
    if _db_pool is None:
        try:
            _db_pool = ConnectionPool(
                conninfo=DB_URL,
                min_size=2,
                max_size=10,
                timeout=30
            )
            logger.info("Database connection pool created")
        except Exception as e:
            logger.error(f"Failed to create database pool: {e}")
            raise
    return _db_pool


# Health check endpoint (no auth required)
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        pool = get_db_pool()
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")

        return jsonify({
            "status": "healthy",
            "service": "wfh-agent-ingestion",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }), 503


# Heartbeat ingestion
@app.route('/api/ingest/heartbeat', methods=['POST'])
@require_api_key
def ingest_heartbeat():
    """Ingest heartbeat data"""
    try:
        data = request.get_json()
        if not data or 'records' not in data:
            return jsonify({"error": "Invalid payload"}), 400

        records = data['records']
        if not isinstance(records, list):
            return jsonify({"error": "Records must be an array"}), 400

        if len(records) > MAX_BATCH_SIZE:
            return jsonify({"error": f"Batch size exceeds maximum ({MAX_BATCH_SIZE})"}), 400

        pool = get_db_pool()
        inserted = 0

        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SET search_path TO {DB_SCHEMA}, public;")

                for record in records:
                    try:
                        # Map client field names to database column names
                        db_record = {
                            'emp_id': record.get('emp_id'),
                            'ts': record.get('ts'),
                            'status': record.get('status', 'active' if record.get('active') else 'idle'),
                            'cpu_percent': record.get('cpu_percent'),
                            'memory_percent': record.get('mem_percent') or record.get('memory_percent'),
                            'process_name': record.get('fg_app') or record.get('process_name'),
                            'window_title': record.get('fg_title') or record.get('window_title'),
                            'domain': record.get('domain'),
                            'url': record.get('url'),
                            'battery_level': record.get('battery_percent') or record.get('battery_level'),
                            'battery_plugged': record.get('battery_plugged'),
                            'geo': record.get('geo')
                        }

                        cur.execute("""
                            INSERT INTO heartbeat (
                                emp_id, ts, status, cpu_percent, memory_percent,
                                process_name, window_title, domain, url,
                                battery_level, battery_plugged, geo
                            ) VALUES (
                                %(emp_id)s, %(ts)s, %(status)s, %(cpu_percent)s, %(memory_percent)s,
                                %(process_name)s, %(window_title)s, %(domain)s, %(url)s,
                                %(battery_level)s, %(battery_plugged)s, %(geo)s
                            )
                        """, db_record)
                        inserted += 1
                    except Exception as e:
                        logger.warning(f"Failed to insert heartbeat record: {e}")
                        continue

                conn.commit()

        logger.info(f"Inserted {inserted}/{len(records)} heartbeat records from emp_id={data.get('emp_id', 'unknown')}")
        return jsonify({"success": True, "inserted": inserted}), 200

    except Exception as e:
        logger.error(f"Heartbeat ingestion error: {e}")
        return jsonify({"error": str(e)}), 500


# Website usage ingestion
@app.route('/api/ingest/website_usage', methods=['POST'])
@require_api_key
def ingest_website_usage():
    """Ingest website usage data"""
    try:
        data = request.get_json()
        if not data or 'records' not in data:
            return jsonify({"error": "Invalid payload"}), 400

        records = data['records']
        pool = get_db_pool()
        inserted = 0

        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SET search_path TO {DB_SCHEMA}, public;")

                for record in records:
                    try:
                        # Map client field names to database column names
                        db_record = {
                            'emp_id': record.get('emp_id'),
                            'date': record.get('date'),
                            'domain': record.get('domain'),
                            'duration_seconds': record.get('duration_sec') or record.get('duration_seconds', 0),
                            'tag': record.get('tag', 'neutral')
                        }

                        cur.execute("""
                            INSERT INTO website_usage (
                                emp_id, date, domain, duration_seconds, tag
                            ) VALUES (
                                %(emp_id)s, %(date)s, %(domain)s, %(duration_seconds)s, %(tag)s
                            )
                            ON CONFLICT (emp_id, date, domain)
                            DO UPDATE SET
                                duration_seconds = website_usage.duration_seconds + EXCLUDED.duration_seconds
                        """, db_record)
                        inserted += 1
                    except Exception as e:
                        logger.warning(f"Failed to insert website usage: {e}")
                        continue

                conn.commit()

        logger.info(f"Inserted {inserted}/{len(records)} website usage records")
        return jsonify({"success": True, "inserted": inserted}), 200

    except Exception as e:
        logger.error(f"Website usage ingestion error: {e}")
        return jsonify({"error": str(e)}), 500


# Work sessions ingestion
@app.route('/api/ingest/work_sessions', methods=['POST'])
@require_api_key
def ingest_work_sessions():
    """Ingest work session data"""
    try:
        data = request.get_json()
        if not data or 'records' not in data:
            return jsonify({"error": "Invalid payload"}), 400

        records = data['records']
        pool = get_db_pool()
        inserted = 0

        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SET search_path TO {DB_SCHEMA}, public;")

                for record in records:
                    try:
                        cur.execute("""
                            INSERT INTO work_sessions (
                                emp_id, start_ts, end_ts, breaks, work_ms, break_ms, total_ms
                            ) VALUES (
                                %(emp_id)s, %(start_ts)s, %(end_ts)s, %(breaks)s, %(work_ms)s, %(break_ms)s, %(total_ms)s
                            )
                        """, record)
                        inserted += 1
                    except Exception as e:
                        logger.warning(f"Failed to insert work session: {e}")
                        continue

                conn.commit()

        logger.info(f"Inserted {inserted}/{len(records)} work session records")
        return jsonify({"success": True, "inserted": inserted}), 200

    except Exception as e:
        logger.error(f"Work session ingestion error: {e}")
        return jsonify({"error": str(e)}), 500


# Screenshot upload
@app.route('/api/upload/screenshot', methods=['POST'])
@require_api_key
def upload_screenshot():
    """Upload screenshot with file system storage and database metadata"""
    try:
        # Check for file in request (support both 'file' and 'screenshot' keys)
        file = request.files.get('file') or request.files.get('screenshot')

        if not file:
            return jsonify({
                "success": False,
                "error": "No screenshot file in request"
            }), 400

        # Validate filename
        if file.filename == '':
            return jsonify({
                "success": False,
                "error": "No file selected"
            }), 400

        # Get form data
        emp_id = request.form.get('emp_id', type=int)
        timestamp = request.form.get('timestamp')
        captured_at = request.form.get('captured_at')

        if not emp_id or not timestamp:
            return jsonify({
                "success": False,
                "error": "Missing emp_id or timestamp"
            }), 400

        # Sanitize filename
        from werkzeug.utils import secure_filename
        filename = secure_filename(file.filename)

        # Extract date from timestamp (format: YYYYMMDD_HHMMSS)
        try:
            date_str = timestamp.split('_')[0]
            date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        except (IndexError, ValueError):
            from datetime import datetime
            date_formatted = datetime.now().strftime('%Y-%m-%d')

        # Build directory structure: uploads/screenshot/{emp_id}/{date}/
        upload_base_dir = os.environ.get('SCREENSHOT_UPLOAD_DIR', './uploads')
        upload_dir = os.path.join(upload_base_dir, 'screenshot', str(emp_id), date_formatted)
        os.makedirs(upload_dir, exist_ok=True)

        # Save file to disk
        file_path = os.path.join(upload_dir, filename)
        file.save(file_path)
        file_size = os.path.getsize(file_path)

        # Generate file hash for verification
        import hashlib
        md5_hash = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                md5_hash.update(chunk)
        file_hash = md5_hash.hexdigest()

        # Build relative URL path
        relative_path = os.path.join('screenshot', str(emp_id), date_formatted, filename)
        url_path = relative_path.replace('\\', '/')

        # Save metadata to database
        pool = get_db_pool()
        screenshot_id = None

        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SET search_path TO {DB_SCHEMA}, public;")

                # Create table if not exists
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {DB_SCHEMA}.screenshots (
                        id SERIAL PRIMARY KEY,
                        emp_id INTEGER NOT NULL,
                        file_name VARCHAR(255) NOT NULL,
                        file_path VARCHAR(512) NOT NULL,
                        file_size INTEGER NOT NULL,
                        file_hash VARCHAR(32),
                        captured_at TIMESTAMPTZ,
                        uploaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE (emp_id, file_name)
                    )
                """)

                # Insert screenshot metadata
                cur.execute(f"""
                    INSERT INTO {DB_SCHEMA}.screenshots (
                        emp_id, file_name, file_path, file_size, file_hash, captured_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (emp_id, file_name) DO UPDATE SET
                        file_path = EXCLUDED.file_path,
                        file_size = EXCLUDED.file_size,
                        file_hash = EXCLUDED.file_hash,
                        captured_at = EXCLUDED.captured_at,
                        uploaded_at = CURRENT_TIMESTAMP
                    RETURNING id
                """, (emp_id, filename, url_path, file_size, file_hash, captured_at or timestamp))

                screenshot_id = cur.fetchone()[0]
                conn.commit()

        logger.info(f"Screenshot uploaded: {url_path} | Size: {file_size} bytes | Hash: {file_hash}")

        return jsonify({
            "success": True,
            "id": screenshot_id,
            "url": url_path,
            "file_name": filename,
            "file_size": file_size,
            "file_hash": file_hash
        }), 200

    except Exception as e:
        logger.error(f"Screenshot upload error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# List screenshots for an employee
@app.route('/api/screenshots/<int:emp_id>', methods=['GET'])
@require_api_key
def list_screenshots(emp_id):
    """List all screenshots for an employee with optional date filter"""
    try:
        # Get query parameters
        date_filter = request.args.get('date')
        limit = int(request.args.get('limit', 100))

        # Build path
        upload_base_dir = os.environ.get('SCREENSHOT_UPLOAD_DIR', './uploads')
        emp_dir = os.path.join(upload_base_dir, 'screenshot', str(emp_id))

        if not os.path.exists(emp_dir):
            return jsonify({
                "success": True,
                "emp_id": emp_id,
                "screenshots": [],
                "count": 0
            })

        screenshots = []

        # Iterate through date directories
        for date_dir in sorted(os.listdir(emp_dir), reverse=True):
            # Filter by date if provided
            if date_filter and date_dir != date_filter:
                continue

            date_path = os.path.join(emp_dir, date_dir)
            if not os.path.isdir(date_path):
                continue

            # List files in date directory
            for filename in sorted(os.listdir(date_path), reverse=True):
                if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    file_path = os.path.join(date_path, filename)
                    file_stats = os.stat(file_path)

                    screenshots.append({
                        "url": f"screenshot/{emp_id}/{date_dir}/{filename}",
                        "filename": filename,
                        "date": date_dir,
                        "size": file_stats.st_size,
                        "created_at": datetime.fromtimestamp(file_stats.st_ctime).isoformat(),
                        "modified_at": datetime.fromtimestamp(file_stats.st_mtime).isoformat()
                    })

                    # Respect limit
                    if len(screenshots) >= limit:
                        break

            if len(screenshots) >= limit:
                break

        return jsonify({
            "success": True,
            "emp_id": emp_id,
            "screenshots": screenshots,
            "count": len(screenshots)
        })

    except Exception as e:
        logger.error(f"List screenshots error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# Screenshot storage statistics
@app.route('/api/screenshots/stats', methods=['GET'])
@require_api_key
def screenshot_stats():
    """Get screenshot storage statistics"""
    try:
        total_size = 0
        total_files = 0
        employees = set()

        upload_base_dir = os.environ.get('SCREENSHOT_UPLOAD_DIR', './uploads')
        screenshot_dir = os.path.join(upload_base_dir, 'screenshot')

        if os.path.exists(screenshot_dir):
            for emp_id in os.listdir(screenshot_dir):
                emp_path = os.path.join(screenshot_dir, emp_id)
                if not os.path.isdir(emp_path):
                    continue

                employees.add(emp_id)

                for date_dir in os.listdir(emp_path):
                    date_path = os.path.join(emp_path, date_dir)
                    if not os.path.isdir(date_path):
                        continue

                    for filename in os.listdir(date_path):
                        file_path = os.path.join(date_path, filename)
                        if os.path.isfile(file_path):
                            total_files += 1
                            total_size += os.path.getsize(file_path)

        return jsonify({
            "success": True,
            "stats": {
                "total_screenshots": total_files,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / 1024 / 1024, 2),
                "total_employees": len(employees),
                "upload_directory": upload_base_dir
            }
        })

    except Exception as e:
        logger.error(f"Screenshot stats error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# Generic batch ingestion
@app.route('/api/ingest/batch', methods=['POST'])
@require_api_key
def ingest_batch():
    """Generic batch ingestion endpoint"""
    try:
        data = request.get_json()
        if not data or 'table' not in data or 'records' not in data:
            return jsonify({"error": "Invalid payload"}), 400

        table = data['table']
        records = data['records']

        # Whitelist allowed tables
        allowed_tables = [
            'heartbeat', 'website_usage', 'work_sessions',
            'wellness_daily', 'productivity_by_tag', 'itsm_tickets'
        ]

        if table not in allowed_tables:
            return jsonify({"error": f"Table '{table}' not allowed"}), 400

        pool = get_db_pool()
        inserted = 0

        # Define ON CONFLICT clauses for each table
        conflict_handlers = {
            'productivity_by_tag': 'ON CONFLICT (emp_id, date, tag) DO UPDATE SET duration_seconds = productivity_by_tag.duration_seconds + EXCLUDED.duration_seconds',
            'wellness_daily': 'ON CONFLICT (emp_id, day) DO UPDATE SET work_seconds = EXCLUDED.work_seconds, active_seconds = EXCLUDED.active_seconds, idle_seconds = EXCLUDED.idle_seconds, break_seconds = EXCLUDED.break_seconds, utilization_ratio = EXCLUDED.utilization_ratio, wellness_flags = EXCLUDED.wellness_flags, esg_metrics = EXCLUDED.esg_metrics',
            'timeline': 'ON CONFLICT (emp_id, date, hour, status) DO UPDATE SET duration_seconds = EXCLUDED.duration_seconds',
            'itsm_tickets': 'ON CONFLICT (ticket_id) DO NOTHING'
        }

        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SET search_path TO {DB_SCHEMA}, public;")

                for record in records:
                    try:
                        # Dynamic insert with ON CONFLICT handling
                        columns = ', '.join(record.keys())
                        placeholders = ', '.join([f'%({k})s' for k in record.keys()])

                        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"

                        # Add ON CONFLICT clause if defined for this table
                        if table in conflict_handlers:
                            query += f" {conflict_handlers[table]}"

                        cur.execute(query, record)
                        inserted += 1
                    except Exception as e:
                        logger.warning(f"Failed to insert into {table}: {e}")
                        continue

                conn.commit()

        logger.info(f"Batch insert: {inserted}/{len(records)} records into {table}")
        return jsonify({"success": True, "inserted": inserted}), 200

    except Exception as e:
        logger.error(f"Batch ingestion error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    # Production server (use gunicorn or uwsgi in production)
    port = int(os.environ.get('PORT', 5050))

    logger.info("=" * 60)
    logger.info("WFH Agent - Data Ingestion Server")
    logger.info("=" * 60)
    logger.info(f"Database: {DB_URL.split('@')[1] if '@' in DB_URL else 'configured'}")
    logger.info(f"Schema: {DB_SCHEMA}")
    logger.info(f"Port: {port}")
    logger.info("=" * 60)

    # Use waitress for production
    try:
        from waitress import serve
        logger.info("Starting server with Waitress (production)...")
        serve(app, host='0.0.0.0', port=port, threads=4)
    except ImportError:
        logger.warning("Waitress not available, using Flask dev server (NOT for production!)")
        logger.warning("Install waitress: pip install waitress")
        app.run(host='0.0.0.0', port=port, debug=False)
