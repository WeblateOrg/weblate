# Copyright © Michal Čihař <michal@weblate.org>
# SPDX-FileCopyrightText: 2025 Javier Pérez <jdbp@protonmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.utils.translation import gettext
from drf_spectacular.authentication import SessionScheme
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import TokenAuthentication


class BearerAuthentication(TokenAuthentication):
    """RFC 6750 compatible Bearer authentication."""

    keyword = "Bearer"


class WeblateSessionScheme(SessionScheme):
    target_class = "rest_framework.authentication.SessionAuthentication"
    priority = 1

    def get_security_definition(self, auto_schema):
        result = super().get_security_definition(auto_schema)
        result["description"] = gettext(
            "Session-based authentication used when user is signed in."
        )
        return result


class BearerScheme(OpenApiAuthenticationExtension):
    target_class = "weblate.api.authentication.BearerAuthentication"
    name = "bearerAuth"
    priority = 1

    def get_description(self, keyword: str) -> str:
        intro = (
            gettext("Token-based authentication with required prefix `%s`.") % keyword
        )
        user_token = gettext(
            "Each user has a personal access token which they can get from their respective user profile. These tokens have the `wlu_` prefix."
        )
        project_token = gettext(
            "It is possible to create project tokens whose access to the API is limited to operations to their associated project. These tokens have the `wlp_` prefix."
        )
        return f"""{intro}

- {user_token}
- {project_token}
        """

    def get_security_definition(self, auto_schema):
        keyword = self.target.keyword
        return {
            "type": "apiKey",
            "in": "header",
            "name": keyword,
            "description": self.get_description(keyword),
        }


class TokenScheme(BearerScheme):
    target_class = "rest_framework.authentication.TokenAuthentication"
    name = "tokenAuth"
