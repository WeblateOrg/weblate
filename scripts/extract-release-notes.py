#!/usr/bin/env python3

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
import sys
from pathlib import Path

RUBRIC_RE = re.compile(
    r'<p\b(?=[^>]*\bclass="(?:[^" ]+ )*rubric(?: [^"]*)?")[^>]*>(.*?)</p>',
    re.DOTALL,
)
PERMALINK_RE = re.compile(r'<a\b[^>]*\bclass="headerlink"[^>]*>.*?</a>', re.DOTALL)

version = '[^"]*'
if len(sys.argv) == 2:
    version = sys.argv[1].replace(".", "-")

tag = f'<section id="weblate-{version}">.+?<h1>(.+?)</h1>(.+?)</section>'

data = Path("docs/_build/html/changes.html").read_text(encoding="utf-8")
data = PERMALINK_RE.sub("", data)

for match in re.findall(tag, data, re.MULTILINE | re.DOTALL):
    print(match[0])
    print()
    print(RUBRIC_RE.sub(r"<h3>\1</h3>", match[1]))
    break
