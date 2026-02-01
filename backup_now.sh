#!/bin/bash
# Flask Schedule Webapp - Manual Backup Wrapper
# Run database backup manually for testing

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
echo -e "${BLUE}Manual Database Backup${NC}"
echo "=========================================="
echo ""

# Check if virtual environment exists
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

# Activate virtual environment
source .venv/bin/activate

# Run backup script
echo "Running backup script..."
echo ""

python scripts/backup_database.py

BACKUP_STATUS=$?

echo ""

if [ $BACKUP_STATUS -eq 0 ]; then
    echo "=========================================="
    echo -e "${GREEN}✓ Backup successful!${NC}"
    echo "=========================================="
    echo ""
    echo "Recent backups:"
    ls -lht backups/ | head -10
    echo ""
    echo "View backup logs: ${BLUE}tail -f logs/backup.log${NC}"
else
    echo "=========================================="
    echo -e "${RED}✗ Backup failed!${NC}"
    echo "=========================================="
    echo ""
    echo "Check logs for details: ${BLUE}tail -50 logs/backup.log${NC}"
    echo ""
    exit 1
fi

echo ""
