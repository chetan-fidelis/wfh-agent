#!/bin/bash
# WFH Agent Ingestion Server - Quick Deployment Script
# Run as: sudo bash deploy.sh

set -e

echo "======================================"
echo "WFH Agent Ingestion Server Deployment"
echo "======================================"
echo

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)"
   exit 1
fi

# Update system
echo "[1/8] Updating system packages..."
apt update && apt upgrade -y

# Install dependencies
echo "[2/8] Installing dependencies..."
apt install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx

# Create application user
echo "[3/8] Creating application user..."
if id "wfhagent" &>/dev/null; then
    echo "User wfhagent already exists"
else
    useradd -m -s /bin/bash wfhagent
    echo "User wfhagent created"
fi

# Setup application directory
echo "[4/8] Setting up application directory..."
mkdir -p /home/wfhagent/ingestion-server
cp ingestion_server.py /home/wfhagent/ingestion-server/
cp requirements.txt /home/wfhagent/ingestion-server/
chown -R wfhagent:wfhagent /home/wfhagent/ingestion-server

# Create virtual environment and install dependencies
echo "[5/8] Creating Python virtual environment..."
sudo -u wfhagent bash << EOF
cd /home/wfhagent/ingestion-server
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
EOF

# Configure environment variables
echo "[6/8] Configuring environment variables..."
echo
read -p "Enter PostgreSQL Database URL (e.g., postgresql://user:pass@host:5432/db): " DB_URL
read -p "Enter Database Schema [employee_monitor]: " DB_SCHEMA
DB_SCHEMA=${DB_SCHEMA:-employee_monitor}

# Generate API key
API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

cat > /home/wfhagent/.env << EOF
# WFH Agent Ingestion Server Configuration
export WFH_AGENT_API_KEY="$API_KEY"
export EMP_DB_URL="$DB_URL"
export DB_SCHEMA="$DB_SCHEMA"
export PORT=5050
export SCREENSHOT_UPLOAD_DIR="/home/wfhagent/uploads"
EOF

# Create uploads directory
mkdir -p /home/wfhagent/uploads
chown -R wfhagent:wfhagent /home/wfhagent/uploads

chown wfhagent:wfhagent /home/wfhagent/.env
chmod 600 /home/wfhagent/.env

echo "source ~/.env" >> /home/wfhagent/.bashrc

# Create systemd service
echo "[7/8] Creating systemd service..."
cat > /etc/systemd/system/wfh-ingestion.service << 'EOF'
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
EOF

# Start service
echo "[8/8] Starting service..."
systemctl daemon-reload
systemctl enable wfh-ingestion
systemctl start wfh-ingestion

# Configure firewall
echo "Configuring firewall..."
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 22/tcp
ufw --force enable

echo
echo "======================================"
echo "✅ Deployment Complete!"
echo "======================================"
echo
echo "📋 Service Status:"
systemctl status wfh-ingestion --no-pager
echo
echo "🔑 API Key (save this!):"
echo "   $API_KEY"
echo
echo "📝 Next Steps:"
echo "   1. Configure nginx reverse proxy (see README.md)"
echo "   2. Setup SSL certificate with certbot"
echo "   3. Update client config.json with:"
echo "      - base_url: https://your-domain.com"
echo "      - API Key: $API_KEY"
echo
echo "📊 Check logs:"
echo "   sudo journalctl -u wfh-ingestion -f"
echo
echo "🌐 Test health check:"
echo "   curl http://localhost:5050/health"
echo
