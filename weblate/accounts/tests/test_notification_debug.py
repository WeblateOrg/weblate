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
from django.urls import reverse
from django.utils.translation import override

from weblate.accounts.models import Subscription
from weblate.accounts.notification_debug import (
    NotificationDebugger,
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
from weblate.accounts.views import UserNotifications
from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.trans.models import Category, Component, Project, Translation
from weblate.trans.models.component import ComponentLink
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
            reverse("user_notifications", kwargs={"user": self.user.username}),
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

    def test_multiple_watched_projects_do_not_duplicate_subscriptions(self) -> None:
        projects = Project.objects.bulk_create(
            [
                Project(
                    name=f"Watched {index}",
                    slug=f"watched-{index}",
                    web="https://example.com/",
                )
                for index in range(3)
            ]
        )
        self.user.profile.watched.add(self.project, *projects)
        self.project.add_user(self.user, "Administration")
        other = self.subscribe()
        watched = self.subscribe(NotificationScope.SCOPE_WATCHED)
        admin = self.subscribe(NotificationScope.SCOPE_ADMIN)
        result = self.explain()
        self.assertEqual(result.subscription, admin)
        self.assertEqual(result.overridden, [watched, other])
        handler = RepositoryNotification([], user_ids=[self.user.pk])
        self.assertEqual(
            handler.filter_subscriptions(self.project), [admin, watched, other]
        )

    def test_language_filter(self) -> None:
        translation = self.component.translation_set.get(language__code="cs")
        self.subscribe(notification=NewStringNotificaton.get_name())
        self.user.profile.languages.clear()
        result = self.explain(NewStringNotificaton, translation)
        self.assertIsNotNone(result.subscription)
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
        self.assertContains(
            response, f'id="overview__notification-subscription-{subscription.pk}"'
        )
        self.assertContains(response, "Operation was performed in the repository")
        self.assertEqual(
            {
                result.notification
                for result in response.context["notification_results"]
            },
            {RepositoryNotification},
        )

    def test_groups_and_languages(self) -> None:
        self.subscribe()
        self.user.profile.watched.add(self.project)
        language = self.component.translation_set.get(language__code="cs").language
        self.user.profile.languages.add(language)
        response = self.client.get(
            reverse("user_notifications", kwargs={"user": self.user.username})
        )
        self.assertEqual(list(response.context["notification_languages"]), [language])
        self.assertIn(self.project, response.context["notification_watched_projects"])
        group = response.context["notification_subscription_groups"][0]
        self.assertIsNone(group["target"])
        self.assertNotContains(response, "RepositoryNotification")
        with override("cs"):
            self.assertNotEqual(NotificationScope.SCOPE_PROJECT.label, "Project")

    def test_subscription_groups_by_target(self) -> None:
        global_subscription = self.subscribe()
        project_subscription = self.subscribe(
            NotificationScope.SCOPE_PROJECT, project=self.project
        )
        other_project = Project.objects.create(
            name="Other subscriptions",
            slug="other-subscriptions",
            web="https://example.com/",
        )
        other_subscription = self.subscribe(
            NotificationScope.SCOPE_PROJECT, project=other_project
        )
        component_subscription = self.subscribe(
            NotificationScope.SCOPE_COMPONENT, component=self.component, onetime=True
        )
        context = self.notification_context()
        groups = context["notification_subscription_groups"]
        self.assertEqual(len(groups), 4)
        self.assertEqual(
            {
                tuple(row.pk for row in group["subscriptions"]): group["target"]
                for group in groups
            },
            {
                (global_subscription.pk,): None,
                (project_subscription.pk,): self.project,
                (other_subscription.pk,): other_project,
                (component_subscription.pk,): self.component,
            },
        )
        html = self.render_notifications(context)
        self.assertIn("One-time", html)
        self.assertEqual(html.count('scope="rowgroup"'), 4)

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
                    reverse("user_notifications", kwargs={"user": self.user.username}),
                    {"notification_target": path},
                )
                self.assertEqual(response.status_code, 200, response.headers)
                self.assertTrue(response.context["notification_form"].errors)
                self.assertNotIn("notification_results", response.context)
        self.assertNotContains(response, "<script>alert(")

    def test_self_access(self) -> None:
        self.client.force_login(self.user)
        self.assertEqual(self.debug().status_code, 200)
        response = self.client.get(reverse("profile"))
        self.assertContains(
            response, reverse("user_notifications", kwargs={"user": self.user.username})
        )

    def test_permission_required(self) -> None:
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("user_notifications", kwargs={"user": self.viewer.username})
        )
        self.assertEqual(response.status_code, 403)
        self.client.logout()
        self.assertEqual(self.debug().status_code, 302)

    def test_case_insensitive_username_access(self) -> None:
        self.client.force_login(self.user)
        for user, status in ((self.user, 200), (self.viewer, 403)):
            with self.subTest(user=user.username):
                response = self.client.get(
                    reverse(
                        "user_notifications", kwargs={"user": user.username.upper()}
                    )
                )
                self.assertEqual(response.status_code, status)

    def test_admin_link(self) -> None:
        response = self.client.get(self.user.get_absolute_url())
        self.assertContains(
            response, reverse("user_notifications", kwargs={"user": self.user.username})
        )
        self.assertNotIn("notification_results", response.context)

    def test_matching_subscriptions_only(self) -> None:
        response = self.debug()
        self.assertEqual(response.context["notification_results"], [])
        self.assertContains(response, "No matching subscriptions in this scope.")
        self.subscribe(frequency=NotificationFrequency.FREQ_NONE)
        response = self.debug()
        self.assertContains(response, "Disabled by the effective subscription.")
        self.assertEqual(
            {
                result.notification
                for result in response.context["notification_results"]
            },
            {RepositoryNotification},
        )

    def test_blocked_matches_remain_visible(self) -> None:
        self.subscribe(notification=NewStringNotificaton.get_name())
        response = self.debug(f"{self.project.slug}/{self.component.slug}/cs")
        self.assertEqual(len(response.context["notification_results"]), 1)
        self.assertContains(response, "notification languages")
        self.user.is_active = False
        self.user.save()
        response = self.debug()
        self.assertTrue(response.context["notification_results"])
        self.assertContains(
            response, "Inactive users and bots do not receive notifications."
        )

    def test_diagnostic_matching_does_not_change_delivery(self) -> None:
        subscription = self.subscribe(notification=NewStringNotificaton.get_name())
        handler = NewStringNotificaton([], user_ids=[self.user.pk])
        translation = self.component.translation_set.get(language__code="cs")
        self.user.profile.languages.clear()
        args = (None, self.project, self.component, translation, None)
        self.assertEqual(
            list(handler.get_scope_subscriptions(*args, include_ineligible=True)),
            [subscription],
        )
        self.assertEqual(list(handler.get_scope_subscriptions(*args)), [])
        self.user.is_bot = True
        self.user.save()
        repository_handler = RepositoryNotification([], user_ids=[self.user.pk])
        self.subscribe()
        repository_args = (None, self.project, self.component, None, None)
        self.assertTrue(
            list(
                repository_handler.get_scope_subscriptions(
                    *repository_args, include_ineligible=True
                )
            )
        )
        self.assertEqual(
            list(repository_handler.get_scope_subscriptions(*repository_args)), []
        )

    def test_overview_respects_viewer_access(self) -> None:
        self.subscribe(NotificationScope.SCOPE_COMPONENT, component=self.component)
        with patch.object(
            Component.objects, "filter_access", return_value=Component.objects.none()
        ):
            context = self.notification_context()
        self.assertEqual(context["notification_subscription_groups"], [])

    def test_uniform_scope_settings(self) -> None:
        subscription = self.subscribe()
        response = self.debug()
        results = response.context["notification_results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].subscription, subscription)
        self.assertEqual(results[0].exceptions, [])
        self.assertEqual(response.context["notification_summary"].component_count, 1)
        self.assertContains(response, "Inherited project settings")
        self.assertNotContains(response, "Inspected targets")

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
        self.assertEqual(response.context["notification_summary"].component_count, 1)

    def test_empty_category(self) -> None:
        Category.objects.bulk_create(
            [Category(project=self.project, name="Empty", slug="empty")]
        )
        response = self.debug(f"{self.project.slug}/empty")
        self.assertContains(response, "No accessible components or translations")
        self.assertTrue(response.context["notification_summary"].empty)

    def test_summary_covers_all_components_and_ignores_pagination(self) -> None:
        components = []
        for index in range(75):
            component = copy(self.component)
            component.pk = None
            component.slug = f"notification-{index}"
            component.name = f"Notification {index}"
            components.append(component)
        Component.objects.bulk_create(components)
        inherited = self.subscribe()
        for component in components:
            self.subscribe(
                NotificationScope.SCOPE_COMPONENT,
                component=component,
                frequency=NotificationFrequency.FREQ_NONE,
            )
        response = self.debug()
        result = response.context["notification_results"][0]
        self.assertEqual(result.subscription, inherited)
        self.assertEqual(response.context["notification_summary"].component_count, 76)
        self.assertEqual(len(result.exceptions), 1)
        exception = result.exceptions[0]
        self.assertEqual(exception.count, 75)
        self.assertIsNone(exception.subscription_id)
        self.assertEqual(exception.examples, components[:5])
        self.assertContains(response, "Different settings in 75 components.")
        self.assertContains(response, "Inspect example components:")
        self.assertNotIn("notification_page", response.context)
        second = self.debug(page="2", limit="1")
        self.assertEqual(
            response.context["notification_summary"],
            second.context["notification_summary"],
        )
        self.assertNotContains(second, "Showing targets")

    def test_inaccessible_target(self) -> None:
        with patch.object(User, "check_access_component", side_effect=PermissionDenied):
            response = self.debug(f"{self.project.slug}/{self.component.slug}")
        self.assertContains(
            response, "The target does not exist or you cannot access it."
        )
        self.assertNotIn("notification_results", response.context)

    @patch("weblate.accounts.notification_debug.NOTIFICATION_COMPONENT_LIMIT", 1)
    def test_summary_component_limit(self) -> None:
        self.subscribe()
        self.assertEqual(
            self.debug().context["notification_summary"].component_count, 1
        )
        component = copy(self.component)
        component.pk = None
        component.slug = "extra"
        component.name = "Extra"
        Component.objects.bulk_create([component])
        with (
            patch.object(NotificationDebugger, "explain") as explain,
            patch.object(Component, "from_db", wraps=Component.from_db) as load,
        ):
            response = self.debug()
        explain.assert_not_called()
        load.assert_not_called()
        self.assertContains(response, "This scope is too large to check.")
        self.assertNotIn("notification_results", response.context)
        self.assertEqual(
            response.context["notification_form"]
            .errors.as_data()["notification_target"][0]
            .code,
            "notification_scope_too_large",
        )
        response = self.debug(f"{self.project.slug}/{self.component.slug}")
        self.assertEqual(response.context["notification_summary"].component_count, 1)
        Component.objects.filter(pk=component.pk).update(restricted=True)
        viewer = User.objects.create_user(username="scope-viewer")
        summary = NotificationDebugger(self.user).inspect(self.project, viewer)
        self.assertEqual(summary.component_count, 1)

    @patch("weblate.accounts.notification_debug.NOTIFICATION_PROJECT_LIMIT", 1)
    def test_summary_source_project_limit(self) -> None:
        project = Project.objects.create(
            name="Linked scope", slug="linked-scope", web="https://example.com/"
        )
        ComponentLink.objects.bulk_create(
            [ComponentLink(component=self.component, project=project)]
        )
        with patch.object(NotificationDebugger, "explain") as explain:
            response = self.debug(project.slug)
        explain.assert_not_called()
        self.assertContains(response, "This scope is too large to check.")
        self.assertNotIn("notification_results", response.context)

    def test_descendants_require_viewer_access(self) -> None:
        Component.objects.filter(pk=self.component.pk).update(restricted=True)
        self.subscribe(NotificationScope.SCOPE_COMPONENT, component=self.component)
        viewer = User.objects.create_user(username="limited-viewer")
        summary = NotificationDebugger(self.user).inspect(self.project, viewer)
        self.assertEqual(summary.component_count, 0)
        self.assertEqual(summary.results, [])

    def test_component_override_does_not_apply_to_project(self) -> None:
        project = self.subscribe(NotificationScope.SCOPE_PROJECT, project=self.project)
        component = self.subscribe(
            NotificationScope.SCOPE_COMPONENT,
            component=self.component,
            frequency=NotificationFrequency.FREQ_NONE,
        )
        response = self.debug()
        results = response.context["notification_results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].subscription, project)
        self.assertEqual(results[0].exceptions[0].outcome.subscription, component)
        self.assertEqual(results[0].exceptions[0].examples, [self.component])
        self.assertEqual(results[0].exceptions[0].subscription_id, component.pk)
        url = reverse("user_notifications", kwargs={"user": self.user.username})
        self.assertContains(
            response, f"{url}?notification_target=test/test#notifications"
        )

    def test_component_only_subscription(self) -> None:
        subscription = self.subscribe(
            NotificationScope.SCOPE_COMPONENT, component=self.component
        )
        response = self.debug()
        self.assertContains(response, "No inherited subscription.")
        result = response.context["notification_results"][0]
        self.assertIsNone(result.subscription)
        self.assertEqual(result.exceptions[0].outcome.subscription, subscription)
        self.assertEqual(result.exceptions[0].count, 1)

    def test_subject_access_restriction_is_an_exception(self) -> None:
        self.subscribe()
        Component.objects.filter(pk=self.component.pk).update(restricted=True)
        self.component.refresh_from_db()
        with patch.object(self.user, "can_access_component", return_value=False):
            summary = NotificationDebugger(self.user).inspect(self.project, self.viewer)
        self.assertEqual(
            summary.results[0].exceptions[0].outcome.reason,
            "The user cannot access this target.",
        )

    def test_linked_components_use_their_own_project_settings(self) -> None:
        project = Project.objects.create(
            name="Linked project", slug="linked-project", web="https://example.com/"
        )
        category = Category(
            project=project, name="Linked category", slug="linked-category"
        )
        Category.objects.bulk_create([category])
        ComponentLink.objects.bulk_create(
            [
                ComponentLink(
                    component=self.component, project=project, category=category
                )
            ]
        )
        inherited = self.subscribe(NotificationScope.SCOPE_PROJECT, project=project)
        actual = self.subscribe(
            NotificationScope.SCOPE_PROJECT,
            project=self.project,
            frequency=NotificationFrequency.FREQ_NONE,
        )
        for target in (project, category):
            with self.subTest(target=target):
                summary = NotificationDebugger(self.user).inspect(target, self.viewer)
                self.assertEqual(summary.component_count, 1)
                self.assertEqual(summary.results[0].subscription, inherited)
                self.assertEqual(
                    summary.results[0].exceptions[0].outcome.subscription, actual
                )
                self.assertEqual(
                    summary.results[0].exceptions[0].examples, [self.component]
                )
        response = self.debug(project.slug)
        self.assertContains(
            response, "Shared components use subscriptions from their original project"
        )
        self.assertEqual(
            response.context["notification_results"][0].exceptions[0].shared_count, 1
        )
        actual.delete()
        response = self.debug(project.slug)
        self.assertContains(
            response,
            "These components have no matching subscription, so this notification will not be sent.",
        )
        self.assertNotContains(response, "Delivery details")
        Component.objects.filter(pk=self.component.pk).update(restricted=True)
        viewer = User.objects.create_user(username="linked-viewer")
        summary = NotificationDebugger(self.user).inspect(category, viewer)
        self.assertTrue(summary.empty)
        self.assertEqual(summary.results, [])

    def test_broad_language_rules_and_exact_translation_checks(self) -> None:
        self.subscribe(notification=NewStringNotificaton.get_name())
        self.subscribe(notification=NewCommentNotificaton.get_name())
        self.user.profile.languages.clear()
        broad = NotificationDebugger(self.user).inspect(self.project, self.viewer)
        comment = next(
            result
            for result in broad.results
            if result.notification is NewCommentNotificaton
        )
        self.assertIn(
            "Source-string comments ignore notification languages; other comments require a matching language.",
            comment.conditions,
        )
        exact = NotificationDebugger(self.user).inspect(
            self.get_translation(), self.viewer
        )
        self.assertTrue(
            all("notification languages" in result.reason for result in exact.results)
        )
        source = self.component.source_translation
        exact = NotificationDebugger(self.user).inspect(source, self.viewer)
        comment = next(
            result
            for result in exact.results
            if result.notification is NewCommentNotificaton
        )
        self.assertIn("Eligible", comment.reason)

    def test_one_time_settings_are_distinct_exceptions(self) -> None:
        self.subscribe()
        other = copy(self.component)
        other.pk = None
        other.slug = "other"
        other.name = "Other"
        Component.objects.bulk_create([other])
        self.subscribe(
            NotificationScope.SCOPE_COMPONENT, component=self.component, onetime=True
        )
        self.subscribe(NotificationScope.SCOPE_COMPONENT, component=other)
        summary = NotificationDebugger(self.user).inspect(self.project, self.viewer)
        self.assertEqual(len(summary.results[0].exceptions), 2)

    def test_translation_debug_renders_notification_names(self) -> None:
        self.subscribe()
        response = self.debug(f"{self.project.slug}/{self.component.slug}/cs")
        self.assertContains(response, "Operation was performed in the repository")
        self.assertFalse(response.context["notification_summary"].broad)
        self.assertEqual(response.context["notification_results"][0].exceptions, [])

    def notification_context(self, **params):
        view = UserNotifications()
        view.object = self.user
        view.request = cast(
            "AuthenticatedHttpRequest",
            self.factory.get(
                reverse("user_notifications", kwargs={"user": self.user.username}),
                params,
            ),
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

    def test_rendered_lists_have_valid_children(self) -> None:
        self.user.profile.watched.add(self.project)
        self.user.profile.languages.add(self.get_translation().language)
        self.subscribe()
        self.subscribe(NotificationScope.SCOPE_COMPONENT, component=self.component)
        context = self.notification_context(notification_target=self.project.slug)
        html = self.render_notifications(context)
        elements: list[tuple[Element, str | None]] = [(parse_html(html), None)]
        lists = 0
        while elements:
            element, parent = elements.pop()
            if element.name == "li":
                self.assertIsNotNone(parent)
                self.assertIn(parent, {"ul", "ol", "menu"})
            if element.name in {"ul", "ol"}:
                lists += 1
                for child in element.children:
                    self.assertIsInstance(child, Element)
                    self.assertIn(child.name, {"li", "script", "template", "style"})
            elements.extend(
                (child, element.name)
                for child in element.children
                if isinstance(child, Element)
            )
        self.assertGreaterEqual(lists, 2)

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
        self.subscribe()
        for target in (self.component, self.project):
            with self.subTest(target=target):
                debugger = NotificationDebugger(self.user)
                with (
                    patch.object(
                        debugger, "explain", wraps=debugger.explain
                    ) as explain,
                    patch.object(
                        Translation, "from_db", wraps=Translation.from_db
                    ) as load_translation,
                ):
                    summary = debugger.inspect(target, self.viewer)
                self.assertEqual(summary.component_count, 1)
                self.assertEqual(len(summary.results), 1)
                self.assertEqual(
                    explain.call_count,
                    len(NOTIFICATIONS) * (2 if target == self.project else 1),
                )
                load_translation.assert_not_called()
