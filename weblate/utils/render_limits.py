# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Resource limits shared by template validation and evaluation."""

from __future__ import annotations

SOURCE_LIMIT = 64 * 1024
LOOP_LIMIT = 10_000
OUTPUT_LIMIT = 1024 * 1024
CONTEXT_LIMIT = 8 * 1024 * 1024
DEPTH_LIMIT = 32
RENDER_TIMEOUT = 5
