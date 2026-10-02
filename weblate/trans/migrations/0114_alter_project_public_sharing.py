# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import django.utils.translation
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0113_source_workflow_gate"),
    ]

    operations = [
        migrations.AlterField(
            model_name="project",
            name="public_sharing",
            field=models.BooleanField(
                default=False,
                help_text=django.utils.translation.gettext_lazy(
                    "Allows anonymous access to the engage pages and status widgets "
                    "for Private and Custom projects. Public and Protected projects "
                    "are always publicly shared regardless of this setting."
                ),
                verbose_name=django.utils.translation.gettext_lazy("Public sharing"),
            ),
        ),
    ]
