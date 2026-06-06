# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Helpers for user-provided messages attached to :class:`~weblate.trans.models.Change`.

A change message is a short, optional, free-text note a translator or reviewer
can supply when editing strings, performing a bulk edit, or running a search and
replace. It explains *why* a change was made, complementing the automatic audit
trail that records *what* changed.

This module centralizes the constants, normalization, and validation used across
forms, models, the REST API, and templates so the behaviour stays consistent.
"""

from __future__ import annotations

import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext, gettext_lazy

__all__ = [
    "CHANGE_MESSAGE_LABEL",
    "CHANGE_MESSAGE_MAX_LENGTH",
    "CHANGE_MESSAGE_PLACEHOLDER",
    "ChangeMessageField",
    "normalize_change_message",
    "validate_change_message",
]

#: Maximum number of characters allowed in a change message.
CHANGE_MESSAGE_MAX_LENGTH = 500

#: Placeholder shown in the message input widgets.
CHANGE_MESSAGE_PLACEHOLDER = gettext_lazy("Reason for this change (optional)")

#: Human-readable label for the message field.
CHANGE_MESSAGE_LABEL = gettext_lazy("Message")

#: Matches control characters that must never be stored in a message. Tabs and
#: newlines are intentionally excluded here because they are collapsed to spaces
#: during normalization rather than rejected outright.
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

#: Matches any run of whitespace (including tabs and newlines) for collapsing.
_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_change_message(message: str | None) -> str:
    """
    Normalize a raw change message into its canonical stored form.

    The normalization performs the following, in order:

    * Treats ``None`` as an empty string.
    * Collapses every run of whitespace (spaces, tabs, newlines) into a single
      space so the message renders predictably on a single line.
    * Strips leading and trailing whitespace.

    The result is safe to store directly on a model instance. It does *not*
    enforce the maximum length; use :func:`validate_change_message` for that.
    """
    if not message:
        return ""
    collapsed = _WHITESPACE_RUN.sub(" ", message)
    return collapsed.strip()


def validate_change_message(message: str | None) -> str:
    """
    Validate and normalize a user-provided change message.

    Returns the normalized message when it is acceptable. Raises
    :class:`django.core.exceptions.ValidationError` when the message contains
    disallowed control characters or exceeds
    :data:`CHANGE_MESSAGE_MAX_LENGTH` characters after normalization.

    An empty or missing message is valid and normalizes to an empty string,
    preserving the optional nature of the field.
    """
    if message and _CONTROL_CHARACTERS.search(message):
        raise ValidationError(
            gettext("The message must not contain control characters."),
            code="control_characters",
        )

    normalized = normalize_change_message(message)

    if len(normalized) > CHANGE_MESSAGE_MAX_LENGTH:
        raise ValidationError(
            gettext("The message is too long (maximum %(limit)d characters).")
            % {"limit": CHANGE_MESSAGE_MAX_LENGTH},
            code="max_length",
        )

    return normalized


class ChangeMessageField(forms.CharField):
    """
    Form field for an optional user-provided change message.

    Bundles everything a change-message input needs so the three forms that
    expose it (single edit, search and replace, and bulk edit) stay consistent:

    * a single-line text widget pre-populated with the shared placeholder,
    * the shared maximum length,
    * normalization and validation via :func:`validate_change_message`.

    The field is always optional; an omitted value cleans to an empty string,
    leaving the existing workflow untouched.
    """

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("label", CHANGE_MESSAGE_LABEL)
        kwargs.setdefault("max_length", CHANGE_MESSAGE_MAX_LENGTH)
        kwargs.setdefault("required", False)
        kwargs.setdefault("initial", "")
        kwargs.setdefault(
            "widget",
            forms.TextInput(
                attrs={
                    "placeholder": CHANGE_MESSAGE_PLACEHOLDER,
                    "maxlength": CHANGE_MESSAGE_MAX_LENGTH,
                    "autocomplete": "off",
                }
            ),
        )
        super().__init__(**kwargs)

    def clean(self, value: str | None) -> str:
        """Normalize and validate the submitted message."""
        value = super().clean(value)
        return validate_change_message(value)
