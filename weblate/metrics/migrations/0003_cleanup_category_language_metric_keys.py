# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations


def cleanup_category_language_metrics(apps, schema_editor) -> None:
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
