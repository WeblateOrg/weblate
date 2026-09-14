# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import django.utils.translation
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0102_migrate_json_sort_keys_to_choice"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="public_sharing",
            field=models.BooleanField(
                default=False,
                help_text=django.utils.translation.gettext_lazy(
                    "Allows anonymous access to the engage pages and status widgets "
                    "for Private and Custom projects."
                ),
                verbose_name=django.utils.translation.gettext_lazy("Public sharing"),
            ),
        ),
    ]
