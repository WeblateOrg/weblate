# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from types import SimpleNamespace

from django.conf import settings
from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase

from weblate.accounts.models import TeamAuditLog
from weblate.auth.admin import WeblateGroupAdmin, WeblateUserAdmin
from weblate.auth.models import Group, TeamMembership, User
from weblate.lang.models import Language
from weblate.workspaces.models import Workspace


class WeblateUserAdminTest(TestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()
        self.site = AdminSite()
        self.user_admin = WeblateUserAdmin(User, self.site)
        self.actor = User.objects.create_user("admin", "admin@example.com", "x")
        self.actor.is_superuser = True
        self.actor.save(update_fields=["is_superuser"])
        self.target = User.objects.create_user("target", "target@example.com", "x")
        self.users_group = Group.objects.get(name="Users")
        self.viewers_group = Group.objects.get(name="Viewers")
        self.target.groups.set([self.users_group])

    def test_group_display_uses_prefetch(self) -> None:
        request = self.factory.get("/")
        request.user = self.actor
        with self.assertNumQueries(2):
            users = list(self.user_admin.get_queryset(request).order_by("pk"))
            names = {user.pk: self.user_admin.user_groups(user) for user in users}
        self.assertEqual(names[self.target.pk], self.users_group.name)
        self.target.groups.add(self.viewers_group)
        with self.assertNumQueries(2):
            users = list(self.user_admin.get_queryset(request).order_by("pk"))
            names = {user.pk: self.user_admin.user_groups(user) for user in users}
        self.assertIn(self.viewers_group.name, names[self.target.pk])

    def test_search_defining_workspace(self) -> None:
        workspace = Workspace.objects.create(name="Distinct workspace")
        group = Group.objects.create(
            name="Scoped translators", defining_workspace=workspace
        )
        self.target.groups.add(group)
        request = self.factory.get("/")
        request.user = self.actor
        for term in (workspace.name, group.name):
            with self.subTest(term=term):
                queryset, duplicates = self.user_admin.get_search_results(
                    request, self.user_admin.get_queryset(request), term
                )
                if duplicates:
                    queryset = queryset.distinct()
                self.assertEqual(list(queryset), [self.target])
        group_admin = WeblateGroupAdmin(Group, self.site)
        for term in (workspace.name,):
            queryset, _duplicates = group_admin.get_search_results(
                request, group_admin.get_queryset(request), term
            )
            self.assertCountEqual(queryset, workspace.defined_groups.all())

    def test_team_admin_preserves_autocomplete_selection(self) -> None:
        group = Group.objects.create(name="Autocomplete team")
        group.admins.add(self.target)
        request = self.factory.get("/")
        request.user = self.actor
        group_admin = WeblateGroupAdmin(Group, admin.site)
        form_class = group_admin.get_form(request, obj=group)
        form = form_class(instance=group)
        # Initial rendering includes existing selections without enumerating users.
        html = str(form["admins"])
        self.assertIn(f'value="{self.target.pk}" selected', html)
        self.assertNotIn(f'<option value="{self.actor.pk}"', html)
        form = form_class(
            data={
                "name": group.name,
                "project_selection": group.project_selection,
                "language_selection": group.language_selection,
                "admins": [self.target.pk, self.actor.pk],
            },
            instance=group,
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.assertCountEqual(group.admins.all(), [self.target, self.actor])

    def test_protected_user_permissions(self) -> None:
        request = self.factory.post("/")
        request.user = self.actor
        anonymous = User.objects.get(username=settings.ANONYMOUS_USER_NAME)
        protected_bot = User.objects.create(
            username="addon:test",
            full_name="Addon Bot",
            email="addon-test@example.org",
            is_bot=True,
            is_active=False,
        )

        for protected_user in (anonymous, protected_bot):
            with self.subTest(username=protected_user.username):
                self.assertEqual(self.user_admin.action_checkbox(protected_user), "")
                self.assertFalse(
                    self.user_admin.has_change_permission(request, protected_user)
                )
                self.assertFalse(
                    self.user_admin.has_delete_permission(request, protected_user)
                )
                with self.assertRaises(PermissionDenied):
                    self.user_admin.save_model(
                        request,
                        protected_user,
                        SimpleNamespace(instance=protected_user),
                        change=True,
                    )
                with self.assertRaises(PermissionDenied):
                    self.user_admin.delete_model(request, protected_user)

    def test_project_token_permissions(self) -> None:
        request = self.factory.post("/")
        request.user = self.actor
        project_token = User.objects.create(
            username="bot-test-token",
            full_name="Project Token",
            email="bot-test-token@example.org",
            is_bot=True,
            is_active=False,
        )

        self.assertNotEqual(self.user_admin.action_checkbox(project_token), "")
        self.assertTrue(self.user_admin.has_change_permission(request, project_token))
        self.assertTrue(self.user_admin.has_delete_permission(request, project_token))

    def test_save_related_audits_security_changes(self) -> None:
        request = self.factory.post("/")
        request.user = self.actor

        obj = User.objects.get(pk=self.target.pk)
        obj.is_superuser = True
        obj.is_active = False
        obj.full_name = "Edited name"
        form = SimpleNamespace(
            instance=obj, save_m2m=lambda: obj.groups.set([self.viewers_group])
        )

        self.user_admin.save_model(request, obj, form, change=True)
        self.user_admin.save_related(request, form, [], change=True)

        self.target.refresh_from_db()

        superuser_audit = self.target.auditlog_set.get(
            activity="superuser-granted", params__username=self.actor.username
        )
        self.assertEqual(superuser_audit.params["username"], self.actor.username)

        add_audit = self.target.auditlog_set.get(
            activity="sitewide-team-add",
            params__team=self.viewers_group.name,
            params__username=self.actor.username,
        )
        self.assertEqual(add_audit.params["username"], self.actor.username)

        remove_audit = self.target.auditlog_set.get(
            activity="sitewide-team-remove",
            params__team=self.users_group.name,
            params__username=self.actor.username,
        )
        self.assertEqual(remove_audit.params["username"], self.actor.username)
        for activity in ("disabled", "full_name"):
            audit = self.target.auditlog_set.get(activity=activity)
            self.assertEqual(audit.params["username"], self.actor.username)
            self.assertIsNone(audit.address)

    def test_new_user_inline_memberships_are_audited(self) -> None:
        request = self.factory.post("/")
        request.user = self.actor
        team = Group.objects.create(name="Explicit inline membership")
        for limited in (False, True):
            with self.subTest(limited=limited):
                target = User(username=f"created-{limited}", is_superuser=True)
                form = SimpleNamespace(instance=target, save_m2m=lambda: None)
                self.user_admin.save_model(request, target, form, change=False)
                membership = TeamMembership.objects.create(user=target, group=team)
                if limited:
                    membership.limit_languages.add(Language.objects.get(code="cs"))
                self.user_admin.save_related(request, form, [], change=False)
                entry = TeamAuditLog.objects.get(
                    team=team,
                    event=TeamAuditLog.Event.MEMBER_ADDED,
                    details__username=target.username,
                )
                self.assertEqual(entry.actor, self.actor)
                if limited:
                    limits = TeamAuditLog.objects.get(
                        team=team,
                        event=TeamAuditLog.Event.MEMBER_CHANGED,
                        details__username=target.username,
                    )
                    self.assertEqual(limits.details["limit_languages"], ["cs"])
                target.auditlog_set.get(
                    activity="sitewide-team-add", params__team=team.name
                )
                target.auditlog_set.get(activity="superuser-granted")

    def test_save_related_keeps_audit_state_per_form(self) -> None:
        second_actor = User.objects.create_user("admin-2", "admin-2@example.com", "x")
        second_actor.is_superuser = True
        second_actor.save(update_fields=["is_superuser"])
        second_target = User.objects.create_user(
            "target-2", "target-2@example.com", "x"
        )
        second_target.is_superuser = True
        second_target.save(update_fields=["is_superuser"])
        second_target.groups.set([self.viewers_group])

        first_request = self.factory.post("/")
        first_request.user = self.actor
        second_request = self.factory.post("/")
        second_request.user = second_actor

        first_obj = User.objects.get(pk=self.target.pk)
        first_obj.is_superuser = True
        first_form = SimpleNamespace(
            instance=first_obj,
            save_m2m=lambda: first_obj.groups.set([self.viewers_group]),
        )

        second_obj = User.objects.get(pk=second_target.pk)
        second_obj.is_superuser = False
        second_form = SimpleNamespace(
            instance=second_obj,
            save_m2m=lambda: second_obj.groups.set([self.users_group]),
        )

        self.user_admin.save_model(first_request, first_obj, first_form, change=True)
        self.user_admin.save_model(second_request, second_obj, second_form, change=True)
        self.user_admin.save_related(first_request, first_form, [], change=True)
        self.user_admin.save_related(second_request, second_form, [], change=True)

        self.target.refresh_from_db()
        second_target.refresh_from_db()

        self.target.auditlog_set.get(
            activity="superuser-granted", params__username=self.actor.username
        )
        self.target.auditlog_set.get(
            activity="sitewide-team-add",
            params__team=self.viewers_group.name,
            params__username=self.actor.username,
        )
        self.target.auditlog_set.get(
            activity="sitewide-team-remove",
            params__team=self.users_group.name,
            params__username=self.actor.username,
        )

        second_target.auditlog_set.get(
            activity="superuser-revoked", params__username=second_actor.username
        )
        second_target.auditlog_set.get(
            activity="sitewide-team-add",
            params__team=self.users_group.name,
            params__username=second_actor.username,
        )
        second_target.auditlog_set.get(
            activity="sitewide-team-remove",
            params__team=self.viewers_group.name,
            params__username=second_actor.username,
        )
