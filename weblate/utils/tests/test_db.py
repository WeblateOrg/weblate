# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import TestCase
from unittest.mock import MagicMock, patch

from weblate.trans.models import Component, Project, Unit
from weblate.trans.tests.test_views import FixtureComponentTestCase
from weblate.utils.db import adjust_similarity_threshold, re_escape

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
