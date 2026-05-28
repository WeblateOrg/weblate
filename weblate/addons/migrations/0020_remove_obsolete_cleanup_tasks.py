# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations
from django.utils.timezone import now

OBSOLETE_CLEANUP_TASKS = (
    "weblate.trans.tasks.cleanup_old_comments",
    "weblate.trans.tasks.cleanup_old_suggestions",
)

OBSOLETE_CLEANUP_SCHEDULES = (
    "cleanup-old-comments",
    "cleanup-old-suggestions",
)


def remove_obsolete_cleanup_tasks(apps, _schema_editor) -> None:
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTasks = apps.get_model("django_celery_beat", "PeriodicTasks")

    deleted = 0
    deleted += PeriodicTask.objects.filter(
        name__in=OBSOLETE_CLEANUP_SCHEDULES
    ).delete()[0]
    deleted += PeriodicTask.objects.filter(task__in=OBSOLETE_CLEANUP_TASKS).delete()[0]

    if deleted:
        PeriodicTasks.objects.update_or_create(ident=1, defaults={"last_update": now()})


class Migration(migrations.Migration):
    dependencies = [
        ("django_celery_beat", "0018_improve_crontab_helptext"),
        ("addons", "0019_update_cdnjs_events"),
    ]

    operations = [
        migrations.RunPython(
            remove_obsolete_cleanup_tasks,
            migrations.RunPython.noop,
            elidable=True,
        ),
    ]
