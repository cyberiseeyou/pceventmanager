#!/bin/bash
# Flask Schedule Webapp - Test Instance Startup Script
# This script starts an isolated test instance on port 8001
# Production instance on port 8000 remains unaffected

set -e

PROJECT_DIR="/home/elliot/flask-schedule-webapp"
cd "$PROJECT_DIR"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo "=========================================="
echo -e "${BLUE}Flask Schedule Webapp - TEST INSTANCE${NC}"
echo "=========================================="
echo ""

# Verify test database exists
if [ ! -f "instance/scheduler_test.db" ]; then
    echo -e "${RED}ERROR: Test database not found!${NC}"
    echo ""
    echo "Please run:"
    echo "  cp instance/scheduler.db instance/scheduler_test.db"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓${NC} Test database found: instance/scheduler_test.db"

# Verify test environment file exists
if [ ! -f ".env.test" ]; then
    echo -e "${RED}ERROR: .env.test configuration not found!${NC}"
    echo ""
    echo "Please create .env.test with test configuration"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓${NC} Test configuration found: .env.test"

# Activate virtual environment
if [ ! -d ".venv" ]; then
    echo -e "${RED}ERROR: Virtual environment not found!${NC}"
    echo ""
    echo "Please create virtual environment first:"
    echo "  python -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install -r requirements.txt"
    echo ""
    exit 1
fi

echo -e "${GREEN}✓${NC} Activating virtual environment"
source .venv/bin/activate

# Load test environment
echo -e "${GREEN}✓${NC} Loading test environment (.env.test)"
set -a
source .env.test
set +a

# Create log directory if it doesn't exist
mkdir -p logs

# Display configuration
echo ""
echo "=========================================="
echo -e "${YELLOW}TEST INSTANCE CONFIGURATION${NC}"
echo "=========================================="
echo -e "Port:         ${BLUE}8002${NC}"
echo -e "Database:     ${BLUE}instance/scheduler_test.db${NC}"
echo -e "Log file:     ${BLUE}logs/scheduler_test.log${NC}"
echo -e "Branch:       ${BLUE}$(git branch --show-current 2>/dev/null || echo 'unknown')${NC}"
echo -e "Sync:         ${BLUE}${SYNC_ENABLED}${NC}"
echo "=========================================="
echo ""
echo -e "${YELLOW}PRODUCTION INSTANCE (port 8000) REMAINS UNCHANGED${NC}"
echo ""
echo -e "Access test instance at: ${GREEN}http://localhost:8002${NC}"
echo -e "Monitor logs with: ${GREEN}tail -f logs/scheduler_test.log${NC}"
echo ""
echo "Press Ctrl+C to stop the test instance"
echo ""
echo "=========================================="
echo ""

# Run Flask development server
python wsgi.py
