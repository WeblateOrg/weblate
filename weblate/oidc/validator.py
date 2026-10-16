# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from django.apps import apps
from django.utils import timezone
from oauth2_provider.models import get_access_token_model
from oauth2_provider.oauth2_validators import OAuth2Validator
from oauth2_provider.settings import oauth2_settings
from oauthlib.oauth2 import InvalidRequestError

from weblate.accounts.models import VerifiedEmail
from weblate.oidc.models import IDTokenAuthentication
from weblate.oidc.settings import AUTH_TIME_SESSION_KEY, REAUTHENTICATION_SESSION_KEY

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.http import HttpRequest
    from oauth2_provider.models import Application, Grant, IDToken
    from oauthlib.common import Request

    from weblate.auth.models import User


def can_authenticate(user: User | None) -> bool:
    return bool(user and user.is_authenticated and user.is_active and not user.is_bot)


def requires_authentication(request: HttpRequest, max_age: int | None) -> bool:
    auth_time = request.session.get(AUTH_TIME_SESSION_KEY)
    return (
        not request.user.is_authenticated
        or AUTH_TIME_SESSION_KEY not in request.session
        or (
            auth_time is None
            and bool(request.session.get(REAUTHENTICATION_SESSION_KEY))
        )
        or (request.user.profile.has_2fa and not request.user.is_verified())
        or (
            max_age is not None
            and (
                auth_time is None
                or max_age == 0
                or timezone.now().timestamp() - auth_time > max_age
            )
        )
    )


