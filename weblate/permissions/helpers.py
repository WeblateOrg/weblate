# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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
"""
Permissions abstract layer for Weblate.
"""
from django.conf import settings
from django.contrib.auth.models import Permission
from django.db.models import Q
from django.http import Http404

from weblate.accounts.models import get_anonymous
from weblate.permissions.models import GroupACL


def has_group_perm(user, permission, translation=None, project=None):
    """Check whether GroupACL rules allow user to have given permission."""
    if user.is_superuser:
        return True
    if not hasattr(user, 'acl_permissions_groups'):
        user.acl_permissions_groups = {}
    if translation is not None:
        key = ('t', translation.pk)
        groups = GroupACL.objects.filter(
            (Q(language=translation.language) | Q(language=None)) &
            (Q(project=translation.subproject.project) | Q(project=None)) &
            (Q(subproject=translation.subproject) | Q(subproject=None)) &
            (~Q(language=None, project=None, subproject=None))
        )
    elif project is not None:
        key = ('p', project.pk)
        groups = GroupACL.objects.filter(
            project=project, subproject=None, language=None
        )
    else:
        return user.has_perm(permission)

    if key in user.acl_permissions_groups:
        groupacls = user.acl_permissions_groups[key]
    else:
        groupacls = []
        # Force fetching query
        acls = list(groups)
        if acls:
            # more specific rules are more important:
            # subproject > project > language
            acls.sort(reverse=True, key=lambda a: (
                a.subproject is not None,
                a.project is not None,
                a.language is not None))
            for acl in acls:
                groupacls.append((
                    acl.groups.all() & user.groups.all(),
                    acl.permissions.values_list('id', flat=True)
                ))
        user.acl_permissions_groups[key] = groupacls

    # Get permission object
    app, perm = permission.split('.')
    perm_obj = Permission.objects.get(
        content_type__app_label=app,
        codename=perm
    )

    for membership, permissions in groupacls:
        # Does this GroupACL affect this permission?
        if perm_obj.pk not in permissions:
            continue

        # Check if group has asked permission
        return membership.filter(permissions=perm_obj).exists()

    return user.has_perm(permission)


def cache_permission(func):
    """Caching for permissions check."""

    def wrapper(user, *args, **kwargs):
        if user is None:
            user = get_anonymous()
        target_object = None
        if args:
            target_object = args[0]
        elif kwargs:
            target_object = list(kwargs.values())[0]
        if target_object is None:
            obj_key = None
        else:
            obj_key = target_object.get_full_slug()

        if not hasattr(user, 'acl_permissions_cache'):
            user.acl_permissions_cache = {}

        key = (func.__name__, obj_key)

        if key not in user.acl_permissions_cache:
            user.acl_permissions_cache[key] = func(user, *args, **kwargs)

        return user.acl_permissions_cache[key]

    return wrapper


def can_edit(user, translation, permission):
    """Generic checker for changing translation."""
    if translation.subproject.locked:
        return False
    if user.is_authenticated and not user.email:
        return False
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
    """Check whether user can translate given translation.

    This also requires either translate or suggest permission to be able to
    actually store the uploaded translations.
    """
    return can_edit(user, translation, 'trans.upload_translation') and (
        can_translate(user, translation) or can_suggest(user, translation)
    )


@cache_permission
def can_translate(user, translation=None, project=None):
    """Check whether user can translate given translation."""
    if project is not None:
        return has_group_perm(user, 'trans.save_translation', project=project)
    return can_edit(user, translation, 'trans.save_translation')


@cache_permission
def can_suggest(user, translation):
    """Check whether user can add suggestions to given translation."""
    if not translation.subproject.enable_suggestions:
        return False
    if has_group_perm(user, 'trans.add_suggestion', translation):
        return True
    return has_group_perm(
        user, 'trans.add_suggestion', project=translation.subproject.project
    )


@cache_permission
def can_accept_suggestion(user, translation):
    """Check whether user can accept suggestions to given translation."""
    return can_edit(user, translation, 'trans.accept_suggestion')


@cache_permission
def _can_delete_suggestion(user, translation):
    """Check whether user can delete suggestions to given translation."""
    return can_edit(user, translation, 'trans.delete_suggestion')


def can_delete_suggestion(user, translation, suggestion):
    """Check whether user can delete given suggestion."""
    if user.is_authenticated and suggestion.user == user:
        return True
    return _can_delete_suggestion(user, translation)


@cache_permission
def can_vote_suggestion(user, translation):
    """Check whether user can vote suggestions on given translation."""
    if not translation.subproject.suggestion_voting:
        return False
    if translation.subproject.locked:
        return False
    if not has_group_perm(user, 'trans.vote_suggestion', translation):
        return False
    if translation.is_template() \
            and not has_group_perm(user, 'trans.save_template', translation):
        return False
    return True


@cache_permission
def can_use_mt(user, translation):
    """Check whether user can use machine translation."""
    if not settings.MACHINE_TRANSLATION_ENABLED:
        return False
    if not has_group_perm(user, 'trans.use_mt', translation):
        return False
    return can_translate(user, translation) or can_suggest(user, translation)


@cache_permission
def can_see_repository_status(user, project):
    """Check whether user can view repository status."""
    return (
        can_commit_translation(user, project) or
        can_update_translation(user, project)
    )


@cache_permission
def can_commit_translation(user, project):
    """Check whether user can commit to translation repository."""
    return has_group_perm(user, 'trans.commit_translation', project=project)


