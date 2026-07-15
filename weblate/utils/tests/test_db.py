# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import TestCase
from unittest.mock import MagicMock, patch

from django.db import DatabaseError
from django.test import TestCase as DjangoTestCase

from weblate.trans.models import Component, Project, Unit
from weblate.trans.tests.test_views import FixtureComponentTestCase
from weblate.utils.db import (
    adjust_similarity_threshold,
    get_database_disk_usage,
    get_database_size,
    get_invalid_database_statistics,
    re_escape,
)

BASE_SQL = 'SELECT "trans_unit"."id" FROM "trans_unit" WHERE '


class DbTest(TestCase):
    def test_re_escape(self) -> None:
        self.assertEqual(re_escape("[a-z]"), "\\[a\\-z\\]")
        self.assertEqual(re_escape("a{1,4}"), "a\\{1,4\\}")

    @patch("weblate.utils.db.connections")
    def test_adjust_similarity_threshold_applies_boundary_updates(
        self, connections_mock
    ) -> None:
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        connection = MagicMock()
        connection.cursor.return_value = cursor
        connection.weblate_similarity = 0.97
        connections_mock.__contains__.return_value = False
        connections_mock.__getitem__.return_value = connection

        adjust_similarity_threshold(0.92)

        cursor.execute.assert_called_once_with("SELECT set_limit(%s)", [0.92])

    @patch("weblate.utils.db.connections")
    def test_adjust_similarity_threshold_applies_nearby_updates(
        self, connections_mock
    ) -> None:
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        connection = MagicMock()
        connection.cursor.return_value = cursor
        connection.weblate_similarity = 0.98
        connections_mock.__contains__.return_value = False
        connections_mock.__getitem__.return_value = connection

        adjust_similarity_threshold(0.966)

        cursor.execute.assert_called_once_with("SELECT set_limit(%s)", [0.966])

    @patch("weblate.utils.db.connections")
    def test_get_database_size_postgresql(self, connections_mock) -> None:
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = [123456]
        connection = MagicMock(vendor="postgresql")
        connection.cursor.return_value = cursor
        connections_mock.__getitem__.return_value = connection

        self.assertEqual(get_database_size(), 123456)
        cursor.execute.assert_called_once_with(
            "SELECT pg_database_size(current_database())"
        )

    @patch("weblate.utils.db.connections")
    def test_get_database_size_non_postgresql(self, connections_mock) -> None:
        connection = MagicMock(vendor="sqlite")
        connections_mock.__getitem__.return_value = connection

        self.assertIsNone(get_database_size())
        connection.cursor.assert_not_called()

    @patch("weblate.utils.db.connections")
    def test_get_database_size_database_error(self, connections_mock) -> None:
        connection = MagicMock(vendor="postgresql")
        connection.cursor.side_effect = DatabaseError
        connections_mock.__getitem__.return_value = connection

        self.assertIsNone(get_database_size())

    @patch("weblate.utils.db.connections")
    def test_get_invalid_database_statistics(self, connections_mock) -> None:
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchall.return_value = [
            ("public", "trans_unit"),
            ("weblate", "memory_memory"),
        ]
        connection = MagicMock(vendor="postgresql")
        connection.cursor.return_value = cursor
        connections_mock.__getitem__.return_value = connection

        self.assertEqual(
            get_invalid_database_statistics(),
            ["public.trans_unit", "weblate.memory_memory"],
        )
        cursor.execute.assert_called_once()
        query = cursor.execute.call_args.args[0]
        self.assertIn("pg_catalog.pg_index", query)
        self.assertIn("('r', 'm', 'p', 'i')", query)
        self.assertNotIn("'I'", query)
        self.assertIn("index_statistics.indrelid", query)

    @patch("weblate.utils.db.connections")
    def test_get_invalid_database_statistics_non_postgresql(
        self, connections_mock
    ) -> None:
        connection = MagicMock(vendor="sqlite")
        connections_mock.__getitem__.return_value = connection

        self.assertEqual(get_invalid_database_statistics(), [])
        connection.cursor.assert_not_called()

    @patch("weblate.utils.db.disk_usage", return_value="usage")
    @patch("weblate.utils.db.connections")
    def test_get_database_disk_usage_postgresql(
        self, connections_mock, disk_usage_mock
    ) -> None:
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = ["/var/lib/postgresql/data"]
        connection = MagicMock(vendor="postgresql")
        connection.settings_dict = {"HOST": ""}
        connection.cursor.return_value = cursor
        connections_mock.__getitem__.return_value = connection

        self.assertEqual(get_database_disk_usage(), "usage")
        cursor.execute.assert_called_once_with(
            "SELECT current_setting('data_directory')"
        )
        disk_usage_mock.assert_called_once_with("/var/lib/postgresql/data")

    @patch("weblate.utils.db.disk_usage")
    @patch("weblate.utils.db.connections")
    def test_get_database_disk_usage_remote_postgresql(
        self, connections_mock, disk_usage_mock
    ) -> None:
        connection = MagicMock(vendor="postgresql")
        connection.settings_dict = {"HOST": "database.example.com"}
        connections_mock.__getitem__.return_value = connection

        self.assertIsNone(get_database_disk_usage())
        connection.cursor.assert_not_called()
        disk_usage_mock.assert_not_called()

    @patch("weblate.utils.db.disk_usage", side_effect=OSError)
    @patch("weblate.utils.db.connections")
    def test_get_database_disk_usage_error(
        self, connections_mock, disk_usage_mock
    ) -> None:
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchone.return_value = ["/var/lib/postgresql/data"]
        connection = MagicMock(vendor="postgresql")
        connection.settings_dict = {"HOST": "localhost"}
        connection.cursor.return_value = cursor
        connections_mock.__getitem__.return_value = connection

        self.assertIsNone(get_database_disk_usage())
        disk_usage_mock.assert_called_once_with("/var/lib/postgresql/data")


class DatabaseStatisticsTest(DjangoTestCase):
    def test_query(self) -> None:
        self.assertIsInstance(get_invalid_database_statistics(), list)


class PostgreSQLOperatorTest(TestCase):
    def test_search(self) -> None:
        queryset = Unit.objects.filter(source__trgm_search="test").only("id")
        self.assertEqual(
            str(queryset.query),
            f'{BASE_SQL}"trans_unit"."source" % test = true',
        )
        queryset = Unit.objects.filter(source__trgm_search="'''").only("id")
        self.assertEqual(
            str(queryset.query),
            f'{BASE_SQL}UPPER("trans_unit"."source") LIKE UPPER(%\'\'\'%)',
        )

    def test_substring(self) -> None:
        queryset = Unit.objects.filter(source__substring="test").only("id")
        self.assertEqual(
            str(queryset.query),
            f'{BASE_SQL}"trans_unit"."source" ILIKE %test%',
        )
        queryset = Unit.objects.filter(source__substring="'''").only("id")
        self.assertEqual(
            str(queryset.query),
            f'{BASE_SQL}UPPER("trans_unit"."source") LIKE UPPER(%\'\'\'%)',
        )


class SearchSQLOperatorTest(FixtureComponentTestCase):
    def test_search(self) -> None:
        # Verifies that even complex query with a fallback is built properly
        # This is essentially what bulk edit does with such search

        obj = Project.objects.all()[0]
        unit_set = Unit.objects.filter(translation__component__project=obj).prefetch()
        matching = unit_set.search("10°", project=obj)
        components = Component.objects.filter(
            id__in=matching.values_list("translation__component_id", flat=True)
        )
        self.assertEqual(len(components), 0)
