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
"""Definition of permissions and default roles and groups."""

from __future__ import unicode_literals

from django.utils.translation import ugettext_noop as _

from weblate.utils.translation import pgettext_noop


PERMISSIONS = (
    ('billing.view', _('View billing information')),

    ('change.download', _('Download changes')),

    ('component.edit', _('Edit component settings')),
    ('component.lock', _('Lock component from translating')),

    ('comment.add', _('Post coment')),
    ('comment.delete', _('Delete comment')),

    ('dictionary.add', _('Add glossary entry')),
    ('dictionary.change', _('Edit glossary entry')),
    ('dictionary.delete', _('Delete glossary entry')),
    ('dictionary.upload', _('Uploady glossary entries')),

    ('machinery.view', _('Use machine translation services')),

    ('project.edit', _('Edit project settings')),
    ('project.permissions', _('Manage project access')),

    ('reports.view', _('Download reports')),

    ('screenshot.add', _('Add screenshot')),
    ('screenshot.change', _('Edit screenshot')),
    ('screenshot.delete', _('Delete screenshot')),

    ('source.edit', _('Edit source strings information')),

    ('suggestion.accept', _('Accept suggestion')),
    ('suggestion.add', _('Add suggestion')),
    ('suggestion.delete', _('Delete suggestion')),
    ('suggestion.vote', _('Vote suggestion')),

    ('translation.add', _('Start new translation')),
    ('translation.delete', _('Delete existing translation')),
    ('translation.add_more', _('Start new translation into more languages')),

    ('unit.add', _('Add new string')),
    ('unit.check', _('Ignore failing check')),
    ('unit.edit', _('Edit strings')),
    ('unit.review', _('Review strings')),
    ('unit.override', _('Edit string when suggestions are enforced')),
    ('unit.template', _('Edit source strings')),

    ('upload.authorship', _('Define author of translation upload')),
    ('upload.overwrite', _('Overwrite existing strings with upload')),
    ('upload.perform', _('Upload translation strings')),

    ('vcs.access', _('Access the internal repository')),
    ('vcs.commit', _('Commit changes to the internal repository')),
    ('vcs.push', _('Push change from the the internal repository')),
    ('vcs.reset', _('Reset changes in the internal repository')),
    ('vcs.view', _('View upstream repository location')),
    ('vcs.update', _('Update the internal repository')),
)


def filter_perms(prefix):
    """Filter permission based on prefix."""
    return set(
        [perm[0] for perm in PERMISSIONS if perm[0].startswith(prefix)]
    )


# Translator permissions
TRANSLATE_PERMS = {
    'comment.add',
    'suggestion.accept', 'suggestion.add', 'suggestion.vote',
    'unit.check', 'unit.edit',
    'upload.overwrite', 'upload.perform',
}

# Default set of roles
ROLES = (
    (
        pgettext_noop('Access control role', 'Add suggestion'),
        {
            'suggestion.add'
        }
    ),
    (
        pgettext_noop('Access control role', 'Power user'),
        TRANSLATE_PERMS | {
            'translation.add',
            'unit.template',
            'vcs.access', 'vcs.view',
        } | filter_perms('dictionary.')
    ),
    (
        pgettext_noop('Access control role', 'Translate'),
        TRANSLATE_PERMS,
    ),
    (
        pgettext_noop('Access control role', 'Edit source'),
        TRANSLATE_PERMS | {'unit.template'},
    ),
    (
        pgettext_noop('Access control role', 'Manage languages'),
        filter_perms('translation.')
    ),
    (
        pgettext_noop('Access control role', 'Manage glossary'),
        filter_perms('dictionary.')
    ),
    (
        pgettext_noop('Access control role', 'Manage screenshots'),
        filter_perms('screenshot.')
    ),
    (
        pgettext_noop('Access control role', 'Review strings'),
        TRANSLATE_PERMS | {'unit.review', 'unit.override'},
    ),
    (
        pgettext_noop('Access control role', 'Manage repository'),
        filter_perms('vcs.')
    ),
    (
        pgettext_noop('Access control role', 'Administration'),
        [perm[0] for perm in PERMISSIONS],
    ),
    (
        pgettext_noop('Access control role', 'Billing'),
        filter_perms('billing.')
    ),
)

# Default set of roles for groups
GROUPS = (
    (
        pgettext_noop('Access control group', 'Guests'),
        ('Add suggestion',),
    ),
    (
        pgettext_noop('Access control group', 'Users'),
        ('Power user',),
    ),
    (
        pgettext_noop('Access control group', 'Reviewers'),
        ('Review strings',),
    ),
    (
        pgettext_noop('Access control group', 'Managers'),
        ('Administration',),
    ),
)

# Mapping of old default GroupACL groups to roles
ACL_GROUPS = {
    'Translate': 'Translate',
    'Template': 'Edit source',
    'Languages': 'Manage languages',
    'Glossary': 'Manage glossary',
    'Screenshots': 'Manage screenshots',
    'Review': 'Review strings',
    'VCS': 'Manage repository',
    'Administration': 'Administration',
}
