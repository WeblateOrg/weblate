# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Repair synthetic database fixtures after the historical upgrade stops."""

from __future__ import annotations

from django.db import connection
from django.db.migrations.executor import MigrationExecutor

apps = (
    MigrationExecutor(connection)
    .loader.project_state([("trans", "0123_unit_line_number")])
    .apps
)
Project = apps.get_model("trans", "Project")
Component = apps.get_model("trans", "Component")

Project.objects.filter(slug="Slug-Upgrade-Duplicate").update(
    slug="slug-upgrade-repaired"
)
Component.objects.filter(project__slug="Slug-Upgrade", slug="shared-component").update(
    slug="component-repaired"
)
