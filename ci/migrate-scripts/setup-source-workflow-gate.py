# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Populate workflow configuration on the release schema before upgrading."""

from __future__ import annotations

from django.apps import apps

Project = apps.get_model("trans", "Project")
WorkflowSetting = apps.get_model("trans", "WorkflowSetting")
Language = apps.get_model("lang", "Language")

project = Project.objects.bulk_create(
    [
        Project(
            name="Source gate upgrade",
            slug="source-gate-upgrade",
            web="https://example.com/",
        )
    ]
)[0]
WorkflowSetting.objects.bulk_create(
    [
        WorkflowSetting(
            project=project,
            language=Language.objects.get(code="cs"),
            translation_review=True,
        )
    ]
)
