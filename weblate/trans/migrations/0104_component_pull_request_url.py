# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0103_project_public_sharing"),
    ]

    operations = [
        migrations.AddField(
            model_name="component",
            name="pull_request_url",
            field=models.URLField(
                blank=True, default="", editable=False, max_length=300
            ),
        ),
    ]
