# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Seed project-token repair cases using the source release's historical models."""

from __future__ import annotations

from django.contrib.auth.hashers import make_password
from django.db import connection
from django.db.migrations.loader import MigrationLoader

apps = MigrationLoader(connection).project_state().apps
User = apps.get_model("weblate_auth", "User")
Group = apps.get_model("weblate_auth", "Group")
TeamMembership = apps.get_model("weblate_auth", "TeamMembership")
Token = apps.get_model("authtoken", "Token")
Project = apps.get_model("trans", "Project")
Workspace = apps.get_model("workspaces", "Workspace")

project = Project.objects.get(slug="test")
workspace = Workspace.objects.create(name="Project token repair")
owners = Group.objects.create(name="Owners", defining_workspace=workspace)
global_group = Group.objects.create(name="Project token repair global")
project_group = Group.objects.create(
    name="Project token repair project", defining_project=project
)

for name, is_bot, is_active, has_project, has_token in (
    ("orphan-sentinel", True, True, False, True),
    ("orphan-normal", True, True, False, True),
    ("orphan-inactive", True, False, False, True),
    ("orphan-revoked", True, False, False, False),
    ("live-sentinel", True, True, True, True),
    ("human", False, True, False, True),
    ("custom", True, True, False, True),
    ("internal", True, False, False, True),
):
    username = f"bot-repair-{name}"
    email = f"{username}@bots.noreply.weblate.org"
    if name == "custom":
        username = "repair-custom"
    elif name == "internal":
        username = "weblate:repair-internal"
    user = User.objects.create(
        username=username,
        email=email,
        full_name="Deleted User" if name.endswith("sentinel") else "Repair control",
        is_bot=is_bot,
        is_active=is_active,
        password=make_password("repair-test-password"),
    )
    for group in (owners, global_group, project_group):
        # Orphans can retain project team administration without membership.
        group.admins.add(user)
        if group != project_group or has_project:
            TeamMembership.objects.create(user=user, group=group)
    if has_token:
        Token.objects.create(user=user, key=f"repair-{name}")
