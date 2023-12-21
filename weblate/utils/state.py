# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.utils.translation import pgettext_lazy

STATE_EMPTY = 0
STATE_FUZZY = 10
STATE_TRANSLATED = 20
STATE_APPROVED = 30
STATE_READONLY = 100

STATE_CHOICES = (
    (STATE_EMPTY, pgettext_lazy("String state", "Empty")),
    (STATE_FUZZY, pgettext_lazy("String state", "Needs editing")),
    (STATE_TRANSLATED, pgettext_lazy("String state", "Translated")),
    (STATE_APPROVED, pgettext_lazy("String state", "Approved")),
    (STATE_READONLY, pgettext_lazy("String state", "Read only")),
)

STATE_LOOKUP = dict(STATE_CHOICES)

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
