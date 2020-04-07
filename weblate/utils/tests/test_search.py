#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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

from datetime import datetime
from unittest import expectedFailure

from django.db.models import Q
from django.test import SimpleTestCase, TestCase
from pytz import utc

from weblate.trans.models import Change, Unit
from weblate.trans.util import PLURAL_SEPARATOR
from weblate.utils.search import Comparer, parse_query
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_READONLY,
    STATE_TRANSLATED,
)


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
    def assert_query(self, string, expected):
        result = parse_query(string)
        self.assertEqual(result, expected)
        self.assertFalse(Unit.objects.filter(result).exists())

    def test_simple(self):
        self.assert_query(
            "hello world",
            (
                Q(source__substring="hello")
                | Q(target__substring="hello")
                | Q(context__substring="hello")
            )
            & (
                Q(source__substring="world")
                | Q(target__substring="world")
                | Q(context__substring="world")
            ),
        )

    def test_quote(self):
        expected = (
            Q(source__substring="hello world")
            | Q(target__substring="hello world")
            | Q(context__substring="hello world")
        )
        self.assert_query('"hello world"', expected)
        self.assert_query("'hello world'", expected)

    def test_field(self):
        self.assert_query(
            "source:hello target:world",
            Q(source__substring="hello") & Q(target__substring="world"),
        )
        self.assert_query("location:hello.c", Q(location__substring="hello.c"))

    def test_exact(self):
        self.assert_query("source:='hello'", Q(source__iexact="hello"))
        self.assert_query('source:="hello world"', Q(source__iexact="hello world"))
        self.assert_query("source:='hello world'", Q(source__iexact="hello world"))
        self.assert_query("source:=hello", Q(source__iexact="hello"))

    def test_regex(self):
        self.assert_query('source:r"^hello"', Q(source__regex="^hello"))
        with self.assertRaises(ValueError):
            self.assert_query('source:r"^(hello"', Q(source__regex="^(hello"))

    def test_logic(self):
        self.assert_query(
            "source:hello AND NOT target:world",
            Q(source__substring="hello") & ~Q(target__substring="world"),
        )
        self.assert_query(
            "source:hello OR target:world",
            Q(source__substring="hello") | Q(target__substring="world"),
        )

    def test_empty(self):
        self.assert_query("", Q())

    def test_invalid(self):
        self.assert_query(
            "changed:inval AND target:world", Q(target__substring="world")
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
        self.assert_query(
            "added:>2019-03-01",
            Q(timestamp__gte=datetime(2019, 3, 1, 0, 0, tzinfo=utc)),
        )

    def test_bool(self):
        self.assert_query("pending:true", Q(pending=True))

    def test_state(self):
        self.assert_query("state:>=empty", Q(state__gte=STATE_EMPTY))
        self.assert_query("state:>=translated", Q(state__gte=STATE_TRANSLATED))
        self.assert_query("state:<translated", Q(state__lt=STATE_TRANSLATED))
        self.assert_query("state:translated", Q(state=STATE_TRANSLATED))
        self.assert_query("state:needs-editing", Q(state=STATE_FUZZY))

    @expectedFailure
    def test_invalid_state(self):
        with self.assertRaises(ValueError):
            self.assert_query("state:invalid", Q())

    def test_parenthesis(self):
        self.assert_query(
            "state:translated AND (source:hello OR source:bar)",
            Q(state=STATE_TRANSLATED)
            & (Q(source__substring="hello") | Q(source__substring="bar")),
        )

    def test_language(self):
        self.assert_query("language:cs", Q(translation__language__code__iexact="cs"))
        self.assert_query('language:r".*"', Q(translation__language__code__regex=".*"))

    def test_html(self):
        self.assert_query(
            "<b>bold</b>",
            Q(source__substring="<b>bold</b>")
            | Q(target__substring="<b>bold</b>")
            | Q(context__substring="<b>bold</b>"),
        )

    def test_has(self):
        self.assert_query("has:plural", Q(source__contains=PLURAL_SEPARATOR))
        self.assert_query("has:suggestion", Q(has_suggestion=True))
        self.assert_query("has:check", Q(has_failing_check=True))
        self.assert_query("has:comment", Q(has_comment=True))
        self.assert_query("has:ignored-check", Q(check__ignore=True))
        self.assert_query("has:translation", Q(state__gte=STATE_TRANSLATED))
        self.assert_query("has:shaping", Q(shaping__isnull=False))
        self.assert_query("has:label", Q(labels__isnull=False))
        self.assert_query("has:context", ~Q(context=""))

    def test_is(self):
        self.assert_query("is:pending", Q(pending=True))
        self.assert_query("is:translated", Q(state__gte=STATE_TRANSLATED))
        self.assert_query("is:untranslated", Q(state__lt=STATE_TRANSLATED))
        self.assert_query("is:approved", Q(state=STATE_APPROVED))
        self.assert_query("is:read-only", Q(state=STATE_READONLY))

    def test_suggestions(self):
        self.assert_query(
            "suggestion_author:nijel", Q(suggestion__user__username__iexact="nijel")
        )

    def test_checks(self):
        self.assert_query(
            "check:ellipsis",
            Q(check__check__iexact="ellipsis") & Q(check__ignore=False),
        )
        self.assert_query(
            "ignored_check:ellipsis",
            Q(check__check__iexact="ellipsis") & Q(check__ignore=True),
        )

    def test_labels(self):
        self.assert_query("label:'test label'", Q(labels__name__iexact="test label"))

    def test_priority(self):
        self.assert_query("priority:10", Q(priority=10))
        self.assert_query("priority:>=10", Q(priority__gte=10))

    @expectedFailure
    def test_text_html(self):
        self.assert_query("target:<name>", Q(target="<name>"))

    @expectedFailure
    def test_text_long(self):
        self.assert_query(
            "[one to other]",
            (
                Q(source__substring="[one")
                | Q(target__substring="[one")
                | Q(context__substring="[one")
            )
            & (
                Q(source__substring="to")
                | Q(target__substring="to")
                | Q(context__substring="to")
            )
            & (
                Q(source__substring="other]")
                | Q(target__substring="other]")
                | Q(context__substring="other]")
            ),
        )

    @expectedFailure
    def test_lowercase_or(self):
        self.assert_query(
            "state:<translated or state:empty",
            Q(state__lt=STATE_TRANSLATED) | Q(state=STATE_EMPTY),
        )

    @expectedFailure
    def test_timestamp_format(self):
        self.assert_query(
            "changed:>=01/20/2020",
            Q(change__timestamp__gte=datetime(2020, 20, 1, 0, 0, tzinfo=utc)),
        )

    @expectedFailure
    def test_non_quoted_strings(self):
        self.assert_query(
            "%(count)s word", parse_query("'%(count)s' 'word'"),
        )

    @expectedFailure
    def test_specialchars(self):
        self.assert_query(
            "to %{_topdir}",
            (
                Q(source__substring="to")
                | Q(target__substring="to")
                | Q(context__substring="to")
            )
            & (
                Q(source__substring="%{_topdir}")
                | Q(target__substring="%{_topdir}")
                | Q(context__substring="%{_topdir}")
            ),
        )
