# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Pending team administration grants through invitations."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.template.loader import render_to_string
from django.test import TestCase
from django.utils import timezone

from weblate.auth.invitations import create_team_invitation
from weblate.auth.models import (
    Group,
    Invitation,
    InvitationBlockedAdminError,
    InvitationExpiredError,
    InvitationRemovedError,
    InvitationUserMismatchError,
    User,
    UserBlock,
)
from weblate.lang.models import Language
from weblate.trans.models import Project


class TeamAdminInvitationTest(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.author = User.objects.create_user("inviter", "inviter@example.com", "x")
        self.user = User.objects.create_user("invited", "invited@example.com", "x")
        self.project = Project.objects.create(name="Test", slug="test")
        self.team = Group.objects.create(name="Invited", defining_project=self.project)
        self.team.projects.add(self.project)

    def create_invitation(self, *, team_admin: bool = True) -> Invitation:
        with patch.object(Invitation, "send_email"):
            return create_team_invitation(
                author=self.author,
                group=self.team,
                project=self.project,
                user=self.user,
                team_admin=team_admin,
            )

    def assert_not_granted(self) -> None:
        self.assertFalse(self.team.admins.filter(pk=self.user.pk).exists())
        self.assertFalse(self.user.groups.filter(pk=self.team.pk).exists())
        self.assertFalse(self.user.auditlog_set.filter(activity="accepted").exists())

    def test_grant_on_acceptance(self) -> None:
        invitation = self.create_invitation()
        self.assert_not_granted()

        invitation.accept(None, self.user)

        self.assertTrue(self.team.admins.filter(pk=self.user.pk).exists())
        self.assertTrue(self.user.groups.filter(pk=self.team.pk).exists())
        self.assertFalse(Invitation.objects.filter(pk=invitation.pk).exists())
        audit = self.user.auditlog_set.get(activity="accepted")
        self.assertTrue(audit.params["team_admin"])
        self.assertEqual(audit.params["username"], self.author.username)

    def test_existing_member(self) -> None:
        self.user.add_team(None, self.team, user=self.author)
        invitation = self.create_invitation()
        self.assertFalse(self.team.admins.filter(pk=self.user.pk).exists())

        invitation.accept(None, self.user)

        self.assertTrue(self.team.admins.filter(pk=self.user.pk).exists())
        self.assertEqual(self.team.memberships.filter(user=self.user).count(), 1)

    def test_accept_through_view(self) -> None:
        invitation = self.create_invitation()
        self.client.force_login(self.user)

        response = self.client.post(invitation.get_absolute_url())

        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.team.admins.filter(pk=self.user.pk).exists())
        self.assertFalse(Invitation.objects.filter(pk=invitation.pk).exists())

    def test_membership_invitation_does_not_grant_admin(self) -> None:
        self.create_invitation(team_admin=False).accept(None, self.user)

        self.assertTrue(self.user.groups.filter(pk=self.team.pk).exists())
        self.assertFalse(self.team.admins.filter(pk=self.user.pk).exists())

    def test_membership_invitation_preserves_existing_admin(self) -> None:
        self.user.add_team(None, self.team, user=self.author)
        self.team.admins.add(self.user)

        self.create_invitation(team_admin=False).accept(None, self.user)

        self.assertTrue(self.team.admins.filter(pk=self.user.pk).exists())

    def test_revoked(self) -> None:
        invitation = self.create_invitation()
        stale = Invitation.objects.get(pk=invitation.pk)
        invitation.revoke()

        with self.assertRaises(InvitationRemovedError):
            stale.accept(None, self.user)

        self.assert_not_granted()

    def test_expired(self) -> None:
        invitation = self.create_invitation()
        Invitation.objects.filter(pk=invitation.pk).update(
            timestamp=timezone.now() - timedelta(seconds=settings.AUTH_TOKEN_VALID)
        )

        with self.assertRaises(InvitationExpiredError):
            invitation.accept(None, self.user)

        self.assert_not_granted()

    def test_mismatched_user(self) -> None:
        invitation = self.create_invitation()
        with self.assertRaises(InvitationUserMismatchError):
            invitation.accept(None, self.author)

        self.assert_not_granted()
        self.assertFalse(self.team.admins.filter(pk=self.author.pk).exists())

    def test_stale_grant_uses_current_invitation(self) -> None:
        invitation = self.create_invitation()
        Invitation.objects.filter(pk=invitation.pk).update(team_admin=False)

        invitation.accept(None, self.user)

        self.assertFalse(self.team.admins.filter(pk=self.user.pk).exists())

    def test_blocked_user_cannot_accept_admin_grant(self) -> None:
        UserBlock.objects.create(user=self.user, project=self.project)
        invitation = self.create_invitation()
        # A language limit must not bypass validation of the administrative grant.
        invitation.limit_languages.add(Language.objects.get(code="cs"))

        with self.assertRaises(InvitationBlockedAdminError):
            invitation.accept(None, self.user)

        self.assert_not_granted()
        self.assertTrue(Invitation.objects.filter(pk=invitation.pk).exists())

    def test_acceptance_is_not_replayed(self) -> None:
        invitation = self.create_invitation()
        stale = Invitation.objects.get(pk=invitation.pk)
        invitation.accept(None, self.user)
        self.team.admins.remove(self.user)

        with self.assertRaises(InvitationRemovedError):
            stale.accept(None, self.user)

        self.assertFalse(self.team.admins.filter(pk=self.user.pk).exists())

    def test_pending_role_is_disclosed(self) -> None:
        invitation = self.create_invitation()
        self.client.force_login(self.user)
        message = (
            "Accepting this invitation will also make you a team administrator, "
            "allowing you to add or remove team members."
        )
        self.assertContains(self.client.get(invitation.get_absolute_url()), message)
        with patch("weblate.accounts.notifications.queue_mails") as queue:
            invitation.send_email()
        self.assertIn(message, queue.call_args.args[0][0]["body"])
        invitation.team_admin = False
        self.assertNotIn(
            message,
            render_to_string(
                "snippets/invite-info.html",
                {"invitation": invitation, "site_title": "Weblate"},
            ),
        )
