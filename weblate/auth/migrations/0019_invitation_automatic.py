# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("weblate_auth", "0018_update_builtin_roles")]

    operations = [
        migrations.AddField(
            model_name="invitation",
            name="automatic",
            field=models.BooleanField(default=False, editable=False),
        ),
    ]
