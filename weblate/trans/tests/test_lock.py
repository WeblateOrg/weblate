# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for locking."""

from django.urls import reverse

from weblate.trans.models.component import Component
from weblate.trans.tests.test_views import ViewTestCase


class LockTest(ViewTestCase):
    def setUp(self):
        super().setUp()

        # Need extra power
        self.user.is_superuser = True
        self.user.save()

    def assert_component_locked(self):
        component = Component.objects.get(
            slug=self.component.slug, project__slug=self.project.slug
        )
        self.assertTrue(component.locked)
        response = self.client.get(reverse("component", kwargs=self.kw_component))
        self.assertContains(
            response,
            "The translation is temporarily closed for contributions due "
            "to maintenance, please come back later.",
        )

    def assert_component_not_locked(self):
        component = Component.objects.get(
            slug=self.component.slug, project__slug=self.project.slug
        )
        self.assertFalse(component.locked)
        response = self.client.get(reverse("component", kwargs=self.kw_component))
        self.assertNotContains(
            response,
            "The translation is temporarily closed for contributions due "
            "to maintenance, please come back later.",
        )

    def test_component(self):
        response = self.client.post(reverse("lock_component", kwargs=self.kw_component))
        redirect_url = "{}#repository".format(
            reverse("component", kwargs=self.kw_component)
        )
        self.assertRedirects(response, redirect_url)
        self.assert_component_locked()

        response = self.client.post(
            reverse("unlock_component", kwargs=self.kw_component)
        )
        self.assertRedirects(response, redirect_url)
        self.assert_component_not_locked()

    def test_project(self):
        response = self.client.post(reverse("lock_project", kwargs=self.kw_project))
        redirect_url = "{}#repository".format(
            reverse("project", kwargs=self.kw_project)
        )
        self.assertRedirects(response, redirect_url)
        self.assert_component_locked()

        response = self.client.get(reverse("component", kwargs=self.kw_component))
        self.assertContains(
            response,
            "The translation is temporarily closed for contributions due "
            "to maintenance, please come back later.",
        )

        response = self.client.post(reverse("unlock_project", kwargs=self.kw_project))
        self.assertRedirects(response, redirect_url)
        self.assert_component_not_locked()
