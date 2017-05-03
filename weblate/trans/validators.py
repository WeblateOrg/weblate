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
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext as _, ugettext_lazy
from weblate.trans.checks import CHECKS

EXTRA_FLAGS = {
    v.enable_string: v.name
    for k, v in CHECKS.items()
    if v.default_disabled
}

EXTRA_FLAGS['rst-text'] = ugettext_lazy('RST text')
EXTRA_FLAGS['xml-text'] = ugettext_lazy('XML text')
EXTRA_FLAGS['skip-review-flag'] = ugettext_lazy(
    'Skip review flag when importing'
)
EXTRA_FLAGS['add-source-review'] = ugettext_lazy(
    'Add review flag for new source strings'
)
EXTRA_FLAGS['add-review'] = ugettext_lazy(
    'Add review flag for new translated strings'
)

IGNORE_CHECK_FLAGS = {CHECKS[x].ignore_string for x in CHECKS}


def validate_extra_file(val):
    """Validate extra file to commit."""
    try:
        val % {'language': 'cs'}
    except Exception as error:
        raise ValidationError(_('Bad format string (%s)') % str(error))


def validate_commit_message(val):
    """Validate that commit message is a valid format string."""
    try:
        val % {
            'language': 'cs',
            'language_name': 'Czech',
            'project': 'Weblate',
            'subproject': 'master',
            'resource': 'master',
            'component': 'master',
            'url': 'https://example.com/projects/weblate/master',
            'total': 200,
            'fuzzy': 20,
            'fuzzy_percent': 10.0,
            'translated': 40,
            'translated_percent': 20.0,
        }
    except Exception as error:
        raise ValidationError(_('Bad format string (%s)') % str(error))


def validate_filemask(val):
    """Validate file mask that it contains *."""
    if '*' not in val:
        raise ValidationError(
            _('File mask does not contain * as a language placeholder!')
        )


def validate_autoaccept(val):
    """Validate correct value for autoaccept."""
    if val == 1:
        raise ValidationError(_(
            'Value of 1 is not allowed for autoaccept as '
            'every user gives vote to his suggestion.'
        ))


def validate_check_flags(val):
    """Validate check influencing flags."""
    if not val:
        return
    for flag in val.split(','):
        name = flag.split(':')[0]
        if name in EXTRA_FLAGS or name in IGNORE_CHECK_FLAGS:
            continue
        raise ValidationError(_('Invalid check flag: "%s"') % flag)
