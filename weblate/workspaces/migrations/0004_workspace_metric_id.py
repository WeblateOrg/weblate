# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.db import migrations, models
from django.db.models.expressions import RawSQL


class Migration(migrations.Migration):
    dependencies = [
        ("workspaces", "0003_workspace_translation_memory"),
    ]

    operations = [
        migrations.RunSQL(
            sql="CREATE SEQUENCE workspaces_workspace_metric_id_seq AS integer",
            reverse_sql="DROP SEQUENCE workspaces_workspace_metric_id_seq",
        ),
        migrations.AddField(
            model_name="workspace",
            name="metric_id",
            field=models.IntegerField(
                db_default=RawSQL(
                    "nextval('workspaces_workspace_metric_id_seq'::regclass)", ()
                ),
                editable=False,
                unique=True,
            ),
        ),
    ]
