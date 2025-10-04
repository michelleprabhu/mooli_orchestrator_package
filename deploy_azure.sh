#!/bin/bash
set -e

echo "🚀 MoolAI Controller - Azure Deployment"
echo "========================================"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
VM_IP="4.155.149.35"
VM_USER="azureuser"
SSH_KEY="~/Desktop/Controller_key.pem"
DEPLOY_DIR="/home/azureuser/moolai"

echo -e "${YELLOW}Step 1: Stopping old services on VM...${NC}"
ssh -i ${SSH_KEY} ${VM_USER}@${VM_IP} 'bash -s' < stop_old_services.sh

echo -e "${GREEN}✓ Old services stopped${NC}"

echo -e "${YELLOW}Step 2: Installing Docker (if not installed)...${NC}"
ssh -i ${SSH_KEY} ${VM_USER}@${VM_IP} << 'ENDSSH'
    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        echo "Installing Docker..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sudo sh get-docker.sh
        sudo usermod -aG docker $USER
        echo "✓ Docker installed"
    else
        echo "✓ Docker already installed"
    fi
    
    # Check if Docker Compose is installed
    if ! command -v docker-compose &> /dev/null; then
        echo "Installing Docker Compose..."
        sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        sudo chmod +x /usr/local/bin/docker-compose
        echo "✓ Docker Compose installed"
    else
        echo "✓ Docker Compose already installed"
    fi
ENDSSH

echo -e "${GREEN}✓ Docker setup complete${NC}"

echo -e "${YELLOW}Step 3: Preparing deployment directory...${NC}"
ssh -i ${SSH_KEY} ${VM_USER}@${VM_IP} << 'ENDSSH'
    # Create deployment directory
    mkdir -p /home/azureuser/moolai
    cd /home/azureuser/moolai
    
    # Backup old deployment if exists
    if [ -d "mooli_orchestrator_package" ]; then
        echo "Backing up old deployment..."
        sudo mv mooli_orchestrator_package mooli_orchestrator_package.backup.$(date +%Y%m%d_%H%M%S) 2>/dev/null || true
    fi
    
    mkdir -p mooli_orchestrator_package
    echo "✓ Deployment directory ready"
ENDSSH

echo -e "${GREEN}✓ Deployment directory ready${NC}"

echo -e "${YELLOW}Step 4: Copying files to VM...${NC}"
# Copy entire project to VM
rsync -avz -e "ssh -i ${SSH_KEY}" \
           --exclude 'node_modules' \
           --exclude '__pycache__' \
           --exclude '.git' \
           --exclude 'controller/app/gui/frontend/dist' \
           --exclude 'controller/app/gui/frontend/node_modules' \
           ./ ${VM_USER}@${VM_IP}:${DEPLOY_DIR}/mooli_orchestrator_package/

echo -e "${GREEN}✓ Files copied${NC}"

echo -e "${YELLOW}Step 5: Building and starting Docker containers...${NC}"
ssh -i ${SSH_KEY} ${VM_USER}@${VM_IP} << 'ENDSSH'
    cd /home/azureuser/moolai/mooli_orchestrator_package
    
    # Stop any existing containers
    docker-compose down 2>/dev/null || true
    
    # Build and start containers
    echo "Building Docker images (this may take a few minutes)..."
    docker-compose build --no-cache
    
    echo "Starting services..."
    docker-compose up -d
    
    # Wait for services to be healthy
    echo "Waiting for services to start..."
    sleep 15
    
    # Check status
    echo ""
    echo "Container status:"
    docker-compose ps
    
    echo ""
    echo "✓ Services started"
ENDSSH

echo -e "${GREEN}✓ Docker containers started${NC}"

echo -e "${YELLOW}Step 6: Verifying deployment...${NC}"
ssh -i ${SSH_KEY} ${VM_USER}@${VM_IP} << 'ENDSSH'
    cd /home/azureuser/moolai/mooli_orchestrator_package
    
    # Check if services are running
    echo "Checking service health..."
    sleep 5
    
    # Check controller
    if curl -s http://localhost:8765/health | grep -q "healthy"; then
        echo "✓ Controller is healthy"
    else
        echo "⚠ Controller health check failed (may still be starting)"
    fi
    
    # Check frontend
    if curl -s http://localhost:80 | grep -q "html"; then
        echo "✓ Frontend is serving"
    else
        echo "⚠ Frontend check failed (may still be starting)"
    fi
    
    # Show recent logs
    echo ""
    echo "Recent logs:"
    echo "============"
    docker-compose logs --tail=30
ENDSSH

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Access your application at:"
echo "  🌐 Frontend: http://${VM_IP}"
echo "  🔐 Login: http://${VM_IP}/login"
echo "  🔌 API Health: http://${VM_IP}/api/v1/controller/health"
echo ""
echo "Login credentials:"
echo "  Username: michelleprabhu"
echo "  Password: password123"
echo ""
echo "Useful commands:"
echo "  SSH to VM:"
echo "    ssh -i ${SSH_KEY} ${VM_USER}@${VM_IP}"
echo ""
echo "  View logs:"
echo "    ssh -i ${SSH_KEY} ${VM_USER}@${VM_IP} 'cd ${DEPLOY_DIR}/mooli_orchestrator_package && docker-compose logs -f'"
echo ""
echo "  Restart services:"
echo "    ssh -i ${SSH_KEY} ${VM_USER}@${VM_IP} 'cd ${DEPLOY_DIR}/mooli_orchestrator_package && docker-compose restart'"
echo ""
echo "  Stop services:"
echo "    ssh -i ${SSH_KEY} ${VM_USER}@${VM_IP} 'cd ${DEPLOY_DIR}/mooli_orchestrator_package && docker-compose down'"
echo ""
echo "  Check status:"
echo "    ssh -i ${SSH_KEY} ${VM_USER}@${VM_IP} 'cd ${DEPLOY_DIR}/mooli_orchestrator_package && docker-compose ps'"
echo ""
