# Backup and Restore Scripts Explanation

This document explains the two scripts for backing up Weblate from a server and restoring it to your local machine.

## Overview

There are **two scripts** that work together:

1. **`backup_from_server.sh`** - Run on the **SERVER** to create a backup
2. **`restore_to_local.sh`** - Run on your **LOCAL** machine to restore the backup

---

## Script 1: `backup_from_server.sh`

### Purpose
Creates a complete backup of your Weblate server, including:
- **Database** (all projects, components, translations, users, etc.)
- **Files** (VCS repositories, media files, SSH keys, etc.)

### Where to Run
**On the SERVER** where Weblate is running

### What It Does

#### Step 1: Database Backup
```bash
pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" \
    --format=plain \          # Generate standard SQL
    -f "$DB_DUMP_FILE" \      # Output file
    --no-owner \              # Don't include ownership info
    --no-privileges           # Don't include privilege info
```

**Why plain SQL now?**
- Works directly with `psql`, no need for `pg_restore`
- Easy to inspect or diff (human-readable text)
- Plays nicely with custom ordering dumps (e.g., `dump_database.sh`)
- No dependency on PostgreSQL binary dump format

#### Step 2: Files Backup
```bash
tar -czf "$FILES_ARCHIVE" \
    -C "$DATA_DIR" \
    --exclude='cache/*' \     # Cache can be regenerated
    backups/ vcs/ ssh/ home/ media/ fonts/ secret/
```

**What gets backed up:**
- `backups/` - Database dumps, settings backups
- `vcs/` - **All Git repositories** (this is important!)
- `ssh/` - SSH keys for repository access
- `home/` - Home directory for scripts
- `media/` - User-uploaded files (screenshots, etc.)
- `fonts/` - Custom fonts
- `secret/` - Secret keys and credentials

**What's excluded:**
- `cache/` - Can be regenerated, not needed

#### Step 3: Create Info File
Creates a `backup_info.txt` file with metadata about the backup.

### Configuration

The script uses environment variables with defaults. You can override them:

```bash
# On the server, before running the script:
export DB_HOST="127.0.0.1"
export DB_USER="weblate"
export DB_NAME="weblate"
export DB_PASSWORD="your_password"
export DATA_DIR="/home/weblate/data"  # Your server's DATA_DIR
export BACKUP_BASE_DIR="$HOME/weblate_backup"  # Where to save backup

# Then run:
./backup_from_server.sh
```

Or edit the script directly to change the defaults.

### Usage Example

```bash
# On the server
cd /path/to/scripts
chmod +x backup_from_server.sh

# Set your server's DATA_DIR (if different from default)
export DATA_DIR="/var/lib/weblate"

# Run the backup
./backup_from_server.sh
```

**Output:**
```
========================================
Weblate Server Backup Script
========================================

[1/3] Backing up database...
✓ Database backup created: weblate_database_20250114_120000.sql
-rw-r--r-- 1 user user 120M Jan 14 12:00 weblate_database_20250114_120000.sql

[2/3] Backing up files from DATA_DIR...
✓ Files backup created: weblate_files_20250114_120000.tar.gz
-rw-r--r-- 1 user user 2.1G Jan 14 12:00 weblate_files_20250114_120000.tar.gz

[3/3] Creating backup info file...
✓ Backup info file created: backup_info.txt

========================================
Backup completed successfully!
========================================

Backup location: /home/user/weblate_backup/weblate_backup_20250114_120000
```

### Transferring to Local

After backup, transfer the entire backup directory to your local machine:

```bash
# Using scp
scp -r user@server:/home/user/weblate_backup/weblate_backup_20250114_120000 \
      ~/weblate_backup/

# Using rsync (better for large files, can resume)
rsync -avz --progress \
      user@server:/home/user/weblate_backup/weblate_backup_20250114_120000/ \
      ~/weblate_backup/weblate_backup_20250114_120000/
```

---

## Script 2: `restore_to_local.sh`

### Purpose
Restores the backup created by `backup_from_server.sh` to your local Weblate installation.

### Where to Run
**On your LOCAL machine** where you want to restore Weblate

