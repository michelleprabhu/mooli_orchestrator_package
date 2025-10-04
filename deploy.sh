#!/bin/bash
set -e

echo "🚀 MoolAI Controller Deployment Script"
echo "========================================"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
VM_IP="4.155.149.35"
VM_USER="michelleprabhu"
DEPLOY_DIR="/home/michelleprabhu/moolai"
GIT_REPO="https://github.com/YOUR_USERNAME/mooli_orchestrator_package.git"  # Update this!

echo -e "${YELLOW}Step 1: Stopping old services on VM...${NC}"
ssh ${VM_USER}@${VM_IP} << 'ENDSSH'
    # Stop old services
    echo "Stopping old processes..."
    sudo systemctl stop nginx 2>/dev/null || true
    pkill -f "python.*controller" || true
    pkill -f "node.*vite" || true
    
    # Stop and remove old Docker containers
    echo "Stopping old Docker containers..."
    docker stop $(docker ps -aq) 2>/dev/null || true
    docker rm $(docker ps -aq) 2>/dev/null || true
    
    echo "✓ Old services stopped"
ENDSSH

echo -e "${GREEN}✓ Old services stopped${NC}"

echo -e "${YELLOW}Step 2: Preparing deployment directory...${NC}"
ssh ${VM_USER}@${VM_IP} << 'ENDSSH'
    # Create deployment directory
    mkdir -p /home/michelleprabhu/moolai
    cd /home/michelleprabhu/moolai
    
    # Backup old deployment if exists
    if [ -d "mooli_orchestrator_package" ]; then
        echo "Backing up old deployment..."
        mv mooli_orchestrator_package mooli_orchestrator_package.backup.$(date +%Y%m%d_%H%M%S)
    fi
    
    echo "✓ Deployment directory ready"
ENDSSH

echo -e "${GREEN}✓ Deployment directory ready${NC}"

echo -e "${YELLOW}Step 3: Copying files to VM...${NC}"
# Copy entire project to VM
rsync -avz --exclude 'node_modules' \
           --exclude '__pycache__' \
           --exclude '.git' \
           --exclude 'controller/app/gui/frontend/dist' \
           ./ ${VM_USER}@${VM_IP}:${DEPLOY_DIR}/mooli_orchestrator_package/

echo -e "${GREEN}✓ Files copied${NC}"

echo -e "${YELLOW}Step 4: Building and starting Docker containers...${NC}"
ssh ${VM_USER}@${VM_IP} << 'ENDSSH'
    cd /home/michelleprabhu/moolai/mooli_orchestrator_package
    
    # Build and start containers
    echo "Building Docker images..."
    docker-compose build
    
    echo "Starting services..."
    docker-compose up -d
    
    # Wait for services to be healthy
    echo "Waiting for services to start..."
    sleep 10
    
    # Check status
    docker-compose ps
    
    echo "✓ Services started"
ENDSSH

echo -e "${GREEN}✓ Docker containers started${NC}"

echo -e "${YELLOW}Step 5: Verifying deployment...${NC}"
ssh ${VM_USER}@${VM_IP} << 'ENDSSH'
    cd /home/michelleprabhu/moolai/mooli_orchestrator_package
    
    # Check if services are running
    echo "Checking service health..."
    
    # Check controller
    if curl -s http://localhost:8765/health | grep -q "healthy"; then
        echo "✓ Controller is healthy"
    else
        echo "✗ Controller health check failed"
    fi
    
    # Check frontend
    if curl -s http://localhost:80 | grep -q "Mool AI"; then
        echo "✓ Frontend is serving"
    else
        echo "✗ Frontend check failed"
    fi
    
    # Show logs
    echo ""
    echo "Recent logs:"
    docker-compose logs --tail=20
ENDSSH

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Access your application at:"
echo "  🌐 Frontend: http://${VM_IP}"
echo "  🔌 API: http://${VM_IP}/api/v1/controller/health"
echo "  🔐 Login: http://${VM_IP}/login"
echo ""
echo "Useful commands:"
echo "  View logs: ssh ${VM_USER}@${VM_IP} 'cd ${DEPLOY_DIR}/mooli_orchestrator_package && docker-compose logs -f'"
echo "  Restart: ssh ${VM_USER}@${VM_IP} 'cd ${DEPLOY_DIR}/mooli_orchestrator_package && docker-compose restart'"
echo "  Stop: ssh ${VM_USER}@${VM_IP} 'cd ${DEPLOY_DIR}/mooli_orchestrator_package && docker-compose down'"
echo ""
