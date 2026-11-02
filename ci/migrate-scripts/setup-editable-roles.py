# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from weblate.auth.models import Group, Permission, Role

role = Role.objects.get(name="Access repository")
team = Group.objects.create(name="Role migration assignment")
team.roles.add(role)
custom = Role.objects.create(name="Role migration custom")
custom.permissions.set(Permission.objects.filter(codename="comment.add"))
# Persist original primary keys across the checkout to verify identity preservation.
team.name = f"Role migration assignment {role.pk}:{custom.pk}"
team.save()

# Preserve a local default-team role assignment through visibility upgrades.
users = Group.objects.get(name="Users", internal=True)
users.roles.add(custom)


for name in ("Discover users", "View user profiles"):
    collision = Role.objects.create(name=name)
    collision.permissions.set(Permission.objects.filter(codename="comment.add"))
    Role.objects.create(name=f"{name} (custom)")
    collision_team = Group.objects.create(name=f"Visibility collision {collision.pk}")
    collision_team.roles.add(collision)