### What It Does

#### Step 1: Database Restore
```bash
# Drop existing database
dropdb -h "$DB_HOST" -U "$DB_USER" "$DB_NAME"

# Create new database
createdb -h "$DB_HOST" -U "$DB_USER" "$DB_NAME"

# Restore from backup (SQL file)
psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" \
    -v ON_ERROR_STOP=1 \
    -f weblate_database_20250114_120000.sql
```

**Important:** This **OVERWRITES** your existing local database!

#### Step 2: Reset Sequences
After restoring, PostgreSQL sequences (auto-increment counters) may be out of sync. The script resets them:

```python
# For each sequence, set it to MAX(id) from the table
SELECT setval('trans_change_id_seq', (SELECT MAX(id) FROM trans_change));
SELECT setval('trans_unit_id_seq', (SELECT MAX(id) FROM trans_unit));
# ... etc for all sequences
```

**Why is this needed?**
- When you restore data, sequences don't automatically update
- Next insert would try to use an ID that already exists
- This causes "duplicate key" errors

#### Step 3: Restore Files
```bash
# Extract files to DATA_DIR
tar -xzf "$FILES_ARCHIVE" -C "$DATA_DIR"
```

This restores:
- All Git repositories (so translations are available)
- SSH keys (for repository access)
- Media files (screenshots, etc.)
- Other configuration files

#### Step 4: Post-Restore Steps
```bash
# Update Git repositories
python manage.py updategit --all

# Reload translations from files
python manage.py loadpo --all --force

# Regenerate static files
python manage.py compress --force
```

### Configuration

```bash
# On local machine, before running:
export DB_HOST="127.0.0.1"
export DB_USER="weblate"
export DB_NAME="weblate"
export DB_PASSWORD="weblate"
export DATA_DIR="$HOME/boost-weblate/data"  # Your local DATA_DIR
export WEBLATE_DIR="$HOME/boost-weblate"    # Your Weblate installation

# Then run:
./restore_to_local.sh /path/to/backup_directory
```

### Usage Example

```bash
# On local machine
cd ~/boost-weblate/scripts
chmod +x restore_to_local.sh

# Run restore (replace with your actual backup directory)
./restore_to_local.sh ~/weblate_backup/weblate_backup_20250114_120000
```

**Output:**
```
========================================
Weblate Local Restore Script
========================================

Backup directory: /home/user/weblate_backup/weblate_backup_20250114_120000
Database: weblate
DATA_DIR: /home/user/boost-weblate/data

This will OVERWRITE your local Weblate database and files. Continue? (yes/no): yes

[1/4] Restoring database from SQL...
Dropping existing database (if exists)...
Creating new database...
Restoring database from weblate_database_20250114_120000.sql...
✓ Database restored successfully

[2/4] Resetting database sequences...
Reset 45 sequences successfully
✓ Sequences reset

[3/4] Restoring files...
Extracting files to /home/user/boost-weblate/data...
✓ Files restored successfully

[4/4] Running post-restore steps...
Updating Git repositories...
Reloading translations...
Regenerating static files...
✓ Post-restore steps completed

========================================
Restore completed successfully!
========================================
```

---

## Complete Workflow

### On Server:

```bash
# 1. Navigate to scripts directory (or copy script to server)
cd /path/to/scripts

# 2. Make executable
chmod +x backup_from_server.sh

# 3. Configure (if needed)
export DATA_DIR="/var/lib/weblate"  # Your server's DATA_DIR
export DB_PASSWORD="your_password"

# 4. Run backup
./backup_from_server.sh

# 5. Transfer to local (example)
scp -r ~/weblate_backup/weblate_backup_* user@local:/home/user/weblate_backup/
```

### On Local:

```bash
# 1. Navigate to scripts directory
cd ~/boost-weblate/scripts

# 2. Make executable
chmod +x restore_to_local.sh

# 3. Configure (if needed)
export DATA_DIR="$HOME/boost-weblate/data"
export WEBLATE_DIR="$HOME/boost-weblate"

# 4. Run restore
./restore_to_local.sh ~/weblate_backup/weblate_backup_20250114_120000

# 5. Verify
cd ~/boost-weblate
source weblate-env/bin/activate
python manage.py check

# 6. Start Weblate
./start-weblate.sh
```

