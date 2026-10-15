# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for changes browsing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from html import escape
from typing import TYPE_CHECKING, cast
from unittest.mock import Mock, patch

from django.core import serializers
from django.db import connection
from django.http import QueryDict
from django.template.loader import render_to_string
from django.test import TestCase
from django.test.utils import CaptureQueriesContext, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from lxml import html

from weblate.auth.models import User, get_anonymous
from weblate.lang.models import Language
from weblate.screenshots.models import Screenshot
from weblate.trans.actions import ActionEvents
from weblate.trans.feeds import ChangeFeedScope, TranslationChangesFeed
from weblate.trans.forms import ChangesDateForm
from weblate.trans.models import Announcement, Change, Project, Translation, Unit
from weblate.trans.models.change import COMPONENT_ORIGINS
from weblate.trans.repository_context import repository_changes
from weblate.trans.templatetags.translations import format_last_changes_content
from weblate.trans.tests.test_views import (
    FixtureTestCase,
    ReusableViewTestCase,
    ViewTestCase,
)
from weblate.trans.tests.utils import get_test_actor
from weblate.trans.views.changes import ChangesView
from weblate.utils.change_origin import change_origin_context
from weblate.utils.state import STATE_EMPTY, STATE_READONLY, STATE_TRANSLATED
from weblate.utils.stats import CategoryLanguage, ProjectLanguage
from weblate.utils.xml import parse_xml

if TYPE_CHECKING:
    from django.test.client import _MonkeyPatchedWSGIResponse

    from weblate.trans.models import Component
    from weblate.utils.change_origin import ChangeOrigin


