#!/usr/bin/env bash
# ==============================================================================
# Bong Hneshel — Download MongoDB Backups from EC2 to Local Mac
# Run on MacBook: ./from_aws_to_local.sh
# ==============================================================================
set -e

HOST="13.222.67.9"
USER="ec2-user"
PEM_FILE="${HOME}/dev/app/aws/aws_linux_webapp.pem"
SERVER_BACKUP_FOLDER="/home/ec2-user/mongodb_backup"
LOCAL_DESTINATION="${1:-${HOME}/Desktop}"

echo "=================================================="
echo "📥 Downloading MongoDB Backups from EC2 -> Local Mac"
echo "Source:      ${USER}@${HOST}:${SERVER_BACKUP_FOLDER}"
echo "Destination: ${LOCAL_DESTINATION}"
echo "=================================================="

# Copy all archive files from the EC2 backup folder to local Mac
scp -i "${PEM_FILE}" "${USER}@${HOST}:${SERVER_BACKUP_FOLDER}/*.archive.gz" "${LOCAL_DESTINATION}/"

echo ""
echo "✅ Download complete! Files saved to: ${LOCAL_DESTINATION}"
