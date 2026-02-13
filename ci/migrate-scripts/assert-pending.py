# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Assertion for pending changes migration."""

from weblate.trans.models import PendingUnitChange

change = PendingUnitChange.objects.get()
unit = change.unit

errors = []
if change.target != unit.target:
    errors.append(f"Target mismatch: '{change.target}' != '{unit.target}'")
if change.explanation != unit.explanation:
    errors.append(
        f"Explanation mismatch: '{change.explanation}' != '{unit.explanation}'"
    )
if change.state != unit.state:
    errors.append(f"State mismatch: {change.state} != {unit.state}")
# The migration uses get_last_content_change to get author
author = unit.get_last_content_change()[0]
if change.author != author:
    errors.append(f"Author mismatch: {change.author} != {author}")
if change.source_unit_explanation != unit.source_unit.explanation:
    errors.append(
        f"Source unit explanation mismatch: '{change.source_unit_explanation}' != '{unit.source_unit.explanation}'"
    )
assert not errors, "\n".join(errors)
