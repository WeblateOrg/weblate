#!/usr/bin/env python3

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import sys
from glob import glob

from translate.storage.pypo import pofile

if len(sys.argv) < 3 or len(sys.argv) % 2 != 1:
    print("Usage: ./scripts/locales-fixup.py match replacement [match replacement]...")
    sys.exit(1)

match = sys.argv[1]
replacement = sys.argv[2]
additional = [
    (sys.argv[3 + 2 * i], sys.argv[4 + 2 * i])
    for i in range(int((len(sys.argv) - 3) / 2))
]

for filename in glob("weblate/locale/*/LC_MESSAGES/*.po"):
    print(filename)
    storage = pofile.parsefile(filename)
    modified = False
    for unit in storage.units:
        if not unit.istranslatable():
            continue
        if match in unit.source:
            modified = True
            unit.source = unit.source.replace(match, replacement)
            unit.target = unit.target.replace(match, replacement)
            for m, r in additional:
                unit.source = unit.source.replace(m, r)
                unit.target = unit.target.replace(m, r)
    if modified:
        storage.save()
