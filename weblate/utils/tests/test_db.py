# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import TestCase

from weblate.trans.models import Unit
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.utils.db import re_escape, using_postgresql

BASE_SQL = 'SELECT "trans_unit"."id" FROM "trans_unit" WHERE '


class DbTest(TestCase):
    def test_re_escape(self) -> None:
        self.assertEqual(re_escape("[a-z]"), "\\[a\\-z\\]")
        self.assertEqual(re_escape("a{1,4}"), "a\\{1,4\\}")


class PostgreSQLOperatorTest(TestCase):
    def setUp(self) -> None:
        if not using_postgresql():
            self.skipTest("PostgreSQL only test.")

    def test_search(self) -> None:
        queryset = Unit.objects.filter(source__search="test").only("id")
        self.assertEqual(
            str(queryset.query),
            BASE_SQL + '"trans_unit"."source" % test = true',
        )
        queryset = Unit.objects.filter(source__search="'''").only("id")
        self.assertEqual(
            str(queryset.query),
            BASE_SQL + """"trans_unit"."source" || '' LIKE %'''%""",
        )

    def test_substring(self) -> None:
        queryset = Unit.objects.filter(source__substring="test").only("id")
        self.assertEqual(
            str(queryset.query),
            BASE_SQL + '"trans_unit"."source" ILIKE %test%',
        )
        queryset = Unit.objects.filter(source__substring="'''").only("id")
        self.assertEqual(
            str(queryset.query),
            BASE_SQL + """"trans_unit"."source" || '' LIKE %'''%""",
        )


class SearchSQLOperatorTest(FixtureTestCase):
    def test_search(self) -> None:
        # Verifies that even complex query with a fallback is built properly
        # This is essentially what bulk edit does with such search
        from weblate.trans.models import Component, Project, Unit

        obj = Project.objects.all()[0]
        unit_set = Unit.objects.filter(translation__component__project=obj).prefetch()
        matching = unit_set.search("10°", project=obj)
        components = Component.objects.filter(
            id__in=matching.values_list("translation__component_id", flat=True)
        )
        self.assertEqual(len(components), 0)
