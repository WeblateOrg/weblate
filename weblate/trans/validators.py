#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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
from django.utils.translation import gettext as _

from weblate.checks.flags import Flags


def validate_filemask(val):
    """Validate that filemask contains *."""
    if "*" not in val:
        raise ValidationError(
            _("Filemask does not contain * as a language placeholder!")
        )


def validate_autoaccept(val):
    """Validate correct value for autoaccept."""
    if val == 1:
        raise ValidationError(
            _(
                "A value of 1 is not allowed for autoaccept as "
                "it would permit users to vote on their own suggestions."
            )
        )


def validate_check_flags(val):
    """Validate check influencing flags."""
    flags = Flags(val)
    flags.validate()
