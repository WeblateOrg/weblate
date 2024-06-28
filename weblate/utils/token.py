# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.utils.crypto import get_random_string


def get_token(scope: str) -> str:
    return f"{scope}_{get_random_string(36)}"
