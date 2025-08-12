# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0045_alter_change_action"),
    ]

    operations = [
        migrations.AddField(
            model_name="component",
            name="hide_glossary_matches",
            field=models.BooleanField(
                default=False,
                verbose_name="Do not show glossary matches",
                help_text="Hides the glossary panel in the translation editor.",
            ),
        ),
    ]
