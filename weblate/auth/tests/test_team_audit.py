# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Team audit records preserve actor attribution and administrative boundaries."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, cast

from django.contrib.admin.sites import AdminSite
from django.db import connection
from django.test.utils import CaptureQueriesContext, override_settings
from django.urls import reverse
from django.utils.timezone import now
from lxml.html import fromstring

from weblate.accounts.models import AuditLog, TeamAuditLog
from weblate.accounts.tasks import cleanup_auditlog
from weblate.accounts.utils import remove_user
from weblate.auth.admin import GroupChangeForm, WeblateGroupAdmin
from weblate.auth.audit import (
    audit_membership_limits,
    audit_team_changes,
    membership_limits,
    record_team_event,
)
from weblate.auth.models import Group, Invitation, Role, TeamMembership, User, UserBlock
from weblate.lang.models import Language
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Change, Component, Project
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.change_origin import acting_user_context
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


class TeamAuditTest(ViewTestCase):
    def create_team(self, name: str = "Audit team") -> Group:
        team = Group(name=name, defining_project=self.project)
        with audit_team_changes(team, self.user):
            team.save()
            team.projects.add(self.project)
        return team

    def test_definition_lifecycle_and_rollback(self) -> None:
        changes = Change.objects.count()
        team = self.create_team()
        created = TeamAuditLog.objects.get(team=team, event="created")
        self.assertEqual(created.actor, self.user)
        self.assertEqual(created.project, self.project)
        self.assertEqual(created.details["current"]["name"], team.name)
        self.assertEqual(Change.objects.count(), changes)
        with audit_team_changes(team, self.user):
            team.enforced_2fa = True
            team.save()
            team.roles.add(Role.objects.get(name="Administration"))
        updated = TeamAuditLog.objects.get(team=team, event="changed")
        self.assertEqual(
            updated.details["enforced_2fa"], {"previous": False, "current": True}
        )
        self.assertEqual(
            updated.details["roles"]["current"][0]["name"], "Administration"
        )
        with audit_team_changes(team, self.user):
            team.save()
        self.assertEqual(TeamAuditLog.objects.filter(team=team).count(), 2)
        with (
            self.assertRaisesMessage(ValueError, "rollback"),
            audit_team_changes(team, self.user),
        ):
            team.enforced_2fa = False
            team.save()
            msg = "rollback"
            raise ValueError(msg)
        team.refresh_from_db()
        self.assertTrue(team.enforced_2fa)
        self.assertEqual(TeamAuditLog.objects.filter(team=team).count(), 2)
        with audit_team_changes(team, self.user):
            team.delete()
        deleted = TeamAuditLog.objects.get(event="deleted", team_name="Audit team")
        self.assertIsNone(deleted.team_id)
        self.assertEqual(deleted.project, self.project)
        self.assertEqual(deleted.actor, self.user)

    def test_team_form_save_includes_automatic_assignment_rules(self) -> None:
        team = self.create_team()
        self.project.add_user(self.user, "Administration")
        response = self.client.post(
            team.get_absolute_url(),
            {
                "name": "Changed team",
                "all_languages": "on",
                "enforced_2fa": "on",
                "roles": [Role.objects.get(name="Administration").pk],
                "autogroup_set-TOTAL_FORMS": "1",
                "autogroup_set-INITIAL_FORMS": "0",
                "autogroup_set-0-match": "^staff@example.org$",
                "autogroup_set-0-group": team.pk,
            },
        )
        self.assertEqual(response.status_code, 302)
        team.refresh_from_db()
        self.assertEqual(team.name, "Changed team")
        entry = TeamAuditLog.objects.get(team=team, event="changed")
        self.assertEqual(entry.actor, self.user)
        self.assertEqual(
            entry.details["automatic_rules"]["current"], ["^staff@example.org$"]
        )

    def test_admin_form_records_related_changes(self) -> None:
        team = self.create_team()
        request = self.factory.post("/")
        request.user = self.user
        form = GroupChangeForm(
            {
                "name": "Admin changed team",
                "defining_project": self.project.pk,
                "project_selection": 0,
                "language_selection": 0,
                "roles": [Role.objects.get(name="Administration").pk],
                "projects": [self.project.pk],
            },
            instance=team,
        )
        self.assertTrue(form.is_valid(), form.errors)
        instance = form.save(commit=False)
        admin = WeblateGroupAdmin(Group, AdminSite())
        admin.save_model(request, instance, form, change=True)
        admin.save_related(request, form, [], change=True)
        entry = TeamAuditLog.objects.get(team=team, event="changed")
        self.assertEqual(entry.details["name"]["previous"], "Audit team")
        self.assertEqual(entry.details["roles"]["current"][0]["name"], "Administration")
        self.assertEqual(entry.actor, self.user)

    def test_invitation_admin_grant_preserves_inviter(self) -> None:
        team = self.create_team()
        invitation = Invitation.objects.create(
            author=self.user, user=self.anotheruser, group=team, team_admin=True
        )
        request = cast("AuthenticatedHttpRequest", self.factory.post("/"))
        request.user = self.anotheruser
        invitation.accept(request, self.anotheruser)
        entry = TeamAuditLog.objects.get(team=team, event="changed")
        self.assertEqual(entry.actor, self.user)
        audit = AuditLog.objects.get(user=self.anotheruser, activity="team-admin-added")
        self.assertEqual(audit.params["username"], self.user.username)

    def test_existing_member_invitation_locks_scope_before_membership(self) -> None:
        team = self.create_team()
        team.user_set.add(self.anotheruser)
        invitation = Invitation.objects.create(
            author=self.user, user=self.anotheruser, group=team, team_admin=True
        )
        with CaptureQueriesContext(connection) as queries:
            invitation.accept(None, self.anotheruser)
        locks = [
            query["sql"]
            for query in queries
            if " FOR UPDATE" in query["sql"] or " FOR NO KEY UPDATE" in query["sql"]
        ]
        lock_positions = [
            next(index for index, sql in enumerate(locks) if f'FROM "{table}"' in sql)
            for table in (
                "trans_project",
                "weblate_auth_group",
                "weblate_auth_invitation",
                "weblate_auth_user_groups",
            )
        ]
        self.assertEqual(lock_positions, sorted(lock_positions))
        self.assertTrue(team.admins.filter(pk=self.anotheruser.pk).exists())

    def test_administrator_changes_audit_the_affected_account(self) -> None:
        team = self.create_team()
        with audit_team_changes(team, self.user):
            team.admins.add(self.anotheruser)
        added = AuditLog.objects.get(user=self.anotheruser, activity="team-admin-added")
        self.assertEqual(added.params["username"], self.user.username)
        with audit_team_changes(team, self.user):
            team.admins.remove(self.anotheruser)
        removed = AuditLog.objects.get(
            user=self.anotheruser, activity="team-admin-removed"
        )
        self.assertEqual(removed.params["username"], self.user.username)

    def test_membership_removal_includes_administrator_revocation(self) -> None:
        team = self.create_team()
        request = cast("AuthenticatedHttpRequest", self.factory.post("/"))
        request.user = self.user
        self.anotheruser.add_team(request, team)
        entry = TeamAuditLog.objects.get(team=team, event="member-added")
        self.assertEqual(entry.actor, self.user)
        self.assertEqual(entry.details["username"], self.anotheruser.username)
        with audit_team_changes(team, self.user, request):
            team.admins.add(self.anotheruser)
        self.anotheruser.remove_team(request, team)
        self.assertFalse(team.admins.filter(pk=self.anotheruser.pk).exists())
        self.assertEqual(
            AuditLog.objects.filter(
                user=self.anotheruser, activity="team-admin-removed"
            ).count(),
            1,
        )
        self.assertEqual(
            TeamAuditLog.objects.get(team=team, event="member-removed").actor, self.user
        )

    def test_account_deletion_with_team_administration(self) -> None:
        team = self.create_team()
        self.anotheruser.add_team(None, team, user=self.user)
        with audit_team_changes(team, self.user):
            team.admins.add(self.anotheruser)
        with acting_user_context(self.user):
            self.anotheruser.delete()
        self.assertFalse(team.admins.exists())
        self.assertTrue(
            TeamAuditLog.objects.filter(team=team, event="changed").exists()
        )

    def test_account_removal_audits_memberships_before_anonymizing(self) -> None:
        team = self.create_team()
        workspace = Workspace.objects.create(name="Account removal audit")
        workspace_team = workspace.get_owners_group()
        for self_removal in (False, True):
            with self.subTest(self_removal=self_removal):
                member = User.objects.create_user(
                    username=f"removed-member-{int(self_removal)}",
                    email=f"removed-member-{int(self_removal)}@example.org",
                )
                for group in (team, workspace_team):
                    member.add_team(None, group, user=self.user)
                previous_team_ids = list(member.groups.values_list("pk", flat=True))
                original_username = member.username
                request = cast("AuthenticatedHttpRequest", self.factory.post("/"))
                request.user = member if self_removal else self.user
                remove_user(member, request)
                self.assertFalse(member.groups.exists())
                self.assertNotEqual(member.username, original_username)
                entries = TeamAuditLog.objects.filter(
                    event="member-removed", details__username=original_username
                )
                self.assertCountEqual(
                    entries.values_list("team_id", flat=True),
                    previous_team_ids,
                )
                self.assertEqual(
                    set(entries.values_list("actor_id", flat=True)),
                    {request.user.pk},
                )

    def test_nonmember_removal_does_not_create_false_audit_events(self) -> None:
        team = self.create_team()
        before = TeamAuditLog.objects.count()
        request = cast("AuthenticatedHttpRequest", self.factory.post("/"))
        request.user = self.user
        self.anotheruser.remove_team(request, team)
        self.assertEqual(TeamAuditLog.objects.count(), before)

    def test_admin_membership_language_changes(self) -> None:
        team = self.create_team()
        self.anotheruser.add_team(None, team, user=self.user)
        before = membership_limits(self.anotheruser)
        membership = TeamMembership.objects.get(user=self.anotheruser, group=team)
        membership.limit_languages.add(Language.objects.get(code="cs"))
        request = self.factory.post("/")
        request.user = self.user
        audit_membership_limits(
            self.anotheruser,
            before,
            self.user,
            cast("AuthenticatedHttpRequest", request),
        )
        entry = TeamAuditLog.objects.get(team=team, event="member-changed")
        self.assertEqual(entry.details["limit_languages"], ["cs"])
        self.assertEqual(entry.actor, self.user)

    def test_initial_membership_limits_are_audited(self) -> None:
        team = self.create_team()
        self.anotheruser.add_team(None, team, user=self.user)
        membership = TeamMembership.objects.get(user=self.anotheruser, group=team)
        membership.set_limit_languages(
            [Language.objects.get(code="cs")], actor=self.user, audit=False
        )
        self.assertEqual(
            TeamAuditLog.objects.get(team=team, event="member-changed").details[
                "limit_languages"
            ],
            ["cs"],
        )

    def test_stale_assignments_do_not_disclose_destination_names(self) -> None:
        team = self.create_team()
        team.components.add(self.component)
        destination = self.create_project(
            name="Hidden destination",
            slug="hidden-destination",
            access_control=Project.ACCESS_PRIVATE,
        )
        Component.objects.filter(pk=self.component.pk).update(
            project=destination, slug="private-destination-component"
        )
        with audit_team_changes(team, self.user):
            team.delete()
        entry = TeamAuditLog.objects.get(team_name="Audit team", event="deleted")
        self.assertEqual(
            entry.details["previous"]["components"],
            [{"id": self.component.pk, "unavailable": True}],
        )
        self.assertNotIn(destination.slug, str(entry.details))
        self.assertNotIn("private-destination-component", str(entry.details))

    def test_project_scope_change_does_not_disclose_the_other_scope(self) -> None:
        team = self.create_team()
        target = self.create_project(
            name="Hidden target",
            slug="hidden-target",
            access_control=Project.ACCESS_PRIVATE,
        )
        with audit_team_changes(team, self.user):
            team.projects.clear()
            team.defining_project = target
            team.save()
            team.projects.add(target)
        removed = TeamAuditLog.objects.get(project=self.project, event="deleted")
        added = TeamAuditLog.objects.get(project=target, event="created")
        self.assertNotIn(target.slug, str(removed.details))
        self.assertEqual(added.details["current"]["project_slug"], target.slug)

    def test_log_visibility_deleted_teams_and_html_escaping(self) -> None:
        team = self.create_team('<img src=x onerror="secret">')
        entry = TeamAuditLog.objects.get(team=team)
        url = reverse("team-audit-detail", kwargs={"pk": entry.pk})
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(reverse("team-audit")).status_code, 403)
        self.project.add_user(self.user, "Administration")
        response = self.client.get(reverse("team-audit"))
        self.assertContains(response, "&lt;img")
        self.assertNotContains(response, '<img src=x onerror="secret">')
        detail = self.client.get(url)
        self.assertEqual(detail.status_code, 200)
        for page in (response, detail):
            document = fromstring(page.content)
            self.assertTrue(
                document.xpath('//ol[@class="breadcrumb"]/li[@aria-current="page"]')
            )
        with audit_team_changes(team, self.user):
            team.delete()
        self.assertEqual(self.client.get(url).status_code, 200)
        UserBlock.objects.create(user=self.user, project=self.project)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_project_access_audit_tab_is_scoped_to_project(self) -> None:
        self.project.add_user(self.user, "Administration")
        team = self.create_team()
        other_project = self.create_project(
            name="Other audit project", slug="other-audit"
        )
        other_project.add_user(self.user, "Administration")
        other_team = Group.objects.create(
            name="Other audit team", defining_project=other_project
        )
        record_team_event(other_team, self.user, "changed", {"name": "other"})
        response = self.client.get(
            reverse("manage-access", kwargs={"project": self.project.slug})
        )
        entries = response.context["team_audit_entries"]
        self.assertTrue(any(entry.team_id == team.pk for entry in entries))
        self.assertTrue(all(entry.project_id == self.project.pk for entry in entries))
        document = fromstring(response.content)
        self.assertEqual(
            len(
                document.xpath(
                    '//ul[contains(@class,"nav-pills")]//a[@id="tab_team_audit"]'
                )
            ),
            1,
        )
        self.assertTrue(document.xpath('//div[@id="team-audit"]//table'))
        self.assertNotContains(response, "Other audit team")

    def test_team_audit_tab_requires_scope_management(self) -> None:
        team = self.create_team()
        team.user_set.add(self.user)
        team.admins.add(self.user)
        response = self.client.get(team.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="tab_team_audit"')
        self.assertNotIn("team_audit_entries", response.context)

        self.project.add_user(self.user, "Administration")
        self.create_team("Unrelated team audit")
        response = self.client.get(team.get_absolute_url())
        self.assertContains(response, 'id="tab_team_audit"')
        entries = response.context["team_audit_entries"]
        self.assertTrue(entries)
        self.assertTrue(all(entry.team_id == team.pk for entry in entries))
        document = fromstring(response.content)
        self.assertTrue(document.xpath('//div[@id="team-audit"]//table'))
        self.assertNotContains(response, "Unrelated team audit")

    def test_audit_paginators_have_separate_submission_forms(self) -> None:
        self.project.add_user(self.user, "Administration")
        team = self.create_team()
        for index in range(11):
            member = User.objects.create_user(
                username=f"audit-page-{index}", email=f"audit-page-{index}@example.org"
            )
            team.user_set.add(member)
            record_team_event(team, self.user, "changed", {"name": f"entry {index}"})
        for url in (
            team.get_absolute_url(),
            reverse("manage-access", kwargs={"project": self.project.slug}),
        ):
            with self.subTest(url=url):
                response = self.client.get(url, {"limit": 10})
                document = fromstring(response.content)
                for form_id, panel in (
                    ("paginator-form", "users"),
                    ("team-audit-paginator-form", "team-audit"),
                ):
                    inputs = document.xpath(f'//input[@name="page"][@form="{form_id}"]')
                    self.assertEqual(len(inputs), 1)
                    self.assertTrue(document.xpath(f'//form[@id="{form_id}"]'))
                    self.assertTrue(
                        document.xpath(
                            f'//div[@id="{panel}"]//input[@id="{inputs[0].get("id")}"]'
                        )
                    )
                ids = document.xpath('//input[@name="page"]/@id')
                self.assertEqual(len(ids), len(set(ids)))
                self.assertTrue(
                    document.xpath(
                        '//div[@id="team-audit"]//a[contains(@href,"page=2") and contains(@href,"#team-audit")]'
                    )
                )

    def test_workspace_and_site_permissions(self) -> None:
        workspace = Workspace.objects.create(name="Audit workspace")
        workspace_team = workspace.get_owners_group()
        site_team = Group.objects.create(name="Site secret")
        record_team_event(workspace_team, self.user, "changed", {"secret": "workspace"})
        record_team_event(site_team, self.user, "changed", {"secret": "site"})
        workspace_entry = TeamAuditLog.objects.get(team=workspace_team)
        site_entry = TeamAuditLog.objects.get(team=site_team)
        workspace.add_owner(self.user)
        self.user.clear_permissions_cache()
        ids = set(TeamAuditLog.objects.for_user(self.user).values_list("pk", flat=True))
        self.assertIn(workspace_entry.pk, ids)
        self.assertNotIn(site_entry.pk, ids)
        self.user.is_superuser = True
        self.assertIn(
            site_entry.pk,
            TeamAuditLog.objects.for_user(self.user).values_list("pk", flat=True),
        )

    @override_settings(AUDITLOG_EXPIRY=30)
    def test_retention_and_deleted_scope(self) -> None:
        workspace = Workspace.objects.create(name="Deleted audit workspace")
        team = workspace.get_owners_group()
        workspace.add_owner(self.user)
        record_team_event(team, self.user, "changed", {"name": "old"})
        expired = TeamAuditLog.objects.get(team=team, event="changed")
        TeamAuditLog.objects.filter(pk=expired.pk).update(
            timestamp=now() - timedelta(days=31)
        )
        record_team_event(team, self.user, "changed", {"name": "recent"})
        recent = (
            TeamAuditLog.objects.filter(team=team, event="changed")
            .exclude(pk=expired.pk)
            .get()
        )
        cleanup_auditlog()
        self.assertFalse(TeamAuditLog.objects.filter(pk=expired.pk).exists())
        self.assertTrue(
            TeamAuditLog.objects.for_user(self.user).filter(pk=recent.pk).exists()
        )
        workspace.delete()
        recent.refresh_from_db()
        self.assertIsNone(recent.workspace_id)
        self.assertIsNone(recent.team_id)
        self.assertFalse(
            TeamAuditLog.objects.for_user(self.user).filter(pk=recent.pk).exists()
        )
        self.user.is_superuser = True
        self.assertTrue(
            TeamAuditLog.objects.for_user(self.user).filter(pk=recent.pk).exists()
        )

    def test_log_list_queries_do_not_grow_with_rows(self) -> None:
        self.project.add_user(self.user, "Administration")
        TeamAuditLog.objects.all().delete()
        team = Group.objects.create(name="Audit rows", defining_project=self.project)
        counts = []
        for count in (1, 8):
            for _index in range(TeamAuditLog.objects.filter(team=team).count(), count):
                record_team_event(team, self.user, "changed", {"name": "updated"})
            self.client.get(reverse("team-audit"))
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(reverse("team-audit"))
            self.assertEqual(len(response.context["entries"]), count)
            counts.append(len(queries))
        self.assertEqual(counts[0], counts[1])

    def test_existing_team_history_is_hidden_from_public_viewers(self) -> None:
        change = self.project.change_set.create(
            action=ActionEvents.ADD_USER,
            user=self.user,
            details={"username": "private-admin", "group": "Private team"},
        )
        self.assertFalse(
            Change.objects.last_changes(self.user, project=self.project)
            .filter(pk=change.pk)
            .exists()
        )
        self.project.add_user(self.user, "Administration")
        self.user.clear_permissions_cache()
        self.assertTrue(
            Change.objects.last_changes(self.user, project=self.project)
            .filter(pk=change.pk)
            .exists()
        )
