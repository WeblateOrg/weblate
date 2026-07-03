# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.contrib.postgres import indexes as postgres_indexes
from django.contrib.postgres.operations import BtreeGistExtension
from django.db import migrations, models
from django.db.models.functions import Left


class Migration(migrations.Migration):
    dependencies = [
        ("memory", "0005_memory_scopes"),
    ]

    operations = [
        BtreeGistExtension(),
        migrations.AddIndex(
            model_name="memory",
            index=postgres_indexes.GistIndex(
                models.F("source_language"),
                models.F("target_language"),
                postgres_indexes.OpClass(Left("source", 2048), name="gist_trgm_ops"),
                name="memory_source_gist_prefix",
            ),
        ),
    ]
