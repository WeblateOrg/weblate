# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext
from pyparsing import ParseException

from weblate.checks.flags import FlagsValidator
from weblate.lang.models import Language
from weblate.trans.defines import LANGUAGE_CODE_LENGTH


def validate_filemask(val) -> None:
    """Validate that the filemask contains *."""
    if "*" not in val:
        raise ValidationError(
            gettext("File mask does not contain * as a language placeholder!")
        )


def validate_autoaccept(val) -> None:
    """Validate correct value for automatic acceptance."""
    if val == 1:
        raise ValidationError(
            gettext(
                "A value of 1 is not allowed for automatic acceptance as "
                "it would permit users to vote on their own suggestions."
            )
        )


def validate_check_flags(val) -> None:
    """Validate check-influencing flags."""
    try:
        flags = FlagsValidator(val)
    except (ParseException, re.error) as error:
        raise ValidationError(gettext("Could not parse flags: %s") % error) from error
    flags.validate()


def validate_language_code(code: str | None, filename: str, required: bool = False):
    if not code:
        if not required:
            return None
        message = gettext(
            'The language code for "%(filename)s" is empty, please check the file mask.'
        ) % {"filename": filename}
        raise ValidationError({"filemask": message})

    if len(code) > LANGUAGE_CODE_LENGTH:
        message = gettext(
            'The language code "%(code)s" for "%(filename)s" is too long,'
            " please check the file mask."
        ) % {"code": code, "filename": filename}
        raise ValidationError({"filemask": message})

    return Language.objects.auto_get_or_create(code=code, create=False)
