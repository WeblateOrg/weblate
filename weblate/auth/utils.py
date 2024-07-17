# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from email.errors import HeaderDefect
from email.headerregistry import Address
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError

from weblate.auth.data import (
    GLOBAL_PERMISSIONS,
    GROUPS,
    PERMISSIONS,
    ROLES,
    SELECTION_ALL,
)

if TYPE_CHECKING:
    from weblate.auth.models import Group, Role


def is_django_permission(permission: str):
    """
    Check whether permission looks like a Django one.

    Django permissions are <app>.<action>_<model>, while
    Weblate ones are <scope>.<action> where action lacks underscores
    with single exception of "add_more".
    """
    parts = permission.split(".", 1)
    if len(parts) != 2:
        return False
    return "_" in parts[1] and parts[1] != "add_more"


def migrate_permissions_list(model, permissions):
    ids = set()
    # Update/create permissions
    for code, name in permissions:
        instance, created = model.objects.get_or_create(
            codename=code, defaults={"name": name}
        )
        ids.add(instance.pk)
        if not created and instance.name != name:
            instance.name = name
            instance.save(update_fields=["name"])
    return ids


def migrate_permissions(model) -> None:
    """Create permissions as defined in the data."""
    ids = set()
    # Per object permissions
    ids.update(migrate_permissions_list(model, PERMISSIONS))
    # Global permissions
    ids.update(migrate_permissions_list(model, GLOBAL_PERMISSIONS))
    # Delete stale permissions
    model.objects.exclude(id__in=ids).delete()


def migrate_roles(model, perm_model) -> set[str]:
    """Create roles as defined in the data."""
    result = set()
    for role, permissions in ROLES:
        instance, created = model.objects.get_or_create(name=role)
        if created:
            result.add(role)
        instance.permissions.set(
            perm_model.objects.filter(codename__in=permissions), clear=True
        )
    return result


def migrate_groups(
    model: type[Group], role_model: type[Role], update: bool = False
) -> dict[str, Group]:
    """Create groups as defined in the data."""
    result: dict[str, Group] = {}
    for group, roles, selection in GROUPS:
        instance, created = model.objects.get_or_create(
            name=group,
            internal=True,
            defining_project=None,
            defaults={
                "project_selection": selection,
                "language_selection": SELECTION_ALL,
            },
        )
        result[group] = instance
        if update and not created:
            instance.project_selection = selection
            instance.language_selection = SELECTION_ALL
            instance.save()
        if created or update:
            instance.roles.set(role_model.objects.filter(name__in=roles), clear=True)
    return result


def create_anonymous(model, group_model, update=True) -> None:
    try:
        user, created = model.objects.get_or_create(
            username=settings.ANONYMOUS_USER_NAME,
            defaults={
                "full_name": "Anonymous",
                "email": "noreply@weblate.org",
                "is_active": False,
                "password": make_password(None),
            },
        )
    except IntegrityError as error:
        raise ValueError(
            f"Anonymous user ({settings.ANONYMOUS_USER_NAME}) and could not be created, "
            f"most likely because other user is using noreply@weblate.org e-mail.: {error}"
        ) from error
    if user.is_active:
        raise ValueError(
            f"Anonymous user ({settings.ANONYMOUS_USER_NAME}) already exists and is "
            "active, please change the ANONYMOUS_USER_NAME setting or mark the user "
            "as not active in the admin interface."
        )

    if created or update:
        user.set_unusable_password()
        user.save()
        user.groups.set(
            group_model.objects.filter(name__in=("Guests", "Viewers")), clear=True
        )


def format_address(display_name: str, email: str) -> str:
    """Format e-mail address with display name."""
    # While Address does quote the name following RFC 5322,
    # git still doesn't like <> being used in the string
    try:
        address = Address(
            display_name=display_name.replace("<", "").replace(">", ""),
            addr_spec=email,
        )
    except HeaderDefect as error:
        raise ValueError(f"Invalid e-mail address '{email}': {error}") from error
    return str(address)
