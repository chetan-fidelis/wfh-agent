# Quick Start Guide - WFH Agent Ingestion Server

## 🚀 Deploy in 5 Minutes

### Option 1: Automated Deployment (Recommended)

```bash
# 1. Upload files to your Ubuntu server
scp -r ingestion-server/ root@your-server:/tmp/

# 2. SSH into server
ssh root@your-server

# 3. Run deployment script
cd /tmp/ingestion-server
chmod +x deploy.sh
sudo ./deploy.sh

# Follow the prompts to enter your PostgreSQL credentials
# Script will automatically generate API key
```

### Option 2: Manual Deployment

```bash
# 1. Install dependencies
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nginx

# 2. Create user and directory
sudo useradd -m -s /bin/bash wfhagent
sudo mkdir -p /home/wfhagent/ingestion-server
sudo cp ingestion_server.py requirements.txt /home/wfhagent/ingestion-server/

# 3. Setup Python environment
sudo su - wfhagent
cd ~/ingestion-server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. Configure environment variables
nano ~/.env
```

Add to `.env`:
```bash
export WFH_AGENT_API_KEY="generate-with-python3-secrets-token"
export EMP_DB_URL="postgresql://user:pass@host:5432/employee_monitor"
export DB_SCHEMA="employee_monitor"
export PORT=5050
export SCREENSHOT_UPLOAD_DIR="/home/wfhagent/uploads"
```

```bash
# 5. Load environment and test
source ~/.env
python ingestion_server.py
```

---

## ✅ Verification

### 1. Check Health
```bash
curl http://localhost:5050/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "wfh-agent-ingestion",
  "database": "connected",
  "timestamp": "2025-10-03T10:30:00"
}
```

### 2. Test API (with authentication)
```bash
curl -X POST http://localhost:5050/api/ingest/heartbeat \
  -H "X-Api-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "emp_id": 1,
    "records": [{
      "emp_id": 1,
      "ts": "2025-10-03T10:00:00",
      "cpu_percent": 45.2,
      "mem_percent": 62.1,
      "net_sent_mb": 10.5,
      "net_recv_mb": 25.3,
      "fg_app": "chrome.exe",
      "fg_title": "Test",
      "idle_sec": 0,
      "active": true,
      "day_active_sec": 3600,
      "day_idle_sec": 300,
      "work_location": "remote",
      "battery_percent": 85,
      "battery_plugged": true,
      "country": "India",
      "ip_address": "192.168.1.10"
    }]
  }'
```

---

## 🌐 Setup Domain & SSL

### 1. Point Domain to Server
Create an A record:
```
ingest.your-domain.com → your-server-ip
```

### 2. Configure Nginx
```bash
sudo nano /etc/nginx/sites-available/wfh-ingestion
```

Paste:
```nginx
server {
    listen 80;
    server_name ingest.your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5050;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        client_max_body_size 50M;
    }
}
```

Enable:
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

## 💻 Configure Clients

### 1. Update config.json on employee machines
Edit `monitor_data/config.json`:

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

### 2. Set API Key on Employee Machines

**Windows:**
```cmd
setx WFH_AGENT_API_KEY "your-api-key-from-server"
```

**Or add to System Environment Variables:**
1. Search "Environment Variables" in Windows
2. Add new system variable:
   - Name: `WFH_AGENT_API_KEY`
   - Value: `your-api-key-from-server`
3. Restart WFH Agent application

---

## 📊 Monitor Server

### View Logs
```bash
sudo journalctl -u wfh-ingestion -f
```

### Service Status
```bash
sudo systemctl status wfh-ingestion
```

### Restart Service
```bash
sudo systemctl restart wfh-ingestion
```

---

## 🔒 Security Checklist

- ✅ Strong API key (32+ characters)
- ✅ HTTPS enabled (SSL certificate)
- ✅ Firewall configured (UFW)
- ✅ PostgreSQL password is strong
- ✅ Database credentials NOT in client config
- ✅ Regular system updates enabled

---

## 🆘 Troubleshooting

### Service won't start
```bash
sudo journalctl -u wfh-ingestion -xe
```

### Can't connect to database
```bash
# Test PostgreSQL connection
psql "postgresql://user:pass@host:5432/employee_monitor"
```

### Port already in use
```bash
sudo lsof -i :5050
sudo kill -9 <PID>
```

---

## 📞 Support

Email: support@fidelisgroup.in
