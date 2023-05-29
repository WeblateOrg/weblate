#!/usr/bin/env python3

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import sys
from glob import glob

from translate.storage.pypo import pofile

for filename in glob("weblate/locale/*/LC_MESSAGES/*.po"):
    print(filename)
    storage = pofile.parsefile(filename)
    for unit in storage.units:
        if not unit.istranslatable():
            continue
        if sys.argv[1] in unit.source:
            print(unit.source)
        if unit.istranslated() and sys.argv[1] in unit.target:
            print(unit.target)
