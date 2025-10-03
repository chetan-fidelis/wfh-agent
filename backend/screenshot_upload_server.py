"""
Screenshot Upload API Server
This server receives screenshot uploads from the employee monitoring client
and stores them in an organized directory structure.

Usage:
    python screenshot_upload_server.py

The server will run on http://0.0.0.0:8080 by default.
"""

import os
import json
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import hashlib

app = Flask(__name__)

# Configuration
UPLOAD_BASE_DIR = os.environ.get('SCREENSHOT_UPLOAD_DIR', './uploads')
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png'}

# Create base upload directory
os.makedirs(UPLOAD_BASE_DIR, exist_ok=True)


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_file_size(file_storage):
    """Validate file size"""
    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)
    return size <= MAX_FILE_SIZE


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'screenshot-upload-api',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/upload/screenshot', methods=['POST'])
def upload_screenshot():
    """
    Upload screenshot endpoint

    Expected form data:
        - screenshot: File (JPEG/PNG image)
        - emp_id: Employee ID
        - timestamp: Timestamp in format YYYYMMDD_HHMMSS
        - captured_at: ISO datetime string
        - server_path: Desired server path (optional)

    Returns:
        JSON response with success status and file URL
    """
    try:
        # Validate request has file
        if 'screenshot' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No screenshot file in request'
            }), 400

        file = request.files['screenshot']

        # Validate filename
        if file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No file selected'
            }), 400

        # Validate file extension
        if not allowed_file(file.filename):
            return jsonify({
                'success': False,
                'error': f'Invalid file type. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'
            }), 400

        # Validate file size
        if not validate_file_size(file):
            return jsonify({
                'success': False,
                'error': f'File too large. Max size: {MAX_FILE_SIZE / 1024 / 1024}MB'
            }), 400

        # Get form data
        emp_id = request.form.get('emp_id')
        timestamp = request.form.get('timestamp')
        captured_at = request.form.get('captured_at')
        server_path = request.form.get('server_path')

        # Validate required fields
        if not emp_id:
            return jsonify({
                'success': False,
                'error': 'emp_id is required'
            }), 400

        if not timestamp:
            return jsonify({
                'success': False,
                'error': 'timestamp is required'
            }), 400

        # Sanitize filename
        filename = secure_filename(file.filename)

        # Extract date from timestamp or use current date
        # Expected format: YYYYMMDD_HHMMSS
        try:
            date_str = timestamp.split('_')[0]  # YYYYMMDD
            date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"  # YYYY-MM-DD
        except (IndexError, ValueError):
            # Fallback to current date
            date_formatted = datetime.now().strftime('%Y-%m-%d')

        # Build directory structure: screenshot/{emp_id}/{date}/
        upload_dir = os.path.join(UPLOAD_BASE_DIR, 'screenshot', str(emp_id), date_formatted)
        os.makedirs(upload_dir, exist_ok=True)

        # Save file
        file_path = os.path.join(upload_dir, filename)
        file.save(file_path)

        # Get file size
        file_size = os.path.getsize(file_path)

        # Generate MD5 hash for verification
        md5_hash = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                md5_hash.update(chunk)
        file_hash = md5_hash.hexdigest()

        # Build relative URL path
        relative_path = os.path.join('screenshot', str(emp_id), date_formatted, filename)
        # Convert to forward slashes for URLs
        url_path = relative_path.replace('\\', '/')

        # Log upload
        print(f"[{datetime.now().isoformat()}] Screenshot uploaded: {url_path} | Size: {file_size} bytes | Hash: {file_hash}")

        # Return success response
        return jsonify({
            'success': True,
            'url': url_path,
            'file_name': filename,
            'file_size': file_size,
            'file_hash': file_hash,
            'emp_id': emp_id,
            'timestamp': timestamp,
            'captured_at': captured_at,
            'stored_at': datetime.now().isoformat()
        }), 200

    except Exception as e:
        print(f"[{datetime.now().isoformat()}] Upload error: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }), 500


@app.route('/api/screenshots/<int:emp_id>', methods=['GET'])
def list_screenshots(emp_id):
    """
    List all screenshots for an employee

    Query parameters:
        - date: Filter by date (YYYY-MM-DD format)
        - limit: Max number of results (default: 100)
    """
    try:
        # Get query parameters
        date_filter = request.args.get('date')
        limit = int(request.args.get('limit', 100))

        # Build path
        emp_dir = os.path.join(UPLOAD_BASE_DIR, 'screenshot', str(emp_id))

        if not os.path.exists(emp_dir):
            return jsonify({
                'success': True,
                'emp_id': emp_id,
                'screenshots': [],
                'count': 0
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
                        'url': f"screenshot/{emp_id}/{date_dir}/{filename}",
                        'filename': filename,
                        'date': date_dir,
                        'size': file_stats.st_size,
                        'created_at': datetime.fromtimestamp(file_stats.st_ctime).isoformat(),
                        'modified_at': datetime.fromtimestamp(file_stats.st_mtime).isoformat()
                    })

                    # Respect limit
                    if len(screenshots) >= limit:
                        break

            if len(screenshots) >= limit:
                break

        return jsonify({
            'success': True,
            'emp_id': emp_id,
            'screenshots': screenshots,
            'count': len(screenshots)
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stats', methods=['GET'])
def stats():
    """Get upload statistics"""
    try:
        total_size = 0
        total_files = 0
        employees = set()

        screenshot_dir = os.path.join(UPLOAD_BASE_DIR, 'screenshot')

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
            'success': True,
            'stats': {
                'total_screenshots': total_files,
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / 1024 / 1024, 2),
                'total_employees': len(employees),
                'upload_directory': UPLOAD_BASE_DIR
            }
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


if __name__ == '__main__':
    # Get configuration from environment
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 8080))
    debug = os.environ.get('DEBUG', 'false').lower() == 'true'

    print(f"""
╔═══════════════════════════════════════════════════════╗
║     Screenshot Upload API Server                     ║
╠═══════════════════════════════════════════════════════╣
║  Server: http://{host}:{port}                   ║
║  Upload Endpoint: /api/upload/screenshot              ║
║  Health Check: /health                                ║
║  Stats: /api/stats                                    ║
║  Upload Directory: {UPLOAD_BASE_DIR:<30} ║
╚═══════════════════════════════════════════════════════╝
    """)

    app.run(host=host, port=port, debug=debug)
