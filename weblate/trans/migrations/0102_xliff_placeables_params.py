# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.db import migrations

FORMAT_MIGRATION_MAPPING = {
    "xliff": ("xliff", {"xliff_placeables": "placeables"}),
    "plainxliff": ("xliff", {"xliff_placeables": "plain"}),
    "xliff2": ("xliff2", {"xliff_placeables": "plain"}),
    "xliff2-placeables": ("xliff2", {"xliff_placeables": "placeables"}),
}


def migrate_xliff_placeables(apps, schema_editor) -> None:
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


def reverse_migration(apps, schema_editor) -> None:
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


class Migration(migrations.Migration):
    dependencies = [
        ("trans", "0101_component_vcs_params"),
    ]

    operations = [
        migrations.RunPython(migrate_xliff_placeables, reverse_code=reverse_migration),
    ]
