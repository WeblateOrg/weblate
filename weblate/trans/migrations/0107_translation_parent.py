# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("lang", "0007_alter_language_code"),
        ("trans", "0106_alter_component_manage_units"),
    ]

    operations = [
        migrations.AddField(
            model_name="unit",
            name="translation_parent",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="translation_children",
                to="trans.unit",
            ),
        ),
        migrations.AddField(
            model_name="workflowsetting",
            name="source_language",
            field=models.ForeignKey(
                blank=True,
                help_text="Translate from this language. Leave empty to use the component source language.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="source_workflow_settings",
                to="lang.language",
                verbose_name="Source language",
            ),
        ),
    ]
