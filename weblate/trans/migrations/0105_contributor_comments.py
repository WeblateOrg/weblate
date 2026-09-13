# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import migrations

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps


def migrate_contributor_comments(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    Component = apps.get_model("trans", "Component")
    Category = apps.get_model("trans", "Category")
    Addon = apps.get_model("addons", "Addon")
    database = schema_editor.connection.alias
    addons = Addon.objects.using(database).filter(name="weblate.gettext.authors")
    if not addons.exists():
        return
    components = set()
    categories = set()
    projects = set()
    sitewide = False
    for component_id, category_id, project_id in addons.values_list(
        "component_id", "category_id", "project_id"
    ):
        if component_id is not None:
            components.add(component_id)
        elif category_id is not None:
            categories.add(category_id)
        elif project_id is not None:
            projects.add(project_id)
        else:
            sitewide = True

    parents = dict(Category.objects.using(database).values_list("pk", "category_id"))
    pending = []
    for component in (
        Component.objects.using(database)
        .filter(file_format__in=("po", "po-mono"))
        .only("pk", "project_id", "category_id", "file_format_params")
        .iterator(chunk_size=1000)
    ):
        covered = (
            sitewide or component.pk in components or component.project_id in projects
        )
        category_id = component.category_id
        visited = set()
        while not covered and category_id is not None and category_id not in visited:
            covered = category_id in categories
            visited.add(category_id)
            category_id = parents.get(category_id)
        params = dict(component.file_format_params or {})
        if not covered or "po_contributor_comments" in params:
            continue
        params["po_contributor_comments"] = "gettext"
        component.file_format_params = params
        pending.append(component)
        if len(pending) == 1000:
            Component.objects.using(database).bulk_update(
                pending, ["file_format_params"]
            )
            pending.clear()
    if pending:
        Component.objects.using(database).bulk_update(pending, ["file_format_params"])
    addons.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0104_existing_project_languages"),
        ("addons", "0022_addonactivitylog_status"),
    ]

    operations = [
        migrations.RunPython(migrate_contributor_comments, migrations.RunPython.noop),
    ]