class ChangeOriginTest(FixtureTestCase):
    def test_repository_changes_preserve_automation_attribution(self) -> None:
        @repository_changes
        def imported_change(component: Component) -> Change:
            return Change(component=component)

        origin: ChangeOrigin = {
            "scope": "automation",
            "automation": {"addon_id": 12, "activity_id": 34},
        }
        with change_origin_context(origin):
            change = imported_change(self.component)
        self.assertEqual(change.details["change_origin"], origin)
        self.assertEqual(change.details["automation_origin"], 34)

    def test_bulk_creation_and_historical_records(self) -> None:
        details = {"reason": "test"}
        with change_origin_context({"scope": "api"}):
            change = Change(project=self.project, details=details, user=self.user)
            Change.objects.bulk_create([change])
        change.refresh_from_db()
        self.assertEqual(change.details["change_origin"], {"scope": "api"})
        self.assertEqual(details, {"reason": "test"})
        with change_origin_context({"scope": "ui"}):
            change.save()
        change.refresh_from_db()
        self.assertEqual(change.details["change_origin"], {"scope": "api"})

        Change.objects.filter(pk=change.pk).update(details=details)
        with change_origin_context({"scope": "api"}):
            historical = Change.objects.only("id", "details").get(pk=change.pk)
            historical.save()
        historical.refresh_from_db()
        self.assertEqual(historical.details, details)

    def test_explicit_origin(self) -> None:
        with change_origin_context({"scope": "api"}):
            change = Change(details={"change_origin": {"scope": "repository"}})
        self.assertEqual(change.details["change_origin"], {"scope": "repository"})
        self.assertEqual(Change().details["change_origin"], {"scope": "system"})

    def test_fixture_history_has_no_origin(self) -> None:
        change = Change.objects.get(component=self.component, action=ActionEvents.MERGE)
        self.assertEqual(change.details, {})
        self.assertEqual(change.get_origin_display(), "")
        self.assertEqual(change.get_origin_description(), "")

    def test_serialized_history_preserves_origin(self) -> None:
        for details in (
            {},
            {"reason": "historical"},
            {"change_origin": {"scope": "api"}},
        ):
            with self.subTest(details=details):
                change = Change.objects.create(project=self.project, user=self.user)
                Change.objects.filter(pk=change.pk).update(details=details)
                change.refresh_from_db()
                serialized = serializers.serialize("json", [change])
                Change.objects.filter(pk=change.pk).delete()

                with change_origin_context({"scope": "ui"}):
                    (restored,) = serializers.deserialize("json", serialized)
                    self.assertEqual(cast("Change", restored.object).details, details)
                    restored.save()

                change.refresh_from_db()
                self.assertEqual(change.details, details)

    def test_component_creation_origins(self) -> None:
        for scope in ("ui", "api"):
            for origin, description in COMPONENT_ORIGINS.items():
                with self.subTest(scope=scope, origin=origin):
                    with change_origin_context({"scope": scope}):
                        self.component.post_create(self.user, origin=origin)
                    change = self.component.change_set.filter(
                        action=ActionEvents.CREATE_COMPONENT, user=self.user
                    ).latest("pk")
                    self.assertEqual(change.details["origin"], origin)
                    self.assertEqual(change.details["change_origin"], {"scope": scope})
                    self.assertEqual(change.get_details_display(), description)
                    for in_email in (False, True):
                        rendered = render_to_string(
                            "snippets/last-changes-content.html",
                            format_last_changes_content(
                                [change], self.user, in_email=in_email
                            ),
                        )
                        self.assertIn(str(description), rendered)
                        self.assertIn(
                            f"Origin: {change.get_origin_display()}",
                            html.fromstring(rendered).text_content(),
                        )

    def test_historical_component_creation_origin(self) -> None:
        change = Change.objects.create(
            user=self.user,
            component=self.component,
            action=ActionEvents.CREATE_COMPONENT,
            details={"origin": "vcs"},
        )
        Change.objects.filter(pk=change.pk).update(details={"origin": "vcs"})
        change.refresh_from_db()
        self.assertEqual(change.get_details_display(), COMPONENT_ORIGINS["vcs"])
        self.assertEqual(change.get_origin_display(), "")

    def test_component_creation_with_non_string_origin(self) -> None:
        change = Change(
            action=ActionEvents.CREATE_COMPONENT,
            details={"origin": {"scope": "system"}},
        )
        self.assertEqual(
            change.get_details_display(), ActionEvents.CREATE_COMPONENT.label
        )

    def test_history_label_visibility(self) -> None:
        from django.contrib.auth.models import AnonymousUser  # ruff: ignore[import-outside-top-level]

        change = Change(
            project=self.project,
            user=self.user,
            details={"ip_address": "127.0.0.1"},
        )
        for viewer in (
            self.user,
            self.anotheruser,
            AnonymousUser(),
            "digest recipient",
        ):
            with self.subTest(viewer=viewer):
                rendered = render_to_string(
                    "snippets/last-changes-content.html",
                    format_last_changes_content([change], viewer),
                )
                self.assertIn(
                    "Origin: System", html.fromstring(rendered).text_content()
                )
                self.assertNotIn("127.0.0.1", rendered)
        self.anotheruser.is_superuser = True
        context = format_last_changes_content([change], self.anotheruser)
        self.assertEqual(context["changes_with_context"][0]["origin"], "System")
        change.details.pop("change_origin")
        context = format_last_changes_content([change], self.user)
        self.assertEqual(context["changes_with_context"][0]["origin"], "")
        rendered = render_to_string("snippets/last-changes-content.html", context)
        self.assertFalse(
            html.fromstring(rendered).xpath('//span[contains(@class, "badge")]')
        )

    def test_origin_and_ip_address_layout(self) -> None:
        from django.contrib.auth.models import AnonymousUser  # ruff: ignore[import-outside-top-level]

        change = Change(
            project=self.project,
            user=self.user,
            details={"change_origin": {"scope": "ui"}, "ip_address": "127.0.0.1"},
        )
        self.anotheruser.is_superuser = True
        for viewer in (self.user, self.anotheruser, AnonymousUser()):
            for in_email in (False, True):
                with self.subTest(viewer=viewer, in_email=in_email):
                    content = render_to_string(
                        "snippets/last-changes-content.html",
                        format_last_changes_content(
                            [change], viewer, in_email=in_email
                        ),
                    )
                    tree = html.fromstring(content)
                    badges = tree.xpath(
                        '//div[contains(@class, "history-author")]/span[contains(@class, "badge")]'
                    )
                    expected = ["Web"]
                    if viewer.is_superuser:
                        expected.append("127.0.0.1")
                    self.assertEqual(
                        ["".join(badge.xpath("text()")).strip() for badge in badges],
                        expected,
                    )
                    self.assertIn("Origin: Web", badges[0].text_content())
                    self.assertEqual(
                        badges[0].get("title"),
                        "Initiated through the web interface.",
                    )
                    if viewer.is_superuser:
                        self.assertIn("IP address: 127.0.0.1", badges[1].text_content())
                        self.assertEqual(
                            badges[1].get("title"),
                            "IP address recorded for this change.",
                        )
                    for badge in badges:
                        if in_email:
                            self.assertIsNone(badge.get("tabindex"))
                            self.assertIsNone(badge.get("data-bs-toggle"))
                            self.assertIn(badge.attrib["title"], badge.text_content())
                        else:
                            self.assertEqual(badge.get("tabindex"), "0")
                            self.assertEqual(badge.get("data-bs-toggle"), "tooltip")
                    breadcrumbs = tree.xpath('//ul[@class="breadcrumb"]')
                    self.assertNotIn("127.0.0.1", breadcrumbs[0].text_content())
                    if not viewer.is_superuser:
                        self.assertNotIn("127.0.0.1", content)

    def test_origin_badge_labels(self) -> None:
        for scope, label, description in (
            ("ui", "Web", "Initiated through the web interface."),
            ("api", "API", "Initiated through the API using an authentication token."),
            (
                "repository",
                "Repository",
                "Imported from translation files in the repository.",
            ),
            (
                "system",
                "System",
                "Created by Weblate without a recorded initiating request.",
            ),
            ("automation", "Automation", "Created by automation #12 (run #34)."),
            ("future", "", ""),
        ):
            for in_email in (False, True):
                with self.subTest(scope=scope, in_email=in_email):
                    change = Change(
                        project=self.project,
                        user=self.user,
                        details={
                            "change_origin": {
                                "scope": scope,
                                "automation": {"addon_id": 12, "activity_id": 34},
                            },
                            "ip_address": "2001:db8:1234:5678:90ab:cdef:1234:5678",
                        },
                    )
                    viewer = self.anotheruser
                    viewer.is_superuser = True
                    content = render_to_string(
                        "snippets/last-changes-content.html",
                        format_last_changes_content(
                            [change], viewer, in_email=in_email
                        ),
                    )
                    badges = html.fromstring(content).xpath(
                        '//div[contains(@class, "history-author")]/span[contains(@class, "badge")]'
                    )
                    expected = [label] if label else []
                    expected.append(change.details["ip_address"])
                    self.assertEqual(
                        ["".join(badge.xpath("text()")).strip() for badge in badges],
                        expected,
                    )
                    if label:
                        self.assertEqual(badges[0].get("title"), description)
                    self.assertEqual(change.get_origin_description(), description)

    def test_invalid_origin_and_automation_descriptions(self) -> None:
        invalid_origins: tuple[object, ...] = (
            None,
            [],
            {"scope": None},
            {"scope": "unknown"},
        )
        for origin in invalid_origins:
            with self.subTest(origin=origin):
                change = Change(details={"change_origin": origin})
                self.assertEqual(change.get_origin_display(), "")
                self.assertEqual(change.get_origin_description(), "")
        for automation in (
            None,
            {},
            {"addon_id": "12", "activity_id": 34},
            {"addon_id": 12},
        ):
            with self.subTest(automation=automation):
                change = Change(
                    details={
                        "change_origin": {
                            "scope": "automation",
                            "automation": automation,
                        }
                    }
                )
                self.assertEqual(change.get_origin_display(), "Automation")
                self.assertEqual(
                    change.get_origin_description(), "Created by an automation."
                )


