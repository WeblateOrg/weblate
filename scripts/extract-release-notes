#!/usr/bin/env python3

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re
import sys

RUBRIC_RE = re.compile(r'<p class="rubric">([^<\n]*)</p>')

version = '[^"]*'
if len(sys.argv) == 2:
    version = sys.argv[1].replace(".", "-")

tag = f'<section id="weblate-{version}">.+?<h1>(.+?)<a(.+?)</a></h1>(.+?)</section>'

with open("docs/_build/html/changes.html") as handle:
    data = handle.read()

for match in re.findall(tag, data, re.MULTILINE | re.DOTALL):
    print(match[0])
    print()
    print(RUBRIC_RE.sub(r"<h3>\1</h3>", match[2]))
    break
