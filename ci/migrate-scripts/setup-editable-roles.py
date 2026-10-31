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