class ChangeUserTest(TestCase):
    def test_fixture_actor_is_reused_within_test(self) -> None:
        actor = get_test_actor(self)
        with self.assertNumQueries(0):
            self.assertIs(get_test_actor(self), actor)

    @classmethod
    def setUpTestData(cls) -> None:
        cls.user = User.objects.create_user("history-user", "history@example.com")

    def test_missing_user_is_reported_on_insert(self) -> None:
        for values in ({}, {"user": None}):
            with (
                self.subTest(values=values),
                patch("weblate.trans.models.change.report_message") as report,
            ):
                change = Change(**values)
                report.assert_not_called()
                with self.assertWarnsRegex(
                    RuntimeWarning, "History entry created without a user"
                ):
                    change.save()
                report.assert_called_once_with(
                    "History entry created without a user",
                    level="error",
                    project=None,
                    extra_log=f"Change action: {change.action}",
                )
                change.refresh_from_db()
                self.assertIsNone(change.user_id)
                change.save()
                report.assert_called_once()

    def test_missing_user_is_reported_by_manager(self) -> None:
        with (
            patch("weblate.trans.models.change.report_message") as report,
            self.assertWarnsRegex(
                RuntimeWarning, "History entry created without a user"
            ),
        ):
            change = Change.objects.create()
        self.assertIsNone(change.user_id)
        report.assert_called_once()

    def test_bulk_insert_reports_only_missing_users(self) -> None:
        changes = [
            Change(),
            Change(user=None),
            Change(user=self.user),
            Change(user_id=self.user.pk),
            Change(user=get_anonymous()),
        ]
        with (
            patch("weblate.trans.models.change.report_message") as report,
            self.assertWarnsRegex(
                RuntimeWarning, "History entry created without a user"
            ) as warning,
        ):
            Change.objects.bulk_create(changes)
        self.assertEqual(len(warning.warnings), 2)
        self.assertEqual(report.call_count, 2)
        self.assertEqual(
            Change.objects.filter(pk__in=[change.pk for change in changes]).count(),
            len(changes),
        )
        self.assertIsNone(Change.objects.get(pk=changes[-1].pk).user_id)

    def test_explicit_users_are_not_reported(self) -> None:
        for values in (
            {"user": self.user},
            {"user_id": self.user.pk},
            {"user": get_anonymous()},
        ):
            with (
                self.subTest(values=values),
                patch("weblate.trans.models.change.report_message") as report,
            ):
                change = Change.objects.create(**values)
                change.refresh_from_db()
                change.save()
                report.assert_not_called()

    def test_anonymous_user_keeps_ip_address(self) -> None:
        with (
            patch("weblate.trans.models.change.report_message") as report,
            patch.object(Change, "get_ip_address", return_value="192.0.2.1"),
        ):
            change = Change.objects.create(user=get_anonymous())
        change.refresh_from_db()
        self.assertIsNone(change.user_id)
        self.assertEqual(change.details["ip_address"], "192.0.2.1")
        report.assert_not_called()

    @override_settings(SENTRY_DSN="https://public@example.com/1")
    def test_missing_user_reaches_sentry_as_error_message(self) -> None:
        sentry = Mock()
        with (
            patch("weblate.utils.errors.get_sentry_sdk", return_value=sentry),
            self.assertWarnsRegex(
                RuntimeWarning, "History entry created without a user"
            ),
        ):
            change = Change.objects.create()
        sentry.capture_message.assert_called_once_with(
            "History entry created without a user"
        )
        sentry.set_level.assert_called_once_with("error")
        sentry.capture_exception.assert_not_called()
        self.assertTrue(Change.objects.filter(pk=change.pk, user=None).exists())

    def test_missing_user_warning_is_an_error(self) -> None:
        change = Change()
        with (
            patch("weblate.trans.models.change.report_message") as report,
            self.assertRaisesRegex(
                RuntimeWarning, "History entry created without a user"
            ),
        ):
            change.save()
        report.assert_called_once()
        self.assertIsNone(change.pk)

    def test_missing_user_warning_stops_bulk_insert(self) -> None:
        changes = [Change(user=self.user), Change()]
        with (
            patch("weblate.trans.models.change.report_message") as report,
            self.assertRaisesRegex(
                RuntimeWarning, "History entry created without a user"
            ),
        ):
            Change.objects.bulk_create(changes)
        report.assert_called_once()
        self.assertFalse(Change.objects.exists())


class ChangeCompletionTest(ViewTestCase):
    def complete_component(self, user: User) -> None:
        last_unit = self.get_unit("Hello, world!\n")
        with self.captureOnCommitCallbacks(execute=True):
            last_unit.translate(self.user, "", STATE_EMPTY)
        for translation in self.component.translation_set.exclude_source():
            for unit in (
                translation.unit_set.exclude(pk=last_unit.pk)
                .exclude(state=STATE_READONLY)
                .order_by("pk")
            ):
                if unit.state < STATE_TRANSLATED:
                    with self.captureOnCommitCallbacks(execute=True):
                        unit.translate(
                            self.user,
                            [
                                "Completed translation"
                                for _ in range(translation.plural.number)
                            ]
                            if unit.is_plural
                            else "Completed translation",
                            STATE_TRANSLATED,
                        )

        last_unit.translation.stats.update_stats()
        self.assertEqual(
            last_unit.translation.stats.translated,
            last_unit.translation.stats.all - 1,
        )
        previous_change = self.component.change_set.latest("pk")
        with (
            patch("weblate.trans.models.change.report_message") as report,
            self.captureOnCommitCallbacks(execute=True),
        ):
            last_unit.translate(user, "Completed translation", STATE_TRANSLATED)
        report.assert_not_called()

        completions = self.component.change_set.filter(
            pk__gt=previous_change.pk,
            action__in=(ActionEvents.COMPLETE, ActionEvents.COMPLETED_COMPONENT),
        )
        self.assertCountEqual(
            completions.values_list("action", flat=True),
            (ActionEvents.COMPLETE, ActionEvents.COMPLETED_COMPONENT),
        )
        self.assertFalse(
            completions.exclude(user=None if user.is_anonymous else user).exists()
        )

    def test_anonymous_completion(self) -> None:
        self.complete_component(get_anonymous())

    def test_authenticated_completion(self) -> None:
        self.complete_component(self.user)


