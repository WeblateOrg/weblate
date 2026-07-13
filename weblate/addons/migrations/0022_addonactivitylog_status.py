# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations, models


def migrate_activity_status(apps, schema_editor) -> None:
    activity_log = apps.get_model("addons", "AddonActivityLog")
    # These high-frequency events were always excluded from activity logging,
    # but rows used to be created for them before the exclusion was applied.
    activity_log.objects.filter(event__in=(6, 8)).delete()
    activity_log.objects.filter(details__error=True).update(status=2)
    activity_log.objects.filter(pending=True).update(status=0)


class Migration(migrations.Migration):
    dependencies = [
        ("addons", "0021_migrate_fedora_messaging_amqp_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="addonactivitylog",
            name="status",
            field=models.IntegerField(
                choices=[
                    (0, "Pending"),
                    (1, "Success"),
                    (2, "Error"),
                    (3, "Skipped"),
                ],
                default=1,
            ),
        ),
        migrations.RunPython(migrate_activity_status, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="addonactivitylog",
            name="pending",
        ),
    ]
