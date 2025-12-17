#!/bin/bash
#########################################
# Revive Battery System Health Check
# Quick diagnostic script
#########################################

echo "🔋 Revive Battery - System Health Check"
echo "========================================"
echo ""

# Check Docker containers
echo "📦 Docker Containers:"
docker ps --format "table {{.Names}}\t{{.Status}}" | grep -E "chainlit|postgres|raganything|ollama|traefik"
echo ""

# Check RAG API health
echo "🔌 RAG API Status:"
response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:9621/health 2>/dev/null)
if [ "$response" = "200" ]; then
    echo "✅ RAG API: ONLINE"
else
    echo "❌ RAG API: OFFLINE (HTTP $response)"
fi
echo ""

# Check databases
echo "💾 Database Status:"
docker exec postgres_rag psql -U raguser -d ragdb -c "SELECT COUNT(*) as chunks FROM lightrag_vdb_chunks;" -t 2>/dev/null | xargs echo "  RAG DB chunks:"
docker exec postgres_chainlit psql -U chainlit -d chainlit_db -c 'SELECT COUNT(*) as messages FROM "Step";' -t 2>/dev/null | xargs echo "  Chat messages:"
echo ""

# Check disk space
echo "💿 Disk Space:"
df -h / | tail -1 | awk '{print "  Used: "$3" / "$2" ("$5" full)"}'
echo ""

# Check memory
echo "🧠 Memory Usage:"
free -h | grep Mem | awk '{print "  Used: "$3" / "$2}'
echo ""

# Check recent errors in logs
echo "🚨 Recent Errors (last 5):"
docker logs chainlit_revive --tail 100 2>/dev/null | grep -i "error\|exception" | tail -5 || echo "  ✅ No recent errors"
echo ""

echo "========================================"
echo "✅ Health check complete!"
echo "Run again: /root/monitoring/health_check.sh"





