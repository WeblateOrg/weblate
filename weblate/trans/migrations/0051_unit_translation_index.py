# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
# Generated manually to optimize pending changes counting

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0050_alter_component_file_format_params"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="unit",
            index=models.Index(
                fields=["translation"],
                name="trans_unit_translation_idx",
            ),
        ),
    ]
