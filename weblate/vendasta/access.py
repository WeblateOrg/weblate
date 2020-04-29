# -*- coding: utf-8 -*-
from weblate.auth.models import Group
from weblate.logger import LOGGER


def set_permissions(strategy, backend, user, details, **kwargs):
    """Set permissions for new Vendasta users.

    Add all users to Viewers, add developers to 'Vendasta Internal',
    and add namespaced users to namespace group.
    """
    LOGGER.info("details from api: %s", details)

    groups_to_add = [Group.objects.get(name="Viewers")]

    roles = details.get("roles", [])
    if "developer" in roles:
        groups_to_add.append(Group.objects.get(name="Vendasta Developers"))
    elif "partner" in roles:
        groups_to_add.append(Group.objects.get(name="Partner Users"))

    namespace = details.get("namespace")
    if namespace:
        groups_to_add.append(Group.objects.get_or_create(name=namespace.upper()))

    user.groups.add(*[group for group in groups_to_add if group])
