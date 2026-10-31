# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import sys
from importlib import import_module, invalidate_caches
from io import StringIO
from pathlib import Path
from runpy import run_path
from shutil import copytree, ignore_patterns
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.apps import apps
from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.loader import MigrationLoader
from django.test import RequestFactory, TestCase

from weblate.auth.admin import RoleAdmin
from weblate.auth.data import ROLES
from weblate.auth.models import Group, Permission, Role, User
from weblate.auth.utils import migrate_roles

migration = import_module("weblate.auth.migrations.0014_editable_builtin_roles")


class RoleMergeTest(TestCase):
    def test_merge(self) -> None:
        role = Role.objects.get(name="Access repository")
        group = Group.objects.create(name="Merge assignment")
        group.roles.add(role)
        custom = Role.objects.create(name="Independent")
        custom.permissions.set(Permission.objects.filter(codename="comment.add"))
        cases = [
            (
                {"vcs.access"},
                {"vcs.access", "comment.add"},
                {"vcs.access", "vcs.view"},
                {"vcs.access", "vcs.view", "comment.add"},
            ),
            (
                {"vcs.access", "vcs.view"},
                {"vcs.access"},
                {"vcs.access", "vcs.view", "comment.add"},
                {"vcs.access", "comment.add"},
            ),
            (
                {"vcs.access", "vcs.view"},
                {"vcs.access", "vcs.view", "comment.add"},
                {"vcs.access"},
                {"vcs.access", "comment.add"},
            ),
            ({"vcs.access"}, set(), set(), set()),
            (set(), {"comment.add"}, {"comment.add"}, {"comment.add"}),
        ]
        for old, local, new, expected in cases:
            with self.subTest(old=old, local=local, new=new):
                role.permissions.set(Permission.objects.filter(codename__in=local))
                with (
                    patch.object(migration, "OLD_DEFAULTS", {role.name: old}),
                    patch.object(migration, "NEW_DEFAULTS", {role.name: new}),
                    connection.schema_editor() as editor,
                ):
                    migration.merge_roles(apps, editor)
                    migration.merge_roles(apps, editor)
                self.assertEqual(
                    set(role.permissions.values_list("codename", flat=True)), expected
                )
        self.assertTrue(group.roles.filter(pk=role.pk).exists())
        self.assertEqual(
            list(custom.permissions.values_list("codename", flat=True)), ["comment.add"]
        )

    def test_new_permissions_and_roles(self) -> None:
        historical = (
            MigrationLoader(connection)
            .project_state([("weblate_auth", "0013_cleanup_bot_memberships")])
            .apps
        )
        with (
            patch.object(migration, "OLD_DEFAULTS", {}),
            patch.object(
                migration, "NEW_DEFAULTS", {"New built-in": ["new.permission"]}
            ),
            patch.object(
                migration, "PERMISSION_LABELS", {"new.permission": "New permission"}
            ),
            connection.schema_editor() as editor,
        ):
            migration.merge_roles(historical, editor)
        role = Role.objects.get(name="New built-in")
        self.assertEqual(
            list(role.permissions.values_list("codename", flat=True)),
            ["new.permission"],
        )

    def test_generated_migration(self) -> None:
        command_module = "weblate.auth.management.commands.generate_role_migration"
        source_file = migration.__file__
        assert source_file is not None
        with TemporaryDirectory() as directory:
            snapshot = Path(directory) / "0014_editable_builtin_roles.py"
            snapshot.write_text(Path(source_file).read_text(encoding="utf-8"))
            with (
                patch.object(migration, "__file__", str(snapshot)),
                patch(
                    f"{command_module}.ROLES", [*ROLES, ("New role", {"comment.add"})]
                ),
            ):
                call_command("generate_role_migration", stdout=StringIO())
            generated = Path(directory) / "0015_update_builtin_roles.py"
            namespace = run_path(str(generated))
            self.assertEqual(namespace["OLD_DEFAULTS"], migration.NEW_DEFAULTS)
            self.assertEqual(namespace["NEW_DEFAULTS"]["New role"], ["comment.add"])
            with connection.schema_editor() as editor:
                namespace["merge_roles"](apps, editor)
            self.assertTrue(
                Role.objects.filter(
                    name="New role", permissions__codename="comment.add"
                ).exists()
            )

    def test_consecutive_generated_upgrades(self) -> None:
        command_module = "weblate.auth.management.commands.generate_role_migration"
        source_file = migration.__file__
        assert source_file is not None
        package = "role_upgrade_migrations"
        baseline = ("weblate_auth", "0014_editable_builtin_roles")
        first = ("weblate_auth", "0015_update_builtin_roles")
        second = ("weblate_auth", "0016_update_builtin_roles")
        role_name = "Access repository"
        defaults_b = {name: set(permissions) for name, permissions in ROLES}
        defaults_b[role_name] = {"vcs.access", "translation.download", "unit.edit"}
        defaults_c = {
            **defaults_b,
            role_name: defaults_b[role_name] | {"vcs.view", "suggestion.add"},
        }
        with TemporaryDirectory() as directory:
            copytree(
                Path(source_file).parent,
                Path(directory) / package,
                ignore=ignore_patterns("__pycache__"),
            )
            try:
                with (
                    patch.object(sys, "path", [directory, *sys.path]),
                    patch.dict(sys.modules),
                    self.settings(
                        MIGRATION_MODULES={
                            **settings.MIGRATION_MODULES,
                            "weblate_auth": package,
                        }
                    ),
                ):
                    for defaults in (defaults_b, defaults_c):
                        invalidate_caches()
                        with patch(f"{command_module}.ROLES", list(defaults.items())):
                            call_command("generate_role_migration", stdout=StringIO())
                            invalidate_caches()
                            call_command(
                                "generate_role_migration", check=True, stdout=StringIO()
                            )
                    loader = MigrationLoader(None)
                    first_module = import_module(f"{package}.{first[1]}")
                    second_module = import_module(f"{package}.{second[1]}")
                    self.assertEqual(first_module.OLD_DEFAULTS, migration.NEW_DEFAULTS)
                    self.assertEqual(
                        first_module.NEW_DEFAULTS, second_module.OLD_DEFAULTS
                    )
                    self.assertEqual(
                        loader.disk_migrations[first].dependencies, [baseline]
                    )
                    self.assertEqual(
                        loader.disk_migrations[second].dependencies, [first]
                    )
                    self.assertEqual(
                        loader.graph.forwards_plan(second)[-2:], [first, second]
                    )
                    for edit_between in (False, True):
                        with self.subTest(edit_between=edit_between):
                            self.assert_upgrade_sequence(
                                loader,
                                edit_between=edit_between,
                                defaults_b=defaults_b,
                                defaults_c=defaults_c,
                            )
            finally:
                invalidate_caches()

    def assert_upgrade_sequence(
        self,
        loader: MigrationLoader,
        *,
        edit_between: bool,
        defaults_b: dict[str, set[str]],
        defaults_c: dict[str, set[str]],
    ) -> None:
        baseline = ("weblate_auth", "0014_editable_builtin_roles")
        first = ("weblate_auth", "0015_update_builtin_roles")
        second = ("weblate_auth", "0016_update_builtin_roles")
        role_name = "Access repository"
        state = loader.project_state([baseline])
        historical_role = state.apps.get_model("weblate_auth", "Role")
        historical_permission = state.apps.get_model("weblate_auth", "Permission")
        role = historical_role.objects.get(name=role_name)
        role_id = role.pk
        role.permissions.set(
            historical_permission.objects.filter(
                codename__in={"vcs.access", "comment.add"}
            )
        )
        group = Group.objects.create(name=f"Upgrade assignment {edit_between}")
        group.roles.add(role_id)
        custom = Role.objects.create(name=f"Independent upgrade {edit_between}")
        custom.permissions.set(Permission.objects.filter(codename="comment.resolve"))
        with connection.schema_editor() as editor:
            state = loader.disk_migrations[first].apply(state, editor)
        expected = {"vcs.access", "unit.edit", "comment.add"}
        self.assertEqual(
            set(role.permissions.values_list("codename", flat=True)),
            expected,
        )
        self.assertEqual(Role.objects.get(name=role_name).pk, role_id)
        self.assertEqual(list(group.roles.values_list("pk", flat=True)), [role_id])
        self.assertEqual(
            list(custom.permissions.values_list("codename", flat=True)),
            ["comment.resolve"],
        )
        if edit_between:
            with patch("weblate.auth.utils.ROLES", list(defaults_b.items())):
                migrate_roles(Role, Permission)
            self.assertEqual(
                set(role.permissions.values_list("codename", flat=True)), expected
            )
            role.permissions.remove(
                historical_permission.objects.get(codename="unit.edit")
            )
            role.permissions.add(
                historical_permission.objects.get(codename="comment.delete")
            )
            expected = {
                "vcs.access",
                "comment.add",
                "comment.delete",
            }
        with connection.schema_editor() as editor:
            loader.disk_migrations[second].apply(state, editor)
        expected |= {"vcs.view", "suggestion.add"}
        self.assertEqual(
            set(role.permissions.values_list("codename", flat=True)),
            expected,
        )
        with patch("weblate.auth.utils.ROLES", list(defaults_c.items())):
            migrate_roles(Role, Permission)
        self.assertEqual(
            set(role.permissions.values_list("codename", flat=True)),
            expected,
        )
        self.assertEqual(Role.objects.get(name=role_name).pk, role_id)
        self.assertEqual(
            list(group.roles.values_list("pk", flat=True)),
            [role_id],
        )
        self.assertEqual(
            list(custom.permissions.values_list("codename", flat=True)),
            ["comment.resolve"],
        )

    def test_bootstrap_and_post_migrate(self) -> None:
        role = Role.objects.get(name="Access repository")
        role.permissions.clear()
        with connection.schema_editor() as editor:
            migration.merge_roles(apps, editor)
        self.assertFalse(role.is_customized)
        role.permissions.clear()
        migrate_roles(Role, Permission)
        self.assertTrue(role.is_customized)
        self.assertFalse(role.permissions.exists())
        role.reset_permissions()
        self.assertFalse(role.is_customized)

    def test_generator_check(self) -> None:
        call_command("generate_role_migration", check=True, stdout=StringIO())
        with (
            patch(
                "weblate.auth.management.commands.generate_role_migration.ROLES",
                [*ROLES, ("New role", {"comment.add"})],
            ),
            self.assertRaises(CommandError),
        ):
            call_command("generate_role_migration", check=True)

    def test_admin_prefetches_permissions(self) -> None:
        admin = RoleAdmin(Role, AdminSite())
        with self.assertNumQueries(2):
            roles = list(admin.get_queryset(RequestFactory().get("/")))
            self.assertTrue(roles)
            self.assertFalse(any(role.is_customized for role in roles))

    def test_admin_permissions_and_reset(self) -> None:
        admin = RoleAdmin(Role, AdminSite())
        role = Role.objects.get(name="Access repository")
        user = User.objects.create_superuser(
            "role-admin", "role-admin@example.com", "password"
        )
        request = RequestFactory().get("/")
        request.user = user
        self.assertTrue(admin.has_change_permission(request, role))
        self.assertFalse(admin.has_delete_permission(request, role))
        self.assertEqual(admin.get_readonly_fields(request, role), ("name",))
        self.assertTrue(
            admin.get_deleted_objects(Role.objects.filter(pk=role.pk), request)[3]
        )
        self.client.force_login(user)
        url = "/admin/weblate_auth/role/"
        response = self.client.post(
            f"{url}{role.pk}/change/",
            {
                "permissions": [Permission.objects.get(codename="comment.add").pk],
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        role.refresh_from_db()
        self.assertEqual(role.name, "Access repository")
        self.assertEqual(
            list(role.permissions.values_list("codename", flat=True)), ["comment.add"]
        )
        response = self.client.post(
            url,
            {"action": "delete_selected", "_selected_action": [role.pk], "post": "yes"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Role.objects.filter(pk=role.pk).exists())
        response = self.client.post(
            url, {"action": "reset_permissions", "_selected_action": [role.pk]}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(role.is_customized)
        response = self.client.post(
            url,
            {
                "action": "reset_permissions",
                "_selected_action": [role.pk],
                "confirm": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(role.is_customized)
