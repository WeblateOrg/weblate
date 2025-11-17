# Copying All Projects/Components from Server to Local Weblate

This guide covers methods to copy all projects and components from a remote Weblate server to your local Weblate instance.

## Method 1: Project-Level Backups (Recommended for Individual Projects)

This is the cleanest method for copying individual projects. It includes all translation content but excludes access control and history.

### On the Server:

1. **Create Project Backups via Web Interface:**
   - Navigate to each project
   - Go to **Operations** → **Backups**
   - Click **Create backup**
   - Download the backup file

2. **Or Create Backups via API:**
   ```bash
   # List all projects
   curl -H "Authorization: Token YOUR_API_TOKEN" \
        https://server.weblate.org/api/projects/ | jq -r '.results[].slug'
   
   # Create backup for each project (if API supports it)
   # Note: Project backups are typically created via web interface
   ```

### On Local:

1. **Import Project Backup:**
   ```bash
   cd ~/boost-weblate
   source weblate-env/bin/activate
   
   # Import project backup
   weblate import_projectbackup \
       "Project Name" \
       "project-slug" \
       "your-username" \
       /path/to/project-backup.zip
   ```

2. **Or Import via Web Interface:**
   - Go to **Add project**
   - Choose **Import project backup**
   - Upload the backup file

**Note:** Project backups include:
- ✅ Project, components, translations
- ✅ String comments, suggestions, checks
- ❌ Access control information
- ❌ History

---

## Method 2: Full Database + Files Backup (Complete Copy)

This method copies everything including users, permissions, and history.

### On the Server:

1. **Backup Database:**
   ```bash
   # PostgreSQL
   pg_dump -h 127.0.0.1 -U weblate -d weblate -F c \
       -f weblate_backup_$(date +%Y%m%d_%H%M%S).dump
   
   # Or use your existing dump_database.sh script
   ./dump_database.sh
   ```

2. **Backup Files:**
   ```bash
   # Backup DATA_DIR (typically ~/weblate-data or /var/lib/weblate)
   tar -czf weblate_files_backup_$(date +%Y%m%d_%H%M%S).tar.gz \
       backups/ vcs/ ssh/ home/ media/ fonts/ secret/
   
   # Or if you want to exclude translation memory:
   tar -czf weblate_files_backup_$(date +%Y%m%d_%H%M%S).tar.gz \
       backups/database.sql backups/settings.py vcs ssh home media fonts secret
   ```

### On Local:

1. **Restore Database:**
   ```bash
   cd ~/boost-weblate
   source weblate-env/bin/activate
   
   # Drop existing database (if needed)
   # WARNING: This will delete all local data!
   dropdb -h 127.0.0.1 -U weblate weblate
   createdb -h 127.0.0.1 -U weblate weblate
   
   # Restore database
   pg_restore -h 127.0.0.1 -U weblate -d weblate \
       weblate_backup_YYYYMMDD_HHMMSS.dump
   
   # Or if using SQL dump:
   psql -h 127.0.0.1 -U weblate -d weblate < weblate_backup_YYYYMMDD_HHMMSS.sql
   ```

2. **Fix Database Sequences:**
   ```bash
   # Reset sequences after restore (important!)
   python manage.py shell -c "
   from django.db import connection
   cursor = connection.cursor()
   cursor.execute(\"SELECT setval('trans_change_id_seq', (SELECT MAX(id) FROM trans_change));\")
   cursor.execute(\"SELECT setval('trans_unit_id_seq', (SELECT MAX(id) FROM trans_unit));\")
   cursor.execute(\"SELECT setval('trans_translation_id_seq', (SELECT MAX(id) FROM trans_translation));\")
   cursor.execute(\"SELECT setval('trans_component_id_seq', (SELECT MAX(id) FROM trans_component));\")
   cursor.execute(\"SELECT setval('trans_project_id_seq', (SELECT MAX(id) FROM trans_project));\")
   print('Sequences reset successfully')
   "
   ```

3. **Restore Files:**
   ```bash
   # Extract files to DATA_DIR (check your settings.py for DATA_DIR)
   # If DATA_DIR is not set, default is ~/weblate-data
   tar -xzf weblate_files_backup_YYYYMMDD_HHMMSS.tar.gz -C ~/weblate-data/
   
   # Or if using custom DATA_DIR:
   tar -xzf weblate_files_backup_YYYYMMDD_HHMMSS.tar.gz -C $DATA_DIR/
   ```

