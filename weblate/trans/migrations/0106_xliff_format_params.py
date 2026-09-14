# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import migrations

if TYPE_CHECKING:
    from django.db.backends.base.schema import BaseDatabaseSchemaEditor
    from django.db.migrations.state import StateApps

FORMAT_MIGRATION_MAPPING = {
    "xliff": ("xliff", {"xliff_placeables": "placeables"}),
    "plainxliff": ("xliff", {"xliff_placeables": "plain"}),
    "xliff2": ("xliff2", {"xliff_placeables": "plain"}),
    "xliff2-placeables": ("xliff2", {"xliff_placeables": "placeables"}),
}


def migrate_xliff_placeables(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    Component = apps.get_model("trans", "Component")
    components_to_update = []
    for component in Component.objects.filter(
        file_format__in=FORMAT_MIGRATION_MAPPING.keys()
    ):
        new_format, file_format_params = FORMAT_MIGRATION_MAPPING[component.file_format]
        component.file_format = new_format
        component.file_format_params.update(file_format_params)
        components_to_update.append(component)

    Component.objects.bulk_update(
        components_to_update, ["file_format", "file_format_params"]
    )


def reverse_xliff_placeables_migration(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    Component = apps.get_model("trans", "Component")
    reverse_map = {
        ("xliff", "placeables"): "xliff",
        ("xliff", "plain"): "plainxliff",
        ("xliff2", "plain"): "xliff2",
        ("xliff2", "placeables"): "xliff2-placeables",
    }
    components_to_update = []
    for component in Component.objects.filter(file_format__in=("xliff", "xliff2")):
        params = dict(component.file_format_params or {})
        placeables = params.pop("xliff_placeables", None)
        if placeables is None:
            continue
        key = (component.file_format, placeables)
        if key not in reverse_map:
            continue
        component.file_format = reverse_map[key]
        component.file_format_params = params
        components_to_update.append(component)

    Component.objects.bulk_update(
        components_to_update, ["file_format", "file_format_params"]
    )


def migrate_xliff_whitespace_handling(
    apps: StateApps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    Component = apps.get_model("trans", "Component")
    supported_file_formats = ("xliff", "xliff2", "poxliff", "apple-xliff")
    components_to_update = []
    for component in Component.objects.filter(file_format__in=supported_file_formats):
        params = dict(component.file_format_params or {})
        params["xml_whitespace_handling"] = "standard"
        component.file_format_params = params
        components_to_update.append(component)

    Component.objects.bulk_update(components_to_update, ["file_format_params"])


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0105_contributor_comments"),
    ]

    operations = [
        migrations.RunPython(
            migrate_xliff_placeables, reverse_code=reverse_xliff_placeables_migration
        ),
        migrations.RunPython(
            migrate_xliff_whitespace_handling, reverse_code=migrations.RunPython.noop
        ),
    ]
