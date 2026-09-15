#!/usr/bin/env bash
# switch-variant.sh — switch APP_VARIANT for dev preview.
# Usage:  ./switch-variant.sh customer   |   ./switch-variant.sh delivery
#
# Metro caches the resolved app.config.js at build time, so a plain expo restart
# is NOT enough to switch APP_VARIANT. This script:
#   1. Rewrites APP_VARIANT= line in /app/frontend/.env
#   2. Clears /app/frontend/.metro-cache
#   3. Restarts the expo supervisor service
#
# After ~15 seconds the preview will boot the requested variant.

set -euo pipefail

VARIANT="${1:-}"
if [[ "$VARIANT" != "customer" && "$VARIANT" != "delivery" ]]; then
  echo "Usage: $0 customer|delivery"
  exit 1
fi

ENV_FILE=/app/frontend/.env
if ! grep -q "^APP_VARIANT=" "$ENV_FILE"; then
  echo "APP_VARIANT=$VARIANT" >> "$ENV_FILE"
else
  sed -i "s|^APP_VARIANT=.*|APP_VARIANT=$VARIANT|" "$ENV_FILE"
fi

rm -rf /app/frontend/.metro-cache
sudo supervisorctl restart expo
echo "Switched to $VARIANT variant. Wait ~15s for the preview to reload."
