#!/bin/bash
# Script to restore Weblate backup to LOCAL machine
# Run this script on your LOCAL machine after transferring backup from server

set -e  # Exit on error

# Configuration - ADJUST THESE FOR YOUR LOCAL SETUP
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_USER="${DB_USER:-weblate}"
DB_NAME="${DB_NAME:-weblate}"
DB_PASSWORD="${DB_PASSWORD:-weblate}"
DATA_DIR="${DATA_DIR:-$HOME/boost-weblate/data}"  # Adjust to your local DATA_DIR

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if backup directory is provided
if [ -z "$1" ]; then
    echo -e "${RED}Error: Backup directory not specified${NC}"
    echo ""
    echo "Usage: $0 <backup_directory>"
    echo ""
    echo "Example:"
    echo "  $0 ~/weblate_backup/weblate_backup_20250114_120000"
    echo ""
    echo "Or if backup is in current directory:"
    echo "  $0 ./weblate_backup_20250114_120000"
    exit 1
fi

BACKUP_DIR="$1"

# Check if backup directory exists
if [ ! -d "$BACKUP_DIR" ]; then
    echo -e "${RED}Error: Backup directory '$BACKUP_DIR' does not exist${NC}"
    exit 1
fi

cd "$BACKUP_DIR"

# Find backup files
DB_SQL=$(ls -1 weblate_database_*.sql 2>/dev/null | head -1)
FILES_ARCHIVE=$(ls -1 weblate_files_*.tar.gz 2>/dev/null | head -1)

