# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from types import SimpleNamespace

from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, TestCase

from weblate.auth.admin import WeblateUserAdmin
from weblate.auth.models import Group, User


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

    def test_save_related_audits_security_changes(self) -> None:
        request = self.factory.post("/")
        request.user = self.actor

        obj = User.objects.get(pk=self.target.pk)
        obj.is_superuser = True
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
