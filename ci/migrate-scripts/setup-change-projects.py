# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Seed component history with current, stale, and missing project references."""

from __future__ import annotations

from datetime import UTC, datetime

from django.apps import apps

Project = apps.get_model("trans", "Project")
Component = apps.get_model("trans", "Component")
Category = apps.get_model("trans", "Category")
Change = apps.get_model("trans", "Change")
Workspace = apps.get_model("workspaces", "Workspace")
User = apps.get_model("weblate_auth", "User")

component = Component.objects.get(slug="test", project__slug="test")
original = Project.objects.create(name="Former history project", slug="former-history")
actor = User.objects.create_user("history-upgrade", email="history-upgrade@example.com")
category = Category.objects.create(
    project=original, name="Former category", slug="former-category"
)
workspace = Workspace.objects.create(name="Historical change workspace")
for label, owner, linked in (
    ("current", component.project, component),
    ("stale", original, component),
    ("missing", None, component),
    ("project-only", original, None),
):
    change = Change.objects.create(
        component=linked,
        project=owner,
        user=actor,
        target=f"History upgrade {label}",
    )
    Change.objects.filter(pk=change.pk).update(
        project=owner,
        category=category,
        workspace=workspace,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )
