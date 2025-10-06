# Screenshot Upload Server API

A Flask-based API server for receiving and storing employee monitoring screenshots.

## Features

- ✅ RESTful API endpoint for screenshot uploads
- ✅ Organized storage structure: `screenshot/{emp_id}/{date}/filename.jpg`
- ✅ File validation (type, size)
- ✅ MD5 hash generation for file verification
- ✅ Statistics endpoint
- ✅ Employee screenshot listing
- ✅ Health check endpoint

## Installation

### 1. Install Dependencies

```bash
pip install -r screenshot_server_requirements.txt
```

### 2. Run the Server

**Basic usage:**
```bash
python screenshot_upload_server.py
```

**Custom configuration:**
```bash
# Set custom upload directory
export SCREENSHOT_UPLOAD_DIR=/var/www/screenshots

# Set custom port
export PORT=8080

# Set custom host
export HOST=0.0.0.0

# Enable debug mode
export DEBUG=true

python screenshot_upload_server.py
```

The server will run on `http://0.0.0.0:8080` by default.

## API Endpoints

### 1. Upload Screenshot
**POST** `/api/upload/screenshot`

**Form Data:**
- `screenshot` (file): Image file (JPG/PNG)
- `emp_id` (string): Employee ID
- `timestamp` (string): Format `YYYYMMDD_HHMMSS`
- `captured_at` (string): ISO datetime
- `server_path` (string, optional): Desired server path

**Response:**
```json
{
  "success": true,
  "url": "screenshot/18698/2025-10-03/shot_20251003_121651.jpg",
  "file_name": "shot_20251003_121651.jpg",
  "file_size": 288467,
  "file_hash": "a1b2c3d4e5f6...",
  "emp_id": "18698",
  "timestamp": "20251003_121651",
  "captured_at": "2025-10-03T12:16:51",
  "stored_at": "2025-10-03T12:16:52.123456"
}
```

### 2. List Screenshots
**GET** `/api/screenshots/{emp_id}`

**Query Parameters:**
- `date` (optional): Filter by date (YYYY-MM-DD)
- `limit` (optional): Max results (default: 100)

**Example:**
```bash
curl http://localhost:8080/api/screenshots/18698?date=2025-10-03&limit=10
```

**Response:**
```json
{
  "success": true,
  "emp_id": 18698,
  "screenshots": [
    {
      "url": "screenshot/18698/2025-10-03/shot_20251003_121651.jpg",
      "filename": "shot_20251003_121651.jpg",
      "date": "2025-10-03",
      "size": 288467,
      "created_at": "2025-10-03T12:16:52",
      "modified_at": "2025-10-03T12:16:52"
    }
  ],
  "count": 1
}
```

### 3. Statistics
**GET** `/api/stats`

**Response:**
```json
{
  "success": true,
  "stats": {
    "total_screenshots": 150,
    "total_size_bytes": 45678900,
    "total_size_mb": 43.56,
    "total_employees": 5,
    "upload_directory": "./uploads"
  }
}
```

### 4. Health Check
**GET** `/health`

**Response:**
```json
{
  "status": "healthy",
  "service": "screenshot-upload-api",
  "timestamp": "2025-10-03T12:16:52.123456"
}
```

## File Storage Structure

```
uploads/
└── screenshot/
    └── {emp_id}/
        └── {date}/
            └── {filename}.jpg
```

**Example:**
```
uploads/
└── screenshot/
    ├── 18698/
    │   ├── 2025-10-01/
    │   │   ├── shot_20251001_093000.jpg
    │   │   └── shot_20251001_150000.jpg
    │   ├── 2025-10-02/
    │   │   ├── shot_20251002_093000.jpg
    │   │   └── shot_20251002_150000.jpg
    │   └── 2025-10-03/
    │       └── shot_20251003_121651.jpg
    └── 19609/
        └── 2025-09-29/
            ├── shot_20250929_153158.jpg
            └── shot_20250929_153558.jpg
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SCREENSHOT_UPLOAD_DIR` | `./uploads` | Base directory for uploads |
| `HOST` | `0.0.0.0` | Server host |
| `PORT` | `8080` | Server port |
| `DEBUG` | `false` | Enable debug mode |

### File Validation

- **Allowed Extensions:** `.jpg`, `.jpeg`, `.png`
- **Max File Size:** 10 MB

## Testing

### Test Upload with curl

```bash
curl -X POST http://localhost:8080/api/upload/screenshot \
  -F "screenshot=@/path/to/screenshot.jpg" \
  -F "emp_id=18698" \
  -F "timestamp=20251003_121651" \
  -F "captured_at=2025-10-03T12:16:51"
```

### Test with Python

```python
import requests

url = "http://localhost:8080/api/upload/screenshot"
files = {'screenshot': open('screenshot.jpg', 'rb')}
data = {
    'emp_id': '18698',
    'timestamp': '20251003_121651',
    'captured_at': '2025-10-03T12:16:51'
}

response = requests.post(url, files=files, data=data)
print(response.json())
```

## Production Deployment

### Using Gunicorn (Recommended)

```bash
# Install Gunicorn
pip install gunicorn

# Run with 4 workers
gunicorn -w 4 -b 0.0.0.0:8080 screenshot_upload_server:app
```

### Using systemd (Linux)

Create `/etc/systemd/system/screenshot-upload.service`:

```ini
[Unit]
Description=Screenshot Upload API Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/screenshot-server
Environment="SCREENSHOT_UPLOAD_DIR=/var/www/screenshots"
Environment="PORT=8080"
ExecStart=/usr/bin/gunicorn -w 4 -b 0.0.0.0:8080 screenshot_upload_server:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable screenshot-upload
sudo systemctl start screenshot-upload
```

### Using Nginx as Reverse Proxy

```nginx
server {
    listen 80;
    server_name screenshots.example.com;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # Serve uploaded files directly
    location /screenshot/ {
        alias /var/www/screenshots/screenshot/;
        autoindex off;
    }
}
```

## Client Configuration

Update your client's `config.json`:

```json
{
  "screenshot_upload": {
    "enabled": true,
    "server_url": "http://your-server-ip:8080"
  }
}
```

Or with domain:
```json
{
  "screenshot_upload": {
    "enabled": true,
    "server_url": "https://screenshots.example.com"
  }
}
```

## Security Considerations

1. **Authentication:** This server has NO authentication. In production, add:
   - API key validation
   - JWT tokens
   - IP whitelisting

2. **HTTPS:** Always use HTTPS in production with SSL certificates

3. **File Validation:** The server validates file types and sizes, but consider:
   - Antivirus scanning
   - Image content validation
   - Rate limiting

4. **Storage:** Implement:
   - Disk space monitoring
   - Automatic cleanup of old files
   - Backup strategy

## Troubleshooting

### Port Already in Use
```bash
# Check what's using the port
netstat -tulpn | grep 8080

# Use different port
export PORT=8081
python screenshot_upload_server.py
```

### Permission Denied on Upload Directory
```bash
# Fix permissions
sudo chown -R $USER:$USER /var/www/screenshots
chmod -R 755 /var/www/screenshots
```

### Large File Uploads Failing
Increase limits in your reverse proxy (nginx/apache) or adjust `MAX_FILE_SIZE` in the code.

## License

This is part of the Employee Monitor System.
