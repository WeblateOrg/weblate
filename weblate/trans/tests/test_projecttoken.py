# Copyright © Christian Köberl
# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re

from django.urls import reverse
from rest_framework.authtoken.models import Token

from weblate.auth.models import setup_project_groups
from weblate.trans.models import Project
from weblate.trans.tasks import actual_project_removal
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.utils.files import remove_tree


class ProjectTokenTest(FixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save()
        self.access_url = f"{reverse('manage-access', kwargs=self.kw_project)}#api"

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

    def get_token_user(self, token_key):
        """Get the User associated with a token key."""
        return Token.objects.get(key=token_key).user

    def delete_token(self, token_key) -> None:
        token_user = self.get_token_user(token_key)
        response = self.client.post(
            reverse("delete-user", kwargs=self.kw_project),
            {"user": token_user.username},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)

    def create_additional_project(
        self, name: str = "Other", slug: str = "other"
    ) -> Project:
        project = Project.objects.create(
            name=name,
            slug=slug,
            web="https://nonexisting.weblate.org/",
        )
        self.addCleanup(remove_tree, project.full_path, True)
        return project

    def test_create_token(self) -> None:
        """Managers should be able to create new tokens."""
        token = self.create_token()

        self.assertIsNotNone(token)
        self.assertGreaterEqual(len(token), 10)

    def test_create_token_audit(self) -> None:
        """Creating a token should create an audit log entry."""
        token_key = self.create_token()
        token_user = self.get_token_user(token_key)

        audit = token_user.auditlog_set.get(activity="token-created")

        self.assertEqual(audit.params["project"], self.project.name)
        self.assertEqual(audit.params["username"], self.user.username)
        self.assertEqual(
            audit.get_extra_message(), f"Triggered by {self.user.username}."
        )

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
        self.delete_token(token)
        self.client.logout()

        response = self.client.get(
            reverse("api:project-detail", kwargs={"slug": self.project.slug}),
            headers={"authorization": f"Token {token}"},
        )

        self.assertEqual(response.status_code, 401)

    def test_revoke_token_audit(self) -> None:
        """Manual token removal should create token-specific audit."""
        token_key = self.create_token()
        token_user = self.get_token_user(token_key)

        self.delete_token(token_key)

        audit = token_user.auditlog_set.get(activity="token-removed")
        self.assertEqual(
            audit.params,
            {"project": self.project.name, "username": self.user.username},
        )
        self.assertEqual(
            audit.get_extra_message(), f"Triggered by {self.user.username}."
        )

    def test_remove_all_groups_token(self) -> None:
        """Removing all teams from a token should not be allowed."""
        token_key = self.create_token()
        token_user = self.get_token_user(token_key)
        # Verify the token is currently visible on the access page
        response = self.client.get(reverse("manage-access", kwargs=self.kw_project))
        self.assertContains(response, token_user.username)

        # Try to remove all groups from the token
        response = self.client.post(
            reverse("set-groups", kwargs=self.kw_project),
            {"user": token_user.username},
            follow=True,
        )
        # Verify error message is shown
        self.assertContains(
            response, "At least one team is required for a project token."
        )
        # The token should still have groups
        self.assertTrue(
            token_user.groups.filter(defining_project=self.project).exists()
        )
        # The token should still be visible on the access page
        response = self.client.get(reverse("manage-access", kwargs=self.kw_project))
        self.assertContains(response, token_user.username)

    def test_project_removal_cleans_up_tokens(self) -> None:
        """Project removal should remove associated project tokens."""
        token_key = self.create_token()
        token_user = self.get_token_user(token_key)
        project_name = self.project.name

        actual_project_removal(self.project.pk, self.user.pk)

        self.assertFalse(Project.objects.filter(pk=self.project.pk).exists())
        token_user.refresh_from_db()
        self.assertFalse(token_user.is_active)
        self.assertFalse(Token.objects.filter(key=token_key).exists())

        audit = token_user.auditlog_set.get(activity="token-removed")
        self.assertEqual(
            audit.params,
            {"project": project_name, "username": self.user.username},
        )
        self.assertEqual(
            audit.get_extra_message(), f"Triggered by {self.user.username}."
        )

    def test_project_removal_keeps_tokens_with_other_projects(self) -> None:
        """Project removal should not delete tokens still used by another project."""
        token_key = self.create_token()
        token_user = self.get_token_user(token_key)
        second_project = self.create_additional_project(name="Other", slug="other")
        second_project.access_control = Project.ACCESS_PRIVATE
        second_project.save()
        if not second_project.defined_groups.exists():
            setup_project_groups(sender=Project, instance=second_project, created=False)
        second_project.add_user(token_user, "Administration")

        actual_project_removal(self.project.pk, self.user.pk)

        token_user.refresh_from_db()
        self.assertTrue(token_user.is_active)
        self.assertTrue(Token.objects.filter(key=token_key).exists())
        self.assertTrue(
            token_user.groups.filter(defining_project=second_project).exists()
        )
        self.assertFalse(
            token_user.auditlog_set.filter(activity="token-removed").exists()
        )

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
