# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import migrations
from django.utils.timezone import now

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps

OBSOLETE_BACKUP_SCHEDULES = (
    "settings-backup",
    "database-backup",
)


def remove_obsolete_backup_tasks(
    apps: StateApps, _schema_editor: BaseDatabaseSchemaEditor
) -> None:
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTasks = apps.get_model("django_celery_beat", "PeriodicTasks")

    deleted = PeriodicTask.objects.filter(name__in=OBSOLETE_BACKUP_SCHEDULES).delete()[
        0
    ]

    if deleted:
        PeriodicTasks.objects.update_or_create(ident=1, defaults={"last_update": now()})


class Migration(migrations.Migration):
    dependencies = [
        ("django_celery_beat", "0019_alter_periodictasks_options"),
        ("wladmin", "0006_alter_backuplog_event"),
    ]

    operations = [
        migrations.RunPython(
            remove_obsolete_backup_tasks,
            migrations.RunPython.noop,
            elidable=True,
        ),
    ]
