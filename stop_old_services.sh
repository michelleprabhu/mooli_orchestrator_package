#!/bin/bash
# Script to stop old services on Azure VM

echo "🛑 Stopping Old MoolAI Services"
echo "================================"

# Stop the systemd service if it exists
echo "1. Stopping controller-api systemd service..."
sudo systemctl stop controller-api 2>/dev/null || echo "  - Service not found or already stopped"
sudo systemctl disable controller-api 2>/dev/null || echo "  - Service not enabled"

# Stop nginx
echo "2. Stopping nginx..."
sudo systemctl stop nginx 2>/dev/null || echo "  - Nginx not running"

# Kill the Python processes
echo "3. Stopping Python processes..."
# Kill the uvicorn process (port 8765)
sudo pkill -f "uvicorn services.controller.app.main" || echo "  - Uvicorn not running"

# Kill the ws_server process
sudo pkill -f "app.ws_server" || echo "  - ws_server not running"

# Double check - kill any remaining Python processes on port 8765
echo "4. Checking for processes on port 8765..."
sudo lsof -ti:8765 | xargs -r sudo kill -9 2>/dev/null || echo "  - No processes on port 8765"

# Check for processes on port 80
echo "5. Checking for processes on port 80..."
sudo lsof -ti:80 | xargs -r sudo kill -9 2>/dev/null || echo "  - No processes on port 80"

# Verify everything is stopped
echo ""
echo "✓ Verification:"
echo "  Checking Python processes..."
ps aux | grep -E "(uvicorn|ws_server)" | grep -v grep || echo "  ✓ No Python services running"

echo "  Checking nginx..."
ps aux | grep nginx | grep -v grep || echo "  ✓ Nginx stopped"

echo "  Checking port 8765..."
sudo lsof -i:8765 || echo "  ✓ Port 8765 is free"

echo "  Checking port 80..."
sudo lsof -i:80 || echo "  ✓ Port 80 is free"

echo ""
echo "✅ All old services stopped!"
echo ""
