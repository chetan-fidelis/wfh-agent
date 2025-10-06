# WFH Agent - Data Ingestion Server

Secure PostgreSQL ingestion endpoint for WFH Agent employee monitoring data.
**No database credentials exposed to clients.**

## Features

- ✅ Secure API key authentication
- ✅ PostgreSQL connection pooling
- ✅ Batch data ingestion
- ✅ Screenshot uploads
- ✅ Health check endpoint
- ✅ Production-ready (Waitress WSGI server)

---

## Prerequisites

- **Ubuntu 20.04+** or any Linux distribution
- **Python 3.9+**
- **PostgreSQL 13+** (accessible from server)
- **Domain with SSL** (recommended for production)

---

## Installation on Ubuntu Server

### 1. Update System

```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Install Python and Dependencies

```bash
sudo apt install python3 python3-pip python3-venv nginx -y
```

### 3. Create Application User

```bash
sudo useradd -m -s /bin/bash wfhagent
sudo su - wfhagent
```

### 4. Setup Application Directory

```bash
mkdir -p ~/ingestion-server
cd ~/ingestion-server
```

### 5. Upload Files

Upload the following files to `~/ingestion-server/`:
- `ingestion_server.py`
- `requirements.txt`

```bash
# Or use scp from your local machine:
scp ingestion_server.py wfhagent@your-server:/home/wfhagent/ingestion-server/
scp requirements.txt wfhagent@your-server:/home/wfhagent/ingestion-server/
```

### 6. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 7. Configure Environment Variables

```bash
nano ~/.env
```

Add the following:

```bash
# API Security
export WFH_AGENT_API_KEY="your-secure-random-api-key-here-min-32-chars"

# Database Connection
export EMP_DB_URL="postgresql://postgres:password@localhost:5432/employee_monitor"
export DB_SCHEMA="employee_monitor"

# Server Configuration
export PORT=5050
export SCREENSHOT_UPLOAD_DIR="/home/wfhagent/uploads"
```

Save and exit (`Ctrl+X`, then `Y`, then `Enter`).

Generate a secure API key:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Load environment variables:
```bash
echo 'source ~/.env' >> ~/.bashrc
source ~/.env
```

---

## Running the Server

### Test Run (Development)

```bash
cd ~/ingestion-server
source venv/bin/activate
python ingestion_server.py
```

Visit: `http://your-server-ip:5050/health`

---

## Production Deployment

### 1. Create Systemd Service

Exit from wfhagent user:
```bash
exit  # Back to sudo user
```

Create service file:
```bash
sudo nano /etc/systemd/system/wfh-ingestion.service
```

Add the following:

```ini
[Unit]
Description=WFH Agent Data Ingestion Server
After=network.target postgresql.service

[Service]
Type=simple
User=wfhagent
Group=wfhagent
WorkingDirectory=/home/wfhagent/ingestion-server
Environment="PATH=/home/wfhagent/ingestion-server/venv/bin"
EnvironmentFile=/home/wfhagent/.env
ExecStart=/home/wfhagent/ingestion-server/venv/bin/python ingestion_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 2. Start and Enable Service

```bash
sudo systemctl daemon-reload
sudo systemctl start wfh-ingestion
sudo systemctl enable wfh-ingestion
sudo systemctl status wfh-ingestion
```

### 3. View Logs

```bash
sudo journalctl -u wfh-ingestion -f
```

---

## Nginx Reverse Proxy (Recommended)

### 1. Install Certbot for SSL

```bash
sudo apt install certbot python3-certbot-nginx -y
```

### 2. Configure Nginx

```bash
sudo nano /etc/nginx/sites-available/wfh-ingestion
```

Add:

```nginx
server {
    listen 80;
    server_name ingest.your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5050;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Increase timeout for large uploads
        proxy_connect_timeout 600;
        proxy_send_timeout 600;
        proxy_read_timeout 600;
        send_timeout 600;

        # Increase max upload size
        client_max_body_size 50M;
    }
}
```

Enable site:
```bash
sudo ln -s /etc/nginx/sites-available/wfh-ingestion /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 3. Get SSL Certificate

```bash
sudo certbot --nginx -d ingest.your-domain.com
```

---

