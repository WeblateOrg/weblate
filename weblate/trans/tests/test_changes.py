# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for changes browsing."""

from datetime import timedelta
from html import escape

from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode

from weblate.trans.actions import ActionEvents
from weblate.trans.feeds import ChangeFeedScope, TranslationChangesFeed
from weblate.trans.models import Change, Project, Unit
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
