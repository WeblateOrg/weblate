# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0088_change_workspace_backfill"),
    ]

    operations = [
        migrations.AddField(
            model_name="change",
            name="message",
            field=models.CharField(
                blank=True,
                default="",
                max_length=500,
                verbose_name="Message",
            ),
        ),
    ]
