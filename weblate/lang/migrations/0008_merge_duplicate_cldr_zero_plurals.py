# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import migrations
from django.db.models import Count

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps


def merge_duplicate_cldr_zero_plurals(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    Plural = apps.get_model("lang", "Plural")
    Translation = apps.get_model("trans", "Translation")
    alias = schema_editor.connection.alias
    plurals = Plural.objects.using(alias).filter(source=3)
    duplicates = (
        plurals.values("language_id").annotate(count=Count("pk")).filter(count__gt=1)
    )
    for duplicate in duplicates.iterator():
        ids = list(
            plurals.filter(language_id=duplicate["language_id"])
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        Translation.objects.using(alias).filter(plural_id__in=ids[1:]).update(
            plural_id=ids[0]
        )
        plurals.filter(pk__in=ids[1:]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("lang", "0007_alter_language_code"),
        ("trans", "0121_clear_github_app_push"),
    ]

    operations = [
        migrations.RunPython(
            merge_duplicate_cldr_zero_plurals, migrations.RunPython.noop
        ),
    ]
