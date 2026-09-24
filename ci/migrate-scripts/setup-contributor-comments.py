# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Seed contributor add-ons before upgrading from a release with format parameters."""

from __future__ import annotations

import os

from django.apps import apps

Project = apps.get_model("trans", "Project")
Category = apps.get_model("trans", "Category")
Component = apps.get_model("trans", "Component")
Addon = apps.get_model("addons", "Addon")
has_category_addons = hasattr(Addon, "category")

sitewide = os.environ.get("CONTRIBUTOR_TEST_SITEWIDE") == "1"
project, other = Project.objects.bulk_create(
    [
        Project(name="Contributor project", slug="contributor-project"),
        Project(name="sitewide" if sitewide else "scoped", slug="contributor-other"),
    ]
)
parent = Category.objects.bulk_create(
    [Category(project=other, name="Parent", slug="parent")]
)[0]
child = Category.objects.bulk_create(
    [Category(project=other, category=parent, name="Child", slug="child")]
)[0]
components = Component.objects.bulk_create(
    [
        Component(
            project=project if kind == "project" else other,
            category=child if kind in {"category", "overlap"} else None,
            name=kind,
            slug=f"contributor-{kind}",
            file_format="json"
            if kind == "unrelated"
            else "po-mono"
            if kind == "mono"
            else "po",
            file_format_params={
                "po_line_wrap": -1,
                **({"po_contributor_comments": "none"} if kind == "explicit" else {}),
            },
        )
        for kind in (
            "project",
            "category",
            "direct",
            "mono",
            "overlap",
            "uncovered",
            "unrelated",
            "explicit",
        )
    ]
)
Addon.objects.bulk_create(
    [
        Addon(name="weblate.gettext.authors", project=project),
        *(
            [Addon(name="weblate.gettext.authors", category=parent)]
            if has_category_addons
            else []
        ),
        *[
            Addon(name="weblate.gettext.authors", component=component)
            for component in components
            if component.name in {"direct", "mono", "overlap", "unrelated", "explicit"}
            or (component.name == "category" and not has_category_addons)
        ],
        *([Addon(name="weblate.gettext.authors")] if sitewide else []),
    ]
)
