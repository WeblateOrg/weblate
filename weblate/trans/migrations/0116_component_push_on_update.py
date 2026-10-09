# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0115_alter_project_contribute_shared_tm"),
    ]

    operations = [
        migrations.AddField(
            model_name="component",
            name="push_on_update",
            field=models.BooleanField(
                default=True,
                help_text="Whether the repository should be pushed upstream after updating it, even when the update did not commit any translations. When turned off, commits made by the update are pushed with the next translation commit.",
                verbose_name="Push on update",
            ),
        ),
    ]
