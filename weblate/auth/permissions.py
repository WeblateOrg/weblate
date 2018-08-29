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
from django.db.models import Q

from weblate.machinery import MACHINE_TRANSLATION_SERVICES
from weblate.trans.models import (
    Project, Component, Translation, Unit, ContributorAgreement,
)


SPECIALS = {}


def register_perm(*perms):
    def wrap_perm(function):
        for perm in perms:
            SPECIALS[perm] = function
        return function
    return wrap_perm


def cache_perm(func):
    """Caching for permissions check."""

    def cache_perm_wrapper(user, permission, obj, *args):
        cache_key = (
            func.__name__,
            obj.__class__.__name__,
            obj.pk,
            permission
        )

        # Calculate if not in cache
        if cache_key not in user.perm_cache:
            user.perm_cache[cache_key] = func(user, permission, obj, *args)
        return user.perm_cache[cache_key]

    return cache_perm_wrapper


@cache_perm
def check_permission(user, permission, obj):
    """Generic permission check for base classes"""
    if user.is_superuser:
        return True
    query = user.groups.filter(roles__permissions__codename=permission)
    if isinstance(obj, Project):
        return query.filter(
            projects=obj,
        ).exists()
    elif isinstance(obj, Component):
        return query.filter(
            (Q(projects=obj.project) & Q(componentlist=None)) |
            Q(componentlist__components=obj)
        ).exists()
    elif isinstance(obj, Translation):
        return query.filter(
            (Q(projects=obj.component.project) & Q(componentlist=None)) |
            Q(componentlist__components=obj.component)
        ).filter(
            languages=obj.language
        ).exists()
    else:
        raise ValueError(
            'Not supported type for permission check: {}'.format(
                obj.__class__.__name__
            )
        )


@register_perm('comment.delete', 'suggestion.delete')
@cache_perm
def check_delete_own(user, permission, obj, scope):
    if user.is_authenticated and obj.user == user:
        return True
    return check_permission(user, permission, scope)


@cache_perm
def check_can_edit(user, permission, obj, is_vote=False):
    translation = component = None

    if isinstance(obj, Translation):
        translation = obj
        component = obj.component
    elif isinstance(obj, Component):
        component = obj

    # Email is needed for user to be able to edit
    if user.is_authenticated and not user.email:
        return False

    if component:
        # Check component lock
        if component.locked:
            return False

        # Check contributor agreement
        if (component.agreement and
                not ContributorAgreement.objects.has_agreed(user, component)):
            return False

    # Perform usual permission check
    if not check_permission(user, permission, obj):
        return False

    # Special check for source strings (templates)
    if translation and translation.is_template \
            and not check_permission(user, 'unit.template', obj):
        return False

    # Special check for voting
    if ((is_vote and component and not component.suggestion_voting) or
            (not is_vote and translation and
             component.suggestion_voting and
             component.suggestion_autoaccept > 0 and
             not check_permission(user, 'unit.override', obj))):
        return False

    return True


@register_perm('unit.review')
@cache_perm
def check_unit_review(user, permission, obj):
    project = obj
    if hasattr(project, 'component'):
        project = project.component
    if hasattr(project, 'project'):
        project = project.project
    if not project.enable_review:
        return False
    return check_can_edit(user, permission, obj)


@register_perm('unit.edit', 'suggestion.accept')
@cache_perm
def check_edit_approved(user, permission, obj):
    if isinstance(obj, Unit):
        unit = obj
        obj = unit.translation
        if unit.approved \
                and not check_unit_review(user, 'unit.review', obj):
            return False
    return check_can_edit(user, permission, obj)


@register_perm('unit.add')
@cache_perm
def check_unit_add(user, permission, translation):
    if not translation.is_template:
        return False
    if not translation.component.file_format_cls.can_add_unit:
        return False
    return check_can_edit(user, permission, translation)


@register_perm('suggestion.vote')
@cache_perm
def check_suggestion_vote(user, permission, obj):
    if isinstance(obj, Unit):
        obj = obj.translation
    return check_can_edit(user, permission, obj, True)


@register_perm('suggestion.add')
@cache_perm
def check_suggestion_add(user, permission, translation):
    if not translation.component.enable_suggestions:
        return False
    return check_permission(user, permission, translation)


@register_perm('upload.perform')
@cache_perm
def check_contribute(user, permission, translation):
    return (
        check_can_edit(user, permission, translation)
        and (
            check_edit_approved(user, 'unit.edit', translation)
            or check_suggestion_add(user, 'suggestion.add', translation)
        )
    )


@register_perm('machinery.view')
@cache_perm
def check_machinery(user, permission, obj):
    if not MACHINE_TRANSLATION_SERVICES.exists():
        return False
    if isinstance(obj, Translation) and obj.is_template:
        return False
    return check_contribute(user, permission, obj)


@register_perm('meta:vcs.status')
@cache_perm
def check_repository_status(user, permission, obj):
    return (
        check_permission(user, 'vcs.push', obj)
        or check_permission(user, 'vcs.commit', obj)
        or check_permission(user, 'vcs.reset', obj)
        or check_permission(user, 'vcs.update', obj)
    )


@register_perm('billing:project.permissions')
@cache_perm
def check_billing(user, permission, obj):
    if 'weblate.billing' in settings.INSTALLED_APPS:
        billings = obj.billing_set.filter(plan__change_access_control=True)
        if not billings.exists():
            return False

    return check_permission(user, 'project.permissions', obj)
