# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations, models
from django.db.models import F, Func


class Migration(migrations.Migration):
    dependencies = [
        ("weblate_auth", "0016_user_visibility_teams"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="user", name="weblate_auth_user_email_ci"
        ),
        migrations.AddConstraint(
            model_name="user",
            constraint=models.UniqueConstraint(
                Func(
                    F("email"),
                    function="LOWER",
                    template='LOWER((%(expressions)s) COLLATE "C")',
                ),
                name="weblate_auth_user_email_ci",
            ),
        ),
    ]
