# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workspaces", "0002_workspace_add_message_workspace_addon_message_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="workspace",
            name="contribute_workspace_tm",
            field=models.BooleanField(
                default=False,
                help_text="Contributes translations to the pool shared between projects in this workspace.",
                verbose_name="Contribute to workspace translation memory",
            ),
        ),
        migrations.AddField(
            model_name="workspace",
            name="use_workspace_tm",
            field=models.BooleanField(
                default=False,
                help_text="Uses the pool of shared translations between projects in this workspace.",
                verbose_name="Use workspace translation memory",
            ),
        ),
    ]