class ChangeScopeTest(ViewTestCase):
    def test_settings_change_requires_actor(self) -> None:
        self.component.acting_user = None
        self.component.restricted = True
        with (
            patch("weblate.trans.models.change.report_message") as report,
            self.assertRaisesRegex(
                RuntimeWarning, "History entry created without a user"
            ),
        ):
            self.component.save(update_fields=["restricted"])
        report.assert_called_once()

    def test_language_scoped_history(self) -> None:
        language = self.translation.language
        category = self.create_category(self.project)
        scopes: tuple[
            tuple[
                dict[str, object],
                ProjectLanguage | Translation | CategoryLanguage | Language,
            ],
            ...,
        ] = (
            ({"project": self.project}, ProjectLanguage(self.project, language)),
            (
                {"project": self.project, "component": self.component},
                self.translation,
            ),
            ({"category": category}, CategoryLanguage(category, language)),
            ({}, language),
        )
        for scope, expected in scopes:
            for action in (ActionEvents.ANNOUNCEMENT, ActionEvents.COMMENT):
                with self.subTest(scope=scope, action=action):
                    if action == ActionEvents.ANNOUNCEMENT:
                        announcement = Announcement.objects.create(
                            language=language,
                            message="Scoped announcement",
                            user=self.user,
                            **scope,
                        )
                        change = Change.objects.get(announcement=announcement)
                    else:
                        change = Change(action=action, language=language, **scope)
                    self.assertIsNone(change.translation_id)
                    content = render_to_string(
                        "snippets/last-changes-content.html",
                        format_last_changes_content([change], self.user),
                    )
                    url = expected.get_absolute_url()
                    self.assertInHTML(
                        f'<li class="breadcrumb-item"><a href="{url}">{escape(str(language))}</a></li>',
                        content,
                    )
                    self.assertIn(f'href="{url}"\n', content)
                    self.assertEqual(change.get_absolute_url(), url)
                    self.assertIsNone(change.translation_id)

    def test_component_language_resolution_is_cached(self) -> None:
        Translation.objects.filter(pk=self.translation.pk).update(
            language_code="custom"
        )
        change = Change(component=self.component, language=self.translation.language)
        with self.assertNumQueries(1):
            resolved = change.path_object
        self.assertEqual(resolved, self.translation)
        self.assertEqual(cast("Translation", resolved).language_code, "custom")
        expected_url = self.translation.get_absolute_url()
        with self.assertNumQueries(0):
            self.assertIs(change.path_object, resolved)
            self.assertEqual(change.get_absolute_url(), expected_url)
        self.assertIsNone(change.translation_id)

    def test_missing_translation_falls_back_to_component(self) -> None:
        language = Language.objects.exclude(
            pk__in=self.component.translation_set.values("language_id")
        ).first()
        self.assertIsNotNone(language)
        change = Change(component=self.component, language=language)
        self.assertEqual(change.path_object, self.component)
        self.assertEqual(change.get_absolute_url(), self.component.get_absolute_url())

    def test_existing_destinations(self) -> None:
        category = self.create_category(self.project)
        for field, obj in (
            ("translation", self.translation),
            ("component", self.component),
            ("category", category),
            ("project", self.project),
        ):
            with self.subTest(field=field):
                change = Change(**{field: obj})
                self.assertEqual(change.path_object, obj)
                self.assertEqual(change.get_absolute_url(), obj.get_absolute_url())
        self.assertEqual(Change().get_absolute_url(), "/")

    def test_detail_destinations_take_precedence(self) -> None:
        change = Change(translation=self.translation)
        for field, model in (("unit", Unit), ("screenshot", Screenshot)):
            with self.subTest(field=field):
                detail = model()
                setattr(change, field, detail)
                with patch.object(
                    detail, "get_absolute_url", return_value=f"/{field}/"
                ):
                    self.assertEqual(change.get_absolute_url(), f"/{field}/")
                setattr(change, field, None)


class FeedQueriesTest(FixtureTestCase):
    # Reverse managers populate different related objects up front, so the
    # fixed query budget differs between project/component/translation feeds.
    PROJECT_FEED_QUERIES = 11
    COMPONENT_FEED_QUERIES = 10
    TRANSLATION_FEED_QUERIES = 10

    def setUp(self) -> None:
        super().setUp()
        # Permission filtering has a fixed, request-scoped query cost. This test
        # focuses on queries needed to render each feed item.
        self.user.is_superuser = True
        Change.objects.all().delete()

    def add_feed_changes(self, count: int) -> None:
        for index in range(count):
            self.change_unit(
                f"Feed query target {index}\n",
                translation=self.translation,
            )

    def assert_feed_queries(self, obj, expected_queries: int) -> None:
        feed = TranslationChangesFeed()
        with self.assertNumQueries(expected_queries):
            items = list(feed.items(ChangeFeedScope(self.user, obj)))
            for item in items:
                str(item)

    def test_project_feed_queries_do_not_scale_with_change_count(self) -> None:
        self.add_feed_changes(6)
        self.assert_feed_queries(self.project, self.PROJECT_FEED_QUERIES)

    def test_component_feed_queries_do_not_scale_with_change_count(self) -> None:
        self.add_feed_changes(6)
        self.assert_feed_queries(
            self.component,
            self.COMPONENT_FEED_QUERIES,
        )

    def test_translation_feed_queries_do_not_scale_with_change_count(self) -> None:
        self.add_feed_changes(6)
        self.assert_feed_queries(
            self.translation,
            self.TRANSLATION_FEED_QUERIES,
        )


