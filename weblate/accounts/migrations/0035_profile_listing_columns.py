# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations, models

import weblate.accounts.models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0034_profile_wide_tables"),
    ]

    operations = [
        migrations.AddField(
            model_name="profile",
            name="listing_columns",
            field=models.JSONField(
                blank=True,
                default=weblate.accounts.models.get_default_listing_columns,
                help_text="Choose which statistics columns are shown in project, component, and language lists.",
                validators=[weblate.accounts.models.validate_listing_columns],
                verbose_name="Visible columns in lists",
            ),
        ),
    ]
