# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0095_report"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="change",
            index=models.Index(
                condition=models.Q(("action", 46)),
                fields=["-timestamp"],
                name="trans_change_announce_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="change",
            index=models.Index(
                condition=models.Q(
                    ("component__isnull", False),
                    ("language__isnull", False),
                ),
                fields=["language", "component", "-timestamp"],
                name="trans_change_lang_comp_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="change",
            index=models.Index(
                condition=models.Q(
                    ("category__isnull", False),
                    ("language__isnull", False),
                ),
                fields=["language", "category", "-timestamp"],
                name="trans_change_lang_cat_idx",
            ),
        ),
    ]
