#!/bin/bash
# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p "$CI_BASE_DIR"
rm -f "$CI_BASE_DIR/bootstrap.json"
./ci/pip-install latest
uv run --no-sync python .devcontainer/doctor.py --services-only
uv run --no-sync ./manage.py compilemessages
uv run --no-sync ./manage.py collectstatic --noinput --verbosity 0
uv run --no-sync ./manage.py check
uv run --no-sync ./manage.py shell -c \
    'from weblate.screenshots.ocr import ensure_tesseract_language; ensure_tesseract_language("eng")'
uv run --no-sync python .devcontainer/doctor.py --record-bootstrap
