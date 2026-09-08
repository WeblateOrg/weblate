# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import migrations

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps


def cleanup_category_language_metrics(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    """Remove metrics keyed by project IDs instead of category IDs."""
    metric = apps.get_model("metrics", "Metric")
    metric.objects.filter(scope=9).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("metrics", "0001_squashed_0002_new_public_projects_metric_data"),
    ]

    operations = [
        migrations.RunPython(
            cleanup_category_language_metrics, migrations.RunPython.noop
        ),
    ]
