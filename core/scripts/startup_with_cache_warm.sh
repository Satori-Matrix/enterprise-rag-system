#!/bin/bash
# Startup script that warms cache after RAG server is ready
# This script is designed to be run as a sidecar or post-startup hook

set -e

RAG_API_URL="${RAG_API_URL:-http://raganything:9621}"
MAX_WAIT=120  # Max seconds to wait for RAG API

echo "🚀 Cache Warming Startup Script"
echo "   Waiting for RAG API at $RAG_API_URL..."

# Wait for RAG API to be ready
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -s "$RAG_API_URL/health" > /dev/null 2>&1; then
        echo "✅ RAG API is ready after ${WAITED}s"
        break
    fi
    sleep 5
    WAITED=$((WAITED + 5))
    echo "   Waiting... (${WAITED}s)"
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo "❌ RAG API not ready after ${MAX_WAIT}s. Skipping cache warm."
    exit 1
fi

# Wait a bit more for model to be fully loaded
echo "   Waiting 10s for model initialization..."
sleep 10

# Run cache warming
echo ""
echo "🔥 Starting cache warming..."
cd /app/scripts
python3 warm_cache.py --limit 20 --delay 1

echo ""
echo "✅ Cache warming complete"


