#!/bin/bash
# Upload translations for all components in a project
#
# Usage:
#   ./upload_all_components.sh
#   ./upload_all_components.sh --web-config scripts/auto/web.json --pofiles-dir scripts/auto/pofiles
#   PROJECT=my-project LANGUAGE=en ./upload_all_components.sh

set -e  # Exit on error

# Default values
PROJECT="${PROJECT:-boost-unordered-documentation}"
LANGUAGE="${LANGUAGE:-zh_Hans}"
WEB_CONFIG="${WEB_CONFIG:-web.json}"
POFILES_DIR="${POFILES_DIR:-pofiles}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPLOAD_SCRIPT="${SCRIPT_DIR}/upload_translations.py"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --web-config)
            WEB_CONFIG="$2"
            shift 2
            ;;
        --project)
            PROJECT="$2"
            shift 2
            ;;
        --language)
            LANGUAGE="$2"
            shift 2
            ;;
        --pofiles-dir)
            POFILES_DIR="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --web-config PATH    Path to web.json config file (default: web.json)"
            echo "  --project SLUG       Project slug (default: boost-unordered-documentation)"
            echo "  --language CODE      Language code (default: zh_Hans)"
            echo "  --pofiles-dir DIR    Directory containing PO files (default: pofiles)"
            echo ""
            echo "Environment variables:"
            echo "  PROJECT, LANGUAGE, WEB_CONFIG, POFILES_DIR can also be set via environment"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Use --help for usage information" >&2
            exit 1
            ;;
    esac
done

# Check if upload script exists
if [ ! -f "$UPLOAD_SCRIPT" ]; then
    echo "Error: upload_translations.py not found at $UPLOAD_SCRIPT" >&2
    exit 1
fi

# Get list of components using JSON output
echo "Fetching components for project: $PROJECT"
# Extract JSON from output (may include info messages before JSON)
RAW_OUTPUT=$(python3 "$UPLOAD_SCRIPT" \
    --web-config "$WEB_CONFIG" \
    --project "$PROJECT" \
    --format json 2>&1)
# Extract JSON part (everything from first '[' to last ']')
COMPONENTS_JSON=$(echo "$RAW_OUTPUT" | python3 -c "
import sys
import re
content = sys.stdin.read()
# Find JSON array (from first [ to last ])
match = re.search(r'\[.*\]', content, re.DOTALL)
if match:
    print(match.group(0))
else:
    sys.stderr.write('Error: Could not find JSON array in output\n')
    sys.exit(1)
")

if [ -z "$COMPONENTS_JSON" ]; then
    echo "Error: Failed to fetch components or no components found" >&2
    exit 1
fi

# Extract component slugs from JSON
# Using Python to parse JSON and extract slugs
COMPONENT_SLUGS=$(echo "$COMPONENTS_JSON" | python3 -c "
import json
import sys
try:
    data = json.load(sys.stdin)
    if isinstance(data, list):
        for comp in data:
            slug = comp.get('slug', '')
            if slug:
                print(slug)
except Exception as e:
    sys.stderr.write(f'Error parsing JSON: {e}\n')
    sys.exit(1)
")

if [ -z "$COMPONENT_SLUGS" ]; then
    echo "Error: No component slugs found" >&2
    exit 1
fi

# Count components
TOTAL=$(echo "$COMPONENT_SLUGS" | wc -l)
echo "Found $TOTAL components"
echo ""

# Upload for each component
COUNT=0
FAILED=0
SUCCESS=0

while IFS= read -r component_slug; do
    COUNT=$((COUNT + 1))
    echo "[$COUNT/$TOTAL] Uploading: $component_slug"

    if python3 "$UPLOAD_SCRIPT" \
        --web-config "$WEB_CONFIG" \
        --project "$PROJECT" \
        --component "$component_slug" \
        --upload \
        --language "$LANGUAGE" \
        --pofiles-dir "$POFILES_DIR"; then
        SUCCESS=$((SUCCESS + 1))
        echo "  ✓ Success"
    else
        FAILED=$((FAILED + 1))
        echo "  ✗ Failed"
    fi
    echo ""
done <<< "$COMPONENT_SLUGS"

# Summary
echo "=========================================="
echo "Summary:"
echo "  Total: $TOTAL"
echo "  Success: $SUCCESS"
echo "  Failed: $FAILED"
echo "=========================================="

# Exit with error if any failed
if [ $FAILED -gt 0 ]; then
    exit 1
fi
