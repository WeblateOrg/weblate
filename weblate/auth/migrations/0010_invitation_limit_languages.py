# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("weblate_auth", "0009_teammembership"),
    ]

    operations = [
        migrations.AddField(
            model_name="invitation",
            name="limit_languages",
            field=models.ManyToManyField(
                blank=True,
                help_text="Limit permissions from this team to these languages. Project-wide, component-wide and global permissions from this team are not granted when a language limit is set. Empty selection uses the team language selection without additional limit.",
                to="lang.language",
                verbose_name="Limit languages",
            ),
        ),
    ]
