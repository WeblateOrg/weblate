# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
import time
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.authtoken.models import Token

from weblate.accounts.utils import (
    SESSION_SECOND_FACTOR_TIMESTAMP,
    SESSION_SENSITIVE_FACTOR_GRANT,
)
from weblate.auth.models import Group, Permission, Role, User, setup_project_groups
from weblate.auth.tasks import disable_expired
from weblate.lang.models import Language
from weblate.trans.defines import USERNAME_LENGTH
from weblate.trans.models import Project
from weblate.trans.tasks import project_removal
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.utils.change_origin import acting_user_context
from weblate.utils.files import remove_tree
from weblate.wladmin.forms import (
    SiteTokenCreateForm,
    SiteTokenGroupForm,
    sitewide_teams_queryset,
)
from weblate.workspaces.models import WORKSPACE_OWNERS_GROUP, Workspace


class SiteWideTokenTest(FixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save()
        self.users_group = Group.objects.get(name="Users", defining_project=None)
        self.managers_group = Group.objects.get(name="Managers", defining_project=None)
        self.monitoring_group = Group.objects.create(name="Monitoring")

    def grant_global_permissions(self, *permissions: str) -> None:
        role_name = "Site token admin role:" + ",".join(sorted(permissions))
        role, _created = Role.objects.get_or_create(name=role_name)
        permission_objects = list(Permission.objects.filter(codename__in=permissions))
        self.assertEqual(
            {permission.codename for permission in permission_objects},
            set(permissions),
        )
        role.permissions.set(permission_objects)
        group_name = "Site token admin team:" + ",".join(sorted(permissions))
        group, _created = Group.objects.get_or_create(name=group_name)
        group.roles.set([role])
        self.user.groups.add(group)
        self.user.clear_permissions_cache()

    def make_site_admin(self) -> None:
        self.grant_global_permissions("management.use", "user.view", "user.edit")

    def token_api_client(self):
        """Client without a browser session for token-authenticated API calls."""
        return self.client_class()

    def create_token(
        self,
        *,
        full_name: str = "Test Token",
        date_expires: str = "2999-12-31",
        teams: list[Group] | None = None,
        follow: bool = True,
    ):
        self.make_site_admin()
        if teams is None:
            teams = [self.monitoring_group]
        data: dict[str, object] = {
            "full_name": full_name,
            "teams": [team.pk for team in teams],
        }
        if date_expires is not None:
            data["date_expires"] = date_expires
        response = self.client.post(
            reverse("create-site-token"),
            data,
            follow=follow,
        )
        if follow:
            self.assertContains(response, 'data-clipboard-message="Token copied')
            content = response.content.decode("utf-8")
            result = re.search(r'data-clipboard-value="(\w+)"', content)
            self.assertIsNotNone(result)
            return result.group(1)
        return response

    def get_token_user(self, token_key: str) -> User:
        return Token.objects.get(key=token_key).user

    def delete_token(self, token_key: str):
        token_user = self.get_token_user(token_key)
        return self.client.post(
            reverse("delete-site-token"),
            {"user": token_user.username},
            follow=True,
        )

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

    def create_project_token(self, project: Project | None = None) -> str:
        project = project or self.project
        self.make_manager()
        if project != self.project:
            project.add_user(self.user, "Administration")
        response = self.client.post(
            reverse("create-project-token", kwargs={"project": project.slug}),
            {"full_name": "Project Token", "date_expires": "2999-12-31"},
            follow=True,
        )
        self.assertContains(response, 'data-clipboard-message="Token copied')
        content = response.content.decode("utf-8")
        result = re.search(r'data-clipboard-value="(\w+)"', content)
        self.assertIsNotNone(result)
        return result.group(1)

    def test_create_token(self) -> None:
        token = self.create_token(teams=[self.monitoring_group])
        token_user = self.get_token_user(token)

        self.assertTrue(token.startswith("wls_"))
        self.assertTrue(token_user.username.startswith("sitebot-"))
        self.assertEqual(
            list(token_user.groups.values_list("name", flat=True)),
            ["Monitoring"],
        )
        self.assertFalse(token_user.groups.filter(pk=self.users_group.pk).exists())

        response = self.client.get(reverse("manage-api-tokens"))
        self.assertContains(response, "API access")
        self.assertContains(response, "Create site-wide token")
        self.assertNotContains(response, "Personal API key")
        self.assertContains(response, token_user.full_name)

        audit = token_user.auditlog_set.get(activity="token-created")
        self.assertEqual(audit.params.get("method"), "site")
        self.assertNotIn("project", audit.params)
        self.assertEqual(audit.params["username"], self.user.username)
        self.assertEqual(audit.get_message(), "Site-wide API token was created.")

        # Collision suffix for the same name
        second = self.create_token(teams=[self.monitoring_group])
        second_user = self.get_token_user(second)
        self.assertTrue(second_user.username.startswith("sitebot-"))
        self.assertNotEqual(token_user.username, second_user.username)

        # Normal user tokens stay wlu_
        self.assertTrue(self.user.auth_token.key.startswith("wlu_"))

    def test_create_token_long_name_truncates_username(self) -> None:
        long_name = "a" * 150
        token = self.create_token(full_name=long_name, teams=[self.monitoring_group])
        token_user = self.get_token_user(token)

        self.assertEqual(token_user.full_name, long_name)
        self.assertLessEqual(len(token_user.username), USERNAME_LENGTH)
        self.assertTrue(token_user.username.startswith("sitebot-"))

    def test_site_token_mutations_require_unexpired_verification(self) -> None:
        token = self.create_token()
        token_user = self.get_token_user(token)
        group_count = token_user.groups.count()
        token_count = Token.objects.count()
        manage_url = reverse("manage-api-tokens")

        session = self.client.session
        session[SESSION_SENSITIVE_FACTOR_GRANT]["time"] -= 601
        session.save()

        create_payload = {
            "full_name": "Expired verification",
            "date_expires": "2999-12-31",
            "teams": [self.monitoring_group.pk],
        }
        url = reverse("create-site-token")
        response = self.client.post(url, create_payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            urlparse(response["Location"]).path,
            reverse("first-factor-verify"),
        )
        self.assertEqual(
            parse_qs(urlparse(response["Location"]).query)["next"],
            [manage_url],
        )

        self.assertEqual(Token.objects.count(), token_count)
        token_user.refresh_from_db()
        self.assertEqual(token_user.groups.count(), group_count)
        self.assertTrue(Token.objects.filter(key=token).exists())

    def test_create_site_token_requires_recent_second_factor(self) -> None:
        self.make_site_admin()
        TOTPDevice.objects.create(user=self.user, confirmed=True)
        token_count = Token.objects.count()
        url = reverse("create-site-token")
        payload = {
            "full_name": "Test Token",
            "date_expires": "2999-12-31",
            "teams": [self.monitoring_group.pk],
        }

        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("2fa-login", kwargs={"backend": "totp"}),
            response["Location"],
        )
        self.assertEqual(Token.objects.count(), token_count)

        session = self.client.session
        session[SESSION_SECOND_FACTOR_TIMESTAMP] = {
            "user": self.user.pk,
            "time": int(time.time()),
        }
        session.save()
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Token.objects.count(), token_count + 1)

    def test_site_token_create_checks_permission_before_verification(self) -> None:
        self.user.groups.clear()
        self.user.clear_permissions_cache()
        self.grant_global_permissions("management.use", "user.view")
        session = self.client.session
        session.pop(SESSION_SENSITIVE_FACTOR_GRANT)
        session.save()

        response = self.client.post(
            reverse("create-site-token"),
            {
                "full_name": "Denied",
                "date_expires": "2999-12-31",
                "teams": [self.monitoring_group.pk],
            },
        )
        self.assertEqual(response.status_code, 403)

    def test_create_requires_team(self) -> None:
        self.make_site_admin()
        response = self.client.post(
            reverse("create-site-token"),
            {"full_name": "No Team", "date_expires": "2999-12-31"},
            follow=True,
        )
        self.assertContains(
            response, "At least one team is required for a site-wide token."
        )
        self.assertFalse(
            User.objects.filter(
                is_bot=True, username__startswith="sitebot-", full_name="No Team"
            ).exists()
        )

    def test_workspace_teams_excluded(self) -> None:
        workspace = Workspace.objects.create(name="Token workspace")
        owners = workspace.setup_groups()[WORKSPACE_OWNERS_GROUP]

        self.assertNotIn(owners, sitewide_teams_queryset())
        self.assertIn(self.monitoring_group, sitewide_teams_queryset())

        create_form = SiteTokenCreateForm()
        self.assertNotIn(owners, create_form.fields["teams"].queryset)

        self.make_site_admin()
        response = self.client.post(
            reverse("create-site-token"),
            {
                "full_name": "Workspace Team Token",
                "date_expires": "2999-12-31",
                "teams": [owners.pk],
            },
            follow=True,
        )
        self.assertContains(response, "Select a valid choice")
        self.assertFalse(
            User.objects.filter(
                is_bot=True,
                username__startswith="sitebot-",
                full_name="Workspace Team Token",
            ).exists()
        )

        token = self.create_token()
        token_user = self.get_token_user(token)
        response = self.client.get(
            reverse("js-site-token-groups", kwargs={"user_id": token_user.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, f'value="{owners.pk}"')

        edit_form = SiteTokenGroupForm(
            initial={"user": token_user.username, "groups": token_user.groups.all()}
        )
        self.assertNotIn(owners, edit_form.fields["groups"].queryset)

    def test_create_token_expiring_today(self) -> None:
        today = timezone.localdate()
        token_key = self.create_token(date_expires=today.isoformat())
        token_user = self.get_token_user(token_key)

        expires = timezone.localtime(token_user.date_expires)
        self.assertEqual(expires.date(), today)
        self.assertEqual(expires.hour, 23)
        self.assertEqual(expires.minute, 59)
        self.assertEqual(expires.second, 59)
        self.assertEqual(expires.microsecond, 999999)

    def test_create_token_blank_expiry(self) -> None:
        token_key = self.create_token(date_expires="")
        token_user = self.get_token_user(token_key)
        self.assertIsNone(token_user.date_expires)

    def test_create_token_past_expiry_rejected(self) -> None:
        self.make_site_admin()
        past = (timezone.localdate() - timedelta(days=1)).isoformat()
        response = self.client.post(
            reverse("create-site-token"),
            {
                "full_name": "Past Token",
                "date_expires": past,
                "teams": [self.monitoring_group.pk],
            },
            follow=True,
        )
        self.assertContains(response, "Expiry cannot be in the past.")
        self.assertFalse(
            User.objects.filter(is_bot=True, full_name="Past Token").exists()
        )

    def test_expired_site_token_removed_by_disable_expired(self) -> None:
        token = self.create_token()
        token_user = self.get_token_user(token)
        self.assertTrue(token_user.groups.exists())

        token_user.date_expires = timezone.now() - timedelta(hours=1)
        token_user.save(update_fields=["date_expires"])

        disable_expired()
        token_user.refresh_from_db()

        self.assertTrue(token_user.username.startswith("deleted-"))
        self.assertFalse(token_user.groups.exists())
        self.assertFalse(Token.objects.filter(key=token).exists())
        self.assertFalse(
            token_user.auditlog_set.filter(activity="disabled-expiry").exists()
        )
        audit = token_user.auditlog_set.get(activity="token-removed")
        self.assertEqual(audit.params.get("method"), "site")

        response = self.token_api_client().get(
            reverse("api:metrics"),
            headers={"authorization": f"Token {token}"},
        )
        self.assertEqual(response.status_code, 401)

        self.make_site_admin()
        response = self.client.get(reverse("manage-api-tokens"))
        self.assertNotContains(response, token_user.full_name)

    def test_scope_across_projects(self) -> None:
        token = self.create_token(teams=[self.monitoring_group])
        token_user = self.get_token_user(token)
        unit = self.get_unit()
        original_target = unit.target

        token_client = self.token_api_client()
        for header in (f"Token {token}", f"Bearer {token}"):
            response = token_client.get(
                reverse("api:metrics"),
                headers={"authorization": header},
            )
            self.assertEqual(response.status_code, 200)

        response = token_client.patch(
            reverse("api:unit-detail", kwargs={"pk": unit.pk}),
            {"state": "20", "target": ["Should fail"]},
            content_type="application/json",
            headers={"authorization": f"Token {token}"},
        )
        # No team roles: unit is hidden (404) or edit is denied (403).
        self.assertIn(response.status_code, {403, 404})
        unit.refresh_from_db()
        self.assertEqual(unit.target, original_target)

        second = self.create_additional_project()
        second.access_control = Project.ACCESS_PRIVATE
        self.enterContext(acting_user_context(self.user))
        second.save()
        second_component = self.create_po(name="Other", project=second)
        second_unit = second_component.translation_set.get(
            language_code="cs"
        ).unit_set.get(source__startswith="Hello, world!\n")

        token_user.add_team(None, self.managers_group)

        for edit_unit, label in (
            (unit, "first"),
            (second_unit, "second"),
        ):
            response = token_client.patch(
                reverse("api:unit-detail", kwargs={"pk": edit_unit.pk}),
                {"state": "20", "target": [f"Edited {label}"]},
                content_type="application/json",
                headers={"authorization": f"Token {token}"},
            )
            self.assertEqual(response.status_code, 200, response.content)

        project_token = self.create_project_token()
        self.assertTrue(project_token.startswith("wlp_"))
        project_client = self.token_api_client()
        response = project_client.patch(
            reverse("api:unit-detail", kwargs={"pk": unit.pk}),
            {"state": "20", "target": ["Project token ok"]},
            content_type="application/json",
            headers={"authorization": f"Token {project_token}"},
        )
        self.assertEqual(response.status_code, 200)

        response = project_client.patch(
            reverse("api:unit-detail", kwargs={"pk": second_unit.pk}),
            {"state": "20", "target": ["Should fail"]},
            content_type="application/json",
            headers={"authorization": f"Token {project_token}"},
        )
        self.assertIn(response.status_code, {403, 404})

        second.access_control = Project.ACCESS_PUBLIC
        second.save()
        response = project_client.patch(
            reverse("api:unit-detail", kwargs={"pk": second_unit.pk}),
            {"state": "20", "target": ["Still denied"]},
            content_type="application/json",
            headers={"authorization": f"Token {project_token}"},
        )
        self.assertIn(response.status_code, {403, 404})

    def test_edit_teams(self) -> None:
        token = self.create_token(teams=[self.monitoring_group])
        token_user = self.get_token_user(token)
        czech = Language.objects.get(code="cs")

        response = self.client.get(
            reverse("js-site-token-groups", kwargs={"user_id": token_user.pk})
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Users", content)
        self.assertIn("Managers", content)
        self.assertIn("Monitoring", content)
        self.assertNotIn(self.project.defined_groups.first().name, content)

        # Reject clearing all teams
        response = self.client.post(
            reverse("set-site-token-groups"),
            {"user": token_user.username},
            follow=True,
        )
        self.assertContains(
            response, "At least one team is required for a site-wide token."
        )
        self.assertTrue(token_user.groups.filter(pk=self.monitoring_group.pk).exists())

        # Add Managers with language limit
        limit_field = SiteTokenGroupForm.get_limit_languages_field(self.managers_group)
        response = self.client.post(
            reverse("set-site-token-groups"),
            {
                "user": token_user.username,
                "groups": [self.monitoring_group.pk, self.managers_group.pk],
                limit_field: [czech.code],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(token_user.groups.filter(pk=self.managers_group.pk).exists())
        membership = token_user.team_memberships.get(group=self.managers_group)
        self.assertEqual(
            list(membership.limit_languages.values_list("code", flat=True)),
            ["cs"],
        )

        response = self.client.get(reverse("manage-api-tokens"))
        self.assertInHTML(
            f'<span class="badge text-bg-secondary">{self.managers_group} (cs)</span>',
            response.content.decode(),
        )

        self.assertTrue(
            token_user.auditlog_set.filter(
                activity="sitewide-team-add",
                params__team=self.managers_group.name,
            ).exists()
        )
        self.assertTrue(
            token_user.auditlog_set.filter(
                activity="sitewide-team-change",
                params__team=self.managers_group.name,
            ).exists()
            or membership.limit_languages.exists()
        )

        # Remove monitoring, keep managers
        response = self.client.post(
            reverse("set-site-token-groups"),
            {
                "user": token_user.username,
                "groups": [self.managers_group.pk],
                limit_field: [czech.code],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(token_user.groups.filter(pk=self.monitoring_group.pk).exists())
        self.assertTrue(
            token_user.auditlog_set.filter(
                activity="sitewide-team-remove",
                params__team=self.monitoring_group.name,
            ).exists()
        )

    def test_prefix_collision_with_project_slug_site(self) -> None:
        site_project = self.create_additional_project(name="Site", slug="site")
        site_project.access_control = Project.ACCESS_PRIVATE
        self.enterContext(acting_user_context(self.user))
        site_project.save()
        project_token = self.create_project_token(site_project)
        project_user = self.get_token_user(project_token)

        self.assertTrue(project_user.username.startswith("bot-site-"))
        self.assertTrue(project_token.startswith("wlp_"))

        site_token = self.create_token()
        site_user = self.get_token_user(site_token)
        response = self.client.get(reverse("manage-api-tokens"))
        self.assertContains(response, site_user.full_name)
        self.assertNotContains(response, project_user.full_name)

    def test_revoke_token(self) -> None:
        token = self.create_token()
        token_user = self.get_token_user(token)

        response = self.client.get(reverse("manage-api-tokens"))
        self.assertNotContains(response, "generate")
        self.assertNotContains(response, "new secret")

        response = self.delete_token(token)
        self.assertContains(response, "Site-wide API token has been removed.")
        token_user.refresh_from_db()

        self.assertFalse(token_user.is_active)
        self.assertTrue(token_user.username.startswith("deleted-"))
        self.assertFalse(token_user.groups.exists())
        self.assertFalse(Token.objects.filter(key=token).exists())

        audit = token_user.auditlog_set.get(activity="token-removed")
        self.assertEqual(audit.params.get("method"), "site")
        self.assertNotIn("project", audit.params)
        self.assertEqual(audit.params["username"], self.user.username)
        self.assertEqual(audit.get_message(), "Site-wide API token was removed.")

        response = self.token_api_client().get(
            reverse("api:metrics"),
            headers={"authorization": f"Token {token}"},
        )
        self.assertEqual(response.status_code, 401)

        # Deleting underlying user revokes a second token
        second = self.create_token(full_name="Second Token")
        second_user = self.get_token_user(second)
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(
            second_user.get_absolute_url(),
            {"remove_user": "1"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Token.objects.filter(key=second).exists())

        # No dedicated create/revoke REST endpoints
        self.assertEqual(self.client.post("/api/site-tokens/", {}).status_code, 404)

    def test_wrong_account_denied(self) -> None:
        site_token = self.create_token()
        site_user = self.get_token_user(site_token)
        project_token = self.create_project_token()
        project_user = self.get_token_user(project_token)

        internal_bot = User.objects.create_user(
            "addon:security-test",
            "addon-security-test@example.org",
            is_active=False,
            is_bot=True,
        )

        response = self.client.post(
            reverse("delete-site-token"),
            {"user": internal_bot.username},
            follow=True,
        )
        self.assertContains(response, "Could not find any such user.")

        response = self.client.post(
            reverse("delete-site-token"),
            {"user": project_user.username},
            follow=True,
        )
        self.assertContains(response, "Could not find any such user.")
        self.assertTrue(Token.objects.filter(key=project_token).exists())

        # Project admin cannot delete site-wide token from project page
        response = self.client.post(
            reverse("delete-user", kwargs=self.kw_project),
            {"user": site_user.username},
            follow=True,
        )
        self.assertContains(response, "Could not find any such user.")
        site_user.refresh_from_db()
        self.assertTrue(site_user.is_active)
        self.assertTrue(Token.objects.filter(key=site_token).exists())

        # Cannot attach site-wide token to a project team
        admin_group = self.project.defined_groups.get(name="Administration")
        response = self.client.post(
            reverse("set-groups", kwargs=self.kw_project),
            {"user": site_user.username, "groups": [admin_group.pk]},
            follow=True,
        )
        self.assertContains(response, "Could not find any such user.")
        self.assertFalse(
            site_user.groups.filter(defining_project=self.project).exists()
        )

    def test_unavailable_on_hosted_weblate(self) -> None:
        token = self.create_token()
        token_user = self.get_token_user(token)

        payloads = (
            ("GET", reverse("manage-api-tokens"), {}),
            (
                "GET",
                reverse("js-site-token-groups", kwargs={"user_id": token_user.pk}),
                {},
            ),
            (
                "POST",
                reverse("create-site-token"),
                {
                    "full_name": "Denied",
                    "date_expires": "2999-12-31",
                    "teams": [self.monitoring_group.pk],
                },
            ),
            ("POST", reverse("delete-site-token"), {"user": token_user.username}),
            (
                "POST",
                reverse("set-site-token-groups"),
                {
                    "user": token_user.username,
                    "groups": [self.monitoring_group.pk],
                },
            ),
        )

        with override_settings(OFFER_HOSTING=True):
            for method, url, data in payloads:
                response = self.client.generic(method, url, data)
                self.assertEqual(response.status_code, 404)

            response = self.client.get(reverse("manage"))
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, reverse("manage-api-tokens"))

    def test_who_can_see_it(self) -> None:
        token = self.create_token()
        token_user = self.get_token_user(token)

        response = self.client_class().get(reverse("manage-api-tokens"))
        self.assertEqual(response.status_code, 403)

        # Drop previous site-admin groups for permission matrix
        self.user.groups.clear()
        self.user.clear_permissions_cache()

        response = self.client.get(reverse("manage-api-tokens"))
        self.assertEqual(response.status_code, 403)

        self.grant_global_permissions("management.use")
        response = self.client.get(reverse("manage-api-tokens"))
        self.assertEqual(response.status_code, 403)

        self.user.groups.clear()
        self.user.clear_permissions_cache()
        self.grant_global_permissions("management.use", "user.view")
        response = self.client.get(reverse("manage-api-tokens"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, token_user.full_name)
        self.assertNotContains(response, "Create site-wide token")

        response = self.client.post(
            reverse("create-site-token"),
            {
                "full_name": "Denied",
                "date_expires": "2999-12-31",
                "teams": [self.monitoring_group.pk],
            },
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            reverse("delete-site-token"),
            {"user": token_user.username},
        )
        self.assertEqual(response.status_code, 403)

        # Without user.view/edit, token is not enumerated in search
        self.user.groups.clear()
        self.user.clear_permissions_cache()
        User.objects.create_user("attacker", "attacker@example.org", "testpassword")
        client = self.client_class()
        self.assertTrue(client.login(username="attacker", password="testpassword"))

        response = client.get(reverse("api:user-list"), {"username": "sitebot-"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            token_user.username,
            {result["username"] for result in response.json()["results"]},
        )
        response = client.get(reverse("api:search"), {"q": token_user.username})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            token_user.username,
            {result["name"] for result in response.json()},
        )
        # Exact API lookup remains available by design
        response = client.get(
            reverse("api:user-detail", kwargs={"username": token_user.username})
        )
        self.assertEqual(response.status_code, 200)

    def test_api_last_team(self) -> None:
        token = self.create_token(teams=[self.monitoring_group])
        token_user = self.get_token_user(token)
        self.user.is_superuser = True
        self.user.save()

        response = self.client.delete(
            reverse("api:user-groups", kwargs={"username": token_user.username}),
            {"group_id": self.monitoring_group.pk},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("At least one team is required", response.content.decode())
        self.assertTrue(token_user.groups.filter(pk=self.monitoring_group.pk).exists())

    def test_project_removal_keeps_site_token(self) -> None:
        token = self.create_token()
        token_user = self.get_token_user(token)
        token_user.add_team(
            None, self.project.defined_groups.get(name="Administration")
        )

        project_removal.run(self.project.pk, self.user.pk, backup=False)

        token_user.refresh_from_db()
        self.assertTrue(token_user.is_active)
        self.assertTrue(Token.objects.filter(key=token).exists())
        self.assertFalse(
            token_user.auditlog_set.filter(activity="token-removed").exists()
        )
