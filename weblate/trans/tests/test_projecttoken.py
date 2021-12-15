import re

from django.urls import reverse

from weblate.trans.models import Project
from weblate.trans.tests.test_views import ViewTestCase


class ProjectTokenTest(ViewTestCase):
    def setUp(self):
        super().setUp()
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save()
        self.access_url = reverse("manage-access", kwargs=self.kw_project) + "#api"

    def create_token(self):
        self.make_manager()
        response = self.client.post(
            reverse("create-project-token", kwargs=self.kw_project),
            {"name": "Test Token", "expires": "2999-12-31", "project": self.project.id},
            follow=True,
        )
        html = response.content.decode("utf-8")
        result = re.search(
            r'data-clipboard-text="(\w+)" data-clipboard-message="Token copied',
            html,
        )
        self.assertIsNotNone(result)
        return result.group(1)

    def delete_token(self):
        response = self.client.get(self.access_url)
        html = response.content.decode("utf-8")
        token_id = re.search(r'name="token" value="([0-9]+)"', html).group(1)
        response = self.client.post(
            reverse("delete-project-token", kwargs=self.kw_project),
            {"token": token_id},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)

    def test_create_token(self):
        """Managers should be able to create new tokens."""
        token = self.create_token()

        self.assertTrue(token is not None)
        self.assertGreaterEqual(len(token), 10)

    def test_use_token(self):
        """Create a new token, logout and use the token for API access."""
        token = self.create_token()
        self.client.logout()

        response = self.client.get(
            reverse("api:project-detail", kwargs={"slug": self.project.slug}),
            **{"HTTP_AUTHORIZATION": f"Token {token}"},
        )

        self.assertEqual(response.data["slug"], self.project.slug)

    def test_revoke_token(self):
        """Create a token revoke it, check that usage is not allowed."""
        token = self.create_token()
        self.delete_token()
        self.client.logout()

        response = self.client.get(
            reverse("api:project-detail", kwargs={"slug": self.project.slug}),
            **{"HTTP_AUTHORIZATION": f"Token {token}"},
        )

        self.assertEqual(response.status_code, 401)
