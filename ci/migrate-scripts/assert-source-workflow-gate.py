# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Verify the gate against populated, upgraded workflow rows without model helpers."""

from __future__ import annotations

import json

from django.apps import apps
from django.db import connection, transaction

Project = apps.get_model("trans", "Project")
WorkflowSetting = apps.get_model("trans", "WorkflowSetting")
Language = apps.get_model("lang", "Language")

project = Project.objects.get(slug="source-gate-upgrade")
workflow = WorkflowSetting.objects.get(project=project)
assert workflow.translation_review
assert workflow.source_language_id is None
with transaction.atomic(), connection.cursor() as cursor:
    cursor.execute("SELECT weblate_source_workflow_gate(%s, true)::text", [project.pk])
    assert json.loads(cursor.fetchone()[0]) == {}
    source = Language.objects.get(code="en")
    WorkflowSetting.objects.filter(pk=workflow.pk).update(source_language_id=source.pk)
    cursor.execute("SELECT weblate_source_workflow_gate(%s, false)::text", [project.pk])
    assert json.loads(cursor.fetchone()[0]) == {str(workflow.language_id): source.pk}
    # Leave the migration test project in its original configuration.
    transaction.set_rollback(True)
