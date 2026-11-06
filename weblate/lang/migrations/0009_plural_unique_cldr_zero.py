# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("lang", "0008_merge_duplicate_cldr_zero_plurals")]

    operations = [
        migrations.AddConstraint(
            model_name="plural",
            constraint=models.UniqueConstraint(
                fields=("language",),
                condition=models.Q(source=3),
                name="lang_plural_unique_cldr_zero",
            ),
        ),
    ]