if [ -z "$DB_SQL" ] && [ -z "$FILES_ARCHIVE" ]; then
    echo -e "${RED}Error: No backup files found in '$BACKUP_DIR'${NC}"
    echo "Expected files:"
    echo "  - weblate_database_*.sql"
    echo "  - weblate_files_*.tar.gz"
    exit 1
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Weblate Local Restore Script${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "Backup directory: ${YELLOW}$BACKUP_DIR${NC}"
echo -e "Database: ${YELLOW}$DB_NAME${NC}"
echo -e "DATA_DIR: ${YELLOW}$DATA_DIR${NC}"
echo ""

# Confirm before proceeding
read -p "This will OVERWRITE your local Weblate database and files. Continue? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo -e "${YELLOW}Restore cancelled${NC}"
    exit 0
fi

export PGPASSWORD="$DB_PASSWORD"

# Restore database
if [ -n "$DB_SQL" ]; then
    echo -e "${GREEN}[1/4] Restoring database from SQL...${NC}"
    
    # Drop and recreate database
    echo -e "${YELLOW}Dropping existing database (if exists)...${NC}"
    dropdb -h "$DB_HOST" -U "$DB_USER" "$DB_NAME" 2>/dev/null || true
    
    echo -e "${YELLOW}Creating new database...${NC}"
    createdb -h "$DB_HOST" -U "$DB_USER" "$DB_NAME"
    
    echo -e "${YELLOW}Restoring database from $DB_SQL...${NC}"
    psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" \
        -v ON_ERROR_STOP=1 \
        -f "$DB_SQL"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Database restored successfully${NC}"
    else
        echo -e "${RED}✗ Database restore failed!${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}[1/4] Skipping database restore (no SQL file found)${NC}"
fi

# Reset sequences
echo ""
echo -e "${GREEN}[2/4] Resetting database sequences...${NC}"

# Get the Weblate project directory
WEBLATE_DIR="${WEBLATE_DIR:-$HOME/boost-weblate}"
if [ ! -d "$WEBLATE_DIR" ]; then
    echo -e "${YELLOW}Warning: Weblate directory not found at $WEBLATE_DIR${NC}"
    echo -e "${YELLOW}Set WEBLATE_DIR environment variable or edit this script${NC}"
    WEBLATE_DIR=""
fi

if [ -n "$WEBLATE_DIR" ] && [ -f "$WEBLATE_DIR/manage.py" ]; then
    cd "$WEBLATE_DIR"
    source weblate-env/bin/activate 2>/dev/null || true
    
    python manage.py shell <<'PYTHON_EOF'
from django.db import connection
cursor = connection.cursor()

# Get all sequences and reset them
sequences_query = """
    SELECT sequence_name, 
           REPLACE(REPLACE(sequence_name, '_id_seq', ''), 'trans_', 'trans_') as table_name
    FROM information_schema.sequences
    WHERE sequence_schema = 'public'
    AND sequence_name LIKE '%_id_seq';
"""

cursor.execute(sequences_query)
sequences = cursor.fetchall()

reset_count = 0
for seq_name, table_name in sequences:
    try:
        # Try to get max ID from the table
        cursor.execute(f'SELECT COALESCE(MAX(id), 0) FROM "{table_name}";')
        max_id = cursor.fetchone()[0]
        if max_id > 0:
            cursor.execute(f"SELECT setval('{seq_name}', {max_id});")
            reset_count += 1
    except Exception as e:
        # Table might not have 'id' column or might not exist, skip
        pass

print(f'Reset {reset_count} sequences successfully')
PYTHON_EOF

    echo -e "${GREEN}✓ Sequences reset${NC}"
else
    echo -e "${YELLOW}Warning: Could not reset sequences automatically${NC}"
    echo -e "${YELLOW}You may need to reset them manually using:${NC}"
    echo -e "${YELLOW}  python manage.py shell${NC}"
    echo -e "${YELLOW}  (then run sequence reset commands)${NC}"
fi

# Ensure we are back in the backup directory for file restore
cd "$BACKUP_DIR"

# Restore files
if [ -n "$FILES_ARCHIVE" ]; then
    echo ""
    echo -e "${GREEN}[3/4] Restoring files...${NC}"
    
    # Create DATA_DIR if it doesn't exist
    mkdir -p "$DATA_DIR"
    
    echo -e "${YELLOW}Extracting files to $DATA_DIR...${NC}"
    tar -xzf "$FILES_ARCHIVE" -C "$DATA_DIR"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Files restored successfully${NC}"
        
        # Set proper permissions (adjust user/group as needed)
        echo -e "${YELLOW}Setting file permissions...${NC}"
        chmod -R u+rwX "$DATA_DIR" 2>/dev/null || true
    else
        echo -e "${RED}✗ Files restore failed!${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}[3/4] Skipping files restore (no archive found)${NC}"
fi

# Post-restore steps
if [ -n "$WEBLATE_DIR" ] && [ -f "$WEBLATE_DIR/manage.py" ]; then
    echo ""
    echo -e "${GREEN}[4/4] Running post-restore steps...${NC}"
    
    cd "$WEBLATE_DIR"
    source weblate-env/bin/activate 2>/dev/null || true
    
    echo -e "${YELLOW}Updating Git repositories...${NC}"
    python manage.py updategit --all 2>/dev/null || echo -e "${YELLOW}Note: Some repositories may need manual update${NC}"
    
    echo -e "${YELLOW}Synchronizing files with database (committing all components)...${NC}"
    python manage.py commitgit --all 2>/dev/null || echo -e "${YELLOW}Note: Some components may need manual commit${NC}"
    
    # echo -e "${YELLOW}Reloading translations...${NC}"
    # python manage.py loadpo --all --force 2>/dev/null || echo -e "${YELLOW}Note: Some translations may need manual reload${NC}"
    
    echo -e "${YELLOW}Regenerating static files...${NC}"
    python manage.py compress --force 2>/dev/null || echo -e "${YELLOW}Note: Static files may need manual regeneration${NC}"
    
    echo -e "${GREEN}✓ Post-restore steps completed${NC}"
else
    echo -e "${YELLOW}[4/4] Skipping post-restore steps (Weblate directory not found)${NC}"
    echo -e "${YELLOW}Please run these commands manually:${NC}"
    echo -e "${YELLOW}  weblate updategit --all${NC}"
    echo -e "${YELLOW}  weblate commitgit --all${NC}"
    echo -e "${YELLOW}  weblate loadpo --all --force${NC}"
    echo -e "${YELLOW}  python manage.py compress --force${NC}"
fi

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}Restore completed successfully!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo -e "1. Verify your Weblate installation:"
echo -e "   ${YELLOW}cd ~/boost-weblate${NC}"
echo -e "   ${YELLOW}source weblate-env/bin/activate${NC}"
echo -e "   ${YELLOW}python manage.py check${NC}"
echo ""
echo -e "2. Start Weblate:"
echo -e "   ${YELLOW}./start-weblate.sh${NC}"
echo ""
echo -e "3. Access Weblate in your browser and verify projects/components are present"
echo ""
echo -e "${YELLOW}Note: If you see parse errors, check the logs and fix any malformed files${NC}"

