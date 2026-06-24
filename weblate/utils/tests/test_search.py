# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING, ClassVar, Literal

from django.db.models import Count, F, Q
from django.test import TestCase
from django.utils.timezone import get_current_timezone

from weblate.auth.models import User
from weblate.screenshots.models import Screenshot
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Change, Project, Unit
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.util import PLURAL_SEPARATOR
from weblate.utils.search import SearchQueryError, parse_query
from weblate.utils.state import (
    FUZZY_STATES,
    STATE_APPROVED,
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_NEEDS_CHECKING,
    STATE_NEEDS_REWRITING,
    STATE_READONLY,
    STATE_TRANSLATED,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from django.db.models import Expression


class SearchTestCase(TestCase):
    object_class: ClassVar[type[Unit | User | Screenshot]] = Unit
    parser: ClassVar[Literal["unit", "user", "superuser", "screenshot"]] = "unit"

    def assert_query(
        self,
        string: str,
        expected: Q | tuple[Q, Mapping[str, Expression]],
        *,
        expected_annotations: Mapping[str, Expression] | None = None,
        exists: bool = False,
        **context,
    ) -> None:
        filters, annotations = parse_query(string, parser=self.parser, **context)
        if isinstance(expected, tuple):
            expected, expected_annotations = expected
        elif expected_annotations is None:
            expected_annotations = {}
        self.assertEqual(filters, expected)
        self.assertEqual(annotations, expected_annotations)
        self.assertEqual(
            self.object_class.objects.annotate(**annotations).filter(filters).exists(),
            exists,
        )

    def assert_query_sql(
        self,
        string: str,
        *,
        sql_contains: tuple[str, ...] = (),
        sql_not_contains: tuple[str, ...] = (),
        params_contains: tuple[object, ...] = (),
        exists: bool = False,
        **context,
    ) -> tuple[str, tuple[object, ...]]:
        filters, annotations = parse_query(string, parser=self.parser, **context)
        self.assertEqual(annotations, {})
        query = self.object_class.objects.annotate(**annotations).filter(filters)
        sql, params = query.query.sql_with_params()
        for fragment in sql_contains:
            self.assertIn(fragment, sql)
        for fragment in sql_not_contains:
            self.assertNotIn(fragment, sql)
        for param in params_contains:
            self.assertIn(param, params)
        self.assertEqual(query.exists(), exists)
        return sql, params


class UnitQueryParserTest(SearchTestCase):
    def test_simple(self) -> None:
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

    def test_quote(self) -> None:
        expected = (
            Q(source__substring="hello world")
            | Q(target__substring="hello world")
            | Q(context__substring="hello world")
        )
        self.assert_query('"hello world"', expected)
        self.assert_query("'hello world'", expected)

    def test_context(self) -> None:
        expected = Q(context__substring="hello world")
        self.assert_query('key:"hello world"', expected)
        self.assert_query("context:'hello world'", expected)

    def test_text(self) -> None:
        self.assert_query("note:TEXT", Q(note__substring="TEXT"))
        self.assert_query("location:TEXT", Q(location__substring="TEXT"))

    def test_newline(self) -> None:
        self.assert_query("location:TEXT\r\n", Q(location__substring="TEXT"))
        self.assert_query("location:TEXT\r", Q(location__substring="TEXT"))
        self.assert_query("location:TEXT\n", Q(location__substring="TEXT"))
        self.assert_query("location:'TEXT'\r\n", Q(location__substring="TEXT"))

    def test_comment(self) -> None:
        self.assert_query(
            "comment:TEXT",
            Q(comment__comment__substring="TEXT") & Q(comment__resolved=False),
        )
        self.assert_query(
            "resolved_comment:TEXT",
            Q(comment__comment__substring="TEXT") & Q(comment__resolved=True),
        )
        self.assert_query(
            "comment_author:nijel", Q(comment__user__username__iexact="nijel")
        )

    def test_field(self) -> None:
        self.assert_query(
            "source:hello target:world",
            Q(source__substring="hello") & Q(target__substring="world"),
        )
        self.assert_query("location:hello.c", Q(location__substring="hello.c"))

    def test_exact(self) -> None:
        self.assert_query("source:='hello'", Q(source__exact="hello"))
        self.assert_query('source:="hello world"', Q(source__exact="hello world"))
        self.assert_query("source:='hello world'", Q(source__exact="hello world"))
        self.assert_query("source:=hello", Q(source__exact="hello"))

    def test_regex(self) -> None:
        self.assert_query('source:r"^hello"', Q(source__trgm_regex="^hello"))
        # Invalid regex
        with self.assertRaises(SearchQueryError):
            self.assert_query('source:r"^(hello"', Q(source__trgm_regex="^(hello"))
        # Not supported regex on PostgreSQL
        with self.assertRaises(SearchQueryError):
            self.assert_query(
                'source:r"^(?i)hello"', Q(source__trgm_regex="^(?i)hello")
            )
        self.assert_query('source:r"(?i)^hello"', Q(source__trgm_regex="(?i)^hello"))

    def test_logic(self) -> None:
        self.assert_query(
            "source:hello AND NOT target:world",
            Q(source__substring="hello") & ~Q(target__substring="world"),
        )
        self.assert_query(
            "source:hello OR target:world",
            Q(source__substring="hello") | Q(target__substring="world"),
        )

    def test_empty(self) -> None:
        self.assert_query("", Q())

    def test_invalid(self) -> None:
        with self.assertRaises(SearchQueryError):
            self.assert_query(
                "changed:inval AND target:world", Q(target__substring="world")
            )

    def test_year(self) -> None:
        self.assert_query_sql(
            "changed:2018",
            sql_contains=('"timestamp" BETWEEN', '"action" IN', "EXISTS"),
            params_contains=(
                datetime(2018, 1, 1, 0, 0, tzinfo=UTC),
                datetime(2018, 12, 31, 23, 59, 59, 999999, tzinfo=UTC),
            ),
        )

    def test_change_action(self) -> None:
        self.assert_query_sql(
            "change_time:2018 AND change_action:marked-for-edit",
            sql_contains=('"timestamp" BETWEEN', '"action" =', "EXISTS"),
            params_contains=(
                datetime(2018, 1, 1, 0, 0, tzinfo=UTC),
                datetime(2018, 12, 31, 23, 59, 59, 999999, tzinfo=UTC),
                ActionEvents.MARKED_EDIT,
            ),
        )
        sql, _params = self.assert_query_sql(
            "change_time:2018 AND change_action:'Marked for edit'",
            sql_contains=('"timestamp" BETWEEN', '"action" =', "EXISTS"),
            params_contains=(
                datetime(2018, 1, 1, 0, 0, tzinfo=UTC),
                datetime(2018, 12, 31, 23, 59, 59, 999999, tzinfo=UTC),
                ActionEvents.MARKED_EDIT,
            ),
        )
        self.assertEqual(sql.count("EXISTS"), 1)
        with self.assertRaises(SearchQueryError):
            self.assert_query("NOT change_action:new-string", Q())

    def test_dates(self) -> None:
        self.assert_query_sql(
            "changed:>20190301",
            sql_contains=('"timestamp" >=', '"action" IN', "EXISTS"),
            params_contains=(datetime(2019, 3, 1, 0, 0, tzinfo=UTC),),
        )
        self.assert_query_sql(
            "changed:>2019-03-01",
            sql_contains=('"timestamp" >=', '"action" IN', "EXISTS"),
            params_contains=(datetime(2019, 3, 1, 0, 0, tzinfo=UTC),),
        )
        self.assert_query_sql(
            "changed:2019-03-01",
            sql_contains=('"timestamp" BETWEEN', '"action" IN', "EXISTS"),
            params_contains=(
                datetime(2019, 3, 1, 0, 0, tzinfo=UTC),
                datetime(2019, 3, 1, 23, 59, 59, 999999, tzinfo=UTC),
            ),
        )
        self.assert_query_sql(
            "changed:>'March 1, 2019'",
            sql_contains=('"timestamp" >=', '"action" IN', "EXISTS"),
            params_contains=(datetime(2019, 3, 1, 0, 0, tzinfo=UTC),),
        )
        with self.assertRaises(SearchQueryError):
            self.assert_query("changed:>'Not a date'", Q())
        with self.assertRaises(SearchQueryError):
            self.assert_query("changed:>'Invalid 1, 2019'", Q())

    def test_date_range(self) -> None:
        self.assert_query_sql(
            "changed:[2019-03-01 to 2019-04-01]",
            sql_contains=('"timestamp" BETWEEN', '"action" IN', "EXISTS"),
            params_contains=(
                datetime(2019, 3, 1, 0, 0, tzinfo=UTC),
                datetime(2019, 4, 1, 23, 59, 59, 999999, tzinfo=UTC),
            ),
        )

    def test_date_added(self) -> None:
        self.assert_query(
            "added:>2019-03-01",
            Q(timestamp__gte=datetime(2019, 3, 1, 0, 0, tzinfo=UTC)),
        )

    def test_source_changed(self) -> None:
        self.assert_query(
            "source_changed:>20190301",
            Q(source_unit__last_updated__gte=datetime(2019, 3, 1, 0, 0, tzinfo=UTC)),
        )

    def test_last_updated(self) -> None:
        self.assert_query(
            "last_changed:>20190301",
            Q(last_updated__gte=datetime(2019, 3, 1, 0, 0, tzinfo=UTC)),
        )

    def test_bool(self) -> None:
        self.assert_query("pending:true", Q(pending_changes__isnull=False))

    def test_nonexisting(self) -> None:
        with self.assertRaises(SearchQueryError):
            self.assert_query("nonexisting:true", Q())

    def test_state(self) -> None:
        self.assert_query("state:>=empty", Q(state__gte=STATE_EMPTY))
        self.assert_query("state:>=translated", Q(state__gte=STATE_TRANSLATED))
        self.assert_query("state:<translated", Q(state__lt=STATE_TRANSLATED))
        self.assert_query("state:translated", Q(state=STATE_TRANSLATED))
        self.assert_query("state:needs-editing", Q(state=STATE_FUZZY))

    def test_source_state(self) -> None:
        self.assert_query(
            "source_state:>=empty", Q(source_unit__state__gte=STATE_EMPTY)
        )
        self.assert_query(
            "source_state:>=translated", Q(source_unit__state__gte=STATE_TRANSLATED)
        )
        self.assert_query(
            "source_state:<translated", Q(source_unit__state__lt=STATE_TRANSLATED)
        )
        self.assert_query(
            "source_state:translated", Q(source_unit__state=STATE_TRANSLATED)
        )
        self.assert_query(
            "source_state:needs-editing", Q(source_unit__state=STATE_FUZZY)
        )

    def test_position(self) -> None:
        self.assert_query("position:>=1", Q(position__gte=1))
        self.assert_query("position:<10", Q(position__lt=10))
        self.assert_query("position:[1 to 10]", Q(position__range=(1, 10)))

    def test_invalid_state(self) -> None:
        with self.assertRaises(SearchQueryError):
            self.assert_query("state:invalid", Q())

    def test_parenthesis(self) -> None:
        self.assert_query(
            "state:translated AND ( source:hello OR source:bar )",
            Q(state=STATE_TRANSLATED)
            & (Q(source__substring="hello") | Q(source__substring="bar")),
        )
        self.assert_query(
            "state:translated AND (source:hello OR source:bar)",
            Q(state=STATE_TRANSLATED)
            & (Q(source__substring="hello") | Q(source__substring="bar")),
        )

    def test_priorities(self) -> None:
        self.assertEqual(
            parse_query("source:a AND target:b OR context:c"),
            parse_query("(source:a AND target:b) OR context:c"),
        )
        self.assertEqual(
            parse_query("context:c OR source:a AND target:b"),
            parse_query("context:c OR (source:a AND target:b)"),
        )

    def test_implicit_mixed(self) -> None:
        self.assertEqual(
            parse_query("context:c source:a AND target:b"),
            parse_query("context:c AND source:a AND target:b"),
        )
        self.assertEqual(
            parse_query("context:c source:a OR target:b"),
            parse_query("context:c AND source:a OR target:b"),
        )
        self.assertEqual(
            parse_query("context:c source:a target:b"),
            parse_query("context:c AND source:a AND target:b"),
        )
        self.assertEqual(
            parse_query("context:c OR source:a target:b"),
            parse_query("context:c OR source:a AND target:b"),
        )
        self.assertEqual(
            parse_query("c is:translated"),
            parse_query("(source:c OR target:c OR context:c) AND is:translated"),
        )
        self.assertEqual(
            parse_query("c is:translated OR has:dismissed-check"),
            parse_query(
                "((source:c OR target:c OR context:c) AND is:translated) OR has:dismissed-check"
            ),
        )

    def test_language(self) -> None:
        self.assert_query("language:cs", Q(translation__language__code__iexact="cs"))
        self.assert_query(
            'language:r".*"', Q(translation__language__code__trgm_regex=".*")
        )

    def test_component(self) -> None:
        self.assert_query(
            "component:hello",
            Q(translation__component__slug__icontains="hello")
            | Q(translation__component__name__icontains="hello"),
        )

    def test_component_exact(self) -> None:
        self.assert_query(
            "component:=hello",
            Q(translation__component__slug__iexact="hello")
            | Q(translation__component__name__iexact="hello"),
        )

    def test_path(self) -> None:
        # Non-existing project still searches, but matches nothing
        self.assert_query("path:hello", Q(translation=None))

        project = Project.objects.create(slug="testslug", name="Test Name")
        self.assert_query("path:testslug", Q(translation__component__project=project))

    def test_project(self) -> None:
        self.assert_query(
            "project:hello", Q(translation__component__project__slug__iexact="hello")
        )

    def test_html(self) -> None:
        self.assert_query(
            "<b>bold</b>",
            Q(source__substring="<b>bold</b>")
            | Q(target__substring="<b>bold</b>")
            | Q(context__substring="<b>bold</b>"),
        )

    def test_has(self) -> None:
        self.assert_query("has:plural", Q(source__trgm_search=PLURAL_SEPARATOR))
        self.assert_query("has:suggestion", Q(suggestion__isnull=False))
        self.assert_query("has:check", Q(check__dismissed=False))
        self.assert_query("has:comment", Q(comment__resolved=False))
        self.assert_query("has:note", ~Q(note=""))
        self.assert_query("has:location", ~Q(location=""))
        self.assert_query("has:resolved-comment", Q(comment__resolved=True))
        self.assert_query("has:dismissed-check", Q(check__dismissed=True))
        self.assert_query("has:translation", Q(state__gte=STATE_TRANSLATED))
        self.assert_query(
            "has:variant",
            Q(defined_variants__isnull=False)
            | (
                ~Q(variant__variant_regex="")
                & Q(context__regex=F("variant__variant_regex"))
            ),
        )
        self.assert_query("has:label", Q(source_unit__labels__isnull=False))
        self.assert_query("has:context", ~Q(context=""))
        self.assert_query(
            "has:screenshot",
            Q(screenshots__isnull=False) | Q(source_unit__screenshots__isnull=False),
        )
        self.assert_query("has:flags", ~Q(source_unit__extra_flags=""))
        self.assert_query("has:explanation", ~Q(source_unit__explanation=""))
        self.assert_query("has:glossary", Q(source__isnull=True))

    def test_is(self) -> None:
        self.assert_query("is:pending", Q(pending_changes__isnull=False))
        self.assert_query("is:translated", Q(state__gte=STATE_TRANSLATED))
        self.assert_query("is:untranslated", Q(state__lt=STATE_TRANSLATED))
        self.assert_query("is:approved", Q(state=STATE_APPROVED))
        self.assert_query("is:read-only", Q(state=STATE_READONLY))
        self.assert_query("is:fuzzy", Q(state__in=FUZZY_STATES))
        self.assert_query("is:needs-editing", Q(state__in=FUZZY_STATES))

    def test_fuzzy_state_aliases(self) -> None:
        self.assert_query("state:needs-editing", Q(state=STATE_FUZZY))
        self.assert_query("state:needs-rewriting", Q(state=STATE_NEEDS_REWRITING))
        self.assert_query("state:needs-checking", Q(state=STATE_NEEDS_CHECKING))

    def test_changed_by(self) -> None:
        self.assert_query_sql(
            "changed_by:nijel",
            sql_contains=('"username"', '"action" IN', "EXISTS"),
            params_contains=("nijel",),
        )
        self.assert_query_sql(
            "changed_by:none",
            sql_contains=('"username"', '"action" IN', "EXISTS"),
            params_contains=("none",),
        )

        sql, _params = self.assert_query_sql(
            'changed_by:""',
            sql_contains=('"action" IN', '"author_id" IS NULL', "EXISTS"),
            sql_not_contains=('"weblate_auth_user"',),
        )
        self.assertEqual(sql.count("EXISTS"), 1)

        sql, _params = self.assert_query_sql(
            'NOT changed_by:""',
            sql_contains=(
                "NOT (EXISTS",
                '"action" IN',
                '"author_id" IS NULL',
                "EXISTS",
            ),
        )
        self.assertEqual(sql.count("EXISTS"), 1)

        sql, _params = self.assert_query_sql(
            'changed_by:"" AND changed:2026',
            sql_contains=(
                '"timestamp" BETWEEN',
                '"action" IN',
                '"author_id" IS NULL',
                "EXISTS",
            ),
            params_contains=(
                datetime(2026, 1, 1, 0, 0, tzinfo=UTC),
                datetime(2026, 12, 31, 23, 59, 59, 999999, tzinfo=UTC),
            ),
        )
        self.assertEqual(sql.count("EXISTS"), 1)

        sql, _params = self.assert_query_sql(
            'changed_by:"" OR change_action:marked-for-edit',
            sql_contains=('"author_id" IS NULL', '"action" =', "EXISTS"),
            params_contains=(ActionEvents.MARKED_EDIT,),
        )
        self.assertEqual(sql.count("EXISTS"), 2)

        start_2026 = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        end_2026 = datetime(2026, 12, 31, 23, 59, 59, 999999, tzinfo=UTC)
        sql, params = self.assert_query_sql(
            '(changed_by:"" OR changed_by:nijel) AND changed:2026',
            sql_contains=(
                '"timestamp" BETWEEN',
                '"action" IN',
                '"author_id" IS NULL',
                '"username"',
                "EXISTS",
            ),
            params_contains=("nijel", start_2026, end_2026),
        )
        self.assertEqual(sql.count("EXISTS"), 2)
        self.assertEqual(params.count(start_2026), 2)
        self.assertEqual(params.count(end_2026), 2)

    def test_changed_query_complexity_limit(self) -> None:
        query = " AND ".join("(changed_by:nijel OR changed_by:none)" for _ in range(13))
        with self.assertRaises(SearchQueryError):
            parse_query(query)

    def test_explanation(self) -> None:
        self.assert_query(
            "explanation:text", Q(source_unit__explanation__substring="text")
        )

    def test_suggestions(self) -> None:
        self.assert_query("suggestion:text", Q(suggestion__target__substring="text"))
        self.assert_query(
            "suggestion_author:nijel", Q(suggestion__user__username__iexact="nijel")
        )

    def test_priority(self) -> None:
        self.assert_query("priority:10", Q(priority=10))
        self.assert_query("priority:>=10", Q(priority__gte=10))

    def test_id(self) -> None:
        self.assert_query("id:100", Q(id=100))
        self.assert_query("id:100,900", Q(id__in={100, 900}))

    def test_text_html(self) -> None:
        self.assert_query("target:<name>", Q(target__substring="<name>"))

    def test_text_long(self) -> None:
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

    def test_lowercase_or(self) -> None:
        self.assert_query(
            "state:<translated or state:empty",
            Q(state__lt=STATE_TRANSLATED) | Q(state=STATE_EMPTY),
        )

    def test_timestamp_format(self) -> None:
        self.assert_query_sql(
            "changed:>=01/20/2020",
            sql_contains=('"timestamp" >=', '"action" IN', "EXISTS"),
            params_contains=(datetime(2020, 1, 20, 0, 0, tzinfo=UTC),),
        )

    def test_timestamp_exact_iso(self) -> None:
        timestamp = datetime.now(tz=timezone(timedelta(hours=3)))
        self.assert_query_sql(
            f"changed:{timestamp.isoformat()}",
            sql_contains=('"timestamp" =', '"action" IN', "EXISTS"),
            params_contains=(timestamp,),
        )
        self.assert_query_sql(
            f"changed:={timestamp.isoformat()}",
            sql_contains=('"timestamp" =', '"action" IN', "EXISTS"),
            params_contains=(timestamp,),
        )

    def test_timestamp_exact_date(self) -> None:
        # The microsecond = 5 is relict from the parser, it should be avoided if possible
        timestamp = datetime(
            2013, 7, 21, 22, 15, 20, tzinfo=timezone(timedelta(hours=5))
        )
        self.assert_query_sql(
            "changed:='21 July 2013 10:15:20 pm +0500'",
            sql_contains=('"timestamp" =', '"action" IN', "EXISTS"),
            params_contains=(timestamp,),
        )

    def test_timestamp_exact_human(self) -> None:
        timestamp = datetime(2013, 7, 21, 22, 15, 20, tzinfo=get_current_timezone())
        self.assert_query_sql(
            "changed:='21 July year 2013 10:15:20 pm'",
            sql_contains=('"timestamp" =', '"action" IN', "EXISTS"),
            params_contains=(timestamp,),
        )

    def test_timestamp_interval(self) -> None:
        self.assert_query_sql(
            "changed:2020-03-27",
            sql_contains=('"timestamp" BETWEEN', '"action" IN', "EXISTS"),
            params_contains=(
                datetime(2020, 3, 27, 0, 0, tzinfo=UTC),
                datetime(2020, 3, 27, 23, 59, 59, 999999, tzinfo=UTC),
            ),
        )

    def test_timestamp_interval_human(self) -> None:
        today = datetime.now(tz=get_current_timezone())
        timestamp = today - timedelta(days=20)
        self.assert_query_sql(
            "changed:'20 days ago'",
            sql_contains=('"timestamp" BETWEEN', '"action" IN', "EXISTS"),
            params_contains=(
                timestamp.replace(hour=0, minute=0, second=0, microsecond=0),
                timestamp.replace(hour=23, minute=59, second=59, microsecond=999999),
            ),
        )
        self.assert_query_sql(
            "changed:[20_days_ago to today]",
            sql_contains=('"timestamp" BETWEEN', '"action" IN', "EXISTS"),
            params_contains=(
                timestamp.replace(hour=0, minute=0, second=0, microsecond=0),
                today.replace(hour=23, minute=59, second=59, microsecond=999999),
            ),
        )

    def test_non_quoted_strings(self) -> None:
        self.assert_query(
            "%(count)s word",
            parse_query("'%(count)s' 'word'"),
        )
        self.assert_query("{actor}", parse_query("'{actor}'"))

    def test_specialchars(self) -> None:
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

    def test_url(self) -> None:
        self.assert_query("https://weblate.org/", parse_query("'https://weblate.org/'"))

    def test_quotes(self) -> None:
        self.assert_query("'", parse_query('''"'"'''))
        self.assert_query('"', parse_query("""'"'"""))
        self.assert_query("source:'", parse_query('''source:"'"'''))
        self.assert_query('source:"', parse_query("""source:'"'"""))

    def test_labels_count(self) -> None:
        annotation = {"labels_count": Count("source_unit__labels")}
        self.assert_query(
            "labels_count:2", Q(labels_count=2), expected_annotations=annotation
        )
        self.assert_query(
            "labels_count:=2", Q(labels_count__exact=2), expected_annotations=annotation
        )
        self.assert_query(
            "labels_count:>3", Q(labels_count__gt=3), expected_annotations=annotation
        )
        self.assert_query(
            "labels_count:<=1", Q(labels_count__lte=1), expected_annotations=annotation
        )

        with self.assertRaises(SearchQueryError):
            self.assert_query("labels_count:invalid", Q())


class ScreenshotQueryParserTest(SearchTestCase):
    object_class: ClassVar[type[Unit | User | Screenshot]] = Screenshot
    parser: ClassVar[Literal["unit", "user", "superuser", "screenshot"]] = "screenshot"

    def test_simple(self) -> None:
        self.assert_query(
            "login",
            Q(name__icontains="login")
            | Q(repository_filename__icontains="login")
            | Q(translation__language__code__icontains="login")
            | Q(translation__language__name__icontains="login")
            | Q(units__source__icontains="login")
            | Q(units__context__icontains="login")
            | Q(units__location__icontains="login"),
        )

    def test_fields(self) -> None:
        self.assert_query("id:100", Q(id=100))
        self.assert_query("name:login", Q(name__icontains="login"))
        self.assert_query("name:=login", Q(name__exact="login"))
        self.assert_query("path:fastlane", Q(repository_filename__icontains="fastlane"))
        self.assert_query(
            "repository:fastlane", Q(repository_filename__icontains="fastlane")
        )
        self.assert_query("string:Save", Q(units__source__icontains="Save"))
        self.assert_query("context:menu", Q(units__context__icontains="menu"))
        self.assert_query("location:main", Q(units__location__icontains="main"))

    def test_language(self) -> None:
        self.assert_query(
            "language:cs",
            Q(translation__language__code__icontains="cs")
            | Q(translation__language__name__icontains="cs"),
        )
        self.assert_query(
            "language:=Czech",
            Q(translation__language__code__iexact="Czech")
            | Q(translation__language__name__iexact="Czech"),
        )
        self.assert_query(
            'language:r".*"',
            Q(translation__language__code__trgm_regex=".*")
            | Q(translation__language__name__trgm_regex=".*"),
        )
        with self.assertRaises(SearchQueryError):
            self.assert_query('language:r"["', Q())

    def test_has(self) -> None:
        self.assert_query("has:string", Q(units__isnull=False))
        self.assert_query("NOT has:string", ~Q(units__isnull=False))
        self.assert_query("has:repository", ~Q(repository_filename=""))
        self.assert_query("has:path", ~Q(repository_filename=""))

    def test_strings_count(self) -> None:
        annotation = {"strings": Count("units", distinct=True)}
        self.assert_query("strings:2", Q(strings=2), expected_annotations=annotation)
        self.assert_query(
            "strings:>2", Q(strings__gt=2), expected_annotations=annotation
        )

    def test_timestamp(self) -> None:
        self.assert_query(
            "timestamp:2018",
            Q(
                timestamp__range=(
                    datetime(2018, 1, 1, 0, 0, tzinfo=UTC),
                    datetime(2018, 12, 31, 23, 59, 59, 999999, tzinfo=UTC),
                )
            ),
        )

    def test_invalid(self) -> None:
        with self.assertRaises(SearchQueryError):
            self.assert_query("state:translated", Q())
        with self.assertRaises(SearchQueryError):
            self.assert_query("has:translation", Q())
        with self.assertRaises(SearchQueryError):
            self.assert_query("strings:invalid", Q())


class UserQueryParserTest(SearchTestCase):
    object_class: ClassVar[type[Unit | User | Screenshot]] = User
    parser: ClassVar[Literal["unit", "user", "superuser", "screenshot"]] = "user"

    def test_simple(self) -> None:
        self.assert_query(
            "hello",
            Q(username__icontains="hello") | Q(full_name__icontains="hello"),
        )

    def test_fields(self) -> None:
        self.assert_query(
            "username:hello",
            Q(username__icontains="hello"),
        )
        self.assert_query(
            "full_name:hello",
            Q(full_name__icontains="hello"),
        )

    def test_is(self) -> None:
        with self.assertRaises(SearchQueryError):
            self.assert_query("is:bot", Q(is_bot=True))
        with self.assertRaises(SearchQueryError):
            self.assert_query("is:superuser", Q(is_superuser=True))
        with self.assertRaises(SearchQueryError):
            self.assert_query("is:active", Q(is_active=True))

    def test_language(self) -> None:
        self.assert_query("language:cs", (Q(profile__languages__code__iexact="cs")))

    def test_email(self) -> None:
        with self.assertRaises(SearchQueryError):
            self.assert_query(
                "email:hello",
                Q(social_auth__verifiedemail__email__icontains="hello"),
            )

    def test_ip(self) -> None:
        with self.assertRaises(SearchQueryError):
            self.assert_query("ip:192.0.2.1", Q(auditlog__address="192.0.2.1"))

    def test_joined(self) -> None:
        self.assert_query(
            "joined:2018",
            Q(
                date_joined__range=(
                    datetime(2018, 1, 1, 0, 0, tzinfo=UTC),
                    datetime(2018, 12, 31, 23, 59, 59, 999999, tzinfo=UTC),
                )
            ),
        )

    def test_translates(self) -> None:
        self.assert_query(
            "translates:cs",
            Q(change__language__code__iexact="cs"),
        )
        self.assert_query(
            "translates:cs change_time:>'90 days ago'",
            Q(change__language__code__iexact="cs")
            & Q(
                change__timestamp__gte=datetime.now(tz=UTC).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                - timedelta(days=90)
            ),
        )

    def test_contributes(self) -> None:
        user = User.objects.create(is_superuser=True)
        self.assert_query(
            "contributes:test",
            Q(change__project__slug__iexact="test")
            & Q(change__project__in=user.allowed_projects),
            user=user,
        )
        self.assert_query(
            "contributes:test/test",
            Q(change__component_id__in=[])
            & Q(change__project__in=user.allowed_projects),
            user=user,
        )
        self.assert_query(
            "contributes:test change_time:>'90 days ago'",
            Q(change__project__slug__iexact="test")
            & Q(change__project__in=user.allowed_projects)
            & Q(
                change__timestamp__gte=datetime.now(tz=UTC).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                - timedelta(days=90)
            ),
            user=user,
        )


class SuperuserQueryParserTest(UserQueryParserTest):
    object_class: ClassVar[type[Unit | User | Screenshot]] = User
    parser: ClassVar[Literal["unit", "user", "superuser", "screenshot"]] = "superuser"

    def test_simple(self) -> None:
        self.assert_query(
            "hello",
            (
                Q(username__icontains="hello")
                | Q(full_name__icontains="hello")
                | Q(social_auth__verifiedemail__email__iexact="hello")
            ),
        )

    def test_email(self) -> None:
        self.assert_query(
            "email:hello", Q(social_auth__verifiedemail__email__icontains="hello")
        )

    def test_ip(self) -> None:
        self.assert_query("ip:192.0.2.1", Q(auditlog__address="192.0.2.1"))
        self.assert_query("ip:2001:0db8::1", Q(auditlog__address="2001:db8::1"))
        with self.assertRaises(SearchQueryError):
            self.assert_query("ip:not-an-ip", Q(auditlog__address="not-an-ip"))

    def test_plain_ip(self) -> None:
        self.assert_query(
            "192.0.2.1",
            Q(username__icontains="192.0.2.1")
            | Q(full_name__icontains="192.0.2.1")
            | Q(social_auth__verifiedemail__email__iexact="192.0.2.1")
            | Q(auditlog__address="192.0.2.1"),
        )

    def test_is(self) -> None:
        self.assert_query("is:bot", Q(is_bot=True))
        self.assert_query("is:superuser", Q(is_superuser=True))
        self.assert_query("is:active", Q(is_active=True))


class SearchTest(ViewTestCase, SearchTestCase):
    """Search tests on real projects."""

    CREATE_GLOSSARIES: bool = True

    def search_matches_unit(self, query: str, unit: Unit) -> bool:
        filters, annotations = parse_query(query, parser=self.parser)
        return Unit.objects.annotate(**annotations).filter(filters, pk=unit.pk).exists()

    def test_change_search_same_event_semantics(self) -> None:
        unit = self.get_unit()
        Change.objects.filter(unit=unit).delete()
        other_user = User.objects.create(username="other-user")

        authorless_change = Change.objects.create(
            unit=unit, action=ActionEvents.CHANGE, author=None
        )
        Change.objects.filter(pk=authorless_change.pk).update(
            timestamp=datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
        )
        authored_change = Change.objects.create(
            unit=unit, action=ActionEvents.CHANGE, author=other_user
        )
        Change.objects.filter(pk=authored_change.pk).update(
            timestamp=datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        )

        query = 'changed_by:"" AND changed:2026'
        self.assertFalse(self.search_matches_unit(query, unit))
        grouped_query = (
            f'(changed_by:"" OR changed_by:{self.user.username}) AND changed:2026'
        )
        self.assertFalse(self.search_matches_unit(grouped_query, unit))

        authorless_2026_change = Change.objects.create(
            unit=unit, action=ActionEvents.CHANGE, author=None
        )
        Change.objects.filter(pk=authorless_2026_change.pk).update(
            timestamp=datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
        )
        self.assertTrue(self.search_matches_unit(query, unit))
        self.assertTrue(self.search_matches_unit(grouped_query, unit))

    def test_glossary_empty(self) -> None:
        self.assert_query("has:glossary", Q(source__isnull=True), project=self.project)

    def test_glossary_match(self) -> None:
        glossary = self.project.glossaries[0].translation_set.get(language_code="cs")
        glossary.add_unit(None, "", "hello", "ahoj", author=self.user)

        expected = "[[:<:]](hello)[[:>:]]"
        self.assert_query(
            "has:glossary",
            Q(source__iregex=expected),
            exists=True,
            project=self.project,
        )
