#!/bin/bash
# Run cache warming as a one-shot job after RAG container starts
# Can be called manually or via cron/systemd

LOG_FILE="/var/log/rag_cache_warm.log"
LOCK_FILE="/tmp/cache_warm.lock"

# Prevent multiple simultaneous runs
if [ -f "$LOCK_FILE" ]; then
    echo "$(date): Cache warming already running, skipping" >> "$LOG_FILE"
    exit 0
fi
touch "$LOCK_FILE"
trap "rm -f $LOCK_FILE" EXIT

echo "$(date): Starting cache warming" >> "$LOG_FILE"

# Run from raganything container
docker exec -e RAG_API_URL="http://localhost:9621" \
  -e CHAINLIT_DB_HOST="postgres_chainlit" \
  raganything python3 /app/warm_cache.py --limit 20 --delay 1 >> "$LOG_FILE" 2>&1

echo "$(date): Cache warming complete" >> "$LOG_FILE"


