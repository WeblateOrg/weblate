# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for locking."""

from django.urls import reverse

from weblate.trans.models.component import Component
from weblate.trans.tests.test_views import ViewTestCase


class LockTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()

        # Need extra power
        self.user.is_superuser = True
        self.user.save()

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
