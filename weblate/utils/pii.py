# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


def mask_string(string: str, include_first: bool = False, limit: int = 3) -> str:
    length = len(string)
    if length <= limit:
        return length * "*"

    parts = []
    if include_first:
        parts.append(string[0])
        string = string[1:]
        length -= 1

    parts.extend(("*" * (length - 1), string[-1]))
    return "".join(parts)


def mask_email(email: str) -> str:
    name, domain = email.rsplit("@", maxsplit=1)
    masked_name = mask_string(name, include_first=True)

    if len(domain) <= 4 or "." not in domain:
        masked_domain = mask_string(domain, limit=0)
    else:
        part, tld = domain.rsplit(".", maxsplit=1)
        masked_tld = mask_string(tld, limit=0)
        masked_domain = f"{len(part) * '*'}.{masked_tld}"

    return f"{masked_name}@{masked_domain}"
