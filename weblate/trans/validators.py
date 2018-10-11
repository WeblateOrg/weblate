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
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext as _, ugettext_lazy

from weblate.checks import CHECKS

EXTRA_FLAGS = {
    v.enable_string: v.name
    for k, v in CHECKS.items()
    if v.default_disabled
}

EXTRA_FLAGS['rst-text'] = ugettext_lazy('RST text')
EXTRA_FLAGS['xml-text'] = ugettext_lazy('XML text')
EXTRA_FLAGS['dos-eol'] = ugettext_lazy('DOS end of lines')
EXTRA_FLAGS['auto-java-messageformat'] = ugettext_lazy(
    'Automatically detect Java MessageFormat'
)

IGNORE_CHECK_FLAGS = {CHECKS[x].ignore_string for x in CHECKS}


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
