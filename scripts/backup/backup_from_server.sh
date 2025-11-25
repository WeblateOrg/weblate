#!/bin/bash
# Script to backup Weblate from SERVER
# Run this script on the SERVER to create a complete backup

set -e  # Exit on error

# Configuration - ADJUST THESE FOR YOUR SERVER
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_USER="${DB_USER:-weblate}"
DB_NAME="${DB_NAME:-weblate}"
DB_PASSWORD="${DB_PASSWORD:-weblate}"
DATA_DIR="${DATA_DIR:-/home/dsf2eqw1/boost-weblate/data}"  # Adjust to your server's DATA_DIR

# Backup directory
BACKUP_BASE_DIR="${BACKUP_BASE_DIR:-$HOME/weblate_backup}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_BASE_DIR/weblate_backup_$TIMESTAMP"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Weblate Server Backup Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Create backup directory
mkdir -p "$BACKUP_DIR"
cd "$BACKUP_DIR"

echo -e "${GREEN}[1/3] Backing up database (SQL dump)...${NC}"
export PGPASSWORD="$DB_PASSWORD"

# Use pg_dump plain SQL format for compatibility with psql restores
DB_DUMP_FILE="weblate_database_$TIMESTAMP.sql"
pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" \
    --format=plain \
    --no-owner \
    --no-privileges \
    -f "$DB_DUMP_FILE"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Database backup created: $DB_DUMP_FILE${NC}"
    ls -lh "$DB_DUMP_FILE"
else
    echo -e "${RED}✗ Database backup failed!${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}[2/3] Backing up files from DATA_DIR...${NC}"

# Check if DATA_DIR exists
if [ ! -d "$DATA_DIR" ]; then
    echo -e "${YELLOW}Warning: DATA_DIR '$DATA_DIR' does not exist${NC}"
    echo -e "${YELLOW}Please set DATA_DIR environment variable or edit this script${NC}"
    echo -e "${YELLOW}Example: DATA_DIR=/var/lib/weblate ./backup_from_server.sh${NC}"
    exit 1
fi

# Create files backup (excluding cache which can be regenerated)
FILES_BACKUP="weblate_files_$TIMESTAMP.tar.gz"
tar -czf "$FILES_BACKUP" \
    -C "$DATA_DIR" \
    --exclude='cache/*' \
    --exclude='*.pyc' \
    --exclude='__pycache__' \
    backups/ vcs/ ssh/ home/ media/ fonts/ secret/ 2>/dev/null || {
    # If some directories don't exist, try backing up what exists
    echo -e "${YELLOW}Some directories may not exist, backing up available ones...${NC}"
    tar -czf "$FILES_BACKUP" \
        -C "$DATA_DIR" \
        --exclude='cache/*' \
        backups/ vcs/ ssh/ home/ media/ fonts/ secret/ 2>/dev/null || true
}

if [ -f "$FILES_BACKUP" ]; then
    echo -e "${GREEN}✓ Files backup created: $FILES_BACKUP${NC}"
    ls -lh "$FILES_BACKUP"
else
    echo -e "${YELLOW}Warning: Files backup may be incomplete${NC}"
fi

echo ""
echo -e "${GREEN}[3/3] Creating backup info file...${NC}"

# Create info file with backup metadata
INFO_FILE="backup_info.txt"
cat > "$INFO_FILE" <<EOF
Weblate Backup Information
==========================
Backup Date: $(date)
Server Hostname: $(hostname)
Database: $DB_NAME
Database Host: $DB_HOST
Database User: $DB_USER
DATA_DIR: $DATA_DIR

Files included:
- Database SQL: $DB_DUMP_FILE
- Files archive: $FILES_BACKUP

To restore on local machine:
1. Transfer this entire directory to your local machine
2. Run restore_to_local.sh script on local machine
3. Or follow manual restore steps in docs/Copy_Projects_From_Server.md

EOF

echo -e "${GREEN}✓ Backup info file created: $INFO_FILE${NC}"

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Backup completed successfully!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Backup location: ${YELLOW}$BACKUP_DIR${NC}"
echo ""
echo -e "Contents:"
ls -lh "$BACKUP_DIR"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo -e "1. Transfer this directory to your local machine:"
echo -e "   ${YELLOW}scp -r $BACKUP_DIR user@local-machine:/path/to/destination${NC}"
echo -e "   or use rsync:"
echo -e "   ${YELLOW}rsync -avz $BACKUP_DIR/ user@local-machine:/path/to/destination/${NC}"
echo ""
echo -e "2. On local machine, run:"
echo -e "   ${YELLOW}cd ~/boost-weblate${NC}"
echo -e "   ${YELLOW}./scripts/restore_to_local.sh $BACKUP_DIR${NC}"

