# Copyright © Michal Čihař <michal@weblate.org>
# SPDX-FileCopyrightText: 2025 Javier Pérez <jdbp@protonmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.translation import gettext
from drf_spectacular.authentication import SessionScheme
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import (
    BaseAuthentication,
    TokenAuthentication,
    get_authorization_header,
)
from rest_framework.exceptions import AuthenticationFailed

from weblate.utils.change_origin import change_origin

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser
    from drf_spectacular.openapi import AutoSchema
    from rest_framework.authtoken.models import Token
    from rest_framework.request import Request


class WeblateTokenAuthentication(TokenAuthentication):
    """Record the channel only after token authentication succeeds."""

    def authenticate(self, request: Request) -> tuple[AbstractBaseUser, Token] | None:
        result = super().authenticate(request)
        if result is not None:
            # Token.pk is currently the credential, not a safe token identifier.
            change_origin.set({"scope": "api"})
        return result


class BearerAuthentication(WeblateTokenAuthentication):
    """RFC 6750 compatible Bearer authentication."""

    keyword = "Bearer"


class RejectAuthorizationAuthentication(BaseAuthentication):
    """Reject authorization headers not handled by preceding authenticators."""

    def authenticate(self, request: Request) -> None:
        if get_authorization_header(request).split():
            msg = "Unsupported authentication scheme. Use Token or Bearer."
            raise AuthenticationFailed(msg)


class RejectAuthorizationScheme(OpenApiAuthenticationExtension):
    """Exclude the rejection step from advertised authentication schemes."""

    target_class = "weblate.api.authentication.RejectAuthorizationAuthentication"

    def __init__(self, target: BaseAuthentication) -> None:
        super().__init__(target)
        self.name = []

    def get_security_requirement(
        self, auto_schema: AutoSchema
    ) -> list[dict[str, list[str]]]:
        return []

    def get_security_definition(self, auto_schema: AutoSchema) -> list[dict[str, str]]:
        return []


class WeblateSessionScheme(SessionScheme):
    target_class = "rest_framework.authentication.SessionAuthentication"
    priority = 1

    def get_security_definition(self, auto_schema: AutoSchema) -> dict[str, str]:
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

    def get_security_definition(self, auto_schema: AutoSchema) -> dict[str, str]:
        keyword = self.target.keyword
        return {
            "type": "apiKey",
            "in": "header",
            "name": keyword,
            "description": self.get_description(keyword),
        }


class TokenScheme(BearerScheme):
    target_class = "weblate.api.authentication.WeblateTokenAuthentication"
    name = "tokenAuth"