@cache_permission
def can_update_translation(user, project):
    """Check whether user can update translation repository."""
    return has_group_perm(user, 'trans.update_translation', project=project)


@cache_permission
def can_push_translation(user, project):
    """Check whether user can push translation repository."""
    return has_group_perm(user, 'trans.push_translation', project=project)


@cache_permission
def can_reset_translation(user, project):
    """Check whether user can reset translation repository."""
    return has_group_perm(user, 'trans.reset_translation', project=project)


@cache_permission
def can_lock_translation(user, project):
    """Check whether user can lock translation."""
    return has_group_perm(user, 'trans.lock_translation', project=project)


@cache_permission
def can_lock_subproject(user, project):
    """Check whether user can lock translation subproject."""
    return has_group_perm(user, 'trans.lock_subproject', project=project)


@cache_permission
def can_edit_flags(user, project):
    """Check whether user can edit translation flags."""
    return has_group_perm(user, 'trans.edit_flags', project=project)


@cache_permission
def can_edit_priority(user, project):
    """Check whether user can edit translation priority."""
    return has_group_perm(user, 'trans.edit_priority', project=project)


@cache_permission
def can_ignore_check(user, project):
    """Check whether user can ignore check."""
    return has_group_perm(user, 'trans.ignore_check', project=project)


@cache_permission
def can_delete_comment(user, project):
    """Check whether user can delete comment on given project."""
    return has_group_perm(user, 'trans.delete_comment', project=project)


@cache_permission
def can_manage_acl(user, project):
    """Check whether user can manage ACL on given project."""
    return has_group_perm(user, 'trans.manage_acl', project=project)


@cache_permission
def can_download_changes(user, project):
    """Check whether user can download CSV for changes on given project."""
    return has_group_perm(user, 'trans.download_changes', project=project)


@cache_permission
def can_automatic_translation(user, project):
    """Check whether user can do automatic translation on given project."""
    return has_group_perm(user, 'trans.automatic_translation', project=project)


@cache_permission
def can_view_reports(user, project):
    """Check whether user can view reports on given project."""
    return has_group_perm(user, 'trans.view_reports', project=project)


@cache_permission
def can_author_translation(user, project):
    """Check whether user can author translation on given project."""
    return has_group_perm(user, 'trans.author_translation', project=project)


@cache_permission
def can_overwrite_translation(user, project):
    """Check whether user can overwrite translation on given project."""
    return has_group_perm(user, 'trans.overwrite_translation', project=project)


@cache_permission
def can_add_translation(user, project):
    """Check whether user can add translations on given project."""
    return has_group_perm(user, 'trans.add_translation', project=project)


@cache_permission
def can_mass_add_translation(user, project):
    """Check whether user can mass add translations on given project."""
    return has_group_perm(user, 'trans.mass_add_translation', project=project)


@cache_permission
def can_remove_translation(user, project):
    """Check whether user can view reports on given project."""
    return has_group_perm(user, 'trans.delete_translation', project=project)


@cache_permission
def can_edit_subproject(user, project):
    """Check whether user can edit subprojects on given project."""
    return has_group_perm(user, 'trans.change_subproject', project=project)


@cache_permission
def can_edit_project(user, project):
    """Check whether user can edit given project."""
    return has_group_perm(user, 'trans.change_project', project=project)


@cache_permission
def can_upload_dictionary(user, project):
    """Check whether user can upload dictionary for given project."""
    return has_group_perm(user, 'trans.upload_dictionary', project=project)


@cache_permission
def can_delete_dictionary(user, project):
    """Check whether user can delete dictionary for given project."""
    return has_group_perm(user, 'trans.delete_dictionary', project=project)


@cache_permission
def can_change_dictionary(user, project):
    """Check whether user can change dictionary for given project."""
    return has_group_perm(user, 'trans.change_dictionary', project=project)


@cache_permission
def can_add_dictionary(user, project):
    """Check whether user can add dictionary for given project."""
    return has_group_perm(user, 'trans.add_dictionary', project=project)


@cache_permission
def can_add_comment(user, project):
    """Check whether user can add comment for given project."""
    return has_group_perm(user, 'trans.add_comment', project=project)


@cache_permission
def can_see_git_repository(user, project):
    """Check whether user can add comment for given project."""
    return has_group_perm(
        user, 'trans.can_see_git_repository', project=project
    )


@cache_permission
def can_add_screenshot(user, project):
    """Check whether user can add screenshot for given project."""
    return has_group_perm(user, 'screenshots.add_screenshot', project=project)


@cache_permission
def can_change_screenshot(user, project):
    """Check whether user can change screenshot for given project."""
    return has_group_perm(
        user, 'screenshots.change_screenshot', project=project
    )


@cache_permission
def can_delete_screenshot(user, project):
    """Check whether user can delete screenshot for given project."""
    return has_group_perm(
        user, 'screenshots.delete_screenshot', project=project
    )


@cache_permission
def can_access_vcs(user, project):
    """Check whether user can delete screenshot for given project."""
    return has_group_perm(user, 'trans.access_vcs', project=project)


@cache_permission
def can_access_project(user, project):
    """Check whether user can delete screenshot for given project."""
    return has_group_perm(user, 'trans.access_project', project=project)


def check_access(request, project):
    """Raise an error if user is not allowed to access this project."""
    if not can_access_project(request.user, project):
        raise Http404('Access denied')
