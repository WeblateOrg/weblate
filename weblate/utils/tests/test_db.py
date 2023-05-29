# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import SkipTest, TestCase

from weblate.trans.models import Unit
from weblate.utils.db import re_escape, using_postgresql

BASE_SQL = 'SELECT "trans_unit"."id" FROM "trans_unit" WHERE '


class DbTest(TestCase):
    def test_re_escape(self):
        self.assertEqual(re_escape("[a-z]"), "\\[a\\-z\\]")
        self.assertEqual(re_escape("a{1,4}"), "a\\{1,4\\}")


class PostgreSQLOperatorTesT(TestCase):
    def setUp(self):
        if not using_postgresql():
            raise SkipTest("PostgreSQL only test.")

    def test_search(self):
        queryset = Unit.objects.filter(source__search="test").only("id")
        self.assertEqual(
            str(queryset.query),
            BASE_SQL + '"trans_unit"."source" % test = true',
        )
        queryset = Unit.objects.filter(source__search="'''").only("id")
        self.assertEqual(
            str(queryset.query),
            BASE_SQL + """"trans_unit"."source"::text || '' LIKE %'''%""",
        )

    def test_substring(self):
        queryset = Unit.objects.filter(source__substring="test").only("id")
        self.assertEqual(
            str(queryset.query),
            BASE_SQL + '"trans_unit"."source" ILIKE %test%',
        )
        queryset = Unit.objects.filter(source__substring="'''").only("id")
        self.assertEqual(
            str(queryset.query),
            BASE_SQL + """"trans_unit"."source"::text || '' LIKE %'''%""",
        )
