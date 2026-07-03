# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0092_remote_update_change_history"),
        ("workspaces", "0003_workspace_translation_memory"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="contribute_workspace_tm",
            field=models.BooleanField(
                default=False,
                help_text="Contributes translations to the pool shared between projects in the workspace.",
                verbose_name="Contribute to workspace translation memory",
            ),
        ),
        migrations.AddField(
            model_name="project",
            name="use_workspace_tm",
            field=models.BooleanField(
                default=False,
                help_text="Uses the pool of shared translations between projects in the workspace.",
                verbose_name="Use workspace translation memory",
            ),
        ),
    ]
