# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("weblate_auth", "0019_invitation_automatic")]

    operations = [
        migrations.AddField(
            model_name="invitation",
            name="team_admin",
            field=models.BooleanField(default=False, editable=False),
        ),
    ]
