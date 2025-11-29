# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations


def migrate_automatically_translated_labels(apps, schema_editor):
    """
    Migrate the "Automatically translated" label data to the new column.

    This finds all units that have the "Automatically translated" label
    and sets their automatically_translated column to True.
    """
    Label = apps.get_model("trans", "Label")

    auto_labels = Label.objects.filter(name="Automatically translated")

    if not auto_labels.exists():
        return

    for label in auto_labels:
        label.unit_set.update(automatically_translated=True)

    auto_labels.delete()


def reverse_migration(apps, schema_editor):
    """
    Reverse migration: set automatically_translated back to the label.

    This recreates the "Automatically translated" label for units
    that have automatically_translated=True.
    """
    Unit = apps.get_model("trans", "Unit")
    Label = apps.get_model("trans", "Label")

    auto_translated_units = Unit.objects.filter(automatically_translated=True)

    projects = {}
    for unit in auto_translated_units:
        project = unit.translation.component.project
        if project.id not in projects:
            projects[project.id] = project

        label, _ = Label.objects.get_or_create(
            project=project,
            name="Automatically translated",
            defaults={"color": "yellow"},
        )

        unit.labels.add(label)


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0052_unit_automatically_translated_alter_unit_labels"),
    ]

    operations = [
        migrations.RunPython(
            migrate_automatically_translated_labels,
            reverse_code=reverse_migration,
        ),
    ]
