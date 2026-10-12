# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import migrations

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps


def import_settings(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    Setting = apps.get_model("configuration", "Setting")
    Project = apps.get_model("trans", "Project")
    installation_model = apps.get_model("machinery", "MachineryInstallation")
    exclusion_model = apps.get_model("machinery", "MachineryExclusion")
    database = schema_editor.connection.alias

    for setting in Setting.objects.using(database).filter(category=2).iterator():
        installation_model.objects.using(database).create(
            engine=setting.name, configuration=setting.value
        )

    for project in (
        Project.objects.using(database).exclude(machinery_settings={}).iterator()
    ):
        for engine, configuration in project.machinery_settings.items():
            # A project entry replaced the site entry, even when it was disabled.
            exclusion_model.objects.using(database).create(
                project_id=project.pk, engine=engine
            )
            if configuration is not None:
                installation_model.objects.using(database).create(
                    project_id=project.pk, engine=engine, configuration=configuration
                )
    Setting.objects.using(database).filter(category=2).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("machinery", "0001_initial"),
        ("configuration", "0001_squashed_0002_alter_setting_category"),
    ]

    operations = [migrations.RunPython(import_settings, migrations.RunPython.noop)]
