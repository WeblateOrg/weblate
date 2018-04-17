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
from django import template
import weblate.permissions.helpers

register = template.Library()


@register.simple_tag
def can_upload_translation(user, translation):
    return weblate.permissions.helpers.can_upload_translation(
        user, translation
    )


@register.simple_tag
def can_translate(user, unit=None, translation=None):
    return weblate.permissions.helpers.can_translate(
        user, unit, translation
    )


@register.simple_tag
def can_suggest(user, translation):
    return weblate.permissions.helpers.can_suggest(
        user, translation
    )


@register.simple_tag
def can_review(user, translation):
    return weblate.permissions.helpers.can_review(
        user, translation
    )


@register.simple_tag
def can_add_unit(user, translation):
    return weblate.permissions.helpers.can_add_unit(
        user, translation
    )


@register.simple_tag
def can_accept_suggestion(user, unit):
    return weblate.permissions.helpers.can_accept_suggestion(
        user, unit
    )


@register.simple_tag
def can_delete_suggestion(user, translation, suggestion):
    return weblate.permissions.helpers.can_delete_suggestion(
        user, translation, suggestion
    )


@register.simple_tag
def can_vote_suggestion(user, unit):
    return weblate.permissions.helpers.can_vote_suggestion(
        user, unit
    )


@register.simple_tag
def can_use_mt(user, translation):
    return weblate.permissions.helpers.can_use_mt(user, translation)


@register.simple_tag
def can_see_repository_status(user, project):
    return weblate.permissions.helpers.can_see_repository_status(user, project)


@register.simple_tag
def can_commit_translation(user, project):
    return weblate.permissions.helpers.can_commit_translation(user, project)


@register.simple_tag
def can_update_translation(user, project):
    return weblate.permissions.helpers.can_update_translation(user, project)


@register.simple_tag
def can_push_translation(user, project):
    return weblate.permissions.helpers.can_push_translation(user, project)


@register.simple_tag
def can_reset_translation(user, project):
    return weblate.permissions.helpers.can_reset_translation(user, project)


@register.simple_tag
def can_lock_component(user, project):
    return weblate.permissions.helpers.can_lock_component(user, project)


@register.simple_tag
def can_edit_flags(user, project):
    return weblate.permissions.helpers.can_edit_flags(user, project)


@register.simple_tag
def can_edit_priority(user, project):
    return weblate.permissions.helpers.can_edit_priority(user, project)


@register.simple_tag
def can_ignore_check(user, project):
    return weblate.permissions.helpers.can_ignore_check(user, project)


@register.simple_tag
def can_delete_comment(user, comment):
    return weblate.permissions.helpers.can_delete_comment(user, comment)


@register.simple_tag
def can_manage_acl(user, project):
    return weblate.permissions.helpers.can_manage_acl(user, project)


@register.simple_tag
def can_download_changes(user, project):
    return weblate.permissions.helpers.can_download_changes(user, project)


@register.simple_tag
def can_view_reports(user, project):
    return weblate.permissions.helpers.can_view_reports(user, project)


@register.simple_tag
def can_add_translation(user, project):
    return weblate.permissions.helpers.can_add_translation(user, project)


@register.simple_tag
def can_remove_translation(user, project):
    return weblate.permissions.helpers.can_remove_translation(user, project)


@register.simple_tag
def can_edit_component(user, project):
    return weblate.permissions.helpers.can_edit_component(user, project)


@register.simple_tag
def can_edit_project(user, project):
    return weblate.permissions.helpers.can_edit_project(user, project)


@register.simple_tag
def can_upload_dictionary(user, project):
    return weblate.permissions.helpers.can_upload_dictionary(user, project)


@register.simple_tag
def can_delete_dictionary(user, project):
    return weblate.permissions.helpers.can_delete_dictionary(user, project)


@register.simple_tag
def can_change_dictionary(user, project):
    return weblate.permissions.helpers.can_change_dictionary(user, project)


@register.simple_tag
def can_add_dictionary(user, project):
    return weblate.permissions.helpers.can_add_dictionary(user, project)


@register.simple_tag
def can_add_comment(user, project):
    return weblate.permissions.helpers.can_add_comment(user, project)


@register.simple_tag
def can_overwrite_translation(user, project):
    return weblate.permissions.helpers.can_overwrite_translation(user, project)


@register.simple_tag
def can_see_git_repository(user, project):
    return weblate.permissions.helpers.can_see_git_repository(user, project)


@register.simple_tag
def can_add_screenshot(user, project):
    return weblate.permissions.helpers.can_add_screenshot(user, project)


@register.simple_tag
def can_change_screenshot(user, project):
    return weblate.permissions.helpers.can_change_screenshot(user, project)


@register.simple_tag
def can_delete_screenshot(user, project):
    return weblate.permissions.helpers.can_delete_screenshot(user, project)


@register.simple_tag
def can_edit_access_control(user, project):
    return weblate.permissions.helpers.can_edit_access_control(user, project)
