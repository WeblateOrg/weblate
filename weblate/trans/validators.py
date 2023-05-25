#
# Copyright © 2012–2022 Michal Čihař <michal@cihar.com>
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

import re
from typing import Optional

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from pyparsing import ParseException

from weblate.checks.flags import Flags
from weblate.lang.models import Language
from weblate.trans.defines import LANGUAGE_CODE_LENGTH


def validate_filemask(val):
    """Validate that filemask contains *."""
    if "*" not in val:
        raise ValidationError(
            _("File mask does not contain * as a language placeholder!")
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
    try:
        flags = Flags(val)
    except (ParseException, re.error) as error:
        raise ValidationError(_("Failed to parse flags: %s") % error)
    flags.validate()


def validate_language_code(code: Optional[str], filename: str, required: bool = False):
    if not code:
        if not required:
            return None
        message = _(
            'The language code for "%(filename)s" is empty, please check the file mask.'
        ) % {"filename": filename}
        raise ValidationError({"filemask": message})

    if len(code) > LANGUAGE_CODE_LENGTH:
        message = _(
            'The language code "%(code)s" for "%(filename)s" is too long,'
            " please check the file mask."
        ) % {"code": code, "filename": filename}
        raise ValidationError({"filemask": message})

    return Language.objects.auto_get_or_create(code=code, create=False)
