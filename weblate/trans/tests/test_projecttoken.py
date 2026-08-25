# Copyright © Christian Köberl
# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re

from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token

from weblate.auth.models import User, setup_project_groups
from weblate.lang.models import Language
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Project
from weblate.trans.tasks import project_removal
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.utils.files import remove_tree


class ProjectTokenTest(FixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save()
        self.access_url = f"{reverse('manage-access', kwargs=self.kw_project)}#api"

    def create_token(self, date_expires: str = "2999-12-31"):
        self.make_manager()
        response = self.client.post(
            reverse("create-project-token", kwargs=self.kw_project),
            {"full_name": "Test Token", "date_expires": date_expires},
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
        if not project.defined_groups.exists():
            setup_project_groups(sender=Project, instance=project, created=False)
        return project

    def create_attacker(self):
        project = self.create_additional_project(name="Attacker", slug="attacker")
        project.access_control = Project.ACCESS_PRIVATE
        project.save()
        attacker = User.objects.create_user(
            "attacker", "attacker@example.org", "testpassword"
        )
        project.add_user(attacker, "Administration")
        client = self.client_class()
        self.assertTrue(client.login(username="attacker", password="testpassword"))
        return project, attacker, client

    def test_create_token(self) -> None:
        """Managers should be able to create new tokens."""
        token = self.create_token()

        self.assertIsNotNone(token)
        self.assertGreaterEqual(len(token), 10)

    def test_create_token_expiring_today(self) -> None:
        """Tokens expiring today should be valid until the end of the day."""
        today = timezone.localdate()
        token_key = self.create_token(today.isoformat())
        token_user = self.get_token_user(token_key)

        expires = timezone.localtime(token_user.date_expires)
        self.assertEqual(expires.date(), today)
        self.assertEqual(expires.hour, 23)
        self.assertEqual(expires.minute, 59)
        self.assertEqual(expires.second, 59)
        self.assertEqual(expires.microsecond, 999999)

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
        token_user = self.get_token_user(token)
        username = token_user.username
        self.delete_token(token)
        token_user.refresh_from_db()

        self.assertFalse(token_user.is_active)
        self.assertTrue(token_user.username.startswith("deleted-"))
        self.assertFalse(token_user.groups.exists())
        change = self.project.change_set.get(action=ActionEvents.REMOVE_USER)
        self.assertEqual(change.details["username"], username)

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

    def test_revoke_foreign_token_denied(self) -> None:
        """Project administrators can not revoke another project's token."""
        token_key = self.create_token()
        token_user = self.get_token_user(token_key)
        username = token_user.username
        attacker_project, attacker, attacker_client = self.create_attacker()

        self.assertTrue(attacker.has_perm("project.permissions", attacker_project))
        self.assertFalse(attacker.has_perm("project.permissions", self.project))
        self.assertFalse(attacker.has_perm("user.edit"))

        response = attacker_client.post(
            reverse("delete-user", kwargs={"project": attacker_project.slug}),
            {"user": username},
            follow=True,
        )

        self.assertContains(response, "Could not find any such user.")
        self.assertTrue(Token.objects.filter(key=token_key).exists())
        token_user.refresh_from_db()
        self.assertEqual(token_user.username, username)
        self.assertTrue(token_user.is_active)
        self.assertTrue(
            token_user.groups.filter(defining_project=self.project).exists()
        )
        self.assertFalse(
            token_user.groups.filter(defining_project=attacker_project).exists()
        )
        self.assertFalse(
            token_user.auditlog_set.filter(activity="token-removed").exists()
        )
        self.assertFalse(
            attacker_project.change_set.filter(action=ActionEvents.REMOVE_USER).exists()
        )

    def test_foreign_token_team_assignment_denied(self) -> None:
        """Project administrators can not attach another project's token."""
        token_key = self.create_token()
        token_user = self.get_token_user(token_key)
        attacker_project, _attacker, attacker_client = self.create_attacker()
        admin_group = attacker_project.defined_groups.get(name="Administration")

        response = attacker_client.post(
            reverse("set-groups", kwargs={"project": attacker_project.slug}),
            {"user": token_user.username, "groups": [admin_group.pk]},
            follow=True,
        )

        self.assertContains(response, "Could not find any such user.")
        self.assertTrue(Token.objects.filter(key=token_key).exists())
        self.assertFalse(
            token_user.groups.filter(defining_project=attacker_project).exists()
        )
        self.assertTrue(
            token_user.groups.filter(defining_project=self.project).exists()
        )

    def test_revoke_shared_token_detaches_project(self) -> None:
        """Removing a shared token keeps it active for its other projects."""
        token_key = self.create_token()
        token_user = self.get_token_user(token_key)
        username = token_user.username
        second_project = self.create_additional_project(name="Other", slug="other")
        second_project.access_control = Project.ACCESS_PRIVATE
        second_project.save()
        second_project.add_user(token_user, "Administration", allow_bot=True)

        response = self.client.post(
            reverse("delete-user", kwargs=self.kw_project),
            {"user": username},
            follow=True,
        )

        self.assertContains(response, "Token has been removed from this project.")
        token_user.refresh_from_db()
        self.assertEqual(token_user.username, username)
        self.assertTrue(token_user.is_active)
        self.assertTrue(Token.objects.filter(key=token_key).exists())
        self.assertFalse(
            token_user.groups.filter(defining_project=self.project).exists()
        )
        self.assertTrue(
            token_user.groups.filter(defining_project=second_project).exists()
        )
        self.assertFalse(
            token_user.auditlog_set.filter(activity="token-removed").exists()
        )
        change = self.project.change_set.get(action=ActionEvents.REMOVE_USER)
        self.assertEqual(change.details["username"], username)

        token_client = self.client_class()
        token_response = token_client.get(
            reverse("api:project-detail", kwargs={"slug": second_project.slug}),
            headers={"authorization": f"Token {token_key}"},
        )
        self.assertEqual(token_response.status_code, 200)

    def test_revoke_internal_bot_denied(self) -> None:
        """Project access management can not remove internal bots."""
        self.make_manager()
        internal_bot = User.objects.create_user(
            "addon:security-test",
            "addon-security-test@example.org",
            is_active=False,
            is_bot=True,
        )
        admin_group = self.project.defined_groups.get(name="Administration")
        internal_bot.groups.add(admin_group)

        response = self.client.post(
            reverse("delete-user", kwargs=self.kw_project),
            {"user": internal_bot.username},
            follow=True,
        )

        self.assertContains(response, "Could not find any such user.")
        internal_bot.refresh_from_db()
        self.assertEqual(internal_bot.username, "addon:security-test")
        self.assertTrue(internal_bot.groups.filter(pk=admin_group.pk).exists())

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

    def test_limited_token_membership_badge(self) -> None:
        """Project token memberships display language limits."""
        token_key = self.create_token()
        token_user = self.get_token_user(token_key)
        czech = Language.objects.get(code="cs")
        admin_group = self.project.defined_groups.get(name="Administration")
        membership = token_user.team_memberships.get(group=admin_group)
        membership.limit_languages.set([czech])

        response = self.client.get(reverse("manage-access", kwargs=self.kw_project))

        self.assertInHTML(
            f'<span class="badge text-bg-secondary">{admin_group} (cs)</span>',
            response.content.decode(),
        )

    def test_project_removal_cleans_up_tokens(self) -> None:
        """Project removal should remove associated project tokens."""
        token_key = self.create_token()
        token_user = self.get_token_user(token_key)
        project_name = self.project.name

        project_removal.run(self.project.pk, self.user.pk, backup=False)

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
        second_project.add_user(token_user, "Administration", allow_bot=True)

        project_removal.run(self.project.pk, self.user.pk, backup=False)

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
