# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import string
from email.headerregistry import Address
from email.policy import default
from typing import TYPE_CHECKING, cast

from django.db.models import F, Func
from idna import IDNAError, encode

if TYPE_CHECKING:
    from email.headerregistry import AddressHeader, BaseHeader

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


def email_delivery_address(recipient: str) -> str | None:
    """Encode a recipient domain without changing the mailbox identity."""
    if recipient.isascii():
        return recipient

    try:
        _, value = default.header_store_parse("To", recipient)
    except ValueError:
        return None
    addresses = cast("AddressHeader", value).addresses
    if len(addresses) != 1 or cast("BaseHeader", value).defects:
        return None
    (mailbox,) = addresses
    if not mailbox.username.isascii():
        return None
    if mailbox.domain.isascii():
        return recipient

    try:
        # Django otherwise converts Unicode domains with Python's legacy IDNA codec.
        domain = encode(
            mailbox.domain.translate(ASCII_LOWER_TABLE), strict=True
        ).decode("ascii")
    except IDNAError:
        return None
    return str(
        Address(
            display_name=mailbox.display_name, username=mailbox.username, domain=domain
        )
    )
