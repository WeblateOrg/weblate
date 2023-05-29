# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from rest_framework.authentication import TokenAuthentication


class BearerAuthentication(TokenAuthentication):
    """RFC 6750 compatible Bearer authentication."""

    keyword = "Bearer"
