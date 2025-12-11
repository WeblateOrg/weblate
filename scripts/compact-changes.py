#!/usr/bin/env python3

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re
from pathlib import Path

COMPACT_RE = re.compile(
    r""".. rubric:: .*

.. rubric::""",
    re.MULTILINE,
)

ROOT_DIR = Path(__file__).parent.parent

file = ROOT_DIR / "docs" / "changes.rst"

content = file.read_text()
file.write_text(COMPACT_RE.sub(".. rubric::", content))
