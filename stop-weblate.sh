#!/bin/bash

# Weblate Stop Script
# Stop all Weblate server and Celery workers

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${RED}========================================${NC}"
echo -e "${RED}   Stopping Weblate${NC}"
echo -e "${RED}========================================${NC}"
echo ""

# Stop Django server
if pgrep -f "weblate runserver" > /dev/null; then
    echo -e "${YELLOW}Stopping Django server...${NC}"
    pkill -f "weblate runserver"
    sleep 1
    echo -e "${GREEN}✓ Django server stopped${NC}"
else
    echo -e "${YELLOW}Django server is not running${NC}"
fi

# Stop Celery workers
if pgrep -f "celery.*weblate" > /dev/null; then
    echo -e "${YELLOW}Stopping Celery workers...${NC}"
    pkill -f "celery.*weblate"
    sleep 1
    echo -e "${GREEN}✓ Celery workers stopped${NC}"
else
    echo -e "${YELLOW}Celery workers are not running${NC}"
fi

echo ""
echo -e "${GREEN}✓ Weblate has been stopped${NC}"
echo -e "${RED}========================================${NC}"


