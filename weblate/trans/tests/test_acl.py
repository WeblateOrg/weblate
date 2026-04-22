# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for ACL management."""

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.test.utils import modify_settings, override_settings
from django.urls import reverse
from social_django.models import UserSocialAuth

from weblate.accounts.models import VerifiedEmail
from weblate.auth.models import Group, Invitation, Role, User, get_anonymous
from weblate.lang.models import Language
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Change, Project
from weblate.trans.tasks import revert_user_edits as revert_user_edits_task
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
        response = user_client.get(url, follow=True)

        # Accept terms if using legal
        if "weblate.legal.pipeline.tos_confirm" in settings.SOCIAL_AUTH_PIPELINE:
            response = self.confirm_tos(user_client, response)

        self.assertRedirects(response, reverse("password"))

        # Verify user was added
        response = self.client.get(self.access_url)
        self.assertContains(response, "example-username")

        user = User.objects.get(username="example-username")

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
