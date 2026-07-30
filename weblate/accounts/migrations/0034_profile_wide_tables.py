# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0033_audit_rate_limit"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="wide_tables",
            field=models.BooleanField(
                default=False,
                help_text="Instead of hiding columns on narrow screens, keep all columns and scroll the table horizontally.",
                verbose_name="Show all columns in lists using horizontal scrolling",
            ),
        ),
    ]
