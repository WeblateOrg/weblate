# -*- coding: utf-8 -*-
from weblate.auth.models import Group


def set_permissions(strategy, backend, user, details, **kwargs):
    """
    Add all users to Viewers, add developers to 'Vendasta Internal', and add namespaced users to namespace group.
    """
    groups_to_add = [Group.objects.get('Viewers')]

    roles = details.get('roles', [])
    if 'developer' in roles:
        groups_to_add.append(Group.objects.get(name='Vendasta Internal'))
    if 'partner' in roles:
        groups_to_add.append(Group.objects.get(name='Partner Users'))

    namespace = details.get('namespace')
    if namespace:
        groups_to_add.append(Group.objects.get_or_create(name=namespace.upper()))

    user.groups.add(*[group for group in groups_to_add if group])
