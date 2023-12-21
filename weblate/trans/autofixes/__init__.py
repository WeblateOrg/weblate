# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Import all the autofixes defined in settings.

Note, unlike checks, using a sortable data object so fixes are applied in desired order.
"""

from weblate.utils.classloader import ClassLoader

AUTOFIXES = ClassLoader("AUTOFIX_LIST")


def fix_target(target, unit):
    """Apply each autofix to the target translation."""
    if target == []:
        return target, []
    fixups = []
    for fix in AUTOFIXES.values():
        target, fixed = fix.fix_target(target, unit)
        if fixed:
            fixups.append(fix.name)

    return target, fixups
