# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.utils.translation import gettext
from pyparsing import ParseException

from weblate.checks.flags import FlagsValidator
from weblate.lang.models import Language
from weblate.trans.defines import LANGUAGE_CODE_LENGTH
from weblate.utils.params import validate_params

if TYPE_CHECKING:
    from collections.abc import Iterator

    from weblate.trans.models.unit import Unit

SUGGESTION_REJECTION_REASON_LENGTH = 200
DEFAULT_TRANSLATION_MAX_LENGTH = 10000
MAX_TRANSLATION_ALTERNATIVES = 100
MAX_TRANSLATION_TOTAL_LENGTH = 100000
# Applied to text that cannot be matched to an existing unit and its limits.
MAX_NEW_TEXT_LENGTH = 10 * (DEFAULT_TRANSLATION_MAX_LENGTH + 100)


class TranslationTextTooLongError(ValidationError):
    """Text exceeds the length Weblate accepts for a string."""

    def __init__(
        self,
        message: str | None = None,
        code: str | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        # The arguments allow copying and pickling the exception
        super().__init__(
            message if message is not None else gettext("Translation text too long!"),
            code,
            params,
        )


def validate_multivalue_size(is_multivalue: bool, value: list[str]) -> None:
    """Validate the cardinality and aggregate size of multivalue text."""
    if is_multivalue and (
        len(value) > MAX_TRANSLATION_ALTERNATIVES
        or sum(map(len, value)) > MAX_TRANSLATION_TOTAL_LENGTH
    ):
        raise TranslationTextTooLongError


def get_translation_text_max_length(unit: Unit) -> int:
    """Return maximum accepted translation text length for a unit."""
    # Add extra margin to allow XML tags which might be ignored for length checks.
    # On the other side, do not process arbitrarily long strings here.
    try:
        max_length = unit.get_max_length()
    except ValueError:
        max_length = DEFAULT_TRANSLATION_MAX_LENGTH
    return 10 * (max_length + 100)


def validate_translation_text_length(
    unit: Unit,
    target: list[str],
    *,
    add_alternative: bool = False,
    allow_stored: bool = False,
) -> None:
    """
    Validate translation text length for a unit.

    With allow_stored, text already stored in the unit is accepted, matching
    the validation when storing the translation.
    """
    if add_alternative:
        target = [*target, ""]
    if allow_stored:
        validate_translation_text_change(unit, target, unit.get_target_plurals())
        return
    max_length = get_translation_text_max_length(unit)
    validate_multivalue_size(unit.translation.component.is_multivalue, target)
    if any(len(text) > max_length for text in target):
        raise TranslationTextTooLongError


def normalize_stored_newlines(text: str) -> str:
    """Normalize newlines, the editor submits stored CRLF newlines as LF."""
    return text.replace("\r\n", "\n")


def validate_translation_text_change(
    unit: Unit, new_target: list[str], old_target: list[str]
) -> None:
    """
    Validate text which a translation change would store.

    Text which is already stored is not validated again. It can come from the
    repository, which is intentionally not limited, and re-saving it, for
    example to change the state, must keep working. Reusing stored text must
    not grow the aggregate size, as an alternative can be repeated.
    """
    if new_target == old_target:
        return
    is_multivalue = unit.translation.component.is_multivalue
    # Checked first, the following checks scale with the number of alternatives
    if len(new_target) > len(old_target):
        validate_multivalue_size(is_multivalue, new_target)
    stored = {normalize_stored_newlines(text) for text in old_target}
    added = [
        text for text in new_target if normalize_stored_newlines(text) not in stored
    ]
    if added or sum(len(normalize_stored_newlines(text)) for text in new_target) > sum(
        len(normalize_stored_newlines(text)) for text in old_target
    ):
        validate_multivalue_size(is_multivalue, new_target)
    max_length = get_translation_text_max_length(unit)
    if any(len(text) > max_length for text in added):
        raise TranslationTextTooLongError


def is_translation_text_change_too_long(
    unit: Unit, new_target: list[str], old_target: list[str]
) -> bool:
    try:
        validate_translation_text_change(unit, new_target, old_target)
    except TranslationTextTooLongError:
        return True
    return False


def iter_nested_strings(value: object) -> Iterator[str]:
    """Yield all strings from nested lists and dictionaries, such as TBX terms."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from iter_nested_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from iter_nested_strings(item)


def validate_new_text_length(*texts: str) -> None:
    """Validate text of a string which does not exist yet."""
    if any(len(text) > MAX_NEW_TEXT_LENGTH for text in texts):
        raise TranslationTextTooLongError


def validate_changed_text_length(new: list[str], old: list[str]) -> None:
    """
    Validate edited string text, such as the source or explanation.

    Text which is already stored is accepted, it can come from the repository,
    which is intentionally not limited.
    """
    validate_new_text_length(*(text for text in new if text not in old))


def validate_filemask(val: str) -> None:
    """Validate that the filemask contains *."""
    if "*" not in val:
        raise ValidationError(
            gettext("File mask does not contain * as a language placeholder!")
        )


def validate_autoaccept(val: int) -> None:
    """Validate correct value for automatic acceptance."""
    if val == 1:
        raise ValidationError(
            gettext(
                "A value of 1 is not allowed for automatic acceptance as "
                "it would permit users to vote on their own suggestions."
            )
        )


def validate_check_flags(val: str) -> None:
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
        if not isinstance(name, str) or name not in CHECKS:
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
