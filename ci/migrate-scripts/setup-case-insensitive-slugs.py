# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Create conflicting slugs and valid cross-project slug reuse before upgrading."""

from __future__ import annotations

from django.apps import apps

Project = apps.get_model("trans", "Project")
Component = apps.get_model("trans", "Component")
Language = apps.get_model("lang", "Language")

project, other_project, _conflicting_project = Project.objects.bulk_create(
    [
        Project(name="Slug upgrade", slug="Slug-Upgrade"),
        Project(name="Other slug upgrade", slug="slug-upgrade-duplicate"),
        Project(name="Conflicting slug upgrade", slug="Slug-Upgrade-Duplicate"),
    ]
)
language = Language.objects.get(code="en")
Component.objects.bulk_create(
    [
        Component(
            project=owner,
            name=name,
            slug=slug,
            source_language=language,
            vcs="local",
            repo="local:",
        )
        for owner, name, slug in (
            (project, "Original component", "Shared-Component"),
            (project, "Conflicting component", "shared-component"),
            (other_project, "Other component", "Shared-Component"),
        )
    ]
)
