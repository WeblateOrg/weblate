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
    from weblate.auth.models import Group, Permission, Role


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


def migrate_permissions_list(
    model: type[Permission], permissions: tuple[tuple[str, str], ...]
) -> set[int]:
    ids = set()
    # Get all existing permissions
    existing_objects = model.objects.filter(
        codename__in=[perm[0] for perm in permissions]
    )
    existing = {permission.codename: permission for permission in existing_objects}

    # Iterate over expected permissions
    for code, name in permissions:
        try:
            instance = existing[code]
        except KeyError:
            # Missing, create one
            instance = model.objects.create(codename=code, name=name)
        else:
            # Update if needed
            if instance.name != name:
                instance.name = name
                instance.save(update_fields=["name"])
        ids.add(instance.pk)
    return ids


def migrate_permissions(model: type[Permission]) -> None:
    """Create permissions as defined in the data."""
    ids: set[int] = set()
    # Per object permissions
    ids.update(migrate_permissions_list(model, PERMISSIONS))
    # Global permissions
    ids.update(migrate_permissions_list(model, GLOBAL_PERMISSIONS))
    # Delete stale permissions
    model.objects.exclude(id__in=ids).delete()


def migrate_roles(model: type[Role], perm_model: type[Permission]) -> set[str]:
    """Create roles as defined in the data."""
    result = set()
    existing: dict[str, Role] = {obj.name: obj for obj in model.objects.all()}
    for role, permissions in ROLES:
        if role in existing:
            instance = existing[role]
        else:
            instance = model.objects.create(name=role)
            result.add(role)
        instance.permissions.set(
            perm_model.objects.filter(codename__in=permissions), clear=True
        )
    return result


def migrate_groups(
    model: type[Group], role_model: type[Role], update: bool = False
) -> dict[str, Group]:
    """Create groups as defined in the data."""
    result: dict[str, Group] = {
        obj.name: obj
        for obj in model.objects.filter(internal=True, defining_project=None)
    }
    for group, roles, selection in GROUPS:
        if group in result:
            instance = result[group]
            created = False
            if update and (
                instance.project_selection != selection
                or instance.language_selection != SELECTION_ALL
            ):
                instance.project_selection = selection
                instance.language_selection = SELECTION_ALL
                instance.save(update_fields=["project_selection", "language_selection"])
        else:
            instance = model.objects.create(
                name=group,
                internal=True,
                defining_project=None,
                project_selection=selection,
                language_selection=SELECTION_ALL,
            )
            created = True
            result[group] = instance
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
        msg = (
            f"Anonymous user ({settings.ANONYMOUS_USER_NAME}) and could not be created, "
            f"most likely because other user is using noreply@weblate.org e-mail.: {error}"
        )
        raise ValueError(msg) from error
    if user.is_active:
        msg = (
            f"Anonymous user ({settings.ANONYMOUS_USER_NAME}) already exists and is "
            "active, please change the ANONYMOUS_USER_NAME setting or mark the user "
            "as not active in the admin interface."
        )
        raise ValueError(msg)

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
        msg = f"Invalid e-mail address '{email}': {error}"
        raise ValueError(msg) from error
    return str(address)
