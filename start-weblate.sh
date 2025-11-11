#!/bin/bash

# Weblate Startup Script
# One-click operation to start Weblate server and Celery workers

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}   Weblate Startup Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Navigate to Weblate directory (IMPORTANT: Must be here before starting Celery)
cd $HOME

# Activate virtual environment
echo -e "${YELLOW}Activating virtual environment...${NC}"
source $HOME/boost-weblate/weblate-env/bin/activate

# Check if Celery is already running
if pgrep -f "celery.*weblate" > /dev/null; then
    echo -e "${YELLOW}Celery workers are already running!${NC}"
else
    echo -e "${GREEN}Starting Celery workers...${NC}"
    # Start Celery using the Weblate examples script
    # Use source directory for editable install
    if [ -f "$HOME/boost-weblate/weblate/examples/celery" ]; then
        $HOME/boost-weblate/weblate/examples/celery start
    fi
    sleep 3
    echo -e "${GREEN}✓ Celery workers started${NC}"
fi

# Check if server is already running
if pgrep -f "weblate runserver" > /dev/null; then
    echo -e "${YELLOW}Django server is already running!${NC}"
else
    echo -e "${GREEN}Starting Django development server...${NC}"
    nohup weblate runserver > server.log 2>&1 &
    sleep 2
    echo -e "${GREEN}✓ Django server started on http://localhost:8000${NC}"
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ Weblate is now running!${NC}"
echo ""
echo -e "  Access Weblate at: ${BLUE}http://localhost:8000${NC}"
echo ""
echo -e "  Logs:"
echo -e "    - Server:  ${YELLOW}tail -f $HOME/server.log${NC}"
echo -e "    - Celery:  ${YELLOW}tail -f $HOME/weblate-celery.log${NC}"
echo ""
echo -e "  To stop Weblate, run: ${YELLOW}./stop-weblate.sh${NC}"
echo -e "${BLUE}========================================${NC}"


