# Copyright © Christian Köberl
# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re

from django.urls import reverse

from weblate.auth.models import User
from weblate.trans.models import Project
from weblate.trans.tests.test_views import ViewTestCase


class ProjectTokenTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save()
        self.access_url = reverse("manage-access", kwargs=self.kw_project) + "#api"

    def create_token(self):
        self.make_manager()
        response = self.client.post(
            reverse("create-project-token", kwargs=self.kw_project),
            {"full_name": "Test Token", "date_expires": "2999-12-31"},
            follow=True,
        )
        self.assertContains(response, 'data-clipboard-message="Token copied')
        html = response.content.decode("utf-8")
        result = re.search(r'data-clipboard-value="(\w+)"', html)
        self.assertIsNotNone(result)
        return result.group(1)

    def delete_token(self) -> None:
        token = User.objects.filter(is_bot=True).get()
        response = self.client.post(
            reverse("delete-user", kwargs=self.kw_project),
            {"user": token.username},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)

    def test_create_token(self) -> None:
        """Managers should be able to create new tokens."""
        token = self.create_token()

        self.assertIsNotNone(token)
        self.assertGreaterEqual(len(token), 10)

    def test_use_token(self) -> None:
        """Create a new token, logout and use the token for API access."""
        token = self.create_token()
        self.client.logout()

        response = self.client.get(
            reverse("api:project-detail", kwargs={"slug": self.project.slug}),
            headers={"authorization": f"Token {token}"},
        )

        self.assertEqual(response.data["slug"], self.project.slug)

    def test_revoke_token(self) -> None:
        """Create a token revoke it, check that usage is not allowed."""
        token = self.create_token()
        self.delete_token()
        self.client.logout()

        response = self.client.get(
            reverse("api:project-detail", kwargs={"slug": self.project.slug}),
            headers={"authorization": f"Token {token}"},
        )

        self.assertEqual(response.status_code, 401)

    def test_use_token_write(self) -> None:
        """Use the token for API write."""
        token = self.create_token()
        self.client.logout()
        unit = self.get_unit()

        response = self.client.patch(
            reverse("api:unit-detail", kwargs={"pk": unit.pk}),
            {"state": "20", "target": ["Test translation"]},
            content_type="application/json",
            headers={"authorization": f"Token {token}"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["target"], ["Test translation\n"])
