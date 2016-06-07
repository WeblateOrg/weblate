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
from django import template
import weblate.trans.permissions

register = template.Library()


@register.assignment_tag
def can_upload_translation(user, translation):
    return weblate.trans.permissions.can_upload_translation(
        user, translation
    )


@register.assignment_tag
def can_translate(user, translation):
    return weblate.trans.permissions.can_translate(
        user, translation
    )


@register.assignment_tag
def can_suggest(user, translation):
    return weblate.trans.permissions.can_suggest(
        user, translation
    )


@register.assignment_tag
def can_accept_suggestion(user, translation):
    return weblate.trans.permissions.can_accept_suggestion(
        user, translation
    )


@register.assignment_tag
def can_delete_suggestion(user, translation):
    return weblate.trans.permissions.can_delete_suggestion(
        user, translation
    )


@register.assignment_tag
def can_vote_suggestion(user, translation):
    return weblate.trans.permissions.can_vote_suggestion(
        user, translation
    )


@register.assignment_tag
def can_use_mt(user, translation):
    return weblate.trans.permissions.can_use_mt(user, translation)


@register.assignment_tag
def can_see_repository_status(user, project):
    return weblate.trans.permissions.can_see_repository_status(user, project)


@register.assignment_tag
def can_commit_translation(user, project):
    return weblate.trans.permissions.can_commit_translation(user, project)


@register.assignment_tag
def can_update_translation(user, project):
    return weblate.trans.permissions.can_update_translation(user, project)


@register.assignment_tag
def can_push_translation(user, project):
    return weblate.trans.permissions.can_push_translation(user, project)


@register.assignment_tag
def can_reset_translation(user, project):
    return weblate.trans.permissions.can_reset_translation(user, project)


@register.assignment_tag
def can_lock_subproject(user, project):
    return weblate.trans.permissions.can_lock_subproject(user, project)


@register.assignment_tag
def can_edit_flags(user, project):
    return weblate.trans.permissions.can_edit_flags(user, project)


@register.assignment_tag
def can_edit_priority(user, project):
    return weblate.trans.permissions.can_edit_priority(user, project)


@register.assignment_tag
def can_ignore_check(user, project):
    return weblate.trans.permissions.can_ignore_check(user, project)


@register.assignment_tag
def can_delete_comment(user, project):
    return weblate.trans.permissions.can_delete_comment(user, project)


@register.assignment_tag
def can_manage_acl(user, project):
    return weblate.trans.permissions.can_manage_acl(user, project)


@register.assignment_tag
def can_download_changes(user, project):
    return weblate.trans.permissions.can_download_changes(user, project)


@register.assignment_tag
def can_view_reports(user, project):
    return weblate.trans.permissions.can_view_reports(user, project)


@register.assignment_tag
def can_add_translation(user, project):
    return weblate.trans.permissions.can_add_translation(user, project)
