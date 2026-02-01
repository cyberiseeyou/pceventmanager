#!/bin/bash
# Flask Schedule Webapp - Test Instance Cleanup Script
# Cleans up test artifacts after testing is complete

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
echo -e "${BLUE}Test Instance Cleanup${NC}"
echo "=========================================="
echo ""

# Check if test instance is still running
TEST_RUNNING=$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 "http://localhost:8002" 2>/dev/null)

if [ "$TEST_RUNNING" == "200" ] || [ "$TEST_RUNNING" == "302" ]; then
    echo -e "${YELLOW}⚠ Test instance appears to be running on port 8002${NC}"
    echo ""
    echo "Please stop the test instance first:"
    echo "  1. Switch to the terminal running the test instance"
    echo "  2. Press Ctrl+C to stop it"
    echo ""
    read -p "Press Enter after stopping the test instance..." -r
    echo ""
else
    echo -e "${GREEN}✓${NC} Test instance is not running"
fi

echo "=========================================="
echo "Cleanup Options:"
echo "=========================================="
echo ""

# Option 1: Delete test database
if [ -f "instance/scheduler_test.db" ]; then
    TEST_SIZE=$(du -h instance/scheduler_test.db | cut -f1)
    echo -e "Test database: ${BLUE}instance/scheduler_test.db${NC} ($TEST_SIZE)"
    read -p "Delete test database? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm instance/scheduler_test.db
        echo -e "${GREEN}✓${NC} Deleted test database"
    else
        echo -e "${YELLOW}⚠${NC}  Kept test database (can reuse for future testing)"
    fi
else
    echo -e "${YELLOW}⚠${NC}  Test database not found"
fi

echo ""

# Option 2: Delete test logs
if [ -f "logs/scheduler_test.log" ]; then
    TEST_LOG_SIZE=$(du -h logs/scheduler_test.log | cut -f1)
    echo -e "Test logs: ${BLUE}logs/scheduler_test.log${NC} ($TEST_LOG_SIZE)"
    read -p "Delete test logs? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm logs/scheduler_test.log
        echo -e "${GREEN}✓${NC} Deleted test logs"
    else
        echo -e "${YELLOW}⚠${NC}  Kept test logs (useful for review)"
    fi
else
    echo -e "${YELLOW}⚠${NC}  Test logs not found"
fi

echo ""

# Option 3: Delete test environment file
if [ -f ".env.test" ]; then
    echo -e "Test configuration: ${BLUE}.env.test${NC}"
    read -p "Delete test configuration? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm .env.test
        echo -e "${GREEN}✓${NC} Deleted test configuration"
    else
        echo -e "${YELLOW}⚠${NC}  Kept test configuration (can reuse for future testing)"
    fi
else
    echo -e "${YELLOW}⚠${NC}  Test configuration not found"
fi

echo ""
echo "=========================================="
echo "Cleanup Summary:"
echo "=========================================="
echo ""

# List remaining test artifacts
REMAINING=0

if [ -f "instance/scheduler_test.db" ]; then
    echo -e "${BLUE}→${NC} Test database still exists (can be reused)"
    REMAINING=$((REMAINING + 1))
fi

if [ -f "logs/scheduler_test.log" ]; then
    echo -e "${BLUE}→${NC} Test logs still exist (can be reviewed)"
    REMAINING=$((REMAINING + 1))
fi

if [ -f ".env.test" ]; then
    echo -e "${BLUE}→${NC} Test configuration still exists (can be reused)"
    REMAINING=$((REMAINING + 1))
fi

if [ $REMAINING -eq 0 ]; then
    echo -e "${GREEN}✓ All test artifacts removed${NC}"
else
    echo ""
    echo "Test artifacts preserved for future testing."
    echo "Run this script again to remove them."
fi

echo ""

# Verify production is still running
PROD_RUNNING=$(curl -s -o /dev/null -w "%{http_code}" --max-time 2 "http://localhost:8000" 2>/dev/null)

if [ "$PROD_RUNNING" == "200" ] || [ "$PROD_RUNNING" == "302" ]; then
    echo -e "${GREEN}✓ Production instance still running on port 8000${NC}"
else
    echo -e "${YELLOW}⚠ Production instance not responding on port 8000${NC}"
    echo "  You may need to restart production"
fi

echo ""
echo "=========================================="
echo "Cleanup complete!"
echo "=========================================="
echo ""
