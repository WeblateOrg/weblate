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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext as _


def validate_repoweb(val):
    '''
    Validates whether URL for repository browser is valid and
    can be filled in using format string.
    '''
    try:
        val % {'file': 'file.po', 'line': '9', 'branch': 'master'}
    except Exception as error:
        raise ValidationError(_('Bad format string (%s)') % str(error))