class ChangesTest(ReusableViewTestCase):
    def assert_rss_response(self, response) -> None:
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/rss+xml; charset=utf-8")
        self.assertContains(response, "<rss")

    def add_filtered_rss_changes(self) -> None:
        Change.objects.all().delete()
        self.change_unit("Initial RSS target\n", user=self.user)
        Change.objects.all().delete()
        self.change_unit("Current user RSS target\n", user=self.user)
        self.change_unit("Another user RSS target\n", user=self.anotheruser)

    def add_same_unit_rss_changes(self) -> None:
        Change.objects.all().delete()
        self.change_unit("Initial RSS target\n", user=self.user)
        Change.objects.all().delete()
        self.change_unit("First RSS target\n", user=self.user)
        self.change_unit("Second RSS target\n", user=self.user)

    def assert_per_change_rss_guids(self, url: str) -> None:
        self.add_same_unit_rss_changes()
        response = self.client.get(url)
        self.assert_rss_response(response)
        items = parse_xml(response.content).findall("./channel/item")
        self.assertGreaterEqual(len(items), 2)
        links = [item.findtext("link") for item in items[:2]]
        guids = [item.find("guid") for item in items[:2]]
        self.assertEqual(len(set(links)), 1)
        self.assertEqual(len({guid.text for guid in guids if guid is not None}), 2)
        for guid in guids:
            self.assertIsNotNone(guid)
            self.assertEqual(guid.attrib["isPermaLink"], "false")
            self.assertIn("/changes/render/", guid.text)

    def test_basic(self) -> None:
        response = self.client.get(reverse("changes"))
        self.assertContains(response, "Resource update")

    def test_basic_rss(self) -> None:
        response = self.client.get(reverse("changes-rss"))
        self.assert_rss_response(response)
        self.assertContains(response, "Resource update")

    def test_changes_rss_guids_identify_changes(self) -> None:
        self.assert_per_change_rss_guids(reverse("changes-rss"))

    def test_export_rss_guids_identify_changes(self) -> None:
        self.assert_per_change_rss_guids(reverse("rss"))

    def test_language_rss_hides_private_project_changes(self) -> None:
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save(update_fields=["access_control"])
        Change.objects.all().delete()
        hidden_change = Change.objects.create(
            action=ActionEvents.LOCK,
            project=self.project,
            component=self.component,
            translation=self.translation,
            language=self.translation.language,
            user=self.anotheruser,
        )
        self.client.logout()

        response = self.client.get(
            reverse("rss-language", kwargs={"lang": self.translation.language.code})
        )

        self.assert_rss_response(response)
        self.assertNotContains(response, f"/changes/render/{hidden_change.pk}/")

    def test_language_rss_hides_restricted_component_changes(self) -> None:
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])
        Change.objects.all().delete()
        hidden_change = Change.objects.create(
            action=ActionEvents.LOCK,
            project=self.project,
            component=self.component,
            translation=self.translation,
            language=self.translation.language,
            user=self.anotheruser,
        )
        self.client.logout()

        response = self.client.get(
            reverse("rss-language", kwargs={"lang": self.translation.language.code})
        )

        self.assert_rss_response(response)
        self.assertNotContains(response, f"/changes/render/{hidden_change.pk}/")

    def test_project_rss_hides_restricted_component_changes(self) -> None:
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])
        self.user.clear_permissions_cache()
        self.assertTrue(self.user.can_access_project(self.project))
        self.assertFalse(self.user.can_access_component(self.component))
        Change.objects.all().delete()
        visible_change = Change.objects.create(
            action=ActionEvents.CREATE_PROJECT,
            project=self.project,
            user=self.user,
        )
        hidden_change = Change.objects.create(
            action=ActionEvents.LOCK,
            project=self.project,
            component=self.component,
            translation=self.translation,
            language=self.translation.language,
            user=self.anotheruser,
        )

        response = self.client.get(
            reverse("rss", kwargs={"path": self.project.get_url_path()})
        )

        self.assert_rss_response(response)
        self.assertContains(response, f"/changes/render/{visible_change.pk}/")
        self.assertNotContains(response, f"/changes/render/{hidden_change.pk}/")

    def test_basic_csv_denied(self) -> None:
        response = self.client.get(reverse("changes-csv"))
        self.assertEqual(response.status_code, 403)

    def test_basic_csv(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        response = self.client.get(reverse("changes-csv"))
        self.assertContains(response, "timestamp,")

    def test_filter(self) -> None:
        response = self.client.get(reverse("changes", kwargs={"path": ["test"]}))
        self.assertContains(response, "Resource update")
        response = self.client.get(
            reverse("changes", kwargs={"path": ["test", "test"]})
        )
        self.assertContains(response, "Resource update")
        response = self.client.get(
            reverse("changes", kwargs={"path": ["test", "test", "cs"]})
        )
        self.assertContains(response, "Resource update")
        response = self.client.get(
            reverse("changes", kwargs={"path": ["-", "-", "cs"]})
        )
        self.assertContains(response, "Resource update")
        response = self.client.get(
            reverse("changes", kwargs={"path": ["testx", "test", "cs"]})
        )
        self.assertEqual(response.status_code, 404)

    def test_show_change_hides_private_change(self) -> None:
        private_project = self.create_project(
            name="Private changes",
            slug="private-changes",
            access_control=Project.ACCESS_PRIVATE,
        )
        private_component = self.create_po(
            project=private_project, name="private-changes"
        )
        hidden_change = Change.objects.create(
            action=ActionEvents.LOCK,
            project=private_project,
            component=private_component,
            user=self.anotheruser,
        )

        response = self.client.get(
            reverse("show_change", kwargs={"pk": hidden_change.pk})
        )
        self.assertEqual(response.status_code, 404)

        response = self.client.get(reverse("show_change", kwargs={"pk": 999999}))
        self.assertEqual(response.status_code, 404)

    def test_show_change_ignores_private_other_changes(self) -> None:
        visible_change = Change.objects.create(
            action=ActionEvents.CREATE_PROJECT,
            project=self.project,
            user=self.user,
        )
        private_project = self.create_project(
            name="Private other changes",
            slug="private-other-changes",
            access_control=Project.ACCESS_PRIVATE,
        )
        private_component = self.create_po(
            project=private_project, name="private-other-changes"
        )
        hidden_change = Change.objects.create(
            action=ActionEvents.LOCK,
            project=private_project,
            component=private_component,
            user=self.anotheruser,
        )

        response = self.client.get(
            reverse("show_change", kwargs={"pk": visible_change.pk}),
            {"other": hidden_change.pk},
        )
        self.assertEqual(response.status_code, 200)

    def test_show_change_ignores_invalid_other_values(self) -> None:
        visible_change = Change.objects.create(
            action=ActionEvents.CREATE_PROJECT,
            project=self.project,
            user=self.user,
        )

        response = self.client.get(
            reverse("show_change", kwargs={"pk": visible_change.pk}),
            {"other": ["invalid", str(visible_change.pk)]},
        )
        self.assertEqual(response.status_code, 200)

    def test_string(self) -> None:
        response = self.client.get(
            reverse("changes", kwargs={"path": Unit.objects.all()[0].get_url_path()})
        )
        self.assertContains(response, "Source string added")
        self.assertContains(response, "Changes of string in")

    def test_user(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        response = self.client.get(reverse("changes"), {"user": self.user.username})
        self.assertContains(response, f'title="{self.user.full_name}"')
        # Filtering by another user should not show the change made by
        # the current test user.
        response = self.client.get(
            reverse("changes"), {"user": self.anotheruser.username}
        )
        self.assertNotContains(response, f'title="{self.user.full_name}"')

    def test_user_rss(self) -> None:
        self.add_filtered_rss_changes()
        response = self.client.get(reverse("changes-rss"), {"user": self.user.username})
        self.assert_rss_response(response)
        self.assertContains(response, "testuser")
        self.assertNotContains(response, "Jane Doe")

    def test_exclude_user(self) -> None:
        self.edit_unit("Hello, world!\n", "Nazdar svete!\n")
        response = self.client.get(reverse("changes"))
        self.assertContains(response, f'title="{self.user.full_name}"')
        # Filtering by current user should not show the change made by
        # the current test user.
        response = self.client.get(
            reverse("changes"), {"exclude_user": self.user.username}
        )
        self.assertNotContains(response, f'title="{self.user.full_name}"')
        # Filtering by another user should show the change made by
        # the current test user.
        response = self.client.get(
            reverse("changes"), {"exclude_user": self.anotheruser.username}
        )
        self.assertContains(response, f'title="{self.user.full_name}"')

    def test_exclude_user_rss(self) -> None:
        self.add_filtered_rss_changes()
        response = self.client.get(
            reverse("changes-rss"), {"exclude_user": self.user.username}
        )
        self.assert_rss_response(response)
        self.assertNotContains(response, "Weblate Test")
        self.assertContains(response, "Jane Doe")

    def test_action_rss(self) -> None:
        Change.objects.all().delete()
        self.change_unit("Initial RSS target\n", user=self.user)
        Change.objects.all().delete()
        self.change_unit("Current user RSS target\n", user=self.user)
        response = self.client.get(
            reverse("changes-rss"), {"action": ActionEvents.CHANGE}
        )
        self.assert_rss_response(response)
        self.assertContains(response, "Translation changed")
        response = self.client.get(
            reverse("changes-rss"), {"action": ActionEvents.UPDATE}
        )
        self.assert_rss_response(response)
        self.assertNotContains(response, "Translation changed")

    def test_daterange(self) -> None:
        end = timezone.now()
        start = end - timedelta(days=1)
        period = f"{start.strftime('%m/%d/%Y')} - {end.strftime('%m/%d/%Y')}"
        response = self.client.get(reverse("changes"), {"period": period})
        self.assertContains(response, "Resource update")

    def test_daterange_rss(self) -> None:
        Change.objects.all().delete()
        self.change_unit("Initial RSS target\n", user=self.user)
        Change.objects.all().delete()
        self.change_unit("Current user RSS target\n", user=self.user)
        end = timezone.now()
        start = end - timedelta(days=1)
        period = f"{start.strftime('%m/%d/%Y')} - {end.strftime('%m/%d/%Y')}"
        response = self.client.get(reverse("changes-rss"), {"period": period})
        self.assert_rss_response(response)
        self.assertContains(response, "Translation changed")
        response = self.client.get(
            reverse("changes-rss"), {"period": "01/01/2020 - 01/02/2020"}
        )
        self.assert_rss_response(response)
        self.assertNotContains(response, "Translation changed")

    def test_scoped_rss(self) -> None:
        Change.objects.all().delete()
        self.change_unit("Initial RSS target\n", user=self.user)
        Change.objects.all().delete()
        unit = self.change_unit("Scoped RSS target\n", user=self.user)
        paths = (
            self.project.get_url_path(),
            self.component.get_url_path(),
            self.translation.get_url_path(),
            ["-", "-", self.translation.language.code],
            [self.project.slug, "-", self.translation.language.code],
            unit.get_url_path(),
        )
        for feed_name in ("changes-rss", "rss"):
            for path in paths:
                with self.subTest(feed_name=feed_name, path=path):
                    response = self.client.get(
                        reverse(feed_name, kwargs={"path": path})
                    )
                    self.assert_rss_response(response)
                    self.assertContains(response, "Translation changed")

    def test_pagination(self) -> None:
        self.component.change_set.create(
            user=self.user, action=ActionEvents.NEW_UNIT_UPLOAD
        )
        for _index in range(20):
            self.component.change_set.create(user=self.user, action=ActionEvents.LOCK)

        end = timezone.now()
        start = end - timedelta(days=1)
        period = f"{start.strftime('%m/%d/%Y')} - {end.strftime('%m/%d/%Y')}"
        response = self.client.get(reverse("changes"), {"period": period})
        document = html.fromstring(response.content)
        next_url = document.xpath('//a[@rel="next"]/@href')[0]
        params = QueryDict(next_url.removeprefix("?"))
        self.assertEqual(params["period"], period)
        self.assertIn("before", params)
        self.assertIn("id", params)
        self.assertNotIn("cursor", params)
        self.assertNotIn("page", params)
        response = self.client.get(f"{reverse('changes')}{next_url}")
        self.assertContains(response, "String added in the upload")

    def create_cursor_changes(self, count: int = 45) -> list[Change]:
        Change.objects.all().delete()
        changes = [
            self.component.change_set.create(user=self.user, action=ActionEvents.LOCK)
            for _ in range(count)
        ]
        # Exercise the ID tie breaker across multiple full pages.
        timestamp = timezone.now()
        Change.objects.all().update(timestamp=timestamp)
        return list(reversed(changes))

    def get_cursor_page(
        self, cursor: dict[str, str | int] | None = None, **params: str | int
    ) -> _MonkeyPatchedWSGIResponse:
        if cursor:
            params.update(cursor)
        return self.client.get(reverse("changes"), params)

    def test_cursor_round_trip(self) -> None:
        changes = self.create_cursor_changes()
        first = self.get_cursor_page()
        self.assertEqual(list(first.context["object_list"]), changes[:20])
        self.assertIsNone(first.context["newer_cursor"])
        first_document = html.fromstring(first.content)
        self.assertEqual(
            len(
                first_document.xpath(
                    '//nav[starts-with(@aria-label, "History navigation")]//li[1]/span[@aria-disabled="true"]'
                )
            ),
            2,
        )
        second = self.get_cursor_page(first.context["older_cursor"])
        second_document = html.fromstring(second.content)
        self.assertEqual(
            len(
                second_document.xpath(
                    '//nav[starts-with(@aria-label, "History navigation")]//li[1]/a'
                )
            ),
            2,
        )
        self.assertEqual(list(second.context["object_list"]), changes[20:40])
        last = self.get_cursor_page(second.context["older_cursor"])
        self.assertEqual(list(last.context["object_list"]), changes[40:])
        self.assertIsNone(last.context["older_cursor"])
        previous = self.get_cursor_page(last.context["newer_cursor"])
        self.assertEqual(list(previous.context["object_list"]), changes[20:40])
        previous = self.get_cursor_page(previous.context["newer_cursor"])
        self.assertEqual(list(previous.context["object_list"]), changes[:20])

    def test_cursor_page_sizes(self) -> None:
        for count in (0, 1, 20, 21):
            with self.subTest(count=count):
                changes = self.create_cursor_changes(count)
                response = self.get_cursor_page()
                self.assertEqual(list(response.context["object_list"]), changes[:20])
                self.assertEqual(bool(response.context["older_cursor"]), count > 20)
                self.assertIsNone(response.context["newer_cursor"])
                document = html.fromstring(response.content)
                navigation = document.xpath(
                    '//nav[starts-with(@aria-label, "History navigation")]'
                )
                self.assertEqual(len(navigation), 2 if count > 20 else 0)
                self.assertEqual(
                    len(document.xpath('//form[@id="change-date-form"]')), 1
                )

    def test_cursor_survives_history_changes(self) -> None:
        changes = self.create_cursor_changes()
        response = self.get_cursor_page()
        changes[19].delete()
        self.component.change_set.create(user=self.user, action=ActionEvents.LOCK)
        response = self.get_cursor_page(response.context["older_cursor"])
        self.assertEqual(list(response.context["object_list"]), changes[20:40])

    def test_cursor_queries_are_bounded(self) -> None:
        self.create_cursor_changes()
        first = self.get_cursor_page()
        for cursor in (None, first.context["older_cursor"]):
            with (
                self.subTest(cursor=cursor),
                CaptureQueriesContext(connection) as queries,
            ):
                response = self.get_cursor_page(cursor)
                self.assertEqual(response.status_code, 200)
            history_queries = [
                q["sql"] for q in queries if 'FROM "trans_change"' in q["sql"]
            ]
            self.assertTrue(history_queries)
            for sql in history_queries:
                self.assertNotIn("COUNT(", sql)
                self.assertNotIn("OFFSET", sql)
                self.assertTrue(
                    "LIMIT" in sql or '"trans_change"."id" IN (' in sql, sql
                )

    def test_readable_cursor_parameters(self) -> None:
        changes = self.create_cursor_changes()
        boundary = changes[20]
        boundary.refresh_from_db()
        timestamp = boundary.timestamp.astimezone(
            timezone.get_fixed_timezone(120)
        ).isoformat()
        response = self.get_cursor_page(before=timestamp, id=boundary.pk)
        self.assertEqual(list(response.context["object_list"]), changes[21:41])
        response = self.get_cursor_page(after=timestamp, id=boundary.pk)
        self.assertEqual(list(response.context["object_list"]), changes[:20])
        params = response.context["older_cursor"]
        self.assertTrue(params["before"].endswith("Z"))
        self.assertEqual(params["id"], changes[19].pk)

    def test_cursor_invalid(self) -> None:
        timestamp = timezone.now().isoformat()
        values: tuple[dict[str, str | int], ...] = (
            {"before": timestamp},
            {"id": 1},
            {"before": timestamp, "after": timestamp, "id": 1},
            {"before": timestamp, "id": -1},
            {"before": timestamp, "id": 2**63},
            {"before": timestamp, "id": "invalid"},
            {"before": "invalid", "id": 1},
            {"before": "", "id": 1},
            {"after": "2026-09-17T00:00:00", "id": 1},
            {"before": "0001-01-01T00:00:00+01:00", "id": 1},
            {"after": "9999-12-31T23:59:59-01:00", "id": 1},
        )
        for value in values:
            with self.subTest(value=value):
                self.assertEqual(
                    self.client.get(reverse("changes"), value).status_code, 404
                )
        for query in (
            "before=2026-09-17T00:00:00Z&id=1&id=2",
            "before=2026-09-17T00:00:00Z&before=2026-09-16T00:00:00Z&id=1",
        ):
            with self.subTest(query=query):
                self.assertEqual(
                    self.client.get(f"{reverse('changes')}?{query}").status_code, 404
                )

    def test_date_jump(self) -> None:
        changes = self.create_cursor_changes(2)
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        Change.objects.filter(pk=changes[1].pk).update(
            timestamp=timezone.now() - timedelta(days=1)
        )
        response = self.get_cursor_page(
            date=yesterday.isoformat(), before="ignored", id="ignored"
        )
        self.assertEqual(list(response.context["object_list"]), [changes[1]])
        self.assertIsNone(response.context["older_cursor"])
        response = self.get_cursor_page(response.context["newer_cursor"])
        self.assertEqual(list(response.context["object_list"]), [changes[0]])
        response = self.get_cursor_page(date="2000-01-01")
        self.assertEqual(list(response.context["object_list"]), [])
        self.assertIsNotNone(response.context["newer_cursor"])
        response = self.get_cursor_page(response.context["newer_cursor"])
        self.assertEqual(list(response.context["object_list"]), changes)

    def test_date_jump_timezone_and_range(self) -> None:
        changes = self.create_cursor_changes(3)
        # Midnight after a DST transition in Prague is 22:00 UTC.
        boundary = datetime(2026, 3, 29, 22, tzinfo=UTC)
        for change, delta in zip(
            changes,
            (timedelta(), timedelta(microseconds=-1), timedelta(days=-2)),
            strict=True,
        ):
            Change.objects.filter(pk=change.pk).update(timestamp=boundary + delta)
        with timezone.override("Europe/Prague"):
            response = self.get_cursor_page(date="2026-03-29")
            self.assertEqual(list(response.context["object_list"]), changes[1:])
            response = self.get_cursor_page(
                date="2026-03-29", period="03/29/2026 - 03/30/2026"
            )
            self.assertEqual(list(response.context["object_list"]), changes[1:2])
            newer = self.get_cursor_page(
                response.context["newer_cursor"], period="03/29/2026 - 03/30/2026"
            )
            self.assertEqual(list(newer.context["object_list"]), changes[:1])

    def test_cursor_scope_and_permissions(self) -> None:
        changes = self.create_cursor_changes()
        private_project = self.create_project(
            name="Cursor private",
            slug="cursor-private",
            access_control=Project.ACCESS_PRIVATE,
        )
        hidden = Change.objects.create(
            user=self.user, project=private_project, action=ActionEvents.LOCK
        )
        cursor = ChangesView.cursor_params(hidden.timestamp, hidden.pk, "older")
        response = self.get_cursor_page(cursor)
        self.assertEqual(list(response.context["object_list"]), changes[:20])
        scoped_url = reverse("changes", kwargs={"path": self.component.get_url_path()})
        response = self.client.get(scoped_url, response.context["older_cursor"])
        self.assertEqual(list(response.context["object_list"]), changes[20:40])
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])
        response = self.get_cursor_page(cursor)
        self.assertEqual(list(response.context["object_list"]), [])
        self.assertIsNone(response.context["older_cursor"])
        self.assertIsNone(response.context["newer_cursor"])

    def test_exports_ignore_navigation(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        self.create_cursor_changes()
        for name in ("changes-rss", "changes-csv"):
            with self.subTest(name=name):
                url = reverse(name)
                expected = self.client.get(url, {"action": ActionEvents.LOCK})
                response = self.client.get(
                    url,
                    {
                        "action": str(ActionEvents.LOCK),
                        "before": "invalid",
                        "id": "invalid",
                        "date": "2000-01-01",
                    },
                )
                if name == "changes-csv":
                    self.assertEqual(response.content, expected.content)
                else:
                    self.assertEqual(
                        len(parse_xml(response.content).findall("channel/item")), 10
                    )
                    self.assertEqual(
                        [
                            item.findtext("guid")
                            for item in parse_xml(response.content).findall(
                                "channel/item"
                            )
                        ],
                        [
                            item.findtext("guid")
                            for item in parse_xml(expected.content).findall(
                                "channel/item"
                            )
                        ],
                    )

    def test_date_jump_invalid(self) -> None:
        for date in ("invalid", "9999-12-31"):
            with self.subTest(date=date):
                response = self.get_cursor_page(date=date)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["date_form"].errors)
                self.assertEqual(list(response.context["object_list"]), [])

    def test_date_jump_rejects_future(self) -> None:
        today = timezone.localdate()
        response = self.get_cursor_page(date=(today + timedelta(days=1)).isoformat())
        self.assertFormError(
            response.context["date_form"], "date", "The date cannot be in the future."
        )
        self.assertEqual(list(response.context["object_list"]), [])
        document = html.fromstring(response.content)
        self.assertEqual(
            document.xpath('//input[@name="date"]/@max'), [today.isoformat()]
        )
        response = self.get_cursor_page(date=today.isoformat())
        self.assertFalse(response.context["date_form"].errors)

    def test_date_jump_future_limit_uses_current_timezone(self) -> None:
        now = datetime(2026, 9, 17, 23, tzinfo=UTC)
        with (
            timezone.override("Europe/Prague"),
            patch("django.utils.timezone.now", return_value=now),
        ):
            form = ChangesDateForm(data={"date": "2026-09-18"})
            self.assertTrue(form.is_valid())
            self.assertEqual(form.fields["date"].widget.attrs["max"], "2026-09-18")
            self.assertFalse(ChangesDateForm(data={"date": "2026-09-19"}).is_valid())

    def test_legacy_pagination_redirect(self) -> None:
        response = self.get_cursor_page(page="last", limit=50, action=ActionEvents.LOCK)
        self.assertRedirects(
            response, f"{reverse('changes')}?action={ActionEvents.LOCK}"
        )

    def test_navigation_not_in_export_links(self) -> None:
        self.user.is_superuser = True
        self.user.save()
        self.create_cursor_changes()
        first = self.get_cursor_page()
        response = self.get_cursor_page(
            first.context["older_cursor"], action=ActionEvents.LOCK
        )
        for name in ("changes-rss", "changes-csv"):
            self.assertContains(response, f"{reverse(name)}?action={ActionEvents.LOCK}")
        response = self.get_cursor_page(date="2000-01-01", action=ActionEvents.LOCK)
        for name in ("changes-rss", "changes-csv"):
            self.assertContains(response, f"{reverse(name)}?action={ActionEvents.LOCK}")

    def test_rss_link_keeps_query_string(self) -> None:
        response = self.client.get(reverse("changes"), {"user": self.user.username})
        query_string = urlencode({"user": self.user.username})
        self.assertContains(response, f"{reverse('changes-rss')}?{query_string}")

    def test_last_changes_display(self) -> None:
        unit_to_delete = self.get_unit("Orangutan has %d banana")
        unit_to_delete.context = "Orangutan unit context"
        unit_to_delete.save()
        self.translation.delete_unit(None, unit_to_delete)
        response = self.client.get(reverse("changes"))
        self.assertContains(
            response, "String removed", count=2
        )  # one is from search options, second from history-data
        # check the string context is also displayed
        self.assertContains(response, "Orangutan unit context")
