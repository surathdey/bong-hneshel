#!/bin/bash
# ==============================================================================
# Bong Hneshel — AWS Deployment & File Sync Script
# Usage:
#   ./copy_to_aws.sh             (Runs default or active scp transfers)
#   ./copy_to_aws.sh all         (Syncs backend, config, nginx, and web_dist)
#   ./copy_to_aws.sh backend     (Syncs all Python backend code & scripts)
#   ./copy_to_aws.sh nginx       (Syncs nginx.conf and reloads nginx)
#   ./copy_to_aws.sh web         (Syncs web_dist frontend SPA build)
# ==============================================================================

set -e

HOST="13.222.67.9"
PEM_FILE="${HOME}/dev/app/aws/aws_linux_webapp.pem"
USER="ec2-user"

SERVER_ROOT_FOLDER="/app/restaurant/bong-hneshel"
SERVER_BACKEND_FOLDER="/app/restaurant/bong-hneshel/backend"
NGINX_REMOTE_PATH="/app/webapp_tss/client_server/nginx/nginx.conf"

SSH_CMD="ssh -i ${PEM_FILE} ${USER}@${HOST}"
SCP_CMD="scp -i ${PEM_FILE}"

echo "=================================================="
echo "🚀 Bong Hneshel AWS Sync -> ${USER}@${HOST}"
echo "=================================================="

# Function to ensure remote directories exist
ensure_remote_dirs() {
  echo "📁 Ensuring remote directories exist..."
  ${SSH_CMD} "mkdir -p ${SERVER_ROOT_FOLDER} ${SERVER_BACKEND_FOLDER}/scripts ${SERVER_BACKEND_FOLDER}/tools ${SERVER_BACKEND_FOLDER}/uploads ${SERVER_BACKEND_FOLDER}/web_dist"
}

# ------------------------------------------------------------------------------
# 1. Configuration & Environment
# ------------------------------------------------------------------------------
copy_config() {
  echo "⚙️  Copying configuration & env files..."
  # Brand JSON definition (copied to both root and backend directory for fallback resilience)
  if [ -f "../brand.json" ]; then
    ${SCP_CMD} ../brand.json ${USER}@${HOST}:${SERVER_ROOT_FOLDER}/
    ${SCP_CMD} ../brand.json ${USER}@${HOST}:${SERVER_BACKEND_FOLDER}/
  elif [ -f "./brand.json" ]; then
    ${SCP_CMD} ./brand.json ${USER}@${HOST}:${SERVER_BACKEND_FOLDER}/
  fi

  # Backend environment file (.env)
  if [ -f "./.env" ]; then
    ${SCP_CMD} ./.env ${USER}@${HOST}:${SERVER_BACKEND_FOLDER}/
  else
    echo "⚠️  No local .env file found in backend directory. Skipping .env copy."
  fi

  # Python Dependencies
  ${SCP_CMD} ./requirements.txt ${USER}@${HOST}:${SERVER_BACKEND_FOLDER}/
}

# ------------------------------------------------------------------------------
# 2. Core Backend Application & Client Modules
# ------------------------------------------------------------------------------
copy_backend_code() {
  echo "🐍 Copying Core FastAPI Backend & Client Modules..."
  ${SCP_CMD} \
    ./server.py \
    ./brand.py \
    ./billing_client.py \
    ./platform_client.py \
    ./menu_ai.py \
    ./drive_client.py \
    ./email_client.py \
    ./exports.py \
    ./settings_crypto.py \
    ./twilio_client.py \
    ${USER}@${HOST}:${SERVER_BACKEND_FOLDER}/
}

# ------------------------------------------------------------------------------
# 3. Catalog Data & Seeding / Migration Scripts
# ------------------------------------------------------------------------------
copy_data_scripts() {
  echo "📦 Copying Product Catalog & Data Migration Scripts..."
  ${SCP_CMD} \
    ./bong_products.csv \
    ./seed_bong_products.py \
    ./build_mg_menu.py \
    ./build_weekly.py \
    ./fix_mg_images.py \
    ./fix_mg_text.py \
    ./gen_login_bg.py \
    ${USER}@${HOST}:${SERVER_BACKEND_FOLDER}/
}

