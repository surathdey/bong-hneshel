#!/usr/bin/env bash
# Run the full backend API test suite against a running backend.
#
# Usage:
#   ./run_api_tests.sh                       # tests http://localhost:8001
#   BASE_URL=https://your-host ./run_api_tests.sh
#
set -euo pipefail

export BASE_URL="${BASE_URL:-http://localhost:8001}"
export ADMIN_EMAIL="${ADMIN_EMAIL:-admin@bong-hneshel.ca}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-DDuCi!dZ0UmN3vXu}"

echo "==> Testing API at: $BASE_URL/api"
cd "$(dirname "$0")"
python -m pytest . "$@"
