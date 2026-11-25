# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Verify project repair preserves historical attribution and content."""

from __future__ import annotations

from datetime import UTC, datetime

from weblate.trans.models import Change

for label in ("current", "stale", "missing", "project-only"):
    change = Change.objects.get(target=f"History upgrade {label}")
    assert change.project.slug == (
        "former-history" if label == "project-only" else "test"
    ), label
    if label == "project-only":
        assert change.category.slug == "former-category", label
    else:
        assert change.category_id == change.component.category_id, label
    assert change.workspace.name == "Historical change workspace", label
    assert change.user.username == "history-upgrade", label
    assert change.timestamp == datetime(2026, 1, 1, tzinfo=UTC), label
