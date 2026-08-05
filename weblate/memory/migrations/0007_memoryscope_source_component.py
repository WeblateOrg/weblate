# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("memory", "0006_memory_source_gist_prefix"),
        ("trans", "0097_workflowsetting_restrict_direct_editing"),
    ]

    operations = [
        migrations.AddField(
            model_name="memoryscope",
            name="source_component",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="trans.component",
            ),
        ),
        migrations.AddIndex(
            model_name="memoryscope",
            index=models.Index(
                fields=["scope", "source_component", "memory"],
                name="memory_scope_source_component",
            ),
        ),
    ]
