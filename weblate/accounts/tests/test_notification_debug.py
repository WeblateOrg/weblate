# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Notification diagnostics and their administrator interface."""

from __future__ import annotations

from copy import copy
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.template.loader import render_to_string
from django.test import override_settings
from django.test.html import Element, parse_html
from django.utils.translation import override

from weblate.accounts.models import Subscription
from weblate.accounts.notification_debug import (
    NotificationDebugger,
    NotificationExplanation,
)
from weblate.accounts.notifications import (
    NOTIFICATIONS,
    MentionCommentNotificaton,
    NewAlertNotificaton,
    NewCommentNotificaton,
    NewStringNotificaton,
    Notification,
    NotificationFrequency,
    NotificationScope,
    RepositoryNotification,
)
from weblate.accounts.views import UserPage
from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.trans.models import Category, Component, Project, Translation
from weblate.trans.tests.test_views import FixtureTestCase

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


@override_settings(SUPPORT_STATUS_CHECK=False)
class NotificationDebugTest(FixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user.subscription_set.all().delete()
        self.viewer = User.objects.create_superuser(
            username="notification-admin",
            email="admin@example.com",
            password="testpassword",
        )
        self.client.force_login(self.viewer)

    def subscribe(self, scope=NotificationScope.SCOPE_ALL, **kwargs):
        return self.user.subscription_set.create(
            scope=scope,
            notification=kwargs.pop("notification", RepositoryNotification.get_name()),
            frequency=kwargs.pop("frequency", NotificationFrequency.FREQ_INSTANT),
            **kwargs,
        )

    def explain(self, notification=RepositoryNotification, translation=None):
        return NotificationDebugger(self.user).explain(
            notification([], user_ids=[self.user.pk]),
            self.project,
            self.component,
            translation,
        )

    def debug(self, path=None, **kwargs):
        return self.client.get(
            self.user.get_absolute_url(),
            {"notification_target": path or self.project.slug, **kwargs},
        )

    def test_precedence_and_disabled_subscription(self) -> None:
        other = self.subscribe()
        self.user.profile.watched.add(self.project)
        watched = self.subscribe(NotificationScope.SCOPE_WATCHED)
        project = self.subscribe(NotificationScope.SCOPE_PROJECT, project=self.project)
        component = self.subscribe(
            NotificationScope.SCOPE_COMPONENT,
            component=self.component,
            project=self.project,
            frequency=NotificationFrequency.FREQ_NONE,
        )
        result = self.explain()
        self.assertEqual(result.subscription, component)
        self.assertEqual(result.overridden, [project, watched, other])
        self.assertEqual(result.reason, "Disabled by the effective subscription.")

    def test_watched_and_admin_scopes(self) -> None:
        self.user.profile.watched.clear()
        watched = self.subscribe(NotificationScope.SCOPE_WATCHED)
        result = self.explain()
        self.assertIsNone(result.subscription)
        self.assertIn("The user is not watching this project.", result.conditions)
        self.user.profile.watched.add(self.project)
        self.assertEqual(self.explain().subscription, watched)
        self.project.add_user(self.user, "Administration")
        admin = self.subscribe(NotificationScope.SCOPE_ADMIN)
        self.assertEqual(self.explain().subscription, admin)

    def test_language_filter(self) -> None:
        translation = self.component.translation_set.get(language__code="cs")
        self.subscribe(notification=NewStringNotificaton.get_name())
        self.user.profile.languages.clear()
        result = self.explain(NewStringNotificaton, translation)
        self.assertIsNone(result.subscription)
        self.assertIn("notification languages", result.reason)
        self.user.profile.languages.add(translation.language)
        self.assertIsNotNone(
            self.explain(NewStringNotificaton, translation).subscription
        )

    def test_comment_languages(self) -> None:
        self.subscribe(notification=NewCommentNotificaton.get_name())
        self.user.profile.languages.clear()
        target = self.component.translation_set.get(language__code="cs")
        result = self.explain(NewCommentNotificaton, target)
        self.assertIn("notification languages", result.reason)
        source = self.component.translation_set.get(
            language=self.component.source_language
        )
        self.assertIsNotNone(self.explain(NewCommentNotificaton, source).subscription)

    def test_ignored_watched_scope(self) -> None:
        self.user.profile.watched.add(self.project)
        self.subscribe(
            NotificationScope.SCOPE_WATCHED,
            notification=MentionCommentNotificaton.get_name(),
        )
        result = self.explain(MentionCommentNotificaton)
        self.assertIsNone(result.subscription)
        self.assertIn(
            "This notification ignores watched-project subscriptions.",
            result.conditions,
        )

    def test_event_dependent_notifications(self) -> None:
        for notification in (
            NewCommentNotificaton,
            MentionCommentNotificaton,
            NewAlertNotificaton,
        ):
            with self.subTest(notification=notification):
                subscription = self.subscribe(notification=notification.get_name())
                result = self.explain(notification)
                self.assertEqual(result.subscription, subscription)
                self.assertIn("Eligible", result.reason)
                self.assertTrue(result.conditions)

    def test_ineligible_accounts_and_access(self) -> None:
        self.subscribe()
        for attribute in ("is_active", "is_bot"):
            with self.subTest(attribute=attribute):
                original = getattr(self.user, attribute)
                setattr(self.user, attribute, not original)
                self.assertIn("Inactive users and bots", self.explain().reason)
                setattr(self.user, attribute, original)
        with patch.object(User, "can_access_component", return_value=False):
            self.assertEqual(
                self.explain().reason, "The user cannot access this target."
            )

    def test_debug_is_read_only(self) -> None:
        subscription = self.subscribe(
            NotificationScope.SCOPE_COMPONENT,
            component=self.component,
            project=self.project,
            onetime=True,
        )
        before = list(Subscription.objects.values())
        with (
            patch.object(Notification, "send") as send,
            patch("weblate.accounts.notifications.queue_mails") as queue,
        ):
            response = self.debug()
        self.assertEqual(response.status_code, 200, response.headers)
        send.assert_not_called()
        queue.assert_not_called()
        self.assertEqual(list(Subscription.objects.values()), before)
        self.assertContains(response, f"#notification-subscription-{subscription.pk}")
        self.assertContains(response, "Operation was performed in the repository")
        self.assertEqual(
            {
                result.notification
                for result in response.context["notification_results"]
            },
            set(NOTIFICATIONS),
        )

    def test_groups_and_languages(self) -> None:
        self.subscribe()
        self.user.profile.watched.add(self.project)
        language = self.component.translation_set.get(language__code="cs").language
        self.user.profile.languages.add(language)
        response = self.client.get(self.user.get_absolute_url())
        self.assertEqual(list(response.context["notification_languages"]), [language])
        self.assertIn(self.project, response.context["notification_watched_projects"])
        group = response.context["notification_subscription_groups"][0]
        self.assertFalse(group["show_project"])
        self.assertFalse(group["show_component"])
        self.assertNotContains(response, "RepositoryNotification")
        with override("cs"):
            self.assertNotEqual(NotificationScope.SCOPE_PROJECT.label, "Project")

    def test_invalid_paths(self) -> None:
        for path in (
            "",
            "/",
            "missing",
            "a//b",
            "<script>",
            "test/no-such-component/cs",
        ):
            with self.subTest(path=path):
                response = self.client.get(
                    self.user.get_absolute_url(), {"notification_target": path}
                )
                self.assertEqual(response.status_code, 200, response.headers)
                self.assertTrue(response.context["notification_form"].errors)
                self.assertNotIn("notification_results", response.context)
                self.assertContains(response, 'class="tab-pane active"\n')
        self.assertNotContains(response, "<script>alert(")

    def test_permission_required(self) -> None:
        self.client.force_login(self.user)
        response = self.debug()
        self.assertEqual(response.status_code, 403)
        response = self.client.get(self.user.get_absolute_url())
        self.assertNotContains(response, "Notification debug")

    def test_descendants_and_grouping(self) -> None:
        subscription = self.subscribe()
        response = self.debug()
        results = [
            result
            for result in response.context["notification_results"]
            if result.notification is RepositoryNotification
        ]
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result.subscription, subscription)
        self.assertIn(self.project, result.targets)
        self.assertIn(self.component, result.targets)
        self.assertTrue(
            any(
                target in result.targets
                for target in self.component.translation_set.all()
            )
        )

    def test_nested_category_and_translation_paths(self) -> None:
        parent = Category(project=self.project, name="Parent", slug="parent")
        Category.objects.bulk_create([parent])
        child = Category(
            project=self.project, category=parent, name="Child", slug="child"
        )
        Category.objects.bulk_create([child])
        # Avoid repository operations: diagnostics need only the database hierarchy.
        type(self.component).objects.filter(pk=self.component.pk).update(category=child)
        path = f"{self.project.slug}/parent/child/{self.component.slug}/cs"
        response = self.debug(path)
        self.assertEqual(response.status_code, 200, response.headers)
        self.assertEqual(
            response.context["notification_debug_target"].language.code, "cs"
        )
        response = self.debug(f"{self.project.slug}/parent")
        self.assertIn(self.component, response.context["notification_page"].object_list)

    def test_empty_category(self) -> None:
        Category.objects.bulk_create(
            [Category(project=self.project, name="Empty", slug="empty")]
        )
        response = self.debug(f"{self.project.slug}/empty")
        self.assertContains(response, "No accessible components or translations")
        self.assertEqual(response.context["notification_page"].paginator.count, 0)

    def test_pagination(self) -> None:
        components = []
        for index in range(51):
            component = copy(self.component)
            component.pk = None
            component.slug = f"notification-{index}"
            component.name = f"Notification {index}"
            components.append(component)
        Component.objects.bulk_create(components)
        self.subscribe()
        response = self.debug()
        page = response.context["notification_page"]
        self.assertEqual(len(page.object_list), 50)
        self.assertEqual(
            page.paginator.count, 53 + self.component.translation_set.count()
        )
        self.assertContains(
            response, "?page=2&amp;limit=50&amp;notification_target=test#notifications"
        )
        second = self.debug(page="2")
        self.assertEqual(
            len(second.context["notification_page"].object_list),
            page.paginator.count - 50,
        )
        self.assertFalse(
            set(page.object_list) & set(second.context["notification_page"].object_list)
        )
        invalid = self.debug(page="invalid")
        self.assertEqual(invalid.context["notification_page"].number, 1)

    def test_inaccessible_target(self) -> None:
        with patch.object(User, "check_access_component", side_effect=PermissionDenied):
            response = self.debug(f"{self.project.slug}/{self.component.slug}")
        self.assertContains(
            response, "The target does not exist or you cannot access it."
        )
        self.assertNotIn("notification_results", response.context)

    def test_descendants_require_viewer_access(self) -> None:
        Component.objects.filter(pk=self.component.pk).update(restricted=True)
        viewer = User.objects.create_user(username="limited-viewer")
        results, page = NotificationDebugger(self.user).inspect(
            self.project, viewer, None
        )
        self.assertEqual(page.paginator.count, 1)
        self.assertEqual(page.object_list, [self.project])
        self.assertTrue(all(result.targets == [self.project] for result in results))

    def test_component_override_does_not_apply_to_project(self) -> None:
        project = self.subscribe(NotificationScope.SCOPE_PROJECT, project=self.project)
        component = self.subscribe(
            NotificationScope.SCOPE_COMPONENT,
            component=self.component,
            frequency=NotificationFrequency.FREQ_NONE,
        )
        response = self.debug()
        results = [
            result
            for result in response.context["notification_results"]
            if result.notification is RepositoryNotification
        ]
        self.assertEqual(
            {result.subscription.pk for result in results}, {project.pk, component.pk}
        )
        project_result = next(
            result for result in results if result.subscription == project
        )
        self.assertEqual(project_result.targets, [self.project])

    def test_translation_debug_renders_notification_names(self) -> None:
        response = self.debug(f"{self.project.slug}/{self.component.slug}/cs")
        self.assertContains(response, "Operation was performed in the repository")
        self.assertTrue(
            all(
                len(result.targets) == 1
                for result in response.context["notification_results"]
            )
        )

    def notification_context(self, **params):
        view = UserPage()
        view.object = self.user
        view.request = cast(
            "AuthenticatedHttpRequest",
            self.factory.get(self.user.get_absolute_url(), params),
        )
        view.request.user = self.viewer
        return view.get_notification_context()

    def render_notifications(self, context):
        return render_to_string(
            "accounts/notification_debug.html",
            {**context, "page_user": self.user},
            request=self.get_request(self.viewer),
        )

    def test_profile_list_summaries(self) -> None:
        projects = Project.objects.bulk_create(
            [
                Project(
                    name=f"Watched {index}",
                    slug=f"watched-{index}",
                    web="https://example.com/",
                )
                for index in range(6)
            ]
        )
        languages = Language.objects.bulk_create(
            [
                Language(name=f"Notification language {index}", code=f"debug-{index}")
                for index in range(6)
            ]
        )
        for count in (0, 1, 5, 6):
            with self.subTest(count=count):
                self.user.profile.watched.set(projects[:count])
                self.user.profile.languages.set(languages[:count])
                context = self.notification_context()
                self.assertEqual(context["notification_watched_count"], count)
                self.assertEqual(context["notification_language_count"], count)
                html = self.render_notifications(context)
                if count > 5:
                    self.assertEqual(context["notification_watched_projects"], [])
                    self.assertEqual(context["notification_languages"], [])
                    self.assertIn("6 watched projects.", html)
                    self.assertIn("6 notification languages.", html)
                    for obj in [*projects, *languages]:
                        self.assertNotIn(f'href="{obj.get_absolute_url()}"', html)
                else:
                    self.assertCountEqual(
                        context["notification_watched_projects"], projects[:count]
                    )
                    self.assertCountEqual(
                        context["notification_languages"], languages[:count]
                    )
                    for obj in [*projects[:count], *languages[:count]]:
                        self.assertIn(f'href="{obj.get_absolute_url()}"', html)
                if not count:
                    self.assertIn("No watched projects.", html)
                    self.assertIn("No notification languages selected.", html)

    def test_large_profile_lists_do_not_load_objects(self) -> None:
        projects = Project.objects.bulk_create(
            [
                Project(
                    name=f"Watched {index}",
                    slug=f"watched-{index}",
                    web="https://example.com/",
                )
                for index in range(6)
            ]
        )
        languages = Language.objects.bulk_create(
            [
                Language(name=f"Debug {index}", code=f"debug-{index}")
                for index in range(6)
            ]
        )
        self.user.profile.watched.set(projects)
        self.user.profile.languages.set(languages)
        with (
            patch.object(Project, "from_db", wraps=Project.from_db) as load_project,
            patch.object(Language, "from_db", wraps=Language.from_db) as load_language,
        ):
            context = self.notification_context()
        load_project.assert_not_called()
        load_language.assert_not_called()
        self.assertEqual(context["notification_watched_count"], 6)
        self.assertEqual(context["notification_language_count"], 6)

    def test_watched_count_respects_viewer_access(self) -> None:
        private = Project.objects.create(
            name="Private watched",
            slug="private-watched",
            web="https://example.com/",
            access_control=Project.ACCESS_PRIVATE,
        )
        self.user.profile.watched.add(self.project, private)
        self.viewer = User.objects.create_user(username="count-viewer")
        context = self.notification_context()
        self.assertEqual(context["notification_watched_count"], 1)
        self.assertEqual(context["notification_watched_projects"], [self.project])

    def test_result_target_summaries(self) -> None:
        targets: list[Project | Component | Translation] = [
            Project(pk=index, slug=f"target-{index}", name=f"Target {index}")
            for index in range(1, 7)
        ]
        for count in (1, 5, 6):
            with self.subTest(count=count):
                context = self.notification_context()
                context.update(
                    {
                        "notification_debug_target": self.project,
                        "notification_page": NotificationDebugger.get_target_page(
                            self.project, self.viewer, None
                        ),
                        "notification_results": [
                            NotificationExplanation(
                                RepositoryNotification, "", targets=targets[:count]
                            )
                        ],
                    }
                )
                html = self.render_notifications(context)
                for obj in targets[:count]:
                    if count > 5:
                        self.assertNotIn(f'href="{obj.get_absolute_url()}"', html)
                    else:
                        self.assertIn(f'href="{obj.get_absolute_url()}"', html)
                if count > 5:
                    self.assertIn("6 targets on this page", html)
                self.assertNotIn("<details>", html)

    def test_rendered_lists_have_valid_children(self) -> None:
        self.user.profile.watched.add(self.project)
        self.user.profile.languages.add(self.get_translation().language)
        self.subscribe()
        self.subscribe(NotificationScope.SCOPE_COMPONENT, component=self.component)
        context = self.notification_context(notification_target=self.project.slug)
        html = self.render_notifications(context)
        elements = [parse_html(html)]
        lists = 0
        while elements:
            element = elements.pop()
            if element.name in {"ul", "ol"}:
                lists += 1
                for child in element.children:
                    self.assertIsInstance(child, Element)
                    self.assertIn(child.name, {"li", "script", "template", "style"})
            elements.extend(
                child for child in element.children if isinstance(child, Element)
            )
        self.assertGreater(lists, 2)

    def test_large_component_bounds_translation_work(self) -> None:
        languages = Language.objects.bulk_create(
            [
                Language(name=f"Debug {index}", code=f"debug-{index}")
                for index in range(200)
            ]
        )
        original = self.get_translation()
        translations = []
        for language in languages:
            translation = copy(original)
            translation.pk = None
            translation.language = language
            translation.language_code = language.code
            translations.append(translation)
        Translation.objects.bulk_create(translations)
        debugger = NotificationDebugger(self.user)
        with (
            patch.object(debugger, "explain", wraps=debugger.explain) as explain,
            patch.object(
                Translation, "from_db", wraps=Translation.from_db
            ) as load_translation,
        ):
            results, page = debugger.inspect(self.component, self.viewer, None)
        self.assertEqual(len(page.object_list), 50)
        self.assertEqual(explain.call_count, 50 * len(NOTIFICATIONS))
        self.assertEqual(load_translation.call_count, 49)
        self.assertEqual(
            page.paginator.count, 1 + self.component.translation_set.count()
        )
        self.assertTrue(all(len(result.targets) <= 50 for result in results))
        actual: list[tuple[type[Component | Translation], int]] = []
        for number in page.paginator.page_range:
            current = debugger.get_target_page(self.component, self.viewer, str(number))
            self.assertLessEqual(len(current.object_list), 50)
            actual.extend((type(obj), obj.pk) for obj in current)
        expected = [
            (Component, self.component.pk),
            *[
                (Translation, pk)
                for pk in self.component.translation_set.order_by("pk").values_list(
                    "pk", flat=True
                )
            ],
        ]
        self.assertEqual(actual, expected)
