#!/bin/bash
# Add or update Boost documentation components via Weblate endpoint
# Usage: ./add-or-update.sh
# Reads weblate_url and api_token from web.json (same directory). Requires jq.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_JSON="${SCRIPT_DIR}/web.json"
if [[ ! -f "${WEB_JSON}" ]]; then
  echo "Error: ${WEB_JSON} not found. Create it with weblate_url and api_token." >&2
  exit 1
fi
if ! command -v jq &>/dev/null; then
  echo "Error: jq is required to read web.json. Install jq and retry." >&2
  exit 1
fi

WEBLATE_URL="$(jq -r '.weblate_url' "${WEB_JSON}")"
TOKEN="$(jq -r '.api_token' "${WEB_JSON}")"
if [[ -z "${TOKEN}" || "${TOKEN}" == "null" ]]; then
  echo "Error: api_token not set in ${WEB_JSON}." >&2
  exit 1
fi

# Request parameters
ORGANIZATION="CppDigest"
SUBMODULES='["json"]'  # Can add more: '["json", "unordered", "container"]'
LANG_CODE="zh_Hans"
VERSION="boost-1.90.0"
# Optional: limit scan to these extensions (Weblate-supported). Use empty [] for no filter.
EXTENSIONS='[]'  # e.g. '[".adoc", ".md"]' or '[]' for all supported

# Trigger API and exit quickly to save CI minutes. Request is sent; we do not wait
# for the long-running response. Server continues add-or-update after we disconnect.
# --max-time: stop after this many seconds (curl exits 28 on timeout; || true avoids failing the job).
curl -X POST "${WEBLATE_URL}/boost-endpoint/add-or-update/" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"organization\": \"${ORGANIZATION}\",
    \"submodules\": ${SUBMODULES},
    \"lang_code\": \"${LANG_CODE}\",
    \"version\": \"${VERSION}\",
    \"extensions\": ${EXTENSIONS}
  }" \
  --max-time 5 \
  || true

echo "Trigger sent. Workflow exiting; add-or-update runs on the server."
