# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("checks", "0002_check_active_unit_index")]

    operations = [
        migrations.AddField(
            model_name="check",
            name="metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
