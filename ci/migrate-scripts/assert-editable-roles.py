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
