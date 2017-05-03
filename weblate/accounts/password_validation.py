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

from __future__ import unicode_literals


from django.core.exceptions import ValidationError
from django.utils.translation import ugettext as _


class CharsPasswordValidator(object):
    """
    Validate whether the password is alphanumeric.
    """
    def validate(self, password, user=None):
        if not password:
            return

        if password.strip() == '':
            raise ValidationError(
                _("This password consists of whitespace only."),
                code='password_whitespace',
            )
        if password.strip(password[0]) == '':
            raise ValidationError(
                _("This password consists of single character."),
                code='password_same_chars',
            )

    def get_help_text(self):
        return _(
            "Your password can't consist of "
            "single character or whitespace only."
        )
