# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.contrib.postgres import indexes as postgres_indexes
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0067_componentlink_alter_component_links"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="unit",
            index=postgres_indexes.GinIndex(
                postgres_indexes.OpClass(models.F("source"), name="gin_trgm_ops"),
                condition=Q(state__gte=20) & ~Q(target=""),
                name="trans_unit_source_tm_idx",
            ),
        ),
    ]
