# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from __future__ import unicode_literals

from datetime import datetime
from unittest import SkipTest

import six
from django.db.models import Q
from django.test import SimpleTestCase, TestCase
from pytz import utc

from weblate.trans.models import Change, Unit
from weblate.utils.search import Comparer, parse_query
from weblate.utils.state import STATE_TRANSLATED


class ComparerTest(SimpleTestCase):
    def test_different(self):
        self.assertLessEqual(Comparer().similarity("a", "b"), 50)

    def test_same(self):
        self.assertEqual(Comparer().similarity("a", "a"), 100)

    def test_unicode(self):
        # Test fallback to Python implementation in jellyfish
        # for unicode strings
        self.assertEqual(Comparer().similarity("NICHOLASŸ", "NICHOLAS"), 88)

    def test_long(self):
        # This is expected to raise MemoryError inside jellyfish
        self.assertLessEqual(Comparer().similarity("a" * 200000, "b" * 200000), 50)


class QueryParserTest(TestCase):
    def setUp(self):
        if six.PY2:
            raise SkipTest("Test not working on Python 2")

    def assert_query(self, string, expected):
        result = parse_query(string)
        self.assertEqual(result, expected)
        self.assertFalse(Unit.objects.filter(result).exists())

    def test_simple(self):
        self.assert_query(
            "hello world",
            (
                Q(source__icontains="hello")
                | Q(target__icontains="hello")
                | Q(context__icontains="hello")
            )
            & (
                Q(source__icontains="world")
                | Q(target__icontains="world")
                | Q(context__icontains="world")
            ),
        )

    def test_quote(self):
        expected = (
            Q(source__icontains="hello world")
            | Q(target__icontains="hello world")
            | Q(context__icontains="hello world")
        )
        self.assert_query('"hello world"', expected)
        self.assert_query("'hello world'", expected)

    def test_field(self):
        self.assert_query(
            "source:hello target:world",
            Q(source__icontains="hello") & Q(target__icontains="world"),
        )
        self.assert_query("location:hello.c", Q(location__icontains="hello.c"))

    def test_regex(self):
        self.assert_query('source:r"^hello"', Q(source__regex="^hello"))
        with self.assertRaises(ValueError):
            self.assert_query('source:r"^(hello"', Q(source__regex="^(hello"))

    def test_logic(self):
        self.assert_query(
            "source:hello AND NOT target:world",
            Q(source__icontains="hello") & ~Q(target__icontains="world"),
        )
        self.assert_query(
            "source:hello OR target:world",
            Q(source__icontains="hello") | Q(target__icontains="world"),
        )

    def test_empty(self):
        self.assert_query("", Q())

    def test_invalid(self):
        self.assert_query(
            "changed:inval AND target:world", Q(target__icontains="world")
        )

    def test_dates(self):
        action_change = Q(change__action__in=Change.ACTIONS_CONTENT)
        self.assert_query(
            "changed:2018",
            Q(change__timestamp__gte=datetime(2018, 1, 1, 0, 0, tzinfo=utc))
            & Q(
                change__timestamp__lte=datetime(
                    2018, 12, 31, 23, 59, 59, 999999, tzinfo=utc
                )
            )
            & action_change,
        )
        self.assert_query(
            "changed:>20190301",
            Q(change__timestamp__gte=datetime(2019, 3, 1, 0, 0, tzinfo=utc))
            & action_change,
        )
        self.assert_query(
            "changed:>2019-03-01",
            Q(change__timestamp__gte=datetime(2019, 3, 1, 0, 0, tzinfo=utc))
            & action_change,
        )
        self.assert_query(
            "changed:2019-03-01",
            Q(change__timestamp__gte=datetime(2019, 3, 1, 0, 0, tzinfo=utc))
            & Q(
                change__timestamp__lte=datetime(
                    2019, 3, 1, 23, 59, 59, 999999, tzinfo=utc
                )
            )
            & action_change,
        )
        self.assert_query(
            "changed:[2019-03-01 to 2019-04-01]",
            Q(change__timestamp__gte=datetime(2019, 3, 1, 0, 0, tzinfo=utc))
            & Q(
                change__timestamp__lte=datetime(
                    2019, 4, 1, 23, 59, 59, 999999, tzinfo=utc
                )
            )
            & action_change,
        )

    def test_bool(self):
        self.assert_query("pending:true", Q(pending=True))

    def test_state(self):
        self.assert_query("state:>=20", Q(state__gte=20))
        self.assert_query("state:>=translated", Q(state__gte=STATE_TRANSLATED))
        self.assert_query("state:translated", Q(state=STATE_TRANSLATED))
        # This should probably raise an error
        self.assert_query("state:invalid", Q())

    def test_parenthesis(self):
        self.assert_query(
            "state:translated AND (source:hello OR source:bar)",
            Q(state=STATE_TRANSLATED)
            & (Q(source__icontains="hello") | Q(source__icontains="bar")),
        )

    def test_language(self):
        self.assert_query("language:cs", Q(translation__language__code="cs"))

    def test_html(self):
        self.assert_query(
            "<b>bold</b>",
            Q(source__icontains="<b>bold</b>")
            | Q(target__icontains="<b>bold</b>")
            | Q(context__icontains="<b>bold</b>"),
        )
