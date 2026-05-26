#!/bin/bash
# Start RQ worker
set -e

echo "⚙️  Starting LicenseGuard RQ Worker..."
python -m rq worker --url "${REDIS_URL:-redis://localhost:6379/0}" scans