# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.template.loader import render_to_string
from django.test import TestCase
from django.utils import timezone

from weblate.auth.bots import InternalBot
from weblate.auth.models import (
    AutoGroup,
    Group,
    Invitation,
    InvitationExpiredError,
    InvitationRemovedError,
    InvitationUserMismatchError,
    Role,
    User,
    auto_assign_group,
)
from weblate.trans.models import Project
from weblate.workspaces.models import Workspace


class AutoGroupTest(TestCase):
    @staticmethod
    def create_user() -> User:
        return User.objects.create_user("test1", "noreply1@weblate.org", "pass")

    def test_default(self) -> None:
        user = self.create_user()
        self.assertEqual(user.groups.count(), 2)

    def test_none(self) -> None:
        AutoGroup.objects.all().delete()
        user = self.create_user()
        self.assertEqual(user.groups.count(), 0)

    def test_bot(self) -> None:
        user = User.objects.create_user("bot", "bot@example.com", is_bot=True)

        self.assertFalse(user.groups.exists())

    def test_matching(self) -> None:
        AutoGroup.objects.create(
            match="^.*@weblate.org", group=Group.objects.get(name="Guests")
        )
        user = self.create_user()
        self.assertEqual(user.groups.count(), 3)

    def test_nonmatching(self) -> None:
        AutoGroup.objects.create(
            match="^.*@example.net", group=Group.objects.get(name="Guests")
        )
        user = self.create_user()
        self.assertEqual(user.groups.count(), 2)

    def test_invalid_rule_does_not_break_user_creation(self) -> None:
        AutoGroup.objects.bulk_create(
            [AutoGroup(match="[", group=Group.objects.get(name="Guests"))]
        )

        user = self.create_user()

        self.assertEqual(user.groups.count(), 2)

    def create_scoped_team(self, *, workspace: bool = False) -> Group:
        if workspace:
            team = Group.objects.create(
                name="Automatic team",
                defining_workspace=Workspace.objects.create(name="Company"),
            )
        else:
            project = Project.objects.create(name="Test", slug="test")
            team = Group.objects.create(name="Automatic team", defining_project=project)
            team.projects.add(project)
        team.roles.add(
            Role.objects.get(
                name="Administration" if not workspace else "Workspace administration"
            )
        )
        AutoGroup.objects.create(group=team, match="^.*$")
        return team

    def test_scoped_assignment_requires_acceptance(self) -> None:
        for workspace in (False, True):
            with self.subTest(workspace=workspace):
                team = self.create_scoped_team(workspace=workspace)
                with (
                    self.captureOnCommitCallbacks(execute=True),
                    patch.object(Invitation, "send_email") as send,
                ):
                    user = User.objects.create_user(
                        f"scoped-{workspace}", f"scoped-{workspace}@example.com"
                    )
                    self.assertFalse(send.called)
                self.assertTrue(send.called)
                invitation = Invitation.objects.get(user=user, group=team)
                self.assertTrue(invitation.automatic)
                self.assertEqual(
                    invitation.author, InternalBot.TEAM_ASSIGNMENT.get_user()
                )
                self.assertFalse(user.groups.filter(pk=team.pk).exists())
                self.assertFalse(user.profile.watched.exists())
                permission = "workspace.edit" if workspace else "project.permissions"
                scope = team.defining_workspace if workspace else team.defining_project
                self.assertFalse(user.has_perm(permission, scope))
                invitation.accept(None, user)
                user.clear_permissions_cache()
                self.assertTrue(user.groups.filter(pk=team.pk).exists())
                self.assertTrue(user.has_perm(permission, scope))
                if not workspace:
                    self.assertTrue(
                        user.profile.watched.filter(
                            pk=team.defining_project_id
                        ).exists()
                    )
                self.assertFalse(Invitation.objects.filter(pk=invitation.pk).exists())
                AutoGroup.objects.filter(group=team).delete()

    def test_duplicate_rules_and_existing_invitation(self) -> None:
        team = self.create_scoped_team()
        AutoGroup.objects.create(group=team, match="^.*@example.com$")
        with (
            self.captureOnCommitCallbacks(execute=True),
            patch.object(Invitation, "send_email") as send,
        ):
            user = User.objects.create_user("duplicate", "duplicate@example.com")
            auto_assign_group(user)
        self.assertEqual(Invitation.objects.filter(group=team, user=user).count(), 1)
        send.assert_called_once()
        invitation = Invitation.objects.get(group=team, user=user)
        invitation.user = None
        invitation.email = user.email
        invitation.save()
        auto_assign_group(user)
        self.assertEqual(Invitation.objects.filter(group=team).count(), 1)
        self.assertFalse(user.groups.filter(pk=team.pk).exists())

    def test_existing_member_is_not_invited(self) -> None:
        user = self.create_user()
        team = self.create_scoped_team()
        user.add_team(None, team, user=user)
        auto_assign_group(user)
        self.assertFalse(Invitation.objects.filter(group=team).exists())

    def test_scoped_nonmatching_and_bot(self) -> None:
        team = self.create_scoped_team()
        AutoGroup.objects.filter(group=team).update(match="^.*@example.net$")
        self.create_user()
        User.objects.create_user("bot", "bot@example.net", is_bot=True)
        self.assertFalse(Invitation.objects.filter(group=team).exists())

    def test_no_email_keeps_pending_invitation(self) -> None:
        team = self.create_scoped_team()
        with (
            self.captureOnCommitCallbacks(execute=True),
            patch.object(Invitation, "send_email") as send,
        ):
            user = User.objects.create_user("no-email")
        send.assert_not_called()
        self.assertTrue(Invitation.objects.filter(group=team, user=user).exists())
        self.assertFalse(user.groups.filter(pk=team.pk).exists())

    def test_automatic_invitation_wording(self) -> None:
        team = self.create_scoped_team()
        user = self.create_user()
        invitation = Invitation.objects.get(group=team, user=user)
        for template in ("mail/invite_subject.txt", "snippets/invite-info.html"):
            rendered = render_to_string(
                template, {"invitation": invitation, "site_title": "Weblate"}
            )
            self.assertIn("automatic team assignment", rendered.lower())
        description = render_to_string(
            "snippets/invite-info.html",
            {"invitation": invitation, "site_title": "Weblate"},
        )
        self.assertIn("only if you accept", description)
        invitation.automatic = False
        manual = render_to_string(
            "snippets/invite-info.html",
            {"invitation": invitation, "site_title": "Weblate"},
        )
        self.assertIn("You were invited", manual)
        self.assertNotIn("automatic team assignment", manual)

    def test_automatic_invitation_validation(self) -> None:
        team = self.create_scoped_team()
        user = self.create_user()
        invitation = Invitation.objects.get(group=team, user=user)
        other = User.objects.create_user("other", "other@example.com")
        with self.assertRaises(InvitationUserMismatchError):
            invitation.accept(None, other)
        Invitation.objects.filter(pk=invitation.pk).update(
            timestamp=timezone.now() - timedelta(seconds=settings.AUTH_TOKEN_VALID + 1)
        )
        with self.assertRaises(InvitationExpiredError):
            invitation.accept(None, user)
        invitation.revoke()
        with self.assertRaises(InvitationRemovedError):
            invitation.accept(None, user)
        self.assertFalse(user.groups.filter(pk=team.pk).exists())

    def test_automatic_invitation_email(self) -> None:
        team = self.create_scoped_team()
        with (
            patch("weblate.accounts.notifications.queue_mails") as queue,
            self.captureOnCommitCallbacks(execute=True),
        ):
            user = self.create_user()
        queue.assert_called_once()
        message = queue.call_args.args[0][0]
        self.assertEqual(message["address"], user.email)
        self.assertIn("Automatic team assignment", message["subject"])
        self.assertIn("only if you accept", message["body"])
        invitation = Invitation.objects.get(group=team, user=user)
        self.assertIn(invitation.get_absolute_url(), message["body"])