class WeblateOAuth2Validator(OAuth2Validator):
    """Expose identity claims without granting Weblate API access."""

    def _load_application(self, client_id: str, request: Request) -> Application | None:
        client = super()._load_application(client_id, request)
        if client is None or (
            client.client_type not in {client.CLIENT_CONFIDENTIAL, client.CLIENT_PUBLIC}
            or client.authorization_grant_type != client.GRANT_AUTHORIZATION_CODE
            or client.algorithm != client.RS256_ALGORITHM
        ):
            return None
        return client

    def validate_response_type(
        self,
        client_id: str,
        response_type: str,
        client: Application,
        request: Request,
        *args: object,
        **kwargs: object,
    ) -> bool:
        if request.claims:
            try:
                claims = (
                    json.loads(request.claims)
                    if isinstance(request.claims, str)
                    else request.claims
                )
            except (ValueError, TypeError) as error:
                raise InvalidRequestError(
                    description="claims must be a JSON object.", request=request
                ) from error
            if not isinstance(claims, dict):
                raise InvalidRequestError(
                    description="claims must be a JSON object.", request=request
                )
            request.claims = claims
        if request.max_age is not None:
            value = request.max_age
            try:
                max_age = int(value) if value.isascii() and value.isdecimal() else -1
            except ValueError:
                max_age = -1
            if max_age < 0:
                raise InvalidRequestError(
                    description="max_age must be a non-negative integer.",
                    request=request,
                )
        if not request.code_challenge or request.code_challenge_method != "S256":
            raise InvalidRequestError(
                description="S256 PKCE is required.", request=request
            )
        return response_type == "code" and super().validate_response_type(
            client_id, response_type, client, request, *args, **kwargs
        )

    def validate_silent_login(self, request: Request) -> bool:
        context = request.headers.get("weblate_oidc_context")
        max_age = int(request.max_age) if request.max_age is not None else None
        return (
            context is not None
            and can_authenticate(context.request.user)
            and not requires_authentication(context.request, max_age)
        )

    def validate_silent_authorization(self, request: Request) -> bool:
        context = request.headers.get("weblate_oidc_context")
        if context is None or not can_authenticate(context.request.user):
            return False
        if request.client.skip_authorization:
            return True
        approval = context.request.GET.get(
            "approval_prompt", oauth2_settings.REQUEST_APPROVAL_PROMPT
        )
        if approval != "auto":
            return False
        tokens = get_access_token_model().objects.filter(
            user=context.request.user,
            application=request.client,
            expires__gt=timezone.now(),
        )
        return any(token.allow_scopes(request.scopes) for token in tokens)

    def validate_grant_type(
        self,
        client_id: str,
        grant_type: str,
        client: Application,
        request: Request,
        *args: object,
        **kwargs: object,
    ) -> bool:
        return grant_type in {
            "authorization_code",
            "refresh_token",
        } and super().validate_grant_type(
            client_id, grant_type, client, request, *args, **kwargs
        )

    def validate_code(
        self,
        client_id: str,
        code: str,
        client: Application,
        request: Request,
        *args: object,
        **kwargs: object,
    ) -> bool:
        if not super().validate_code(
            client_id, code, client, request, *args, **kwargs
        ) or not can_authenticate(request.user):
            return False
        if "_weblate_auth_time" not in (request.claims or {}):
            return False
        auth_time = request.claims.pop("_weblate_auth_time")
        if auth_time is not None and (
            not isinstance(auth_time, int) or isinstance(auth_time, bool)
        ):
            return False
        request.weblate_auth_time = auth_time
        return True

    def _create_authorization_code(
        self, request: Request, code: dict[str, str], expires: datetime | None = None
    ) -> Grant:
        # This value is provided by our view, never by the client's claims JSON.
        request.claims = {
            **(request.claims or {}),
            "_weblate_auth_time": request.weblate_auth_time,
        }
        return super()._create_authorization_code(request, code, expires)

    def validate_refresh_token(
        self,
        refresh_token: str,
        client: Application,
        request: Request,
        *args: object,
        **kwargs: object,
    ) -> bool:
        if not super().validate_refresh_token(
            refresh_token, client, request, *args, **kwargs
        ) or not can_authenticate(request.user):
            return False
        access_token = request.refresh_token_instance.access_token
        if access_token is None:
            # A grace-period retry uses the access token minted by rotation.
            access_token = (
                get_access_token_model()
                .objects.filter(source_refresh_token=request.refresh_token_instance)
                .first()
            )
        if access_token is None:
            return False
        if "openid" in access_token.scope.split():
            auth_time = (
                IDTokenAuthentication.objects.filter(
                    id_token_id=access_token.id_token_id
                )
                .values("auth_time")
                .first()
            )
            if auth_time is None:
                return False
            request.weblate_auth_time = auth_time["auth_time"]
        return True

    def get_id_token_dictionary(
        self, token: object, token_handler: object, request: Request
    ) -> tuple[dict[str, Any], datetime]:
        claims, expires = super().get_id_token_dictionary(token, token_handler, request)
        if request.weblate_auth_time is None:
            claims.pop("auth_time", None)
        else:
            claims["auth_time"] = request.weblate_auth_time
        return claims, expires

    def _save_id_token(
        self,
        jti: str,
        request: Request,
        expires: datetime,
        *args: object,
        **kwargs: object,
    ) -> IDToken:
        id_token = super()._save_id_token(jti, request, expires, *args, **kwargs)
        IDTokenAuthentication.objects.create(
            id_token=id_token, auth_time=request.weblate_auth_time
        )
        return id_token

    def validate_bearer_token(
        self, token: str, scopes: list[str], request: Request
    ) -> bool:
        # UserInfo bypasses the toolkit's verify_request transport check.
        if oauth2_settings.COMPLIANT_BCP_RFC9700_ACCESS_TOKEN_TRANSPORT and any(
            name == "access_token" for name, _value in request.uri_query_params
        ):
            return False
        return super().validate_bearer_token(
            token, scopes, request
        ) and can_authenticate(request.user)

    def get_discovery_claims(self, request: HttpRequest) -> list[str]:
        claims = super().get_discovery_claims(request)
        if apps.is_installed("weblate.legal"):
            claims.append("weblate_tos_version")
        return claims

    def get_oidc_claims(
        self, token: object, token_handler: object, request: Request
    ) -> dict[str, str | bool]:
        claims = super().get_oidc_claims(token, token_handler, request)
        if apps.is_installed("weblate.legal") and "weblate:legal" in request.scopes:
            accepted_version = (
                apps.get_model("legal", "Agreement")
                .objects.filter(user=request.user)
                .values_list("tos", flat=True)
                .first()
            )
            if accepted_version is not None and accepted_version != date(1970, 1, 1):
                claims["weblate_tos_version"] = accepted_version.isoformat()
        return claims

    # Toolkit discovers callable claims only with this request-independent signature.
    def get_additional_claims(self) -> dict[str, Callable[[Request], str | bool]]:  # pylint: disable=arguments-differ
        return {
            "preferred_username": lambda request: request.user.username,
            "name": lambda request: request.user.full_name,
            "family_name": lambda request: request.user.full_name,
            "email": lambda request: request.user.email,
            "email_verified": lambda request: (
                bool(request.user.email)
                and VerifiedEmail.objects.filter(
                    social__user=request.user, email__iexact=request.user.email
                ).exists()
            ),
        }