4. **Update Repositories:**
   ```bash
   # Update all Git repositories
   weblate updategit --all
   
   # Update translations from repositories
   weblate loadpo --all --force
   ```

5. **Regenerate Static Files:**
   ```bash
   # Regenerate offline compression manifest
   python manage.py compress --force
   ```

---

## Method 3: API-Based Export/Import (Selective Copy)

Use this method if you want to copy specific projects or components selectively.

### On the Server:

1. **Export Project/Component Data via API:**
   ```bash
   # Get API token from server (Settings → API access)
   API_TOKEN="your-api-token"
   SERVER_URL="https://server.weblate.org"
   
   # List all projects
   curl -H "Authorization: Token $API_TOKEN" \
        "$SERVER_URL/api/projects/" | jq '.results[] | {name, slug}' > projects.json
   
   # Export each project's components
   for project_slug in $(jq -r '.results[].slug' projects.json); do
       curl -H "Authorization: Token $API_TOKEN" \
            "$SERVER_URL/api/projects/$project_slug/components/" \
            > "components_${project_slug}.json"
   done
   ```

### On Local:

1. **Import Components via JSON:**
   ```bash
   cd ~/boost-weblate
   source weblate-env/bin/activate
   
   # Create project first (if it doesn't exist)
   # Then import components
   weblate import_json --project PROJECT_SLUG components_PROJECT_SLUG.json
   ```

---

## Method 4: Using import_project Command (From VCS)

If the server's projects are in version control, you can import directly from the repositories.

### On Local:

```bash
cd ~/boost-weblate
source weblate-env/bin/activate

# Import project with all components
weblate import_project \
    PROJECT_SLUG \
    https://github.com/user/repo.git \
    master \
    '**/*.po'

# Or with more options:
weblate import_project \
    --file-format po \
    --name-template 'Component: {{ component }}' \
    PROJECT_SLUG \
    https://github.com/user/repo.git \
    master \
    'locale/*/LC_MESSAGES/**.po'
```

---

## Recommended Approach

For copying **all projects/components** from server to local:

1. **Use Method 2 (Full Database + Files Backup)** if you want:
   - Complete copy including users, permissions, history
   - Exact replica of the server

2. **Use Method 1 (Project-Level Backups)** if you want:
   - Clean import without access control
   - Individual project control
   - Easier to manage

3. **Use Method 3 (API-Based)** if you want:
   - Selective copying
   - Automated scripting
   - Custom filtering

---

## Post-Import Steps

After importing, always:

1. **Update repositories:**
   ```bash
   weblate updategit --all
   ```

2. **Reload translations:**
   ```bash
   weblate loadpo --all --force
   ```

3. **Update checks:**
   ```bash
   weblate updatechecks --all
   ```

4. **Regenerate static files:**
   ```bash
   python manage.py compress --force
   ```

5. **Verify data:**
   - Check project count matches
   - Verify component count per project
   - Test accessing translations in web interface

---

## Troubleshooting

### Sequence Errors After Restore

If you see `duplicate key value violates unique constraint` errors:

```bash
# Reset all sequences
python manage.py shell -c "
from django.db import connection
cursor = connection.cursor()
# Get all tables with sequences
cursor.execute(\"\"\"
    SELECT 'SELECT setval(''' || sequence_name || ''', (SELECT MAX(' || 
           column_name || ') FROM ' || table_name || '));'
    FROM information_schema.sequences s
    JOIN information_schema.columns c ON c.table_schema = 'public'
    WHERE sequence_name LIKE c.table_name || '_%_seq'
    AND sequence_name LIKE '%_id_seq';
\"\"\")
for row in cursor.fetchall():
    cursor.execute(row[0])
print('All sequences reset')
"
```

### Parse Errors After Restore

If you see parse errors (like the `ParseError: "Mismatched closing tag"`):

1. Check the problematic file in the repository
2. Fix the malformed HTML/XML in the source file
3. Update the repository:
   ```bash
   weblate updategit PROJECT/COMPONENT
   weblate loadpo PROJECT/COMPONENT --force
   ```

### Missing Files

If files are missing after restore:

1. Check `DATA_DIR` setting in `settings.py`
2. Verify file permissions
3. Ensure all files were included in backup

---

## References

- [Weblate Backup Documentation](https://docs.weblate.org/en/latest/admin/backup.html)
- [Management Commands](https://docs.weblate.org/en/latest/admin/management.html)
- [Project Configuration](https://docs.weblate.org/en/latest/admin/projects.html)



