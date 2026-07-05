# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-FileCopyrightText: 2026 Samuel Gomes <samuel.esteves.gomes@tecnico.ulisboa.pt>
# SPDX-FileCopyrightText: 2026 Dinis Sales <dinis.sales@tecnico.ulisboa.pt>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Helpers for user-provided messages attached to :class:`~weblate.trans.models.Change`.

A change message is an optional free-text note explaining *why* a change was made.
The constants, normalization, and validation live here so forms, models, and the
API stay consistent.
"""

from __future__ import annotations

import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext, gettext_lazy

#: Maximum number of characters allowed in a change message.
CHANGE_MESSAGE_MAX_LENGTH = 500

#: Human-readable label for the message field.
CHANGE_MESSAGE_LABEL = gettext_lazy("Message")

#: Control characters rejected outright. Whitespace is collapsed, not rejected.
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_change_message(message: str | None) -> str:
    """Collapse whitespace and strip a message into its canonical stored form."""
    if not message:
        return ""
    return _WHITESPACE_RUN.sub(" ", message).strip()


def validate_change_message(message: str | None) -> str:
    """
    Validate and normalize a user-provided change message.

    Returns the normalized message, or raises
    :class:`~django.core.exceptions.ValidationError` when it contains control
    characters or exceeds :data:`CHANGE_MESSAGE_MAX_LENGTH` after normalization.
    An empty or missing message is valid and normalizes to an empty string.
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
    """Optional change-message field shared by the edit, replace, and bulk forms."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("label", CHANGE_MESSAGE_LABEL)
        kwargs.setdefault("max_length", CHANGE_MESSAGE_MAX_LENGTH)
        kwargs.setdefault("required", False)
        kwargs.setdefault("initial", "")
        kwargs.setdefault(
            "widget",
            forms.Textarea(
                attrs={
                    "placeholder": gettext_lazy("Reason for this change (optional)"),
                    "maxlength": CHANGE_MESSAGE_MAX_LENGTH,
                    "autocomplete": "off",
                    "rows": 2,
                    "class": "change-message-input",
                }
            ),
        )
        super().__init__(**kwargs)

    def clean(self, value: str | None) -> str:
        value = super().clean(value)
        return validate_change_message(value)