# ------------------------------------------------------------------------------
# 4. Service Lifecycle & Process Scripts
# ------------------------------------------------------------------------------
copy_service_scripts() {
  echo "🔧 Copying Service Control Scripts (start / stop / run)..."
  ${SCP_CMD} \
    ./start.sh \
    ./stop.sh \
    ./run.sh \
    ${USER}@${HOST}:${SERVER_BACKEND_FOLDER}/

  # Ensure scripts are executable on remote host
  ${SSH_CMD} "chmod +x ${SERVER_BACKEND_FOLDER}/start.sh ${SERVER_BACKEND_FOLDER}/stop.sh ${SERVER_BACKEND_FOLDER}/run.sh"
}

# ------------------------------------------------------------------------------
# 5. Backend Subdirectories (scripts & tools)
# ------------------------------------------------------------------------------
copy_subdirectories() {
  echo "📂 Copying scripts/ and tools/ directories..."
  if [ -d "./scripts" ]; then
    ${SCP_CMD} -r ./scripts/* ${USER}@${HOST}:${SERVER_BACKEND_FOLDER}/scripts/
  fi
  if [ -d "./tools" ]; then
    ${SCP_CMD} -r ./tools/* ${USER}@${HOST}:${SERVER_BACKEND_FOLDER}/tools/
  fi
}

# ------------------------------------------------------------------------------
# 6. Frontend Web Distribution (SPA Assets for Nginx)
# ------------------------------------------------------------------------------
copy_web_dist() {
  echo "🌐 Copying Frontend Web Distribution (web_dist)..."
  if [ -d "./web_dist" ]; then
    ${SCP_CMD} -r ./web_dist/* ${USER}@${HOST}:${SERVER_BACKEND_FOLDER}/web_dist/
  elif [ -f "./dist.zip" ]; then
    ${SCP_CMD} ./dist.zip ${USER}@${HOST}:${SERVER_BACKEND_FOLDER}/
    ${SSH_CMD} "unzip -o ${SERVER_BACKEND_FOLDER}/dist.zip -d ${SERVER_BACKEND_FOLDER}/web_dist/"
  else
    echo "⚠️  Neither web_dist directory nor dist.zip found. Skipping web dist copy."
  fi
}

# ------------------------------------------------------------------------------
# 7. Nginx Configuration
# ------------------------------------------------------------------------------
copy_nginx() {
  echo "🌐 Deploying Nginx configuration..."
  ${SCP_CMD} ./nginx.conf ${USER}@${HOST}:${NGINX_REMOTE_PATH}
  echo "🔄 Testing and reloading Nginx on server..."
  ${SSH_CMD} "sudo nginx -t && sudo systemctl reload nginx || sudo nginx -s reload"
}

# ------------------------------------------------------------------------------
# Execution Logic
# ------------------------------------------------------------------------------
TARGET="${1:-all}"

case "${TARGET}" in
  "all")
    ensure_remote_dirs
    copy_config
    copy_backend_code
    copy_data_scripts
    copy_service_scripts
    copy_subdirectories
    copy_web_dist
    copy_nginx
    echo "✅ All files successfully deployed to AWS!"
    ;;
  "backend")
    ensure_remote_dirs
    copy_config
    copy_backend_code
    copy_data_scripts
    copy_service_scripts
    copy_subdirectories
    echo "✅ Backend files successfully deployed to AWS!"
    ;;
  "nginx")
    copy_nginx
    echo "✅ Nginx configuration deployed and reloaded!"
    ;;
  "web")
    ensure_remote_dirs
    copy_web_dist
    echo "✅ Web distribution successfully deployed!"
    ;;
  "config")
    ensure_remote_dirs
    copy_config
    echo "✅ Configuration files copied!"
    ;;
  *)
    echo "Usage: $0 {all|backend|nginx|web|config}"
    exit 1
    ;;
esac
