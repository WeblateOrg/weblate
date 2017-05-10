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
"""Definition of default groups."""

from __future__ import unicode_literals
from django.utils.translation import pgettext


ADMIN_PERMS = {
    'author_translation',
    'upload_translation',
    'overwrite_translation',
    'commit_translation',
    'update_translation',
    'push_translation',
    'automatic_translation',
    'save_translation',
    'save_template',
    'accept_suggestion',
    'vote_suggestion',
    'override_suggestion',
    'delete_comment',
    'delete_suggestion',
    'ignore_check',
    'upload_dictionary',
    'add_dictionary',
    'change_dictionary',
    'delete_dictionary',
    'lock_subproject',
    'reset_translation',
    'lock_translation',
    'can_see_git_repository',
    'add_comment',
    'delete_comment',
    'add_suggestion',
    'use_mt',
    'edit_priority',
    'edit_flags',
    'manage_acl',
    'download_changes',
    'view_reports',
    'add_translation',
    'mass_add_translation',
    'delete_translation',
    'change_subproject',
    'change_project',
    'add_screenshot',
    'delete_screenshot',
    'change_screenshot',
    'access_vcs',
    'access_project',
}


DEFAULT_GROUPS = {
    'Guests': {
        'access_project',
        'can_see_git_repository',
        'add_suggestion',
        'access_vcs',
    },
    'Users': {
        'access_project',
        'upload_translation',
        'overwrite_translation',
        'save_translation',
        'save_template',
        'accept_suggestion',
        'delete_suggestion',
        'vote_suggestion',
        'ignore_check',
        'upload_dictionary',
        'add_dictionary',
        'change_dictionary',
        'delete_dictionary',
        'lock_translation',
        'can_see_git_repository',
        'add_comment',
        'add_suggestion',
        'use_mt',
        'add_translation',
        'delete_translation',
        'access_vcs',
    },
    'Managers': ADMIN_PERMS,
    '@Translate': {
        'access_project',
        'upload_translation',
        'overwrite_translation',
        'save_translation',
        'accept_suggestion',
        'delete_suggestion',
        'vote_suggestion',
        'ignore_check',
        'lock_translation',
        'add_comment',
        'add_suggestion',
        'use_mt',
    },
    '@Template': {
        'access_project',
        'upload_translation',
        'overwrite_translation',
        'save_translation',
        'save_template',
        'accept_suggestion',
        'delete_suggestion',
        'vote_suggestion',
        'ignore_check',
        'lock_translation',
        'add_comment',
        'add_suggestion',
        'use_mt',
    },
    '@Languages': {
        'access_project',
        'add_translation',
        'delete_translation',
    },
    '@Glossary': {
        'access_project',
        'upload_dictionary',
        'add_dictionary',
        'change_dictionary',
        'delete_dictionary',
    },
    '@Screenshots': {
        'access_project',
        'add_screenshot',
        'delete_screenshot',
        'change_screenshot',
    },
    '@VCS': {
        'access_project',
        'commit_translation',
        'update_translation',
        'push_translation',
        'can_see_git_repository',
        'access_vcs',
    },
    '@Administration': ADMIN_PERMS,
}

ADMIN_ONLY_PERMS = ADMIN_PERMS - DEFAULT_GROUPS['Users']


def translate_groups():
    """Dummy method to allow extraction of group names translation."""
    pgettext('Permissions group', 'Administration')
    pgettext('Permissions group', 'Template')
    pgettext('Permissions group', 'Languages')
    pgettext('Permissions group', 'Glossary')
    pgettext('Permissions group', 'Screenshots')
    pgettext('Permissions group', 'Translate')
    pgettext('Permissions group', 'VCS')
