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

from weblate.utils.translation import pgettext_noop as pgettext

SELECTION_MANUAL = 0
SELECTION_ALL = 1
SELECTION_COMPONENT_LIST = 2
SELECTION_ALL_PUBLIC = 3
SELECTION_ALL_PROTECTED = 4

PERMISSIONS = (
    ('billing.view', _('View billing information')),

    ('change.download', _('Download changes')),

    ('component.edit', _('Edit component settings')),
    ('component.lock', _('Lock component from translating')),

    ('comment.add', _('Post comment')),
    ('comment.delete', _('Delete comment')),

    ('glossary.add', _('Add glossary entry')),
    ('glossary.edit', _('Edit glossary entry')),
    ('glossary.delete', _('Delete glossary entry')),
    ('glossary.upload', _('Upload glossary entries')),

    ('machinery.view', _('Use machine translation services')),

    ('memory.edit', _('Edit translation memory')),
    ('memory.delete', _('Delete translation memory')),

    ('project.edit', _('Edit project settings')),
    ('project.permissions', _('Manage project access')),

    ('reports.view', _('Download reports')),

    ('screenshot.add', _('Add screenshot')),
    ('screenshot.edit', _('Edit screenshot')),
    ('screenshot.delete', _('Delete screenshot')),

    ('source.edit', _('Edit info on source strings')),

    ('suggestion.accept', _('Accept suggestion')),
    ('suggestion.add', _('Add suggestion')),
    ('suggestion.delete', _('Delete suggestion')),
    ('suggestion.vote', _('Vote suggestion')),

    ('translation.add', _('Start new translation')),
    ('translation.auto', _('Perform automatic translation')),
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
    ('vcs.push', _('Push change from the internal repository')),
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
    'machinery.view',
}

# Default set of roles
ROLES = (
    (
        pgettext('Access control role', 'Add suggestion'),
        {
            'suggestion.add'
        }
    ),
    (
        pgettext('Access control role', 'Access repository'),
        {
            'vcs.access', 'vcs.view'
        }
    ),
    (
        pgettext('Access control role', 'Power user'),
        TRANSLATE_PERMS | {
            'translation.add',
            'unit.template',
            'vcs.access', 'vcs.view',
        } | filter_perms('glossary.')
    ),
    (
        pgettext('Access control role', 'Translate'),
        TRANSLATE_PERMS,
    ),
    (
        pgettext('Access control role', 'Edit source'),
        TRANSLATE_PERMS | {'unit.template', 'source.edit'},
    ),
    (
        pgettext('Access control role', 'Manage languages'),
        filter_perms('translation.')
    ),
    (
        pgettext('Access control role', 'Manage glossary'),
        filter_perms('glossary.')
    ),
    (
        pgettext('Access control role', 'Manage translation memory'),
        filter_perms('memory.')
    ),
    (
        pgettext('Access control role', 'Manage screenshots'),
        filter_perms('screenshot.')
    ),
    (
        pgettext('Access control role', 'Review strings'),
        TRANSLATE_PERMS | {'unit.review', 'unit.override'},
    ),
    (
        pgettext('Access control role', 'Manage repository'),
        filter_perms('vcs.')
    ),
    (
        pgettext('Access control role', 'Administration'),
        [x[0] for x in PERMISSIONS],
    ),
    (
        pgettext('Access control role', 'Billing'),
        filter_perms('billing.')
    ),
)

# Default set of roles for groups
GROUPS = (
    (
        pgettext('Access control group', 'Guests'),
        ('Add suggestion', 'Access repository'),
        SELECTION_ALL_PUBLIC,
    ),
    (
        pgettext('Access control group', 'Viewers'),
        (),
        SELECTION_ALL_PROTECTED,
    ),
    (
        pgettext('Access control group', 'Users'),
        ('Power user',),
        SELECTION_ALL_PUBLIC,
    ),
    (
        pgettext('Access control group', 'Reviewers'),
        ('Review strings',),
        SELECTION_ALL,
    ),
    (
        pgettext('Access control group', 'Managers'),
        ('Administration',),
        SELECTION_ALL,
    ),
)

# Per project group definitions
ACL_GROUPS = {
    pgettext('Per project access control group', 'Translate'):
        'Translate',
    pgettext('Per project access control group', 'Template'):
        'Edit source',
    pgettext('Per project access control group', 'Languages'):
        'Manage languages',
    pgettext('Per project access control group', 'Glossary'):
        'Manage glossary',
    pgettext('Per project access control group', 'Memory'):
        'Manage translation memory',
    pgettext('Per project access control group', 'Screenshots'):
        'Manage screenshots',
    pgettext('Per project access control group', 'Review'):
        'Review strings',
    pgettext('Per project access control group', 'VCS'):
        'Manage repository',
    pgettext('Per project access control group', 'Administration'):
        'Administration',
    pgettext('Per project access control group', 'Billing'):
        'Billing',
}
