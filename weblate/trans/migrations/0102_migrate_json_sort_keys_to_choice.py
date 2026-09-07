# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from itertools import batched

from django.db import migrations

BATCH_SIZE = 1000
JSON_SORT_KEYS = "json_sort_keys"
NEW_VALUES = frozenset({"none", "case_sensitive", "case_insensitive"})


def migrate_json_sort_keys_from_bool_to_choice(apps, schema_editor) -> None:
    Component = apps.get_model("trans", "Component")

    def convert(component):
        file_format_params = component.file_format_params or {}
        value = file_format_params.get(JSON_SORT_KEYS)
        if isinstance(value, str) and value in NEW_VALUES:
            return component
        if value is True:
            file_format_params[JSON_SORT_KEYS] = "case_sensitive"
        else:
            file_format_params[JSON_SORT_KEYS] = "none"
        component.file_format_params = file_format_params
        return component

    queryset = Component.objects.filter(
        file_format_params__has_key=JSON_SORT_KEYS
    ).iterator(chunk_size=BATCH_SIZE)
    for batch in batched(queryset, BATCH_SIZE):
        Component.objects.bulk_update(
            [convert(component) for component in batch], ["file_format_params"]
        )


def reverse_json_sort_keys_to_choice(apps, schema_editor) -> None:
    Component = apps.get_model("trans", "Component")

    def convert(component):
        file_format_params = component.file_format_params or {}
        value = file_format_params.get(JSON_SORT_KEYS)
        if not isinstance(value, str) or value not in NEW_VALUES:
            return component
        if value == "case_sensitive":
            file_format_params[JSON_SORT_KEYS] = True
        else:
            file_format_params[JSON_SORT_KEYS] = False
        component.file_format_params = file_format_params
        return component

    queryset = Component.objects.filter(
        file_format_params__has_key=JSON_SORT_KEYS
    ).iterator(chunk_size=BATCH_SIZE)
    for batch in batched(queryset, BATCH_SIZE):
        Component.objects.bulk_update(
            [convert(component) for component in batch], ["file_format_params"]
        )


class Migration(migrations.Migration):
    """Migrate JSON sort keys from bool to choice (see trans.0046_component_file_format_params)."""

    dependencies = [
        ("trans", "0101_component_vcs_params"),
    ]

    operations = [
        migrations.RunPython(
            migrate_json_sort_keys_from_bool_to_choice,
            reverse_code=reverse_json_sort_keys_to_choice,
            elidable=True,
        ),
    ]
