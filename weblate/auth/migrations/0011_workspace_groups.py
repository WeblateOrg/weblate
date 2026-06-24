# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workspaces", "0001_initial"),
        ("weblate_auth", "0010_invitation_limit_languages"),
    ]

    operations = [
        migrations.AddField(
            model_name="group",
            name="defining_workspace",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="defined_groups",
                to="workspaces.workspace",
            ),
        ),
        migrations.AddConstraint(
            model_name="group",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(defining_project__isnull=True)
                    | models.Q(defining_workspace__isnull=True)
                ),
                name="weblate_auth_group_single_definition",
            ),
        ),
        migrations.AddConstraint(
            model_name="group",
            constraint=models.UniqueConstraint(
                condition=models.Q(defining_workspace__isnull=False),
                fields=("defining_workspace", "name"),
                name="weblate_auth_group_unique_workspace_name",
            ),
        ),
    ]
