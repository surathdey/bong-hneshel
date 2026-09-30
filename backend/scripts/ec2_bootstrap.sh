#!/usr/bin/env bash
# ==============================================================================
# Bong Hneshel — EC2 Bootstrap & MongoDB Setup Helper Script
# ==============================================================================
set -e

MONGO_PORT="${1:-27018}"
APP_USER="${2:-ec2-user}"
APP_ROOT="/app/restaurant/bong-hneshel"
BACKEND_DIR="${APP_ROOT}/backend"

echo "=================================================="
echo "🚀 Bootstrapping Bong Hneshel on EC2"
echo "MongoDB Port: ${MONGO_PORT} | App User: ${APP_USER}"
echo "=================================================="

# 1. Ensure Directories Exist
echo "📁 Setting up directory layout..."
sudo mkdir -p "${BACKEND_DIR}/uploads" "${BACKEND_DIR}/scripts" "${BACKEND_DIR}/tools" "${BACKEND_DIR}/web_dist"
sudo chown -R "${APP_USER}:${APP_USER}" "${APP_ROOT}"

# 2. Install MongoDB
if ! command -v mongod &> /dev/null; then
  echo "📦 Installing MongoDB Community Edition..."
  if [ -f /etc/os-release ]; then
    . /etc/os-release
    if [[ "$ID" == "amzn" ]] || [[ "$ID_LIKE" =~ "rhel" ]]; then
      sudo tee /etc/yum.repos.d/mongodb-org-7.0.repo << 'EOF'
[mongodb-org-7.0]
name=MongoDB Repository
baseurl=https://repo.mongodb.org/yum/amazon/2023/mongodb-org/7.0/x86_64/
gpgcheck=1
enabled=1
gpgkey=https://pgp.mongodb.com/server-7.0.asc
EOF
      sudo dnf install -y mongodb-org || sudo yum install -y mongodb-org
    elif [[ "$ID" == "ubuntu" ]] || [[ "$ID_LIKE" =~ "debian" ]]; then
      sudo apt-get update && sudo apt-get install -y gnupg curl
      curl -fsSL https://pgp.mongodb.com/server-7.0.asc | sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
      echo 'deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse' | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list
      sudo apt-get update && sudo apt-get install -y mongodb-org
    fi
  fi
fi

# 3. Configure & Enable MongoDB Service
if [ "$MONGO_PORT" != "27017" ] && [ -f /etc/mongod.conf ]; then
  echo "⚙️ Configuring MongoDB to listen on port ${MONGO_PORT}..."
  sudo sed -i "s/port: 27017/port: ${MONGO_PORT}/g" /etc/mongod.conf || true
fi

sudo systemctl enable mongod
sudo systemctl restart mongod
echo "✅ MongoDB service active:"
sudo systemctl status mongod --no-pager

# 4. Install System Dependencies & Setup Python Virtual Environment
echo "🐍 Setting up Python virtual environment..."
if ! command -v python3 &> /dev/null; then
  if command -v dnf &> /dev/null; then
    sudo dnf install -y python3 python3-pip
  else
    sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv
  fi
fi

cd "${BACKEND_DIR}"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip
if [ -f "requirements.txt" ]; then
  .venv/bin/pip install -r requirements.txt
fi

# 5. Configure Systemd Service
echo "🔧 Installing systemd service: /etc/systemd/system/bong-hneshel.service..."
sudo tee /etc/systemd/system/bong-hneshel.service > /dev/null << EOF
[Unit]
Description=Bong Hneshel FastAPI Backend Service
After=network.target mongod.service

[Service]
Type=simple
User=${APP_USER}
WorkingDirectory=${BACKEND_DIR}
ExecStart=${BACKEND_DIR}/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8002
Restart=always
RestartSec=5
EnvironmentFile=${BACKEND_DIR}/.env
StandardOutput=append:${BACKEND_DIR}/backend.log
StandardError=append:${BACKEND_DIR}/backend.log

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable bong-hneshel
sudo systemctl restart bong-hneshel
echo "✅ Bong Hneshel service active and running!"
