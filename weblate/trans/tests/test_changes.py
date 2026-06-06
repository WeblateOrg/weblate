# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for changes browsing."""

import csv
from datetime import timedelta
from html import escape
from io import StringIO

from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode

from weblate.trans.actions import ActionEvents
from weblate.trans.feeds import TranslationChangesFeed
from weblate.trans.models import Change, Unit
from weblate.trans.tests.test_views import FixtureTestCase, ViewTestCase
from weblate.utils.xml import parse_xml


class FeedQueriesTest(FixtureTestCase):
    # Reverse managers populate different related objects up front, so the
    # fixed query budget differs between project/component/translation feeds.
    PROJECT_FEED_QUERIES = 12
    COMPONENT_FEED_QUERIES = 11
    TRANSLATION_FEED_QUERIES = 11

    def setUp(self) -> None:
        super().setUp()
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
            items = list(feed.items(obj))
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


class ChangesTest(ViewTestCase):
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
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(
                    reverse("changes-rss", kwargs={"path": path})
                )
                self.assert_rss_response(response)
                self.assertContains(response, "Translation changed")

    def test_pagination(self) -> None:
        self.component.change_set.create(action=ActionEvents.NEW_UNIT_UPLOAD)
        for _index in range(20):
            self.component.change_set.create(action=ActionEvents.LOCK)

        end = timezone.now()
        start = end - timedelta(days=1)
        period = f"{start.strftime('%m/%d/%Y')} - {end.strftime('%m/%d/%Y')}"
        response = self.client.get(reverse("changes"), {"period": period})
        query_string = urlencode({"page": 2, "limit": 20, "period": period})
        self.assertContains(response, escape(query_string))
        response = self.client.get(
            reverse("changes"), {"page": 2, "limit": 20, "period": period}
        )
        self.assertContains(response, "String added in the upload")

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

    def test_change_message_display(self) -> None:
        """Test that user-provided message is displayed in change detail and history."""
        # 1. Test change detail view displays the message
        unit = self.get_unit("Hello, world!\n")
        custom_message = "Correcting spelling mistakes in translation."
        change = Change.objects.create(
            unit=unit,
            action=ActionEvents.CHANGE,
            user=self.user,
            author=self.user,
            target="Nazdar světe!\n",
            old="Nazdar svete!\n",
            message=custom_message,
        )

        response = self.client.get(reverse("show_change", kwargs={"pk": change.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="alert alert-info change-user-message"')
        self.assertContains(response, custom_message)

        # 2. Test change list / last changes displays the message (change-message.html snippet)
        response = self.client.get(reverse("changes"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="change-user-message')
        self.assertContains(response, custom_message)

    def test_changes_csv_export_contains_message(self) -> None:
        """Test that the CSV export includes the 'message' column and values."""
        # Clean changes first for easy testing
        Change.objects.all().delete()
        self.change_unit("Nazdar svete!\n", user=self.user)

        message_text = "Reason for CSV export check."
        # Set message on the change manually
        latest_change = Change.objects.order_by("-timestamp").first()
        latest_change.message = message_text
        latest_change.save()

        # Authorize as superuser to download CSV
        self.user.is_superuser = True
        self.user.save()

        response = self.client.get(reverse("changes-csv"))
        self.assertEqual(response.status_code, 200)

        content = response.content.decode("utf-8")
        reader = csv.reader(StringIO(content))
        rows = list(reader)

        # Assert headers have message
        headers = rows[0]
        self.assertIn("message", headers)
        message_index = headers.index("message")

        # Assert row value
        row = rows[1]
        self.assertEqual(row[message_index], message_text)
