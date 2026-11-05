# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for locking."""

from __future__ import annotations

from django.urls import reverse

from weblate.accounts.notifications import NotificationFrequency
from weblate.auth.models import Group, Permission, Role, User
from weblate.trans.models import Category
from weblate.trans.models.component import Component
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.utils.stats import CategoryLanguage, ProjectLanguage


class LockTest(FixtureTestCase):
    def setUp(self) -> None:
        super().setUp()

        # Need extra power
        self.user.is_superuser = True
        self.user.save()

    def grant_project_lock(self, user: User, *, project_edit: bool = False) -> None:
        role = Role.objects.create(name="Test project lock")
        role.permissions.add(Permission.objects.get(codename="component.lock"))
        if project_edit:
            role.permissions.add(Permission.objects.get(codename="project.edit"))
        group = Group.objects.create(name="Test project lock")
        group.roles.add(role)
        group.projects.add(self.project)
        user.groups.add(group)
        user.clear_permissions_cache()

    def assert_component_locked(self) -> None:
        component = Component.objects.get(
            slug=self.component.slug, project__slug=self.project.slug
        )
        self.assertTrue(component.locked)
        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(
            response,
            "The translation is temporarily closed for contributions due "
            "to maintenance, please come back later.",
        )

    def assert_component_not_locked(self) -> None:
        component = Component.objects.get(
            slug=self.component.slug, project__slug=self.project.slug
        )
        self.assertFalse(component.locked)
        response = self.client.get(self.component.get_absolute_url())
        self.assertNotContains(
            response,
            "The translation is temporarily closed for contributions due "
            "to maintenance, please come back later.",
        )

    def test_component(self) -> None:
        response = self.client.post(reverse("lock", kwargs=self.kw_component))
        redirect_url = f"{self.component.get_absolute_url()}#repository"
        self.assertRedirects(response, redirect_url)
        self.assert_component_locked()

        response = self.client.post(reverse("unlock", kwargs=self.kw_component))
        self.assertRedirects(response, redirect_url)
        self.assert_component_not_locked()

    def test_project(self) -> None:
        response = self.client.post(
            reverse("lock", kwargs={"path": self.project.get_url_path()})
        )
        redirect_url = f"{self.project.get_absolute_url()}#repository"
        self.assertRedirects(response, redirect_url)
        self.assert_component_locked()

        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(
            response,
            "The translation is temporarily closed for contributions due "
            "to maintenance, please come back later.",
        )

        response = self.client.post(
            reverse("unlock", kwargs={"path": self.project.get_url_path()})
        )
        self.assertRedirects(response, redirect_url)
        self.assert_component_not_locked()

    def test_project_lock_skips_restricted_component(self) -> None:
        restricted = self.component
        restricted.restricted = True
        restricted.save(update_fields=["restricted"])
        allowed = self.create_po_new_base(name="Allowed", project=self.project)
        limited = User.objects.create_user("limited-lock", "limited-lock@example.com")
        self.grant_project_lock(limited)
        self.assertTrue(limited.has_perm("component.lock", self.project))
        self.assertFalse(limited.has_perm("component.lock", restricted))
        self.assertTrue(limited.has_perm("component.lock", allowed))

        self.client.force_login(limited)
        url = reverse("lock", kwargs={"path": self.project.get_url_path()})
        self.assertEqual(self.client.post(url).status_code, 302)
        restricted.refresh_from_db()
        allowed.refresh_from_db()
        self.assertFalse(restricted.locked)
        self.assertTrue(allowed.locked)

        unlock_url = reverse("unlock", kwargs={"path": self.project.get_url_path()})
        self.assertEqual(self.client.post(unlock_url).status_code, 302)
        allowed.refresh_from_db()
        self.assertFalse(allowed.locked)

    def test_project_lock_requires_eligible_component(self) -> None:
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])
        limited = User.objects.create_user("limited-lock", "limited-lock@example.com")
        self.grant_project_lock(limited)
        self.client.force_login(limited)

        url = reverse("lock", kwargs={"path": self.project.get_url_path()})
        self.assertEqual(self.client.post(url).status_code, 403)
        self.component.refresh_from_db()
        self.assertFalse(self.component.locked)

    def test_component_only_lock_grant_does_not_authorize_project_path(self) -> None:
        limited = User.objects.create_user(
            "component-lock", "component-lock@example.com"
        )
        role = Role.objects.create(name="Test component lock")
        role.permissions.add(Permission.objects.get(codename="component.lock"))
        group = Group.objects.create(name="Test component lock")
        group.roles.add(role)
        group.components.add(self.component)
        limited.groups.add(group)
        limited.clear_permissions_cache()
        self.assertTrue(limited.has_perm("component.lock", self.component))
        self.assertFalse(limited.has_perm("component.lock", self.project))

        self.client.force_login(limited)
        project_url = reverse("lock", kwargs={"path": self.project.get_url_path()})
        self.assertEqual(self.client.post(project_url).status_code, 403)
        self.component.refresh_from_db()
        self.assertFalse(self.component.locked)

    def test_project_editor_locks_restricted_component(self) -> None:
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])
        editor = User.objects.create_user(
            "project-editor", "project-editor@example.com"
        )
        self.grant_project_lock(editor, project_edit=True)
        self.client.force_login(editor)

        url = reverse("lock", kwargs={"path": self.project.get_url_path()})
        self.assertEqual(self.client.post(url).status_code, 302)
        self.component.refresh_from_db()
        self.assertTrue(self.component.locked)

    def test_locked_component_prevents_translation_removal(self) -> None:
        translation = self.component.translation_set.get(language_code="de")
        category = Category(
            name="Locked category", slug="locked-category", project=self.project
        )
        Category.objects.bulk_create([category])
        self.component.category = category
        self.component.save(update_fields=["category"])
        project_language = ProjectLanguage(self.project, translation.language)
        category_language = CategoryLanguage(category, translation.language)
        self.assertTrue(self.user.has_perm("translation.delete", translation))
        self.assertTrue(self.user.has_perm("translation.delete", project_language))
        self.assertTrue(self.user.has_perm("translation.delete", category_language))

        self.component.locked = True
        self.component.save(update_fields=["locked"])
        self.assertFalse(self.user.has_perm("translation.delete", translation))
        self.assertFalse(self.user.has_perm("translation.delete", project_language))
        self.assertFalse(self.user.has_perm("translation.delete", category_language))
        for item in (translation, project_language, category_language):
            url = reverse("remove", kwargs={"path": item.get_url_path()})
            self.assertEqual(self.client.post(url).status_code, 403)
        self.assertTrue(
            self.component.translation_set.filter(pk=translation.pk).exists()
        )

    def test_lock_notification_subscription_button(self) -> None:
        notify_text = "Get notified when this project is unlocked again"
        unsubscribe_text = "Turn off this notification"
        self.component.locked = True
        self.component.save(update_fields=["locked"])

        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, notify_text)
        self.assertNotContains(response, unsubscribe_text)

        response = self.client.post(
            reverse("subscribe"),
            {"onetime": "LockNotification", "component": self.component.pk},
        )
        self.assertRedirects(
            response,
            f"{reverse('profile')}#notifications",
            fetch_redirect_response=False,
        )
        subscription = self.user.subscription_set.get(
            notification="LockNotification",
            project=self.project,
            component=self.component,
            onetime=True,
        )
        self.assertEqual(subscription.frequency, NotificationFrequency.FREQ_INSTANT)

        response = self.client.get(self.component.get_absolute_url())
        self.assertNotContains(response, notify_text)
        self.assertContains(response, unsubscribe_text)
        self.assertContains(response, reverse("unsubscribe"))

        response = self.client.post(subscription.get_unsubscribe_url())
        self.assertRedirects(
            response,
            f"{reverse('profile')}#notifications",
            fetch_redirect_response=False,
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.frequency, NotificationFrequency.FREQ_NONE)

        response = self.client.get(self.component.get_absolute_url())
        self.assertContains(response, notify_text)
        self.assertNotContains(response, unsubscribe_text)

        response = self.client.post(
            reverse("subscribe"),
            {"onetime": "LockNotification", "component": self.component.pk},
        )
        self.assertRedirects(
            response,
            f"{reverse('profile')}#notifications",
            fetch_redirect_response=False,
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.frequency, NotificationFrequency.FREQ_INSTANT)
