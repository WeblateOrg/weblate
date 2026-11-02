# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.core.management import call_command

from weblate.auth.data import ROLES
from weblate.auth.models import Group, Role

team = Group.objects.get(name__startswith="Role migration assignment ")
role_id, custom_id = map(int, team.name.rsplit(" ", 1)[1].split(":"))
role = Role.objects.get(pk=role_id)
assert role.name == "Access repository"
assert team.roles.filter(pk=role_id).exists()
assert set(role.permissions.values_list("codename", flat=True)) == set(
    dict(ROLES)[role.name]
)
custom = Role.objects.get(pk=custom_id, name="Role migration custom")
assert list(custom.permissions.values_list("codename", flat=True)) == ["comment.add"]
role.permissions.clear()
call_command("migrate", verbosity=0)
assert not role.permissions.exists()
assert team.roles.filter(pk=role_id).exists()

users = Group.objects.get(name="Users", internal=True)
assert users.roles.filter(pk=custom_id).exists()
assert users.roles.filter(name="Power user").exists()
assert users.roles.filter(name="Discover users").exists()
assert users.roles.filter(name="View user profiles").exists()
assert (
    Group.objects.get(name="Guests", internal=True)
    .roles.filter(name="View user profiles")
    .exists()
)
assert set(
    Role.objects.get(name="Discover users").permissions.values_list(
        "codename", flat=True
    )
) == {"user.browse", "user.search"}
assert set(
    Role.objects.get(name="View user profiles").permissions.values_list(
        "codename", flat=True
    )
) == {"user.profile"}


for collision_team in Group.objects.filter(name__startswith="Visibility collision "):
    role_id = int(collision_team.name.rsplit(" ", 1)[1])
    collision = collision_team.roles.get(pk=role_id)
    assert collision.name in {
        "Discover users (custom 2)",
        "View user profiles (custom 2)",
    }
    assert list(collision.permissions.values_list("codename", flat=True)) == [
        "comment.add"
    ]
