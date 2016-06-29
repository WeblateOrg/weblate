# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
"""
Permissions abstract layer for Weblate.
"""
from django.db.models import Q
from django.contrib.auth.models import Group, User, Permission

from weblate import appsettings
from weblate.trans.models.group_acl import GroupACL


def check_owner(user, project, permission):
    """
    Checks whether owner group has given permission.
    """
    if project is None:
        return False
    if not project.owners.filter(id=user.id).exists():
        return False
    group = Group.objects.get(name='Owners')
    app, perm = permission.split('.')
    return group.permissions.filter(
        content_type__app_label=app, codename=perm
    ).exists()


def has_group_perm(user, permission, translation=None, project=None):
    """
    Checks whether GroupACL rules allow user to have
    given permission.
    """
    if translation is not None:
        acls = list(GroupACL.objects.filter(
            (Q(language=translation.language) | Q(language=None)) &
            (Q(project=translation.subproject.project) | Q(project=None)) &
            (Q(subproject=translation.subproject) | Q(subproject=None)) &
            (~Q(language=None, project=None, subproject=None))
        ))
    elif project is not None:
        acls = list(GroupACL.objects.filter(
            project=project, subproject=None, language=None
        ))
    else:
        return False

    if not acls:
        return user.has_perm(permission)

    # more specific rules are more important: subproject > project > language
    acls.sort(reverse=True, key=lambda a: (
        a.subproject is not None,
        a.project is not None,
        a.language is not None))

    membership = acls[0].groups.all() & user.groups.all()
    if not membership.exists():
        return False

    app, perm = permission.split('.')
    return Permission.objects.filter(
        group__in=membership,
        content_type__app_label=app,
        codename=perm
    ).exists()


def check_permission(user, project, permission):
    """
    Generic check for permission with owner fallback.
    """
    return (
        has_group_perm(user, permission, project=project) or
        check_owner(user, project, permission) or
        user.has_perm(permission)
    )


def cache_permission(func):
    """
    Caching for permissions check.
    """

    def wrapper(user, target_object):
        if user is None:
            user = User.objects.get(
                username=appsettings.ANONYMOUS_USER_NAME,
            )
        if target_object is None:
            obj_key = None
        else:
            obj_key = target_object.get_full_slug()

        if not hasattr(user, 'acl_permissions_cache'):
            user.acl_permissions_cache = {}

        key = (func.__name__, obj_key)

        if key not in user.acl_permissions_cache:
            user.acl_permissions_cache[key] = func(user, target_object)

        return user.acl_permissions_cache[key]

    return wrapper


def can_edit(user, translation, permission):
    """
    Generic checker for changing translation.
    """
    if translation.subproject.locked:
        return False
    if user.is_authenticated() and not user.email:
        return False
    if check_owner(user, translation.subproject.project, permission):
        return True
    if not has_group_perm(user, permission, translation):
        return False
    if translation.is_template() \
            and not has_group_perm(user, 'trans.save_template', translation):
        return False
    if (not has_group_perm(user, 'trans.override_suggestion', translation) and
            translation.subproject.suggestion_voting and
            translation.subproject.suggestion_autoaccept > 0):
        return False
    return True


@cache_permission
def can_upload_translation(user, translation):
    """
    Checks whether user can translate given translation.
    """
    return can_edit(user, translation, 'trans.upload_translation')


@cache_permission
def can_translate(user, translation):
    """
    Checks whether user can translate given translation.
    """
    return can_edit(user, translation, 'trans.save_translation')


@cache_permission
def can_suggest(user, translation):
    """
    Checks whether user can add suggestions to given translation.
    """
    if not translation.subproject.enable_suggestions:
        return False
    if has_group_perm(user, 'trans.add_suggestion', translation):
        return True
    return check_permission(
        user, translation.subproject.project, 'trans.add_suggestion'
    )


@cache_permission
def can_accept_suggestion(user, translation):
    """
    Checks whether user can accept suggestions to given translation.
    """
    return can_edit(user, translation, 'trans.accept_suggestion')


