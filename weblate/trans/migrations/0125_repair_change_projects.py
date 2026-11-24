# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import migrations
from django.db.models import F, OuterRef, Subquery

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps


def repair_change_projects(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    using = schema_editor.connection.alias
    Change = apps.get_model("trans", "Change")
    Component = apps.get_model("trans", "Component")
    component = Component.objects.using(using).filter(pk=OuterRef("component_id"))
    history = Change.objects.using(using).filter(component__isnull=False)
    history.exclude(project_id=F("component__project_id")).update(
        project_id=Subquery(component.values("project_id"))
    )
    history.filter(category__isnull=False).exclude(
        category__project_id=F("component__project_id")
    ).update(category_id=Subquery(component.values("category_id")))


class Migration(migrations.Migration):
    dependencies = [("trans", "0124_case_insensitive_slugs")]

    operations = [
        migrations.RunPython(repair_change_projects, migrations.RunPython.noop),
    ]
