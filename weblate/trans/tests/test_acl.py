# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for ACL management."""

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.core.exceptions import ValidationError
from django.test.utils import modify_settings, override_settings
from django.urls import reverse
from social_django.models import UserSocialAuth

from weblate.accounts.models import VerifiedEmail
from weblate.auth.models import (
    Group,
    Invitation,
    Role,
    TeamMembership,
    User,
    get_anonymous,
)
from weblate.lang.forms import LimitLanguagesField, validate_language_code
from weblate.lang.models import Language
from weblate.trans.actions import ActionEvents
from weblate.trans.forms import ProjectUserGroupForm
from weblate.trans.models import Change, Comment, Project, Suggestion
from weblate.trans.tasks import (
    cleanup_user_contributions as cleanup_user_contributions_task,
)
from weblate.trans.tasks import (
    revert_user_edits as revert_user_edits_task,
)
from weblate.trans.tests.test_views import FixtureTestCase, RegistrationTestMixin
from weblate.trans.tests.utils import enable_login_required_settings
from weblate.utils.pii import mask_email
from weblate.utils.state import STATE_TRANSLATED

if TYPE_CHECKING:
    from weblate.accounts.models import AuditLog


class ACLTest(FixtureTestCase, RegistrationTestMixin):
    def setUp(self) -> None:
        super().setUp()
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save()
        self.access_url = reverse("manage-access", kwargs=self.kw_project)
        self.translate_url = reverse("translate", kwargs=self.kw_translation)
        self.second_user = User.objects.create_user(
            "seconduser", "noreply@example.org", "testpassword"
        )
        self.admin_group = self.project.defined_groups.get(name="Administration")
        self.translate_group = self.project.defined_groups.get(name="Translate")

    def get_project_user_groups_url(self, user: User) -> str:
        return reverse(
            "js-project-user-groups",
            kwargs={**self.kw_project, "user_id": user.id},
        )

    def add_acl(self) -> None:
        """Add user to ACL."""
        self.project.add_user(self.user, "Translate")

    def test_acl_denied(self) -> None:
        """No access to the project without ACL."""
        response = self.client.get(self.access_url)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(get_anonymous().can_access_project(self.project))

    def test_acl_disable(self) -> None:
        """Test disabling ACL."""
        response = self.client.get(self.access_url)
        self.assertEqual(response.status_code, 404)
        self.project.access_control = Project.ACCESS_PUBLIC
        self.project.save()
        self.assertTrue(get_anonymous().can_access_project(self.project))
        response = self.client.get(self.access_url)
        self.assertEqual(response.status_code, 403)
        response = self.client.get(self.translate_url)
        self.assertContains(response, ' name="save"')

    def test_anonymous_translate_view_checksum_access(self) -> None:
        self.project.access_control = Project.ACCESS_PUBLIC
        self.project.save()
        get_anonymous().clear_permissions_cache()
        unit = self.get_unit()

        response = self.client.get(self.translate_url, {"checksum": unit.checksum})

        self.assertContains(response, ' name="save"')

    def test_acl_protected(self) -> None:
        """Test ACL protected project."""
        response = self.client.get(self.access_url)
        self.assertEqual(response.status_code, 404)
        self.project.access_control = Project.ACCESS_PROTECTED
        self.project.save()
        self.assertTrue(get_anonymous().can_access_project(self.project))
        response = self.client.get(self.access_url)
        self.assertEqual(response.status_code, 403)
        response = self.client.get(self.translate_url)
        self.assertContains(
            response, "Insufficient privileges for saving translations."
        )

    def test_acl(self) -> None:
        """Regular user should not have access to user management."""
        self.add_acl()
        response = self.client.get(self.access_url)
        self.assertEqual(response.status_code, 403)

    def test_edit_acl(self) -> None:
        """Manager should have access to user management."""
        self.add_acl()
        self.make_manager()
        response = self.client.get(self.access_url)
        self.assertContains(response, "Users")

    def test_edit_acl_owner(self) -> None:
        """Owner should have access to user management."""
        self.add_acl()
        self.project.add_user(self.user, "Administration")
        response = self.client.get(self.access_url)
        self.assertContains(response, "Users")

    def test_edit_acl_user_group_form_is_lazy_loaded(self) -> None:
        """Project user team forms are not rendered in every user row."""
        self.project.add_user(self.user, "Administration")
        self.project.add_user(self.second_user, "Translate")
        form_url = self.get_project_user_groups_url(self.second_user)

        response = self.client.get(self.access_url)

        self.assertContains(response, form_url)
        self.assertContains(response, 'id="project-user-groups-modal"')
        self.assertNotContains(response, f'id="edit_user_{self.second_user.id}"')
        self.assertNotContains(response, "project-membership-team-toggle")
        self.assertNotContains(
            response,
            f"id_user_{self.second_user.id}_limit_languages_{self.translate_group.pk}",
        )

    def test_edit_acl_user_group_form_fragment(self) -> None:
        """Project user team form is rendered by the JS endpoint."""
        self.project.add_user(self.user, "Administration")
        self.project.add_user(self.second_user, "Translate")

        response = self.client.get(self.get_project_user_groups_url(self.second_user))

        self.assertContains(response, self.second_user.username)
        self.assertContains(response, "project-membership-team-toggle")
        self.assertContains(
            response,
            f"id_user_{self.second_user.id}_limit_languages_{self.translate_group.pk}",
        )

    def test_edit_acl_user_group_form_fragment_denied(self) -> None:
        """Regular project users can not load team management forms."""
        self.add_acl()
        self.project.add_user(self.second_user, "Translate")

        response = self.client.get(self.get_project_user_groups_url(self.second_user))

        self.assertEqual(response.status_code, 403)

    def test_edit_acl_user_group_form_fragment_project_scope(self) -> None:
        """Team management form is available only for project users."""
        self.project.add_user(self.user, "Administration")
        outside_user = User.objects.create_user(
            "outsideuser", "outside@example.org", "testpassword"
        )

        response = self.client.get(self.get_project_user_groups_url(outside_user))

        self.assertEqual(response.status_code, 404)

    @override_settings(DEFAULT_PAGE_LIMIT=10)
    def test_edit_acl_users_pagination(self) -> None:
        """Project user list should be paginated."""
        self.project.add_user(self.user, "Administration")
        users = []
        for idx in range(11):
            user = User.objects.create_user(
                f"acl-page-{idx:02d}",
                f"acl-page-{idx:02d}@example.org",
                "testpassword",
            )
            self.project.add_user(user, "Translate")
            users.append(user)

        response = self.client.get(self.access_url)

        self.assertContains(response, "acl-page-00")
        self.assertContains(response, "acl-page-09")
        self.assertNotContains(response, "acl-page-10")
        self.assertNotContains(response, f"edit_user_{users[10].id}")
        self.assertContains(response, "?page=2&amp;limit=10#users")

        response = self.client.get(f"{self.access_url}?page=2")

        self.assertContains(response, "acl-page-10")
        self.assertContains(response, self.user.username)
        self.assertNotContains(response, "acl-page-00")

    def add_user(self) -> None:
        self.add_acl()
        self.project.add_user(self.user, "Administration")

        # Add user
        response = self.client.post(
            reverse("add-user", kwargs=self.kw_project),
            {"user": self.second_user.username, "group": self.admin_group.pk},
        )
        self.assertRedirects(response, self.access_url)

        # Ensure user is now listed
        response = self.client.get(self.access_url)
        self.assertContains(response, self.second_user.username)

        # Accept invitation
        invitation = Invitation.objects.get()
        invitation.accept(None, self.second_user)
        self.assertTrue(
            self.second_user.profile.watched.filter(pk=self.project.pk).exists()
        )

        # Ensure user is now listed
        response = self.client.get(self.access_url)
        self.assertContains(response, self.second_user.username)
        invitation_audit = self.second_user.auditlog_set.get(activity="invited")
        self.assertIsNone(invitation_audit.address)

    def test_invite_invalid(self) -> None:
        """Test inviting invalid form."""
        self.project.add_user(self.user, "Administration")
        response = self.client.post(
            reverse("invite-user", kwargs=self.kw_project),
            {"email": "invalid", "group": self.admin_group.pk},
            follow=True,
        )
        self.assertContains(response, "Enter a valid e-mail address.")

    def test_invite_existing(self) -> None:
        """Test inviting existing user."""
        self.project.add_user(self.user, "Administration")
        response = self.client.post(
            reverse("invite-user", kwargs=self.kw_project),
            {"email": self.user.email, "group": self.admin_group.pk},
            follow=True,
        )
        self.assertContains(response, "User invitation e-mail was sent.")
        invitation = Invitation.objects.get()
        # Ensure invitation was mapped to existing user
        self.assertEqual(invitation.user, self.user)

        # check change display is user's username
        change = Project.objects.get(pk=self.project.pk).change_set.get(
            action=ActionEvents.INVITE_USER
        )
        self.assertEqual(change.get_details_display(), self.user.username)

    def test_invite_forms_limit_language_fields(self) -> None:
        """User additions and new-user invitations can specify language limits."""
        self.project.add_user(self.user, "Administration")
        response = self.client.get(self.access_url)

        self.assertEqual(
            list(response.context["invite_user_form"].fields),
            ["user", "group", "limit_languages"],
        )
        self.assertEqual(
            list(response.context["invite_email_form"].fields),
            ["email", "username", "full_name", "group", "limit_languages"],
        )
        self.assertEqual(
            list(response.context["bulk_invite_form"].fields),
            ["group", "emails", "limit_languages"],
        )
        self.assertContains(response, "id_project_add_user_limit_languages")
        self.assertContains(response, "id_project_invite_limit_languages")
        self.assertContains(response, "id_project_bulk_invite_limit_languages")

    def test_limit_languages_form_uses_model_validation(self) -> None:
        language = Language.objects.get(code="cs")
        field = LimitLanguagesField(Language.objects.filter(pk=language.pk))

        # ruff: ignore[private-member-access]
        language_code_field = Language._meta.get_field("code")
        with patch.object(language_code_field, "clean") as clean:
            validate_language_code(language.code)
        clean.assert_called_once_with(language.code, None)

        self.assertEqual(list(field.clean([language.code])), [language])
        for code in (
            "xx/test",
            "cs\x00",
        ):
            with self.assertRaises(ValidationError):
                field.clean([code])

    def test_add_user_limit_languages(self) -> None:
        """Existing-user invitations apply selected language limits."""
        self.add_acl()
        self.project.add_user(self.user, "Administration")
        czech = Language.objects.get(code="cs")
        response = self.client.post(
            reverse("add-user", kwargs=self.kw_project),
            {
                "user": self.second_user.username,
                "group": self.translate_group.pk,
                "limit_languages": [czech.code],
            },
        )

        self.assertRedirects(response, self.access_url)
        invitation = Invitation.objects.get()
        self.assertEqual(
            list(invitation.limit_languages.values_list("code", flat=True)), ["cs"]
        )

        invitation.accept(None, self.second_user)
        membership = TeamMembership.objects.get(
            user=self.second_user, group=self.translate_group
        )
        self.assertEqual(
            list(membership.limit_languages.values_list("code", flat=True)), ["cs"]
        )

    def test_empty_invitation_limit_clears_membership_limit(self) -> None:
        """An invitation without limits makes the resulting membership unrestricted."""
        self.second_user.groups.add(self.translate_group)
        czech = Language.objects.get(code="cs")
        membership = TeamMembership.objects.get(
            user=self.second_user, group=self.translate_group
        )
        membership.limit_languages.set([czech])
        invitation = Invitation.objects.create(
            author=self.user, user=self.second_user, group=self.translate_group
        )

        invitation.accept(None, self.second_user)

        membership.refresh_from_db()
        self.assertFalse(membership.limit_languages.exists())

    @override_settings(REGISTRATION_OPEN=True, REGISTRATION_CAPTCHA=False)
    def test_invite_user_limit_languages(self) -> None:
        """Single new-user invitation applies selected language limits."""
        self.project.add_user(self.user, "Administration")
        czech = Language.objects.get(code="cs")
        response = self.client.post(
            reverse("invite-user", kwargs=self.kw_project),
            {
                "email": "limited@example.com",
                "group": self.translate_group.pk,
                "limit_languages": [czech.code],
            },
            follow=True,
        )

        self.assertContains(response, "User invitation e-mail was sent.")
        invitation = Invitation.objects.get()
        self.assertEqual(
            list(invitation.limit_languages.values_list("code", flat=True)), ["cs"]
        )

        response = self.client.get(self.access_url)
        self.assertContains(response, "(cs)")

        invited_user = User.objects.create_user(
            "limited", "limited@example.com", "testpassword"
        )
        invitation.accept(None, invited_user)
        membership = TeamMembership.objects.get(
            user=invited_user, group=self.translate_group
        )
        self.assertEqual(
            list(membership.limit_languages.values_list("code", flat=True)), ["cs"]
        )

    @override_settings(REGISTRATION_OPEN=True, REGISTRATION_CAPTCHA=False)
    def test_bulk_invite_user_limit_languages(self) -> None:
        """Bulk new-user invitations apply selected language limits."""
        self.project.add_user(self.user, "Administration")
        czech = Language.objects.get(code="cs")
        response = self.client.post(
            reverse("invite-user", kwargs=self.kw_project),
            {
                "emails": "bulk-limited@example.com another-limited@example.com",
                "group": self.translate_group.pk,
                "limit_languages": [czech.code],
            },
            follow=True,
        )

        self.assertContains(response, "2 invitation e-mails were sent.")
        self.assertEqual(Invitation.objects.count(), 2)
        for invitation in Invitation.objects.all():
            self.assertEqual(
                list(invitation.limit_languages.values_list("code", flat=True)), ["cs"]
            )

        invitation = Invitation.objects.get(email="bulk-limited@example.com")
        invited_user = User.objects.create_user(
            "bulk-limited", "bulk-limited@example.com", "testpassword"
        )
        invitation.accept(None, invited_user)
        membership = TeamMembership.objects.get(
            user=invited_user, group=self.translate_group
        )
        self.assertEqual(
            list(membership.limit_languages.values_list("code", flat=True)), ["cs"]
        )

    @override_settings(REGISTRATION_OPEN=True, REGISTRATION_CAPTCHA=False)
    def test_bulk_invite_user(self) -> None:
        """Bulk invite creates invitations and skips invalid addresses."""
        self.project.add_user(self.user, "Administration")
        response = self.client.post(
            reverse("invite-user", kwargs=self.kw_project),
            {
                "emails": (
                    f"{self.user.email}\n"
                    "new@example.com invalid-address new@example.com"
                ),
                "group": self.admin_group.pk,
            },
            follow=True,
        )
        self.assertContains(response, "2 invitation e-mails were sent.")
        self.assertContains(response, "Skipped 2 addresses")
        self.assertContains(response, "invalid-address: Enter a valid e-mail address.")
        self.assertContains(
            response, "new@example.com: duplicate address in the submission"
        )
        self.assertEqual(Invitation.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 2)

        invitation = Invitation.objects.get(user=self.user)
        self.assertEqual(invitation.group, self.admin_group)

        change = Project.objects.get(pk=self.project.pk).change_set.filter(
            action=ActionEvents.INVITE_USER
        )
        self.assertEqual(change.count(), 2)

    @override_settings(REGISTRATION_OPEN=True, REGISTRATION_CAPTCHA=False)
    def test_bulk_invite_skips_pending_invitation(self) -> None:
        """Bulk invite skips equivalent pending invitations."""
        self.project.add_user(self.user, "Administration")
        self.client.post(
            reverse("invite-user", kwargs=self.kw_project),
            {"email": "existing@example.com", "group": self.admin_group.pk},
            follow=True,
        )
        mail.outbox = []

        response = self.client.post(
            reverse("invite-user", kwargs=self.kw_project),
            {
                "emails": "existing@example.com another@example.com",
                "group": self.admin_group.pk,
            },
            follow=True,
        )

        self.assertContains(response, "1 invitation e-mail was sent.")
        self.assertContains(
            response, "existing@example.com: pending invitation already exists"
        )
        self.assertEqual(Invitation.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(REGISTRATION_OPEN=True, REGISTRATION_CAPTCHA=False)
    def test_bulk_invite_keeps_ambiguous_verified_email_email_based(self) -> None:
        """Bulk invite does not bind ambiguous verified e-mails to one user."""
        self.project.add_user(self.user, "Administration")
        first_user = User.objects.create_user(
            "verified-one", "verified-one@example.org", "testpassword"
        )
        second_user = User.objects.create_user(
            "verified-two", "verified-two@example.net", "testpassword"
        )
        first_social = UserSocialAuth.objects.create(
            user=first_user, provider="github", uid="verified-one"
        )
        second_social = UserSocialAuth.objects.create(
            user=second_user, provider="gitlab", uid="verified-two"
        )
        VerifiedEmail.objects.create(
            social=first_social, email="shared-verified@example.com"
        )
        VerifiedEmail.objects.create(
            social=second_social, email="shared-verified@example.com"
        )

        response = self.client.post(
            reverse("invite-user", kwargs=self.kw_project),
            {
                "emails": "shared-verified@example.com",
                "group": self.admin_group.pk,
            },
            follow=True,
        )

        self.assertContains(response, "1 invitation e-mail was sent.")
        invitation = Invitation.objects.get()
        self.assertIsNone(invitation.user)
        self.assertEqual(invitation.email, "shared-verified@example.com")

    @override_settings(
        REGISTRATION_OPEN=True,
        REGISTRATION_CAPTCHA=False,
        REGISTRATION_EMAIL_MATCH=r"^allowed@example\.com$",
    )
    def test_bulk_invite_uses_weblate_email_validation(self) -> None:
        """Bulk invite reuses the same e-mail validation as single invite."""
        self.project.add_user(self.user, "Administration")

        response = self.client.post(
            reverse("invite-user", kwargs=self.kw_project),
            {
                "emails": "blocked@example.com",
                "group": self.admin_group.pk,
            },
            follow=True,
        )

        self.assertContains(response, "No invitations were created.")
        self.assertContains(
            response, "blocked@example.com: This e-mail address is disallowed."
        )
        self.assertEqual(Invitation.objects.count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(REGISTRATION_OPEN=True, REGISTRATION_CAPTCHA=False)
    def test_bulk_invite_clears_email_when_verified_user_resolved(self) -> None:
        """Bulk invite keeps user-bound invitations in the expected either/or state."""
        self.project.add_user(self.user, "Administration")
        invited_user = User.objects.create_user(
            "verified-match", "primary@example.org", "testpassword"
        )
        social = UserSocialAuth.objects.create(
            user=invited_user, provider="github", uid="verified-match"
        )
        VerifiedEmail.objects.create(social=social, email="secondary@example.com")

        response = self.client.post(
            reverse("invite-user", kwargs=self.kw_project),
            {
                "emails": "secondary@example.com",
                "group": self.admin_group.pk,
            },
            follow=True,
        )

        self.assertContains(response, "1 invitation e-mail was sent.")
        invitation = Invitation.objects.get()
        self.assertEqual(invitation.user, invited_user)
        self.assertEqual(invitation.email, "")

    @override_settings(REGISTRATION_OPEN=True, REGISTRATION_CAPTCHA=False)
    def test_bulk_invite_skips_second_address_for_same_resolved_user(self) -> None:
        """Bulk invite avoids duplicate invitations for one resolved account."""
        self.project.add_user(self.user, "Administration")
        invited_user = User.objects.create_user(
            "same-user", "primary@example.org", "testpassword"
        )
        social = UserSocialAuth.objects.create(
            user=invited_user, provider="github", uid="same-user"
        )
        VerifiedEmail.objects.create(social=social, email="secondary@example.com")

        response = self.client.post(
            reverse("invite-user", kwargs=self.kw_project),
            {
                "emails": "primary@example.org secondary@example.com",
                "group": self.admin_group.pk,
            },
            follow=True,
        )

        self.assertContains(response, "1 invitation e-mail was sent.")
        self.assertContains(
            response, "secondary@example.com: pending invitation already exists"
        )
        self.assertEqual(Invitation.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        invitation = Invitation.objects.get()
        self.assertEqual(invitation.user, invited_user)
        self.assertEqual(invitation.email, "")

    @override_settings(REGISTRATION_OPEN=False, REGISTRATION_CAPTCHA=False)
    def test_invite_user_closed(self) -> None:
        self.project.add_user(self.user, "Administration")
        response = self.client.post(
            reverse("invite-user", kwargs=self.kw_project),
            {"email": "user@example.com", "group": self.admin_group.pk},
            follow=True,
        )
        self.assertEqual(response.status_code, 403)

        # It should work for the superuser
        self.user.is_superuser = True
        self.user.save()
        response = self.client.post(
            reverse("invite-user", kwargs=self.kw_project),
            {"email": "user@example.com", "group": self.admin_group.pk},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

    @override_settings(REGISTRATION_OPEN=True, REGISTRATION_CAPTCHA=False)
    def test_invite_user_open(self) -> None:
        """Test inviting user."""
        self.project.add_user(self.user, "Administration")
        response = self.client.post(
            reverse("invite-user", kwargs=self.kw_project),
            {"email": "user@example.com", "group": self.admin_group.pk},
            follow=True,
        )
        # Ensure user invitation is now listed
        self.assertContains(response, "user@example.com")
        self.assertNotContains(response, "example-username")
        # Check invitation mail
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(
            message.subject,
            "[Weblate] testuser has invited you to join the Test project",
        )
        mail.outbox = []

        # Check change display is user's email masked
        change = Project.objects.get(pk=self.project.pk).change_set.get(
            action=ActionEvents.INVITE_USER
        )
        self.assertEqual(change.get_details_display(), mask_email("user@example.com"))

        self.assertEqual(Invitation.objects.count(), 1)

        invitation = Invitation.objects.get()

        # Resend invitation
        response = self.client.post(
            invitation.get_absolute_url(),
            {"action": "resend"},
            follow=True,
        )
        # Check invitation mail
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(
            message.subject,
            "[Weblate] testuser has invited you to join the Test project",
        )
        mail.outbox = []

        user_client = self.client_class()

        # Follow the invitation list
        response = user_client.get(invitation.get_absolute_url(), follow=True)
        self.assertRedirects(response, reverse("register"))
        self.assertContains(response, "user@example.com")
        self.assertContains(response, "You were invited")

        # Perform registration
        response = user_client.post(
            reverse("register"),
            {
                "email": "user@example.com",
                "username": "example-username",
                "fullname": "name",
            },
            follow=True,
        )
        url = self.assert_registration_mailbox()
        response = self.confirm_registration_url(url, user_client, follow=True)

        # Accept terms if using legal
        if "weblate.legal.pipeline.tos_confirm" in settings.SOCIAL_AUTH_PIPELINE:
            response = self.confirm_tos(user_client, response)

        self.assertRedirects(response, reverse("password"))

        # Verify user was added
        response = self.client.get(self.access_url)
        self.assertContains(response, "example-username")

        user = User.objects.get(username="example-username")
        self.assertTrue(user.profile.watched.filter(pk=self.project.pk).exists())

        # Inspect audit log
        audit: AuditLog | None = None
        for current in user.auditlog_set.filter(activity="team-add"):
            if current.params["team"] == "Administration":
                audit = current
                break

        self.assertIsNotNone(
            audit, "Audit log entry for adding to the Administration team not found"
        )
        self.assertEqual(cast("AuditLog", audit).params["username"], self.user.username)

    def remove_user(self) -> None:
        # Remove user
        response = self.client.post(
            reverse("delete-user", kwargs=self.kw_project),
            {"user": self.second_user.username},
        )
        self.assertRedirects(response, self.access_url)

        # Ensure user is now not listed
        response = self.client.get(self.access_url)
        self.assertNotContains(response, self.second_user.username)
        self.assertNotContains(response, self.second_user.email)

    def test_add_acl(self) -> None:
        """Adding and removing users from the ACL project."""
        self.add_user()
        self.remove_user()

    def test_add_owner(self) -> None:
        """Adding and removing owners from the ACL project."""
        self.add_user()
        self.client.post(
            reverse("set-groups", kwargs=self.kw_project),
            {
                "user": self.second_user.username,
                "groups": [self.admin_group.pk],
            },
        )
        self.assertTrue(
            User.objects.all_admins(self.project)
            .filter(username=self.second_user.username)
            .exists()
        )
        self.client.post(
            reverse("set-groups", kwargs=self.kw_project),
            {
                "user": self.second_user.username,
                "groups": [self.translate_group.pk],
            },
        )
        # check group name is included in change details
        change = Project.objects.get(pk=self.project.pk).change_set.get(
            action=ActionEvents.ADD_USER
        )
        self.assertIn(self.translate_group.name, change.get_details_display())

        self.assertFalse(
            User.objects.all_admins(self.project)
            .filter(username=self.second_user.username)
            .exists()
        )
        self.remove_user()

    def test_set_group_limit_languages(self) -> None:
        """Editing ACL groups can set per-membership language limits."""
        self.add_user()
        czech = Language.objects.get(code="cs")
        german = Language.objects.get(code="de")
        self.client.post(
            reverse("set-groups", kwargs=self.kw_project),
            {
                "user": self.second_user.username,
                "groups": [self.translate_group.pk],
                f"limit_languages_{self.translate_group.pk}": [czech.code],
            },
        )

        membership = TeamMembership.objects.get(
            user=self.second_user, group=self.translate_group
        )
        self.assertEqual(
            list(membership.limit_languages.values_list("code", flat=True)), ["cs"]
        )

        response = self.client.get(self.access_url)
        self.assertContains(response, str(self.translate_group))
        self.assertInHTML(
            f'<span class="badge text-bg-secondary">{self.translate_group} (cs)</span>',
            response.content.decode(),
        )

        self.client.post(
            reverse("set-groups", kwargs=self.kw_project),
            {
                "user": self.second_user.username,
                "groups": [self.translate_group.pk],
                f"limit_languages_{self.translate_group.pk}": [german.code],
            },
        )
        membership.refresh_from_db()
        self.assertEqual(
            list(membership.limit_languages.values_list("code", flat=True)), ["de"]
        )
        change = Project.objects.get(pk=self.project.pk).change_set.get(
            action=ActionEvents.USER_ACCESS_CHANGE
        )
        self.assertEqual(
            change.get_details_display(),
            f"{self.second_user.username} ({self.translate_group.name})",
        )
        self.assertEqual(change.details["previous_limit_languages"], ["cs"])
        self.assertEqual(change.details["limit_languages"], ["de"])
        audit = self.second_user.auditlog_set.get(activity="team-change")
        self.assertEqual(audit.params["team"], self.translate_group.name)
        self.assertEqual(audit.params["username"], self.user.username)
        self.assertEqual(audit.params["previous_limit_languages"], ["cs"])
        self.assertEqual(audit.params["limit_languages"], ["de"])

        self.client.post(
            reverse("set-groups", kwargs=self.kw_project),
            {
                "user": self.second_user.username,
                "groups": [self.translate_group.pk],
                f"limit_languages_{self.translate_group.pk}": [german.code],
            },
        )
        self.assertEqual(
            Project.objects.get(pk=self.project.pk)
            .change_set.filter(action=ActionEvents.USER_ACCESS_CHANGE)
            .count(),
            1,
        )

    def test_group_edit_form_plain_dict_selection(self) -> None:
        form = ProjectUserGroupForm(
            self.project,
            data={
                "user": self.second_user.username,
                "groups": [self.translate_group.pk],
            },
        )

        self.assertFalse(
            form.fields[
                ProjectUserGroupForm.get_limit_languages_field(self.translate_group)
            ].disabled
        )
        self.assertTrue(
            form.fields[
                ProjectUserGroupForm.get_limit_languages_field(self.admin_group)
            ].disabled
        )

    def test_delete_owner(self) -> None:
        """Adding and deleting owners from the ACL project."""
        self.add_user()
        self.client.post(
            reverse("set-groups", kwargs=self.kw_project),
            {
                "user": self.second_user.username,
                "groups": [self.admin_group.pk],
            },
        )
        self.remove_user()
        self.assertFalse(
            User.objects.all_admins(self.project)
            .filter(username=self.second_user.username)
            .exists()
        )

    def test_denied_owner_delete(self) -> None:
        """Test that deleting the last owner does not work."""
        self.project.add_user(self.user, "Administration")
        self.client.post(
            reverse("set-groups", kwargs=self.kw_project),
            {
                "user": self.second_user.username,
                "groups": [self.translate_group.pk],
            },
        )
        self.assertTrue(
            User.objects.all_admins(self.project)
            .filter(username=self.user.username)
            .exists()
        )
        self.client.post(
            reverse("set-groups", kwargs=self.kw_project),
            {
                "user": self.user.username,
                "groups": [self.translate_group.pk],
            },
        )
        self.assertTrue(
            User.objects.all_admins(self.project)
            .filter(username=self.user.username)
            .exists()
        )

    def test_nonexisting_user(self) -> None:
        """Test adding non-existing user."""
        self.project.add_user(self.user, "Administration")
        response = self.client.post(
            reverse("add-user", kwargs=self.kw_project),
            {"user": "nonexisting", "group": self.admin_group.pk},
            follow=True,
        )
        self.assertContains(response, "Could not find any such user")

    def test_special_users_denied_project_membership(self) -> None:
        """Test that special users can not be assigned to project teams."""
        self.project.add_user(self.user, "Administration")
        inactive = User.objects.create_user(
            "inactive-acl", "inactive-acl@example.org", "testpassword"
        )
        inactive.is_active = False
        inactive.save()
        users = [get_anonymous(), inactive]

        for user in users:
            response = self.client.post(
                reverse("add-user", kwargs=self.kw_project),
                {"user": user.username, "group": self.admin_group.pk},
                follow=True,
            )
            self.assertContains(response, "can not be assigned to teams")
            self.assertFalse(
                Invitation.objects.filter(user=user, group=self.admin_group).exists()
            )
            self.assertFalse(user.groups.filter(pk=self.admin_group.pk).exists())

            response = self.client.post(
                reverse("set-groups", kwargs=self.kw_project),
                {"user": user.username, "groups": [self.admin_group.pk]},
                follow=True,
            )
            self.assertContains(response, "can not be assigned to teams")
            self.assertFalse(user.groups.filter(pk=self.admin_group.pk).exists())

    def test_acl_groups(self) -> None:
        """Test handling ACL groups."""
        self.project.defined_groups.all().delete()
        self.project.access_control = Project.ACCESS_PUBLIC
        self.project.translation_review = False
        self.project.save()
        self.assertEqual(1, self.project.defined_groups.count())
        self.project.access_control = Project.ACCESS_PROTECTED
        self.project.translation_review = True
        self.project.save()
        self.assertEqual(11, self.project.defined_groups.count())
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.translation_review = True
        self.project.save()
        self.assertEqual(11, self.project.defined_groups.count())
        self.project.access_control = Project.ACCESS_CUSTOM
        self.project.save()
        self.assertEqual(11, self.project.defined_groups.count())
        self.project.access_control = Project.ACCESS_CUSTOM
        self.project.save()
        self.assertEqual(11, self.project.defined_groups.count())
        self.project.defined_groups.all().delete()
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save()
        self.assertEqual(11, self.project.defined_groups.count())
        self.project.delete()

    def test_restricted_component(self) -> None:
        # Make the project public
        self.project.access_control = Project.ACCESS_PUBLIC
        self.project.save()
        # Add user language to ensure the suggestions are shown
        self.user.profile.languages.add(Language.objects.get(code="cs"))

        project_url = self.project.get_absolute_url()
        url = self.component.get_absolute_url()

        # It is shown on the dashboard and accessible
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertContains(self.client.get(reverse("home")), url)
        self.assertContains(self.client.get(project_url), url)

        # Make it restricted
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])

        # It is no longer shown on the dashboard and not accessible
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertNotContains(self.client.get(reverse("home")), url)
        self.assertNotContains(self.client.get(project_url), url)

        # Check superuser can access it
        self.user.is_superuser = True
        self.user.save()
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertContains(self.client.get(reverse("home")), url)
        self.assertContains(self.client.get(project_url), url)

    def test_block_user(self) -> None:
        self.project.add_user(self.user, "Administration")

        # Block user
        response = self.client.post(
            reverse("block-user", kwargs=self.kw_project),
            {"user": self.second_user.username},
        )
        self.assertRedirects(response, self.access_url)
        self.assertEqual(self.project.userblock_set.count(), 1)
        self.assertEqual(self.project.userblock_set.filter(note="").count(), 1)

        # Block user, for second time
        response = self.client.post(
            reverse("block-user", kwargs=self.kw_project),
            {"user": self.second_user.username},
        )
        self.assertRedirects(response, self.access_url)
        self.assertEqual(self.project.userblock_set.count(), 1)

        # Unblock user
        response = self.client.post(
            reverse("unblock-user", kwargs=self.kw_project),
            {"user": self.second_user.username},
        )
        self.assertRedirects(response, self.access_url)
        self.assertEqual(self.project.userblock_set.count(), 0)

        # Block user with a note
        response = self.client.post(
            reverse("block-user", kwargs=self.kw_project),
            {"user": self.second_user.username, "note": "Spamming"},
        )
        self.assertRedirects(response, self.access_url)
        self.assertEqual(self.project.userblock_set.count(), 1)
        self.assertEqual(self.project.userblock_set.filter(note="Spamming").count(), 1)

    def test_block_user_revert_edits(self) -> None:
        self.project.add_user(self.user, "Administration")
        unit = self.get_unit()
        self.change_unit("Nazdar svete!\n", user=self.second_user)

        with patch(
            "weblate.trans.views.acl.revert_user_edits_task.delay",
            return_value=SimpleNamespace(id="task-1"),
        ) as mocked_delay:
            response = self.client.post(
                reverse("block-user", kwargs=self.kw_project),
                {
                    "user": self.second_user.username,
                    "revert_edits": "on",
                },
                follow=True,
            )

        mocked_delay.assert_called_once_with(
            target_user_id=self.second_user.id,
            acting_user_id=self.user.id,
            project_id=self.project.id,
            sitewide=False,
        )
        self.assertContains(
            response, "Reverting edits by seconduser in this project was scheduled."
        )
        unit.refresh_from_db()
        self.assertEqual(unit.target, "Nazdar svete!\n")
        self.assertEqual(unit.state, STATE_TRANSLATED)
        self.assertFalse(
            Change.objects.filter(action=ActionEvents.USER_REVERT).exists()
        )

    def test_block_user_revert_edits_already_blocked(self) -> None:
        self.project.add_user(self.user, "Administration")
        self.client.post(
            reverse("block-user", kwargs=self.kw_project),
            {"user": self.second_user.username},
        )

        with patch(
            "weblate.trans.views.acl.revert_user_edits_task.delay",
            return_value=SimpleNamespace(id="task-3"),
        ) as mocked_delay:
            response = self.client.post(
                reverse("block-user", kwargs=self.kw_project),
                {
                    "user": self.second_user.username,
                    "revert_edits": "on",
                },
                follow=True,
            )

        mocked_delay.assert_called_once_with(
            target_user_id=self.second_user.id,
            acting_user_id=self.user.id,
            project_id=self.project.id,
            sitewide=False,
        )
        self.assertContains(
            response, "Reverting edits by seconduser in this project was scheduled."
        )
        self.assertNotContains(response, "User is already blocked on this project.")

    def test_block_user_cleanup_contributions(self) -> None:
        self.project.add_user(self.user, "Administration")

        with patch(
            "weblate.trans.views.acl.cleanup_user_contributions_task.delay",
            return_value=SimpleNamespace(id="task-cleanup"),
        ) as mocked_delay:
            response = self.client.post(
                reverse("block-user", kwargs=self.kw_project),
                {
                    "user": self.second_user.username,
                    "reject_suggestions": "on",
                    "delete_comments": "on",
                },
                follow=True,
            )

        mocked_delay.assert_called_once_with(
            target_user_id=self.second_user.id,
            acting_user_id=self.user.id,
            project_id=self.project.id,
            sitewide=False,
            reject_suggestions=True,
            delete_comments=True,
        )
        self.assertContains(
            response,
            "Cleaning up contributions by seconduser in this project was scheduled.",
        )

    def test_revert_blocked_user_cleanup_contributions(self) -> None:
        self.project.add_user(self.user, "Administration")
        self.client.post(
            reverse("block-user", kwargs=self.kw_project),
            {"user": self.second_user.username},
        )

        with (
            patch(
                "weblate.trans.views.acl.revert_user_edits_task.delay",
                return_value=SimpleNamespace(id="task-revert"),
            ) as mocked_revert,
            patch(
                "weblate.trans.views.acl.cleanup_user_contributions_task.delay",
                return_value=SimpleNamespace(id="task-cleanup"),
            ) as mocked_cleanup,
        ):
            response = self.client.post(
                reverse("revert-blocked-user-edits", kwargs=self.kw_project),
                {
                    "user": self.second_user.username,
                    "cleanup_user_contributions": "1",
                    "reject_suggestions": "on",
                },
                follow=True,
            )

        mocked_revert.assert_not_called()
        mocked_cleanup.assert_called_once_with(
            target_user_id=self.second_user.id,
            acting_user_id=self.user.id,
            project_id=self.project.id,
            sitewide=False,
            reject_suggestions=True,
            delete_comments=False,
        )
        self.assertContains(
            response,
            "Cleaning up contributions by seconduser in this project was scheduled.",
        )

    def test_revert_blocked_user_cleanup_with_revert_edits(self) -> None:
        self.project.add_user(self.user, "Administration")
        self.client.post(
            reverse("block-user", kwargs=self.kw_project),
            {"user": self.second_user.username},
        )

        with patch(
            "weblate.trans.views.acl.revert_user_edits_task.delay",
            return_value=SimpleNamespace(id="task-revert"),
        ) as mocked_revert:
            response = self.client.post(
                reverse("revert-blocked-user-edits", kwargs=self.kw_project),
                {
                    "user": self.second_user.username,
                    "cleanup_user_contributions": "1",
                    "revert_edits": "on",
                },
                follow=True,
            )

        mocked_revert.assert_called_once_with(
            target_user_id=self.second_user.id,
            acting_user_id=self.user.id,
            project_id=self.project.id,
            sitewide=False,
        )
        self.assertContains(
            response, "Reverting edits by seconduser in this project was scheduled."
        )

    def test_revert_user_edits_task(self) -> None:
        self.project.add_user(self.user, "Administration")
        unit = self.get_unit()
        self.change_unit("Ahoj svete!\n", user=self.user)
        self.change_unit("Nazdar svete!\n", user=self.second_user)
        self.change_unit("Cus svete!\n", user=self.second_user)

        result = revert_user_edits_task(
            target_user_id=self.second_user.id,
            acting_user_id=self.user.id,
            project_id=self.project.id,
        )

        self.assertEqual(
            result,
            {
                "reverted": 1,
                "skipped": 0,
                "skipped_newer": 0,
                "skipped_failed": 0,
            },
        )
        unit.refresh_from_db()
        self.assertEqual(unit.target, "Ahoj svete!\n")
        self.assertEqual(unit.state, STATE_TRANSLATED)

        change = Change.objects.get(action=ActionEvents.USER_REVERT, unit=unit)
        self.assertEqual(change.user, self.user)
        self.assertEqual(change.get_details_display(), self.second_user.username)

    def test_revert_user_edits_task_invalid_old_state(self) -> None:
        self.project.add_user(self.user, "Administration")
        unit = self.get_unit()
        self.change_unit("Ahoj svete!\n", user=self.user)
        self.change_unit("Nazdar svete!\n", user=self.second_user)
        self.change_unit("Cus svete!\n", user=self.second_user)
        change = Change.objects.filter(unit=unit, user=self.second_user).order_by(
            "-timestamp", "-pk"
        )[0]
        change.details["old_state"] = -1
        change.save(update_fields=["details"])

        result = revert_user_edits_task(
            target_user_id=self.second_user.id,
            acting_user_id=self.user.id,
            project_id=self.project.id,
        )

        self.assertEqual(
            result,
            {
                "reverted": 0,
                "skipped": 1,
                "skipped_newer": 0,
                "skipped_failed": 1,
            },
        )
        unit.refresh_from_db()
        self.assertEqual(unit.target, "Cus svete!\n")
        self.assertFalse(
            Change.objects.filter(action=ActionEvents.USER_REVERT).exists()
        )

    def test_block_user_revert_edits_skips_newer_changes(self) -> None:
        self.project.add_user(self.user, "Administration")
        unit = self.get_unit()
        self.change_unit("Nazdar svete!\n", user=self.second_user)
        self.change_unit("Ahoj svete!\n", user=self.user)

        result = revert_user_edits_task(
            target_user_id=self.second_user.id,
            acting_user_id=self.user.id,
            project_id=self.project.id,
        )

        self.assertEqual(
            result,
            {
                "reverted": 0,
                "skipped": 1,
                "skipped_newer": 1,
                "skipped_failed": 0,
            },
        )
        unit.refresh_from_db()
        self.assertEqual(unit.target, "Ahoj svete!\n")
        self.assertEqual(unit.state, STATE_TRANSLATED)
        self.assertFalse(
            Change.objects.filter(action=ActionEvents.USER_REVERT).exists()
        )

    def test_cleanup_user_contributions_task(self) -> None:
        unit = self.get_unit()
        other_user = User.objects.create_user(
            "cleanup-other", "cleanup-other@example.org", "testpassword"
        )
        target_suggestion = Suggestion.objects.create(
            unit=unit, target="Bad suggestion!\n", user=self.second_user
        )
        other_suggestion = Suggestion.objects.create(
            unit=unit, target="Other suggestion!\n", user=other_user
        )
        target_comment = Comment.objects.create(
            unit=unit, comment="Bad comment", user=self.second_user
        )
        other_comment = Comment.objects.create(
            unit=unit, comment="Other comment", user=other_user
        )

        result = cleanup_user_contributions_task(
            target_user_id=self.second_user.id,
            acting_user_id=self.user.id,
            project_id=self.project.id,
            reject_suggestions=True,
            delete_comments=True,
        )

        self.assertEqual(result, {"comments": 1, "suggestions": 1})
        self.assertFalse(Suggestion.objects.filter(pk=target_suggestion.pk).exists())
        self.assertTrue(Suggestion.objects.filter(pk=other_suggestion.pk).exists())
        self.assertFalse(Comment.objects.filter(pk=target_comment.pk).exists())
        self.assertTrue(Comment.objects.filter(pk=other_comment.pk).exists())
        self.assertTrue(
            Change.objects.filter(
                action=ActionEvents.SUGGESTION_DELETE,
                target="Bad suggestion!\n",
                user=self.user,
                unit=unit,
            ).exists()
        )
        self.assertTrue(
            Change.objects.filter(
                action=ActionEvents.COMMENT_DELETE,
                details={"comment": "Bad comment"},
                user=self.user,
                unit=unit,
            ).exists()
        )

    def test_revert_blocked_user_edits(self) -> None:
        self.project.add_user(self.user, "Administration")
        unit = self.get_unit()
        self.change_unit("Nazdar svete!\n", user=self.second_user)
        self.client.post(
            reverse("block-user", kwargs=self.kw_project),
            {"user": self.second_user.username},
        )

        with patch(
            "weblate.trans.views.acl.revert_user_edits_task.delay",
            return_value=SimpleNamespace(id="task-2"),
        ) as mocked_delay:
            response = self.client.post(
                reverse("revert-blocked-user-edits", kwargs=self.kw_project),
                {"user": self.second_user.username},
                follow=True,
            )

        mocked_delay.assert_called_once_with(
            target_user_id=self.second_user.id,
            acting_user_id=self.user.id,
            project_id=self.project.id,
            sitewide=False,
        )
        self.assertContains(
            response, "Reverting edits by seconduser in this project was scheduled."
        )
        self.assertEqual(self.project.userblock_set.count(), 1)
        unit.refresh_from_db()
        self.assertEqual(unit.target, "Nazdar svete!\n")
        self.assertEqual(unit.state, STATE_TRANSLATED)

    def test_delete_group(self) -> None:
        self.project.add_user(self.user, "Administration")
        group = self.project.defined_groups.get(name="Memory")
        response = self.client.post(
            group.get_absolute_url(),
            {"delete": group.pk},
        )
        self.assertRedirects(response, f"{self.access_url}#teams")
        self.assertFalse(Group.objects.filter(pk=group.pk).exists())

    def create_test_group(self):
        self.project.add_user(self.user, "Administration")
        response = self.client.post(
            reverse("create-project-group", kwargs=self.kw_project),
            {
                "name": "Czech team",
                "roles": list(
                    Role.objects.filter(name="Power user").values_list("pk", flat=True)
                ),
                "language_selection": 0,
                "languages": list(
                    Language.objects.filter(code="cs").values_list("pk", flat=True)
                ),
            },
        )
        self.assertRedirects(response, f"{self.access_url}#teams")
        return Group.objects.get(name="Czech team")

    def test_create_group(self) -> None:
        group = self.create_test_group()
        self.assertEqual(group.defining_project, self.project)
        self.assertEqual(group.language_selection, 0)
        self.assertEqual(list(group.languages.values_list("code", flat=True)), ["cs"])
        self.assertEqual(
            set(group.roles.values_list("name", flat=True)), {"Power user"}
        )

    def test_create_group_all_lang(self) -> None:
        self.project.add_user(self.user, "Administration")
        response = self.client.post(
            reverse("create-project-group", kwargs=self.kw_project),
            {
                "name": "All team",
                "roles": list(
                    Role.objects.filter(name="Power user").values_list("pk", flat=True)
                ),
                "language_selection": 1,
                "languages": list(
                    Language.objects.filter(code="cs").values_list("pk", flat=True)
                ),
            },
        )
        self.assertRedirects(response, f"{self.access_url}#teams")
        group = Group.objects.get(name="All team")
        self.assertEqual(group.defining_project, self.project)
        self.assertEqual(group.language_selection, 1)
        self.assertNotEqual(
            list(group.languages.values_list("code", flat=True)), ["cs"]
        )
        self.assertEqual(
            set(group.roles.values_list("name", flat=True)), {"Power user"}
        )

    def test_edit_group(self) -> None:
        group = self.create_test_group()

        response = self.client.post(
            group.get_absolute_url(),
            {
                "name": "Global team",
                "roles": list(
                    Role.objects.filter(name="Power user").values_list("pk", flat=True)
                ),
                "language_selection": 1,
                "languages": list(
                    Language.objects.filter(code="cs").values_list("pk", flat=True)
                ),
                "autogroup_set-TOTAL_FORMS": "0",
                "autogroup_set-INITIAL_FORMS": "0",
            },
        )
        self.assertRedirects(response, group.get_absolute_url())
        group = Group.objects.get(name="Global team")
        self.assertEqual(group.defining_project, self.project)
        self.assertEqual(group.language_selection, 1)
        self.assertNotEqual(
            list(group.languages.values_list("code", flat=True)), ["cs"]
        )


@enable_login_required_settings()
class ACLLoginRequiredTestCase(ACLTest):
    pass


@modify_settings(SOCIAL_AUTH_PIPELINE={"append": "weblate.legal.pipeline.tos_confirm"})
class ACLLegalTestCase(ACLLoginRequiredTestCase):
    pass