@cache_permission
def can_delete_suggestion(user, translation):
    """
    Checks whether user can delete suggestions to given translation.
    """
    return can_edit(user, translation, 'trans.delete_suggestion')


@cache_permission
def can_vote_suggestion(user, translation):
    """
    Checks whether user can vote suggestions on given translation.
    """
    if not translation.subproject.suggestion_voting:
        return False
    if translation.subproject.locked:
        return False
    project = translation.subproject.project
    if check_owner(user, project, 'trans.vote_suggestion'):
        return True
    if not has_group_perm(user, 'trans.vote_suggestion', translation):
        return False
    if translation.is_template() \
            and not has_group_perm(user, 'trans.save_template', translation):
        return False
    return True


@cache_permission
def can_use_mt(user, translation):
    """
    Checks whether user can use machine translation.
    """
    if not appsettings.MACHINE_TRANSLATION_ENABLED:
        return False
    if not has_group_perm(user, 'trans.use_mt', translation):
        return False
    if check_owner(user, translation.subproject.project, 'trans.use_mt'):
        return True
    return can_translate(user, translation) or can_suggest(user, translation)


@cache_permission
def can_see_repository_status(user, project):
    """
    Checks whether user can view repository status.
    """
    return (
        can_commit_translation(user, project) or
        can_update_translation(user, project)
    )


@cache_permission
def can_commit_translation(user, project):
    """
    Checks whether user can commit to translation repository.
    """
    return check_permission(user, project, 'trans.commit_translation')


@cache_permission
def can_update_translation(user, project):
    """
    Checks whether user can update translation repository.
    """
    return check_permission(user, project, 'trans.update_translation')


@cache_permission
def can_push_translation(user, project):
    """
    Checks whether user can push translation repository.
    """
    return check_permission(user, project, 'trans.push_translation')


@cache_permission
def can_reset_translation(user, project):
    """
    Checks whether user can reset translation repository.
    """
    return check_permission(user, project, 'trans.reset_translation')


@cache_permission
def can_lock_translation(user, project):
    """
    Checks whether user can lock translation.
    """
    return check_permission(user, project, 'trans.lock_translation')


@cache_permission
def can_lock_subproject(user, project):
    """
    Checks whether user can lock translation subproject.
    """
    return check_permission(user, project, 'trans.lock_subproject')


@cache_permission
def can_edit_flags(user, project):
    """
    Checks whether user can edit translation flags.
    """
    return check_permission(user, project, 'trans.edit_flags')


@cache_permission
def can_edit_priority(user, project):
    """
    Checks whether user can edit translation priority.
    """
    return check_permission(user, project, 'trans.edit_priority')


@cache_permission
def can_ignore_check(user, project):
    """
    Checks whether user can ignore check.
    """
    return check_permission(user, project, 'trans.ignore_check')


@cache_permission
def can_delete_comment(user, project):
    """
    Checks whether user can delete comment on given project.
    """
    return check_permission(user, project, 'trans.delete_comment')


@cache_permission
def can_manage_acl(user, project):
    """
    Checks whether user can manage ACL on given project.
    """
    return check_permission(user, project, 'trans.manage_acl')


@cache_permission
def can_download_changes(user, project):
    """
    Checks whether user can download CSV for changes on given project.
    """
    return check_permission(user, project, 'trans.download_changes')


@cache_permission
def can_automatic_translation(user, project):
    """
    Checks whether user can do automatic translation on given project.
    """
    return check_permission(user, project, 'trans.automatic_translation')


@cache_permission
def can_view_reports(user, project):
    """
    Checks whether user can view reports on given project.
    """
    return check_permission(user, project, 'trans.view_reports')


@cache_permission
def can_author_translation(user, project):
    """
    Checks whether user can author translation on given project.
    """
    return check_permission(user, project, 'trans.author_translation')


@cache_permission
def can_overwrite_translation(user, project):
    """
    Checks whether user can overwrite translation on given project.
    """
    return check_permission(user, project, 'trans.overwrite_translation')


@cache_permission
def can_add_translation(user, project):
    """
    Checks whether user can view reports on given project.
    """
    return check_permission(user, project, 'trans.add_translation')
