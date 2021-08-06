# -*- coding: utf-8 -*-
from weblate.auth.models import Group, Role
from weblate.logger import LOGGER
from weblate.vendasta.constants import (
    ACCESS_NAMESPACE,
    PARTNER_USERS,
    VENDASTA_DEVELOPERS,
    VIEW_PARTNER_LANGUAGES,
    VIEW_PUBLIC_LANGUAGES,
)


def set_permissions(strategy, backend, user, details, **kwargs):
    """Set permissions for new Vendasta users.

    Add all users to Viewers, add developers to 'Vendasta Internal',
    and add namespaced users to namespace group.
    """
    LOGGER.info("details from api: %s", details)

    groups_to_add = [Group.objects.get(name="Viewers")]

    roles = details.get("roles", [])
    if "developer" in roles:
        groups_to_add.append(Group.objects.get(name=VENDASTA_DEVELOPERS))
    elif "partner" in roles:
        groups_to_add.append(Group.objects.get(name=PARTNER_USERS))
        groups_to_add.append(Group.objects.get(name=VIEW_PARTNER_LANGUAGES))
    else:
        groups_to_add.append(Group.objects.get(name=VIEW_PUBLIC_LANGUAGES))

    namespace = details.get("namespace")
    if namespace:
        groups_to_add.append(get_or_create_namespace_group(namespace.upper()))

    user.groups.add(*[group for group in groups_to_add if group])


def get_or_create_namespace_group(namespace):
    """Ensure the existence of a group for a namespace, and return it.

    get_or_create returns a Group if successful, or a tuple of type (Group, bool)
    if it must create a new Group.
    """
    namespace_group = Group.objects.get_or_create(name=namespace.upper())
    if isinstance(namespace_group, tuple):
        namespace_group = namespace_group[0]

    namespace_group.roles.add(Role.objects.get(name='Translate'))
    access_namespace_role = Role.objects.get_or_create(name=ACCESS_NAMESPACE)
    if isinstance(access_namespace_role, tuple):
        access_namespace_role = access_namespace_role[0]
    namespace_group.roles.add(access_namespace_role)

    return namespace_group
