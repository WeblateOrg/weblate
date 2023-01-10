# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

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
