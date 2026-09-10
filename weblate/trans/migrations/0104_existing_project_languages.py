# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0103_project_public_sharing"),
    ]

    operations = [
        migrations.AlterField(
            model_name="category",
            name="new_lang",
            field=models.CharField(
                choices=[
                    ("contact", "Contact maintainers"),
                    ("url", "Point to translation instructions URL"),
                    ("add", "Create new language file"),
                    (
                        "existing",
                        "Create existing project languages; contact maintainers for new languages",
                    ),
                    ("none", "Disable adding new translations"),
                ],
                default="add",
                help_text="How to handle requests for creating new translations.",
                max_length=10,
                verbose_name="Adding new translation",
            ),
        ),
        migrations.AlterField(
            model_name="component",
            name="new_lang",
            field=models.CharField(
                choices=[
                    ("contact", "Contact maintainers"),
                    ("url", "Point to translation instructions URL"),
                    ("add", "Create new language file"),
                    (
                        "existing",
                        "Create existing project languages; contact maintainers for new languages",
                    ),
                    ("none", "Disable adding new translations"),
                ],
                default="add",
                help_text="How to handle requests for creating new translations.",
                max_length=10,
                verbose_name="Adding new translation",
            ),
        ),
        migrations.AlterField(
            model_name="project",
            name="new_lang",
            field=models.CharField(
                choices=[
                    ("contact", "Contact maintainers"),
                    ("url", "Point to translation instructions URL"),
                    ("add", "Create new language file"),
                    (
                        "existing",
                        "Create existing project languages; contact maintainers for new languages",
                    ),
                    ("none", "Disable adding new translations"),
                ],
                default="add",
                help_text="How to handle requests for creating new translations.",
                max_length=10,
                verbose_name="Adding new translation",
            ),
        ),
    ]
