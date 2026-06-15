# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from email.errors import HeaderDefect
from email.headerregistry import Address
from operator import attrgetter
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils.translation import gettext
from social_core.backends.utils import load_backends

from weblate.auth.data import (
    GLOBAL_PERM_NAMES,
    GLOBAL_PERMISSIONS,
    GROUPS,
    PERMISSION_NAMES,
    PERMISSIONS,
    ROLES,
    SELECTION_ALL,
)

if TYPE_CHECKING:
    from django.db.models import Prefetch
    from django.utils.safestring import SafeString

    from weblate.auth.models import (
        Group,
        Invitation,
        Permission,
        Role,
        TeamMembership,
        User,
    )
    from weblate.lang.models import Language


def get_ordered_membership_limit_languages(
    membership: TeamMembership | Invitation,
) -> list[Language]:
    return sorted(membership.limit_languages.all(), key=attrgetter("code"))


def prefetch_membership_limit_languages() -> Prefetch:
    # ruff: ignore[import-outside-top-level]
    from django.db.models import Prefetch

    # ruff: ignore[import-outside-top-level]
    from weblate.lang.models import Language

    return Prefetch("limit_languages", queryset=Language.objects.order_by("code"))


def format_membership_limit_language_codes(
    membership: TeamMembership | Invitation,
) -> SafeString:
    # ruff: ignore[import-outside-top-level]
    from weblate.utils.html import format_html_join_comma

    return format_html_join_comma(
        "{}",
        (
            (language.code,)
            for language in get_ordered_membership_limit_languages(membership)
        ),
    )


def get_auth_backends():
    return load_backends(settings.AUTHENTICATION_BACKENDS)


def get_auth_keys() -> set[str]:
    return set(get_auth_backends().keys())


def is_django_permission(permission: str):
    """
    Check whether permission looks is a Django one.

    This is purely based on the list of permissions defined in Weblate.
    """
    return (
        permission not in PERMISSION_NAMES
        and permission not in GLOBAL_PERM_NAMES
        and not permission.startswith(("meta:", "billing:"))
    )


def validate_team_assignable_user(user: User, *, allow_bot: bool = False) -> None:
    """Validate a user can be manually assigned to a team."""
    if user.is_anonymous:
        raise ValidationError(
            gettext("The anonymous user can not be assigned to teams.")
        )
    if not user.is_active:
        raise ValidationError(gettext("Inactive users can not be assigned to teams."))
    if user.is_bot and not allow_bot:
        raise ValidationError(
            gettext("Project tokens can not be assigned to teams here.")
        )


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
        for obj in model.objects.filter(
            internal=True, defining_project=None, defining_workspace=None
        )
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
                defining_workspace=None,
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
