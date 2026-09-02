# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for translation migrations."""

from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import SimpleTestCase


class JSONSortKeysMigrationTest(SimpleTestCase):
    def test_unhashable_legacy_values(self) -> None:
        migration = import_module(
            "weblate.trans.migrations.0102_migrate_json_sort_keys_to_choice"
        )
        components = [
            SimpleNamespace(file_format_params={"json_sort_keys": []}),
            SimpleNamespace(file_format_params={"json_sort_keys": {}}),
        ]
        manager = Mock()
        manager.filter.return_value.iterator.return_value = iter(components)
        component_model = SimpleNamespace(objects=manager)
        apps = Mock()
        apps.get_model.return_value = component_model

        migration.migrate_json_sort_keys_from_bool_to_choice(apps, None)

        self.assertEqual(
            [component.file_format_params for component in components],
            [{"json_sort_keys": "none"}, {"json_sort_keys": "none"}],
        )
        manager.bulk_update.assert_called_once_with(components, ["file_format_params"])