---

## Important Notes

### ⚠️ Warnings

1. **Data Loss:** Restoring will **OVERWRITE** your local database and files. Make sure you have a backup of your local data if needed.

2. **Database Sequences:** The script automatically resets sequences, but if you see "duplicate key" errors after restore, you may need to reset them manually.

3. **File Permissions:** After restore, check file permissions in `DATA_DIR`. Files should be readable/writable by the user running Weblate.

4. **Parse Errors:** If you see parse errors (like "Mismatched closing tag"), this means some translation files on the server are malformed. You'll need to fix them in the source repository.

### ✅ What Gets Copied

- ✅ All projects and components
- ✅ All translations and translation history
- ✅ All users and permissions
- ✅ All Git repositories (VCS)
- ✅ SSH keys and credentials
- ✅ Media files (screenshots, etc.)
- ✅ Translation memory
- ✅ Comments and suggestions

### ❌ What Doesn't Get Copied

- ❌ Cache (regenerated automatically)
- ❌ Temporary files
- ❌ Log files

---

## Troubleshooting

### Problem: "Database backup failed"

**Solution:**
- Check database credentials (DB_USER, DB_PASSWORD)
- Verify database is running
- Check PostgreSQL connection: `psql -h $DB_HOST -U $DB_USER -d $DB_NAME`

### Problem: "DATA_DIR does not exist"

**Solution:**
- Find your server's DATA_DIR: Check `settings.py` or run `python manage.py shell -c "from django.conf import settings; print(settings.DATA_DIR)"`
- Set it: `export DATA_DIR="/path/to/your/data/dir"`

### Problem: "Duplicate key value violates unique constraint" after restore

**Solution:**
- Sequences weren't reset properly
- Manually reset them (see script's sequence reset section)
- Or run: `python manage.py shell` and execute sequence reset commands

### Problem: "Parse errors" after restore

**Solution:**
- These are from malformed files on the server
- Check the log file mentioned in the error
- Fix the source file in the Git repository
- Update the component: `weblate updategit PROJECT/COMPONENT`

### Problem: "Permission denied" when extracting files

**Solution:**
- Check DATA_DIR permissions: `ls -ld $DATA_DIR`
- Make sure you have write access: `chmod -R u+rwX $DATA_DIR`

### Problem: Restore script can't find Weblate directory

**Solution:**
- Set WEBLATE_DIR: `export WEBLATE_DIR="/path/to/boost-weblate"`
- Or edit the script to set the default path

---

## Alternative: Manual Steps

If the scripts don't work for your setup, you can do it manually:

### Manual Backup (Server):
```bash
# Database (plain SQL)
pg_dump -h 127.0.0.1 -U weblate -d weblate --format=plain -f backup.sql

# Files
tar -czf files.tar.gz -C /path/to/DATA_DIR vcs/ ssh/ home/ media/ fonts/ secret/
```

### Manual Restore (Local):
```bash
```bash
# Database
dropdb -h 127.0.0.1 -U weblate weblate
createdb -h 127.0.0.1 -U weblate weblate
psql -h 127.0.0.1 -U weblate -d weblate -v ON_ERROR_STOP=1 -f backup.sql

# Files
tar -xzf files.tar.gz -C ~/boost-weblate/data/

# Reset sequences (use Python shell)
python manage.py shell
# Then run sequence reset commands

# Update
weblate updategit --all
weblate loadpo --all --force
python manage.py compress --force
```

---

## Summary

These scripts automate the complete backup and restore process:

1. **Backup script** (server) → Creates database dump + files archive
2. **Transfer** → Copy backup directory to local machine
3. **Restore script** (local) → Restores database, files, and runs post-restore steps

The scripts handle:
- ✅ Database backup/restore
- ✅ Files backup/restore
- ✅ Sequence reset
- ✅ Post-restore updates
- ✅ Error handling and user feedback

Just configure the paths and credentials, and run them!


