# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0089_repair_license_inheritance"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="component",
            index=models.Index(
                fields=["repo", "branch"], name="trans_comp_repo_branch_idx"
            ),
        ),
    ]
