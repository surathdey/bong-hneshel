#!/usr/bin/env bash
# ==============================================================================
# Bong Hneshel — MongoDB Backup Script
# Creates a compressed, timestamped MongoDB archive.
# Run on EC2: ./backup_mongodb.sh
# ==============================================================================
set -e

# Configuration
PORT="${1:-27018}"
DB_NAME="${2:-bong_hneshel_db}"
BACKUP_DIR="/home/ec2-user/mongodb_backup"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.archive.gz"

mkdir -p "${BACKUP_DIR}"

echo "=================================================="
echo "📦 Starting MongoDB Backup: ${DB_NAME}"
echo "Port: ${PORT} | Target: ${BACKUP_FILE}"
echo "=================================================="

# Perform live compressed database dump
mongodump --port "${PORT}" --db "${DB_NAME}" --archive="${BACKUP_FILE}" --gzip

echo "✅ Backup successfully created!"
echo "   File: ${BACKUP_FILE}"
echo "   Size: $(du -h "${BACKUP_FILE}" | cut -f1)"
echo "------------------------------------------------=="
echo "👉 To download to your Mac, run from your MacBook terminal:"
echo "   scp -i ~/dev/app/aws/aws_linux_webapp.pem ec2-user@13.222.67.9:${BACKUP_FILE} ~/Desktop/"
