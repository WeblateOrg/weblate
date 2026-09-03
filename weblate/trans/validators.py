# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.utils.translation import gettext
from pyparsing import ParseException

from weblate.checks.flags import FlagsValidator
from weblate.lang.models import Language
from weblate.trans.defines import LANGUAGE_CODE_LENGTH
from weblate.utils.params import validate_params

if TYPE_CHECKING:
    from weblate.trans.models.unit import Unit

SUGGESTION_REJECTION_REASON_LENGTH = 200
DEFAULT_TRANSLATION_MAX_LENGTH = 10000


def get_translation_text_max_length(unit: Unit) -> int:
    """Return maximum accepted translation text length for a unit."""
    # Add extra margin to allow XML tags which might be ignored for length checks.
    # On the other side, do not process arbitrarily long strings here.
    try:
        max_length = unit.get_max_length()
    except ValueError:
        max_length = DEFAULT_TRANSLATION_MAX_LENGTH
    return 10 * (max_length + 100)


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


def validate_enforced_checks(value: list[str]) -> None:
    """Validate enforced checks names."""
    if not isinstance(value, list):
        raise ValidationError(gettext("Enforced checks has to be a list."))

    # ruff: ignore[import-outside-top-level]
    from weblate.checks.models import CHECKS

    for name in value:
        if name not in CHECKS:
            raise ValidationError(gettext("Unsupported enforced check: %s") % name)


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


def validate_file_format_parameters(value: dict | None) -> None:
    # ruff: ignore[import-outside-top-level]
    from weblate.trans.file_format_params import FILE_FORMATS_PARAMS

    if value is not None and not isinstance(value, dict):
        raise ValidationError(
            gettext("File format parameters must be a dictionary of key-value pairs.")
        )

    validate_params(
        FILE_FORMATS_PARAMS,
        value,
        gettext('Unknown file format parameter: "%(param_name)s".'),
    )


def validate_vcs_parameters(value: dict | None) -> None:
    # ruff: ignore[import-outside-top-level]
    from weblate.vcs.params import VCS_PARAMS

    if value is not None and not isinstance(value, dict):
        raise ValidationError(
            gettext(
                "Version control parameters must be a dictionary of key-value pairs."
            )
        )

    validate_params(
        VCS_PARAMS,
        value,
        gettext('Unknown version control parameter: "%(param_name)s".'),
    )