## Firewall Configuration

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp
sudo ufw enable
```

---

## API Endpoints

### Health Check (No Auth)
```http
GET /health
```

### Heartbeat Ingestion
```http
POST /api/ingest/heartbeat
Headers: X-Api-Key: your-api-key
Body: {
  "emp_id": 123,
  "records": [
    {
      "emp_id": 123,
      "ts": "2025-10-03T10:00:00",
      "cpu_percent": 45.2,
      "mem_percent": 62.1,
      ...
    }
  ]
}
```

### Website Usage
```http
POST /api/ingest/website_usage
Headers: X-Api-Key: your-api-key
```

### Work Sessions
```http
POST /api/ingest/work_sessions
Headers: X-Api-Key: your-api-key
```

### Screenshot Upload
```http
POST /api/upload/screenshot
Headers: X-Api-Key: your-api-key
FormData:
  - file (or screenshot): image file (JPEG/PNG)
  - emp_id: Employee ID
  - timestamp: Format YYYYMMDD_HHMMSS
  - captured_at: ISO datetime (optional)

Response: {
  "success": true,
  "id": 123,
  "url": "screenshot/123/2025-10-04/filename.jpg",
  "file_name": "filename.jpg",
  "file_size": 45678,
  "file_hash": "md5-hash"
}
```

### List Screenshots
```http
GET /api/screenshots/<emp_id>?date=2025-10-04&limit=100
Headers: X-Api-Key: your-api-key

Response: {
  "success": true,
  "emp_id": 123,
  "screenshots": [
    {
      "url": "screenshot/123/2025-10-04/filename.jpg",
      "filename": "filename.jpg",
      "date": "2025-10-04",
      "size": 45678,
      "created_at": "2025-10-04T10:00:00",
      "modified_at": "2025-10-04T10:00:00"
    }
  ],
  "count": 1
}
```

### Screenshot Statistics
```http
GET /api/screenshots/stats
Headers: X-Api-Key: your-api-key

Response: {
  "success": true,
  "stats": {
    "total_screenshots": 150,
    "total_size_bytes": 12345678,
    "total_size_mb": 11.77,
    "total_employees": 5,
    "upload_directory": "./uploads"
  }
}
```

### Generic Batch
```http
POST /api/ingest/batch
Headers: X-Api-Key: your-api-key
Body: {
  "table": "heartbeat",
  "records": [...]
}
```

---

## Client Configuration

Update `monitor_data/config.json` on employee machines:

```json
{
  "ingestion": {
    "enabled": true,
    "mode": "api",
    "api": {
      "base_url": "https://ingest.your-domain.com",
      "auth_header": "X-Api-Key",
      "auth_env": "WFH_AGENT_API_KEY"
    }
  },
  "screenshot_upload": {
    "enabled": true,
    "server_url": "https://ingest.your-domain.com"
  }
}
```

Set environment variable on client machines:
```bash
# Windows
setx WFH_AGENT_API_KEY "your-api-key"

# Or add to system environment variables
```

---

## Monitoring & Maintenance

### Check Service Status
```bash
sudo systemctl status wfh-ingestion
```

### View Logs
```bash
sudo journalctl -u wfh-ingestion -n 100 --no-pager
```

### Restart Service
```bash
sudo systemctl restart wfh-ingestion
```

### Update Code
```bash
sudo su - wfhagent
cd ~/ingestion-server
source venv/bin/activate
git pull  # or upload new files
sudo systemctl restart wfh-ingestion
```

---

## Security Best Practices

1. **Use Strong API Keys** - Minimum 32 characters
2. **Enable HTTPS** - Always use SSL in production
3. **Firewall Rules** - Only allow necessary ports
4. **Regular Updates** - Keep system packages updated
5. **Database Security** - Use strong PostgreSQL passwords
6. **Rate Limiting** - Consider adding nginx rate limits
7. **Log Monitoring** - Set up log rotation and monitoring

---

## Troubleshooting

### Service Won't Start
```bash
sudo journalctl -u wfh-ingestion -xe
```

### Database Connection Failed
```bash
# Test PostgreSQL connection
psql "postgresql://user:pass@host:5432/employee_monitor"
```

### Port Already in Use
```bash
sudo lsof -i :5050
# Kill process or change PORT in .env
```

### Permission Denied
```bash
sudo chown -R wfhagent:wfhagent /home/wfhagent/ingestion-server
```

---

## Support

For issues, contact: support@fidelisgroup.in
