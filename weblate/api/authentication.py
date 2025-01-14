# Copyright © Michal Čihař <michal@weblate.org>
# SPDX-FileCopyrightText: 2025 Javier Pérez <jdbp@protonmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.plumbing import build_bearer_security_scheme_object
from rest_framework.authentication import TokenAuthentication


class BearerAuthentication(TokenAuthentication):
    """RFC 6750 compatible Bearer authentication."""

    keyword = "Bearer"


class BearerScheme(OpenApiAuthenticationExtension):
    """Fix an issue where the drf-spectacular library duplicates the `tokenAuth` security scheme when generating the OpenAPI schema."""

    target_class = 'weblate.api.authentication.BearerAuthentication'
    name = 'bearerAuth'

    def get_security_definition(self, auto_schema):
        return build_bearer_security_scheme_object(
            header_name='Authorization',
            token_prefix=self.target.keyword,
        )
