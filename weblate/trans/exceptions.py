# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


class WeblateError(Exception):
    """Base class for Weblate errors."""

    def __init__(self, message=None):
        super().__init__(message or self.__doc__)


class FileParseError(WeblateError):
    """File parse error."""


class PluralFormsMismatch(WeblateError):
    """Plural forms do not match the language."""


class InvalidTemplate(WeblateError):
    """Template file can not be parsed."""

    def __init__(self, nested, message=None):
        super().__init__(message or f"Template file can not be parsed: {nested}")
        self.nested = nested


class FailedCommitError(WeblateError):
    """Failed to commit file."""
