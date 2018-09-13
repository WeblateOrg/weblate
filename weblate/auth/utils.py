# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
from __future__ import unicode_literals

from django.conf import settings
from django.contrib.auth.hashers import make_password

from weblate.auth.data import PERMISSIONS, ROLES, GROUPS, SELECTION_ALL


def migrate_permissions(model):
    """Create permissions as defined in the data."""
    for code, name in PERMISSIONS:
        instance, created = model.objects.get_or_create(
            codename=code,
            defaults={'name': name}
        )
        if not created and instance.name != name:
            instance.name = name
            instance.save(update_fields=['name'])


def migrate_roles(model, perm_model):
    """Create roles as defined in the data."""
    result = False
    for role, permissions in ROLES:
        instance, created = model.objects.get_or_create(
            name=role
        )
        result |= created
        instance.permissions.set(
            perm_model.objects.filter(codename__in=permissions),
            clear=True
        )
    return result


def migrate_groups(model, role_model, update=False):
    """Create groups as defined in the data."""
    for group, roles, selection in GROUPS:
        defaults = {
            'internal': True,
            'project_selection': selection,
            'language_selection': SELECTION_ALL,
        }
        instance, created = model.objects.get_or_create(
            name=group,
            defaults=defaults,
        )
        if created or update:
            instance.roles.set(
                role_model.objects.filter(name__in=roles),
                clear=True
            )
        if update:
            for key, value in defaults.items():
                setattr(instance, key, value)
            instance.save()


def create_anonymous(model, group_model, update=True):
    user, created = model.objects.get_or_create(
        username=settings.ANONYMOUS_USER_NAME,
        defaults={
            'full_name': 'Anonymous',
            'email': 'noreply@weblate.org',
            'is_active': False,
            'password': make_password(None),
        }
    )
    if user.is_active:
        raise ValueError(
            'Anonymous user ({}) already exists and enabled, '
            'please change ANONYMOUS_USER_NAME setting.'.format(
                settings.ANONYMOUS_USER_NAME,
            )
        )

    if created or update:
        user.set_unusable_password()
        user.save()
        user.groups.set(
            group_model.objects.filter(name__in=('Guests', 'Viewers')),
            clear=True
        )
