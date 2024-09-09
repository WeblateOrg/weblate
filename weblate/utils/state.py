# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import IntegerChoices
from django.utils.translation import pgettext_lazy

if TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise


class StringState(IntegerChoices):
    STATE_EMPTY = 0, pgettext_lazy("String state", "Empty")
    STATE_FUZZY = 10, pgettext_lazy("String state", "Needs editing")
    STATE_TRANSLATED = 20, pgettext_lazy("String state", "Translated")
    STATE_APPROVED = 30, pgettext_lazy("String state", "Approved")
    STATE_READONLY = 100, pgettext_lazy("String state", "Read-only")


STATE_EMPTY = StringState.STATE_EMPTY
STATE_FUZZY = StringState.STATE_FUZZY
STATE_TRANSLATED = StringState.STATE_TRANSLATED
STATE_APPROVED = StringState.STATE_APPROVED
STATE_READONLY = StringState.STATE_READONLY


STATE_NAMES = {
    "empty": STATE_EMPTY,
    "untranslated": STATE_EMPTY,
    "needs-editing": STATE_FUZZY,
    "fuzzy": STATE_FUZZY,
    "translated": STATE_TRANSLATED,
    "approved": STATE_APPROVED,
    "readonly": STATE_READONLY,
    "read-only": STATE_READONLY,
}


def get_state_label(
    state: int, label: StrOrPromise, enable_review: bool
) -> StrOrPromise:
    if state == STATE_TRANSLATED and enable_review:
        return pgettext_lazy("String state", "Waiting for review")
    return label
