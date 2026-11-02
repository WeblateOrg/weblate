# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations, models
from django.db.models import F, Func


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0036_deduplicate_totp_devices"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="verifiedemail", name="accounts_verifiedemail_email"
        ),
        migrations.AddIndex(
            model_name="verifiedemail",
            index=models.Index(
                Func(
                    F("email"),
                    function="LOWER",
                    template='LOWER((%(expressions)s) COLLATE "C")',
                ),
                name="accounts_verifiedemail_email",
            ),
        ),
    ]
