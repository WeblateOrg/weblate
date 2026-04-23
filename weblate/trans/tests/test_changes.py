# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for changes browsing."""

from datetime import timedelta
from html import escape

from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode

from weblate.trans.feeds import TranslationChangesFeed
from weblate.trans.models import Change, Unit
from weblate.trans.tests.test_views import FixtureTestCase, ViewTestCase


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
    def test_basic(self) -> None:
        response = self.client.get(reverse("changes"))
        self.assertContains(response, "Resource update")

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

    def test_daterange(self) -> None:
        end = timezone.now()
        start = end - timedelta(days=1)
        period = f"{start.strftime('%m/%d/%Y')} - {end.strftime('%m/%d/%Y')}"
        response = self.client.get(reverse("changes"), {"period": period})
        self.assertContains(response, "Resource update")

    def test_pagination(self) -> None:
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
