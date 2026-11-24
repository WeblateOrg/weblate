# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import string

from django.db.models import F, Func

ASCII_UPPER = string.ascii_uppercase
ASCII_LOWER = string.ascii_lowercase
ASCII_LOWER_TABLE = str.maketrans(ASCII_UPPER, ASCII_LOWER)


def email_key(email: str) -> str:
    """Fold ASCII case without equating distinct Unicode e-mail addresses."""
    return email.translate(ASCII_LOWER_TABLE)


def email_key_expression(field: str) -> Func:
    """Match email_key in PostgreSQL independently of the database locale."""
    return Func(
        F(field),
        function="LOWER",
        template='LOWER((%(expressions)s) COLLATE "C")',
    )
