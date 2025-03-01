# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Generated by Django 5.1.4 on 2024-12-11 11:43

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0013_bot_notifications"),
        ("trans", "0025_alter_announcement_notify"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="subscription",
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name="subscription",
            constraint=models.UniqueConstraint(
                fields=("notification", "scope", "project", "component", "user"),
                name="accounts_subscription_notification_unique",
                nulls_distinct=False,
            ),
        ),
    ]
