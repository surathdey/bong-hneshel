#!/usr/bin/env bash
# ==============================================================================
# Bong Hneshel — MongoDB Local Restore Script
# Restores a backup archive into your local MongoDB on Mac.
# Usage:
#   ./restore_mongodb.sh                               # Restores latest backup from Desktop
#   ./restore_mongodb.sh path/to/custom_backup.archive.gz
# ==============================================================================
set -e

PORT="${MONGO_PORT:-27017}"
DB_NAME="${DB_NAME:-bong_hneshel_db}"

# Determine backup file: use argument if provided, otherwise find latest on Desktop
if [ -n "$1" ]; then
  ARCHIVE_FILE="$1"
else
  ARCHIVE_FILE=$(ls -t ~/Desktop/bong_hneshel_db_*.archive.gz ~/Desktop/*backup*.archive.gz 2>/dev/null | head -n 1 || true)
fi

if [ -z "$ARCHIVE_FILE" ] || [ ! -f "$ARCHIVE_FILE" ]; then
  echo "❌ Error: No backup archive found on ~/Desktop!"
  echo "👉 Please specify the path: $0 [path_to_backup_archive.archive.gz]"
  exit 1
fi

echo "=================================================="
echo "📥 Restoring MongoDB Database: ${DB_NAME}"
echo "Target Port:  ${PORT}"
echo "Source File:  ${ARCHIVE_FILE}"
echo "=================================================="

# Restore with --drop for a clean state
mongorestore --port "${PORT}" \
  --nsInclude="${DB_NAME}.*" \
  --archive="${ARCHIVE_FILE}" \
  --gzip \
  --drop

echo ""
echo "✅ MongoDB restore completed successfully into local ${DB_NAME} on port ${PORT}!"
