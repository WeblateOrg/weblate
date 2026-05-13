#!/usr/bin/env python

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import ast
from pathlib import Path

from packaging.version import Version

module = ast.parse(Path("weblate/utils/version.py").read_text(encoding="utf-8"))
for node in module.body:
    if not isinstance(node, ast.Assign):
        continue
    if any(
        isinstance(target, ast.Name) and target.id == "VERSION"
        for target in node.targets
    ):
        print(Version(ast.literal_eval(node.value)).base_version)
        break
else:
    msg = "VERSION not found in weblate/utils/version.py"
    raise SystemExit(msg)
