#!/bin/bash
# Flask Schedule Webapp - Test Instance Verification Script
# Verifies that test and production instances are properly isolated

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
echo -e "${BLUE}Test Instance Verification${NC}"
echo "=========================================="
echo ""

# Function to check HTTP endpoint
check_endpoint() {
    local port=$1
    local name=$2

    if curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://localhost:$port" | grep -q "200\|302"; then
        echo -e "${GREEN}✓${NC} $name running (port $port)"
        return 0
    else
        echo -e "${RED}✗${NC} $name NOT running (port $port)"
        return 1
    fi
}

# Check production instance (port 8000)
echo "Checking Production Instance:"
check_endpoint 8000 "Production"
PROD_STATUS=$?

echo ""

# Check test instance (port 8002)
echo "Checking Test Instance:"
check_endpoint 8002 "Test"
TEST_STATUS=$?

echo ""
echo "=========================================="
echo "Database Status:"
echo "=========================================="

# Check database files
if [ -f "instance/scheduler.db" ]; then
    PROD_SIZE=$(du -h instance/scheduler.db | cut -f1)
    PROD_TIME=$(stat -c %y instance/scheduler.db | cut -d'.' -f1)
    echo -e "${GREEN}✓${NC} Production DB: $PROD_SIZE (modified: $PROD_TIME)"
else
    echo -e "${RED}✗${NC} Production DB not found"
fi

if [ -f "instance/scheduler_test.db" ]; then
    TEST_SIZE=$(du -h instance/scheduler_test.db | cut -f1)
    TEST_TIME=$(stat -c %y instance/scheduler_test.db | cut -d'.' -f1)
    echo -e "${GREEN}✓${NC} Test DB: $TEST_SIZE (modified: $TEST_TIME)"
else
    echo -e "${RED}✗${NC} Test DB not found"
fi

echo ""
echo "=========================================="
echo "Migration Status:"
echo "=========================================="

# Check if migration applied to test database
if [ -f "instance/scheduler_test.db" ]; then
    MIGRATION_CHECK=$(sqlite3 instance/scheduler_test.db "PRAGMA table_info(pending_schedules);" 2>/dev/null | grep -c "bumped_posted_schedule_id" || echo "0")

    if [ "$MIGRATION_CHECK" -gt 0 ]; then
        echo -e "${GREEN}✓${NC} Migration applied (bumped_posted_schedule_id field exists)"
    else
        echo -e "${YELLOW}⚠${NC}  Migration NOT applied (bumped_posted_schedule_id field missing)"
        echo "    Run: flask db upgrade"
    fi
else
    echo -e "${RED}✗${NC} Cannot check migration (test DB not found)"
fi

echo ""
echo "=========================================="
echo "Configuration Status:"
echo "=========================================="

# Check configuration files
if [ -f ".env" ]; then
    echo -e "${GREEN}✓${NC} Production config (.env) exists"
else
    echo -e "${RED}✗${NC} Production config (.env) missing"
fi

if [ -f ".env.test" ]; then
    echo -e "${GREEN}✓${NC} Test config (.env.test) exists"

    # Verify test config uses correct database
    if grep -q "DATABASE_URL=sqlite:///instance/scheduler_test.db" .env.test; then
        echo -e "${GREEN}✓${NC} Test config uses correct database"
    else
        echo -e "${RED}✗${NC} Test config database path incorrect"
    fi

    # Verify test config uses correct port
    if grep -q "FLASK_RUN_PORT=8002" .env.test; then
        echo -e "${GREEN}✓${NC} Test config uses correct port (8002)"
    else
        echo -e "${YELLOW}⚠${NC}  Test config port not set to 8002"
    fi
else
    echo -e "${RED}✗${NC} Test config (.env.test) missing"
fi

echo ""
echo "=========================================="
echo "Log Files:"
echo "=========================================="

if [ -f "logs/app.log" ]; then
    PROD_LOG_SIZE=$(du -h logs/app.log | cut -f1)
    echo -e "${GREEN}✓${NC} Production log: $PROD_LOG_SIZE"
else
    echo -e "${YELLOW}⚠${NC}  Production log not found"
fi

if [ -f "logs/scheduler_test.log" ]; then
    TEST_LOG_SIZE=$(du -h logs/scheduler_test.log | cut -f1)
    echo -e "${GREEN}✓${NC} Test log: $TEST_LOG_SIZE"
else
    echo -e "${YELLOW}⚠${NC}  Test log not found (will be created when test starts)"
fi

echo ""
echo "=========================================="
echo "Summary:"
echo "=========================================="

if [ $PROD_STATUS -eq 0 ] && [ $TEST_STATUS -eq 0 ]; then
    echo -e "${GREEN}✓ BOTH instances running correctly${NC}"
    echo -e "  Production: ${BLUE}http://localhost:8000${NC}"
    echo -e "  Test:       ${BLUE}http://localhost:8002${NC}"
elif [ $PROD_STATUS -eq 0 ] && [ $TEST_STATUS -ne 0 ]; then
    echo -e "${YELLOW}⚠ Production running, test NOT running${NC}"
    echo -e "  Start test with: ${BLUE}./start_test_instance.sh${NC}"
elif [ $PROD_STATUS -ne 0 ] && [ $TEST_STATUS -eq 0 ]; then
    echo -e "${YELLOW}⚠ Test running, production NOT running${NC}"
    echo -e "  This is unusual - check production service"
else
    echo -e "${RED}✗ Neither instance is running${NC}"
    echo -e "  Start production with: ${BLUE}gunicorn --config gunicorn_config.py wsgi:app${NC}"
    echo -e "  Start test with: ${BLUE}./start_test_instance.sh${NC}"
fi

echo ""
echo "=========================================="
echo ""
