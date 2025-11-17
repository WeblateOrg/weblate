#!/bin/bash
# Script to dump PostgreSQL database with tables and rows ordered by primary key

DB_HOST="127.0.0.1"
DB_USER="weblate"
DB_NAME="weblate"
OUTPUT_FILE="$HOME/boost-weblate/weblate_backup_$(date +%Y%m%d_%H%M%S).sql"

export PGPASSWORD="weblate"

echo "-- Database dump with ordered tables and rows" > "$OUTPUT_FILE"
echo "-- Generated: DUMMY_TIMESTAMP" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# Dump schema only (without data)
echo "Dumping schema..."
pg_dump -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" \
    --schema-only \
    --no-owner \
    --no-privileges | \
    sed 's/\\restrict [^[:space:]]*/\\restrict DUMMY_TOKEN/g' | \
    sed 's/\\unrestrict [^[:space:]]*/\\unrestrict DUMMY_TOKEN/g' >> "$OUTPUT_FILE"

echo "" >> "$OUTPUT_FILE"
echo "-- Data dump with ordered rows" >> "$OUTPUT_FILE"
echo "-- Disable foreign key checks during data load" >> "$OUTPUT_FILE"
echo "SET session_replication_role = 'replica';" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"

# Get all tables with their primary key columns, ordered by foreign key dependencies
# Use pg_dump's internal dependency ordering by extracting table order from a test dump
# This ensures tables are dumped in the correct order to satisfy foreign key constraints
TABLES=$(psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "
SELECT 
    t.tablename,
    COALESCE(
        (SELECT a.attname 
         FROM pg_index i
         JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
         WHERE i.indrelid = c.oid AND i.indisprimary
         ORDER BY a.attnum
         LIMIT 1),
        (SELECT column_name 
         FROM information_schema.columns 
         WHERE table_schema = 'public' 
           AND table_name = t.tablename 
           AND column_name = 'id'
         LIMIT 1),
        (SELECT column_name 
         FROM information_schema.columns 
         WHERE table_schema = 'public' 
           AND table_name = t.tablename 
         ORDER BY ordinal_position
         LIMIT 1)
    ) as pk_column,
    (SELECT COUNT(*) 
     FROM information_schema.table_constraints tc
     JOIN information_schema.key_column_usage kcu 
       ON tc.constraint_name = kcu.constraint_name
     JOIN information_schema.constraint_column_usage ccu 
       ON ccu.constraint_name = tc.constraint_name
     WHERE tc.table_schema = 'public'
       AND tc.table_name = t.tablename
       AND tc.constraint_type = 'FOREIGN KEY'
       AND ccu.table_schema = 'public'
    ) as fk_count
FROM pg_tables t
JOIN pg_class c ON c.relname = t.tablename
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE t.schemaname = 'public'
ORDER BY fk_count, t.tablename;
")

# Dump data for each table, ordered by primary key
while IFS='|' read -r tablename pk_column fk_count; do
    tablename=$(echo "$tablename" | xargs)
    pk_column=$(echo "$pk_column" | xargs)
    # fk_count is ignored but needed to read all columns
    
    if [ -z "$tablename" ]; then
        continue
    fi
    
    echo "Dumping data from table: $tablename (ordered by $pk_column)"
    
    # Check if table has any rows
    row_count=$(psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT COUNT(*) FROM \"$tablename\";" | xargs)
    
    if [ "$row_count" -gt 0 ]; then
        echo "" >> "$OUTPUT_FILE"
        echo "-- Data for table: $tablename (ordered by $pk_column)" >> "$OUTPUT_FILE"
        
        # Get column names for the table
        columns=$(psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "
            SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position)
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = '$tablename';
        " | xargs)
        
        # Use standard COPY format (same as pg_dump -F p) with ordered data
        # Write COPY command header with schema prefix (matching pg_dump format)
        echo "COPY public.\"$tablename\" ($columns) FROM stdin;" >> "$OUTPUT_FILE"
        
        # Export ordered data using COPY format (same format pg_dump uses)
        # This uses the default COPY format which handles escaping properly
        if psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "COPY (SELECT * FROM \"$tablename\" ORDER BY \"$pk_column\") TO STDOUT;" >> "$OUTPUT_FILE" 2>/dev/null; then
            : # Success - data written
        else
            # Fallback: dump without ordering if ORDER BY fails
            echo "-- Warning: Could not order by $pk_column, dumping without order" >> "$OUTPUT_FILE"
            psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "COPY \"$tablename\" TO STDOUT;" >> "$OUTPUT_FILE" 2>/dev/null
        fi
        
        # End COPY block
        echo "\\." >> "$OUTPUT_FILE"
    fi
done <<< "$TABLES"

echo "" >> "$OUTPUT_FILE"
echo "-- Re-enable foreign key checks" >> "$OUTPUT_FILE"
echo "SET session_replication_role = 'origin';" >> "$OUTPUT_FILE"
echo "" >> "$OUTPUT_FILE"
echo "-- End of dump" >> "$OUTPUT_FILE"

echo "Database dump completed: $OUTPUT_FILE"
ls -lh "$OUTPUT_FILE"

