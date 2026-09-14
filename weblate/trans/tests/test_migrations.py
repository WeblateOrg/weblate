# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for translation migrations."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import SimpleTestCase, TransactionTestCase


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


class ContributorCommentsMigrationTest(TransactionTestCase):
    def test_scoped(self) -> None:
        self.check_upgrade(sitewide=False)

    def test_sitewide(self) -> None:
        self.check_upgrade(sitewide=True)

    def check_upgrade(self, *, sitewide: bool) -> None:
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        old = [("trans", "0104_existing_project_languages")]
        scripts = Path(__file__).resolve().parents[3] / "ci" / "migrate-scripts"
        try:
            executor.migrate(old)
            historical_apps = executor.loader.project_state(old).apps
            with (
                patch("django.apps.apps", historical_apps),
                patch.dict(
                    "os.environ",
                    {"CONTRIBUTOR_TEST_SITEWIDE": "1" if sitewide else "0"},
                ),
            ):
                run_path(str(scripts / "setup-contributor-comments.py"))
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            run_path(str(scripts / "assert-contributor-comments.py"))
        finally:
            MigrationExecutor(connection).migrate(latest)
