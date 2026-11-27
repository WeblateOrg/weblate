# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0042_account_activity")]

    operations = [
        migrations.AddIndex(
            model_name="accountactivity",
            index=models.Index(
                fields=["removal_at"],
                condition=models.Q(removal_at__isnull=False),
                name="accounts_pending_removal_idx",
            ),
        ),
    ]
