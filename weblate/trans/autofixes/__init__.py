# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Import all the autofixes defined in settings.

Note, unlike checks, using a sortable data object so fixes are applied in desired order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from weblate.utils.classloader import ClassLoader

if TYPE_CHECKING:
    from collections.abc import Iterator


class AutofixLoader(ClassLoader):
    def get_ignore_strings(self) -> Iterator[str]:
        for fix in self.values():
            for check in fix.get_related_checks():
                yield check.ignore_string


AUTOFIXES = AutofixLoader("AUTOFIX_LIST")


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
