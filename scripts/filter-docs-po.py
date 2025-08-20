#!/usr/bin/env python3

# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Remove strings which are not useful for translation from the documentation.

Sphinx does not have a way to achieve that, so filter out strings at the PO file level.
"""

from __future__ import annotations

import re
import sys

from translate.storage.pypo import pofile, pounit

EXCLUDE_RE = re.compile(
    r"""
    ^(
        [0-9]+                                      # Numbers
        |
        [A-Z]*_[A-Z_]*                              # Environment variables
        |
        ``[^`]*``                                   # Literals
        |
        :[a-z]*:`[a-z0-9./_\*-]*`                   # Simple roles
        |
        [<>]json[ ].*                               # API descriptions
        |
        :(ref|doc|setting|envvar):`[^<`]+`          # Unlabeled references
        |
        /[a-z_./-]+                                 # File names
    )$
    """,
    re.VERBOSE,
)

NAMES_RE = re.compile(r"^[a-z_]+$")

if len(sys.argv) != 2:
    print("Usage: ./scripts/filter-docs-po.py filename")
    sys.exit(1)


def should_skip(unit: pounit) -> bool:
    if EXCLUDE_RE.match(unit.source):
        return True
    return bool(
        any("admin/management.rst" in location for location in unit.getlocations())
        and NAMES_RE.match(unit.source)
    )


storage = pofile.parsefile(sys.argv[1])

storage.units = [unit for unit in storage.units if not should_skip(unit)]

storage.save()
