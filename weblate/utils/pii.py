# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


def mask_email(email: str):
    name, domain = email.rsplit("@", maxsplit=1)
    if len(name) <= 3:
        masked_name = len(name) * "*"
    else:
        first, *hidden, last = name
        masked_name = f"{first}{'*' * len(hidden)}{last}"

    if len(domain) <= 4 or "." not in domain:
        *hidden, last = domain
        masked_domain = f"{len(hidden) * '*'}{last}"
    else:
        part, tld = domain.rsplit(".", maxsplit=1)
        *hidden, last = tld
        masked_tld = f"{len(hidden) * '*'}{last}"
        masked_domain = f"{len(part) * '*'}.{masked_tld}"

    return f"{masked_name}@{masked_domain}"
