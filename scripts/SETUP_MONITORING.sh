#!/bin/bash
##################################################
# Revive Battery - Complete Monitoring Setup
# Run this once to setup all monitoring tools
##################################################

echo "🔋 Setting up Revive Battery Monitoring..."
echo ""

# 1. Status Dashboard
echo "📊 [1/3] Setting up Status Dashboard..."
cd /root/monitoring
docker compose up -d
echo "   ✅ Available at: https://status.srv1178070.hstgr.cloud"
echo ""

# 2. PgAdmin
echo "🗄️  [2/3] Setting up PgAdmin (Database GUI)..."
cd /root
docker compose -f pgadmin-docker-compose.yml up -d
sleep 5
echo "   ✅ Available at: https://pgadmin.srv1178070.hstgr.cloud"
echo "   📧 Login: admin@revivebattery.eu"
echo "   🔑 Password: ReviveAdmin2025!"
echo ""

# 3. Health Check Script
echo "🏥 [3/3] Testing Health Check..."
/root/monitoring/health_check.sh
echo ""

echo "=========================================="
echo "✅ MONITORING SETUP COMPLETE!"
echo "=========================================="
echo ""
echo "📱 YOUR MONITORING TOOLS:"
echo ""
echo "1️⃣  Status Dashboard (No login needed):"
echo "   https://status.srv1178070.hstgr.cloud"
echo ""
echo "2️⃣  PgAdmin (Database viewer):"
echo "   https://pgadmin.srv1178070.hstgr.cloud"
echo "   Login: admin@revivebattery.eu / ReviveAdmin2025!"
echo ""
echo "3️⃣  Chainlit (Main chat app):"
echo "   https://chat.srv1178070.hstgr.cloud"
echo ""
echo "4️⃣  RAG WebUI:"
echo "   https://rag.srv1178070.hstgr.cloud"
echo ""
echo "🔧 Quick health check anytime:"
echo "   /root/monitoring/health_check.sh"
echo ""
echo "=========================================="
echo "🎉 Ready for production delivery!"
echo "=========================================="





