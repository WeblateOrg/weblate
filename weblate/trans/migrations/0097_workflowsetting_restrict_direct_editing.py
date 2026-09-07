# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0096_change_recent_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="workflowsetting",
            name="restrict_direct_editing",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Only users with the “Edit string when suggestions are enforced” "
                    "permission can make direct changes."
                ),
                verbose_name="Restrict direct editing",
            ),
        ),
        migrations.AlterField(
            model_name="component",
            name="suggestion_voting",
            field=models.BooleanField(
                default=False,
                help_text="Allows users to vote on suggestions.",
                verbose_name="Suggestion voting",
            ),
        ),
        migrations.AlterField(
            model_name="workflowsetting",
            name="suggestion_voting",
            field=models.BooleanField(
                default=False,
                help_text="Allows users to vote on suggestions.",
                verbose_name="Suggestion voting",
            ),
        ),
    ]
