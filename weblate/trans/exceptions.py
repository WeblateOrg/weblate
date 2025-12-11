# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations


class WeblateError(Exception):
    """Base class for Weblate errors."""

    def __init__(self, message=None) -> None:
        super().__init__(message or self.__doc__)


class FileParseError(WeblateError):
    """File parse error."""


class PluralFormsMismatchError(WeblateError):
    """Plural forms do not match the language."""


class InvalidTemplateError(WeblateError):
    """Template file can not be parsed."""

    def __init__(self, message: str | None = None, info: str = "") -> None:
        super().__init__(message or f"Template file can not be parsed: {info}")


class FailedCommitError(WeblateError):
    """Could not commit file."""


class SuggestionSimilarToTranslationError(WeblateError):
    """Target of the Suggestion is similar to source."""
