# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0090_component_repo_branch_index"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="change",
            index=models.Index(
                condition=models.Q(
                    ("action__in", [60, 61, 62]),
                    ("project__isnull", True),
                    ("category__isnull", True),
                    ("component__isnull", True),
                ),
                fields=["-timestamp"],
                name="trans_change_site_addon_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="change",
            index=models.Index(
                condition=models.Q(
                    ("action__in", [60, 61, 62]),
                    ("project__isnull", False),
                    ("component__isnull", True),
                ),
                fields=["project", "-timestamp"],
                name="trans_change_proj_addon_idx",
            ),
        ),
    ]
