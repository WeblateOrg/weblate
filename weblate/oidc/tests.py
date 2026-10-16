# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import base64
import hashlib
import os
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
import unittest
from datetime import date, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from itertools import product
from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING, Any
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

import jwt
import responses
from bs4 import BeautifulSoup, Tag
from django.apps import apps
from django.conf import settings
from django.contrib.sessions.models import Session
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice

if not getattr(settings, "OIDC_PROVIDER_ENABLED", False):
    msg = "The optional OIDC provider is not installed."
    raise unittest.SkipTest(msg)

from oauth2_provider.checks import validate_bcp_configuration
from oauth2_provider.models import AccessToken, Application, Grant, RefreshToken

from weblate.accounts.models import VerifiedEmail
from weblate.accounts.oidc import (
    OIDC_ATTEMPT_LIFETIME,
    OIDC_ATTEMPT_LIMIT,
    OIDC_ATTEMPT_PARAMETER,
    OIDC_ATTEMPTS_SESSION_KEY,
)
from weblate.accounts.utils import (
    SESSION_EXPIRY_SCOPE,
    remove_user,
)
from weblate.auth.models import User
from weblate.oidc.apps import check_signing_key
from weblate.oidc.models import IDTokenAuthentication
from weblate.oidc.settings import (
    AUTH_TIME_SESSION_KEY,
    get_provider_settings,
)
from weblate.trans.tests.utils import social_core_override_settings

if TYPE_CHECKING:
    from types import ModuleType

    from django.test.client import _MonkeyPatchedWSGIResponse


def load_urlconf() -> ModuleType:
    """Load a fresh root URL configuration without changing the cached module."""
    spec = spec_from_file_location(
        "oidc_test_urls", Path(__file__).parent.parent / "urls.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OIDCProviderTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            username="oidc-user",
            email="oidc@example.net",
            full_name="OIDC User",
            password="testpassword",
        )
        self.user.social_auth.get_or_create(
            provider="email", uid=self.user.email, defaults={"id_key": "email"}
        )
        # Keep a linked but unverified address for claim verification tests.
        VerifiedEmail.objects.filter(social__user=self.user).delete()
        self.application = Application.objects.create(
            name="Example client",
            client_id="oidc-client",
            client_secret="test-secret",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            algorithm=Application.RS256_ALGORITHM,
            redirect_uris="https://client.example.net/callback",
            skip_authorization=True,
        )
        self.verifier = "a" * 64
        self.params = {
            "client_id": self.application.client_id,
            "redirect_uri": self.application.redirect_uris,
            "response_type": "code",
            "scope": "openid profile email",
            "state": "client-state",
            "nonce": "client-nonce",
            "code_challenge": base64.urlsafe_b64encode(
                hashlib.sha256(self.verifier.encode()).digest()
            )
            .rstrip(b"=")
            .decode(),
            "code_challenge_method": "S256",
        }
        self.authorize_url = reverse("oauth2_provider:authorize")
        self.token_url = reverse("oauth2_provider:token")
        self.userinfo_url = reverse("oauth2_provider:user-info")

    def authorize(self, **params: str) -> str:
        self.client.force_login(self.user)
        response = self.client.get(self.authorize_url, {**self.params, **params})
        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlsplit(response["Location"]).query)
        self.assertEqual(query["state"], ["client-state"])
        self.assertEqual(query["iss"], ["http://example.com/oidc"])
        return query["code"][0]

    def exchange(self, code: str, **params: str) -> _MonkeyPatchedWSGIResponse:
        return self.client.post(
            self.token_url,
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.application.redirect_uris,
                "client_id": self.application.client_id,
                "client_secret": "test-secret",
                "code_verifier": self.verifier,
                **params,
            },
        )

    def issue_tokens(self, **params: str) -> dict[str, Any]:
        response = self.exchange(self.authorize(**params))
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def refresh(self, token: str, **params: str) -> _MonkeyPatchedWSGIResponse:
        return self.client.post(
            self.token_url,
            {
                "grant_type": "refresh_token",
                "refresh_token": token,
                "client_id": self.application.client_id,
                "client_secret": "test-secret",
                **params,
            },
        )

    def userinfo(self, token: str) -> _MonkeyPatchedWSGIResponse:
        return self.client.get(
            self.userinfo_url, headers={"authorization": f"Bearer {token}"}
        )

    def id_token_claims(self, tokens: dict[str, Any]) -> dict[str, Any]:
        jwks = self.client.get(reverse("oauth2_provider:jwks-info")).json()
        key = jwt.PyJWK.from_dict(jwks["keys"][0]).key
        return jwt.decode(
            tokens["id_token"],
            key,
            algorithms=["RS256"],
            audience=self.application.client_id,
            issuer="http://example.com/oidc",
        )

    def test_code_flow(self) -> None:
        tokens = self.issue_tokens()
        claims = self.id_token_claims(tokens)
        self.assertEqual(claims["sub"], str(self.user.pk))
        self.assertEqual(claims["nonce"], "client-nonce")
        self.assertEqual(claims["name"], self.user.full_name)
        self.assertEqual(tokens["expires_in"], 3600)
        self.client.logout()
        self.assertEqual(
            self.userinfo(tokens["access_token"]).json(),
            {
                "sub": str(self.user.pk),
                "name": "OIDC User",
                "family_name": "OIDC User",
                "preferred_username": "oidc-user",
                "email": "oidc@example.net",
                "email_verified": False,
            },
        )
        self.assertEqual(self.refresh(tokens["refresh_token"]).status_code, 200)

    def test_hashed_token_storage(self) -> None:
        tokens = self.issue_tokens()
        for grant_type in ("authorization_code", "refresh_token"):
            with self.subTest(grant_type=grant_type):
                if grant_type == "refresh_token":
                    response = self.refresh(tokens["refresh_token"])
                    self.assertEqual(response.status_code, 200, response.content)
                    tokens = response.json()
                access_token = AccessToken.objects.get(
                    token_checksum=hashlib.sha256(
                        tokens["access_token"].encode()
                    ).hexdigest()
                )
                refresh_token = RefreshToken.objects.get(
                    token_checksum=hashlib.sha256(
                        tokens["refresh_token"].encode()
                    ).hexdigest()
                )
                self.assertEqual(access_token.token, "")
                self.assertEqual(refresh_token.token, "")
                self.assertEqual(refresh_token.access_token, access_token)
                self.assertEqual(self.userinfo(tokens["access_token"]).status_code, 200)

    def test_deployment_security_checks(self) -> None:
        self.assertEqual(validate_bcp_configuration(None), [])

    def test_access_token_query_rejected(self) -> None:
        tokens = self.issue_tokens()
        self.client.logout()
        for value, header in product((tokens["access_token"], ""), (False, True)):
            with self.subTest(empty=not value, header=header):
                response = self.client.get(
                    self.userinfo_url,
                    {"access_token": value},
                    headers={"Authorization": f"Bearer {tokens['access_token']}"}
                    if header
                    else {},
                )
                self.assertEqual(response.status_code, 401)

    def test_authorization_issuer_replaces_callback_parameter(self) -> None:
        self.application.redirect_uris += "?iss=untrusted&preserved=value"
        self.application.save(update_fields=["redirect_uris"])
        code = self.authorize(redirect_uri=self.application.redirect_uris)
        self.assertEqual(self.exchange(code).status_code, 200)
        response = self.client.get(
            self.authorize_url,
            {
                **self.params,
                "redirect_uri": self.application.redirect_uris,
                "scope": "invalid",
            },
        )
        query = parse_qs(urlsplit(response["Location"]).query)
        self.assertEqual(query["iss"], ["http://example.com/oidc"])
        self.assertEqual(query["error"], ["invalid_scope"])
        self.assertEqual(query["preserved"], ["value"])

    def test_insecure_provider_configuration(self) -> None:
        for overrides, check_id in (
            ({"REFRESH_TOKEN_GRACE_PERIOD_SECONDS": 60}, "oauth2_provider.E001"),
            ({"REFRESH_TOKEN_REUSE_PROTECTION": False}, "oauth2_provider.E002"),
            (
                {"ALLOWED_REDIRECT_URI_SCHEMES": ["http", "https"]},
                "oauth2_provider.E003",
            ),
            ({"ALLOW_URI_WILDCARDS": True}, "oauth2_provider.E004"),
            ({"PKCE_REQUIRED": False}, "oauth2_provider.E005"),
        ):
            with (
                self.subTest(overrides=overrides),
                override_settings(
                    OAUTH2_PROVIDER={**settings.OAUTH2_PROVIDER, **overrides}
                ),
            ):
                checks = validate_bcp_configuration(None)
                self.assertEqual([check.id for check in checks], [check_id])
                self.assertTrue(all(check.is_serious() for check in checks))

    def test_scope_filtering(self) -> None:
        tokens = self.issue_tokens(scope="openid")
        self.assertEqual(
            self.userinfo(tokens["access_token"]).json(), {"sub": str(self.user.pk)}
        )

    @override_settings(LEGAL_TOS_DATE=date(2026, 9, 1))
    def test_legal_claim(self) -> None:
        model = apps.get_model("legal", "Agreement")
        for version in (date(2026, 9, 1), date(2025, 1, 1)):
            with self.subTest(version=version):
                model.objects.update_or_create(
                    user=self.user,
                    defaults={
                        "tos": version,
                        "address": "192.0.2.1",
                        "user_agent": "OIDC test",
                    },
                )
                recorded = model.objects.values().get(user=self.user)
                tokens = self.issue_tokens(scope="openid weblate:legal")
                self.assertEqual(
                    self.id_token_claims(tokens)["weblate_tos_version"],
                    version.isoformat(),
                )
                self.assertEqual(
                    self.userinfo(tokens["access_token"]).json(),
                    {
                        "sub": str(self.user.pk),
                        "weblate_tos_version": version.isoformat(),
                    },
                )
                self.assertEqual(model.objects.values().get(user=self.user), recorded)

    def test_legal_claim_requires_scope(self) -> None:
        model = apps.get_model("legal", "Agreement")
        model.objects.create(user=self.user, tos=date(2026, 9, 1))
        tokens = self.issue_tokens(
            claims='{"id_token":{"weblate_tos_version":null},"userinfo":{"weblate_tos_version":null}}'
        )
        self.assertNotIn("weblate_tos_version", self.id_token_claims(tokens))
        self.assertNotIn(
            "weblate_tos_version", self.userinfo(tokens["access_token"]).json()
        )

    def test_legal_claim_without_acceptance(self) -> None:
        model = apps.get_model("legal", "Agreement")
        for placeholder in (False, True):
            with self.subTest(placeholder=placeholder):
                if placeholder:
                    model.objects.create(user=self.user)
                recorded = list(model.objects.filter(user=self.user).values())
                tokens = self.issue_tokens(scope="openid weblate:legal")
                self.assertNotIn("weblate_tos_version", self.id_token_claims(tokens))
                self.assertNotIn(
                    "weblate_tos_version", self.userinfo(tokens["access_token"]).json()
                )
                self.assertEqual(
                    list(model.objects.filter(user=self.user).values()), recorded
                )

    def test_legal_claim_after_refresh(self) -> None:
        model = apps.get_model("legal", "Agreement")
        agreement = model.objects.create(user=self.user, tos=date(2025, 1, 1))
        tokens = self.issue_tokens(scope="openid weblate:legal")
        self.assertEqual(
            self.id_token_claims(tokens)["weblate_tos_version"], "2025-01-01"
        )
        agreement.tos = date(2026, 9, 1)
        agreement.save(update_fields=["tos"])
        recorded = model.objects.values().get(user=self.user)
        response = self.refresh(tokens["refresh_token"])
        self.assertEqual(response.status_code, 200, response.content)
        refreshed = response.json()
        self.assertEqual(
            self.id_token_claims(refreshed)["weblate_tos_version"], "2026-09-01"
        )
        self.assertEqual(
            self.userinfo(refreshed["access_token"]).json()["weblate_tos_version"],
            "2026-09-01",
        )
        self.assertEqual(model.objects.values().get(user=self.user), recorded)

    def test_legal_scope_discovery(self) -> None:
        discovery = self.client.get(
            reverse("oauth2_provider:oidc-connect-discovery-info")
        ).json()
        self.assertIn("weblate:legal", discovery["scopes_supported"])
        self.assertIn("weblate_tos_version", discovery["claims_supported"])
        self.application.skip_authorization = False
        self.application.save()
        self.client.force_login(self.user)
        response = self.client.get(
            self.authorize_url, {**self.params, "scope": "openid weblate:legal"}
        )
        self.assertContains(
            response, "Read the version of the legal documents you accepted"
        )

    def test_without_legal_module(self) -> None:
        with self.modify_settings(INSTALLED_APPS={"remove": "weblate.legal"}):
            provider = {
                **settings.OAUTH2_PROVIDER,
                "SCOPES": get_provider_settings()["SCOPES"],
            }
            with override_settings(
                OAUTH2_PROVIDER=provider, ROOT_URLCONF=load_urlconf()
            ):
                discovery = self.client.get(
                    reverse("oauth2_provider:oidc-connect-discovery-info")
                ).json()
                self.assertNotIn("weblate:legal", discovery["scopes_supported"])
                self.assertNotIn("weblate_tos_version", discovery["claims_supported"])
                tokens = self.issue_tokens()
                self.assertNotIn("weblate_tos_version", self.id_token_claims(tokens))
                self.assertNotIn(
                    "weblate_tos_version", self.userinfo(tokens["access_token"]).json()
                )
                response = self.client.get(
                    self.authorize_url, {**self.params, "scope": "openid weblate:legal"}
                )
                self.assertEqual(
                    parse_qs(urlsplit(response["Location"]).query)["error"],
                    ["invalid_scope"],
                )

    def test_basic_client_authentication(self) -> None:
        code = self.authorize()
        credentials = base64.b64encode(b"oidc-client:test-secret").decode()
        response = self.client.post(
            self.token_url,
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.application.redirect_uris,
                "code_verifier": self.verifier,
            },
            headers={"authorization": f"Basic {credentials}"},
        )
        self.assertEqual(response.status_code, 200, response.content)

    def test_tokens_do_not_grant_api_access(self) -> None:
        tokens = self.issue_tokens()
        self.client.logout()
        for scheme in ("Bearer", "Token"):
            response = self.client.get(
                reverse("api:user-list"),
                headers={"authorization": f"{scheme} {tokens['access_token']}"},
            )
            self.assertIn(response.status_code, {401, 403})

    def test_verified_email_and_profile_change(self) -> None:
        social = self.user.social_auth.get(provider="email")
        VerifiedEmail.objects.create(social=social, email=self.user.email.upper())
        tokens = self.issue_tokens()
        self.assertTrue(self.userinfo(tokens["access_token"]).json()["email_verified"])
        self.user.username = "renamed-user"
        self.user.email = "changed@example.net"
        self.user.save()
        claims = self.userinfo(tokens["access_token"]).json()
        self.assertEqual(claims["sub"], str(self.user.pk))
        self.assertEqual(claims["preferred_username"], "renamed-user")
        self.assertFalse(claims["email_verified"])

    def test_invalid_code_exchange(self) -> None:
        for params in (
            {"client_secret": "invalid"},
            {"code_verifier": "b" * 64},
            {"redirect_uri": "https://evil.example/"},
        ):
            with self.subTest(params=params):
                self.assertGreaterEqual(
                    self.exchange(self.authorize(), **params).status_code, 400
                )
        code = self.authorize()
        self.assertEqual(self.exchange(code).status_code, 200)
        self.assertEqual(self.exchange(code).status_code, 400)

    def test_expired_code(self) -> None:
        code = self.authorize()
        Grant.objects.filter(code=code).update(
            expires=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(self.exchange(code).status_code, 400)

    def test_invalid_authorization(self) -> None:
        self.client.force_login(self.user)
        for params in (
            {"redirect_uri": "https://evil.example/"},
            {"scope": "openid admin"},
            {"response_type": "token"},
            {"code_challenge": ""},
            {"code_challenge_method": "plain"},
        ):
            with self.subTest(params=params):
                response = self.client.get(
                    self.authorize_url, {**self.params, **params}
                )
                self.assertNotIn("code=", response.get("Location", ""))
                self.assertFalse(
                    Grant.objects.filter(application=self.application).exists()
                )

    def test_unsupported_grants_and_clients(self) -> None:
        for grant_type in ("password", "client_credentials", "implicit"):
            response = self.client.post(
                self.token_url,
                {
                    "grant_type": grant_type,
                    "client_id": self.application.client_id,
                    "client_secret": "test-secret",
                },
            )
            self.assertGreaterEqual(response.status_code, 400)
        self.application.algorithm = Application.HS256_ALGORITHM
        self.application.save()
        self.client.force_login(self.user)
        response = self.client.get(self.authorize_url, self.params)
        self.assertEqual(response.status_code, 400)

    def test_public_client(self) -> None:
        self.application.client_type = Application.CLIENT_PUBLIC
        self.application.save()
        response = self.exchange(self.authorize(), client_secret="")
        self.assertEqual(response.status_code, 200, response.content)
        tokens = response.json()
        self.assertEqual(self.id_token_claims(tokens)["sub"], str(self.user.pk))
        self.assertEqual(self.userinfo(tokens["access_token"]).status_code, 200)
        self.assertEqual(
            self.refresh(tokens["refresh_token"], client_secret="").status_code, 200
        )
        self.assertEqual(
            self.exchange(
                self.authorize(), client_secret="", code_verifier="wrong"
            ).status_code,
            400,
        )
        self.assertEqual(
            self.exchange(
                self.authorize(), client_secret="", code_verifier=""
            ).status_code,
            400,
        )

    def test_confidential_client_requires_secret(self) -> None:
        self.assertEqual(
            self.exchange(self.authorize(), client_secret="").status_code, 401
        )

    def test_refresh_authentication_time(self) -> None:
        code = self.authorize(claims='{"_weblate_auth_time":1}')
        original_auth_time = self.client.session[AUTH_TIME_SESSION_KEY]
        # Another browser login before code exchange must not change the grant.
        User.objects.filter(pk=self.user.pk).update(
            last_login=timezone.now() + timedelta(days=1)
        )
        response = self.exchange(code)
        self.assertEqual(response.status_code, 200, response.content)
        tokens = response.json()
        self.assertEqual(self.id_token_claims(tokens)["auth_time"], original_auth_time)
        for later_login in (timezone.now(), timezone.now() + timedelta(hours=1)):
            User.objects.filter(pk=self.user.pk).update(last_login=later_login)
            response = self.refresh(tokens["refresh_token"])
            self.assertEqual(response.status_code, 200, response.content)
            tokens = response.json()
            self.assertEqual(
                self.id_token_claims(tokens)["auth_time"],
                original_auth_time,
            )

    def test_refresh_without_authentication_provenance(self) -> None:
        tokens = self.issue_tokens()
        IDTokenAuthentication.objects.filter(id_token__user=self.user).delete()
        self.assertEqual(self.refresh(tokens["refresh_token"]).status_code, 400)

    def test_refresh_rotation_and_replay(self) -> None:
        tokens = self.issue_tokens()
        rotated = self.refresh(tokens["refresh_token"]).json()
        self.assertNotEqual(tokens["refresh_token"], rotated["refresh_token"])
        self.assertEqual(self.refresh(tokens["refresh_token"]).status_code, 400)
        self.assertEqual(self.refresh(rotated["refresh_token"]).status_code, 400)

    @override_settings(
        OAUTH2_PROVIDER={
            **settings.OAUTH2_PROVIDER,
            "COMPLIANT_BCP_RFC9700_TOKEN_STORAGE": False,
            "REFRESH_TOKEN_GRACE_PERIOD_SECONDS": 60,
        }
    )
    def test_refresh_grace_period(self) -> None:
        for auth_time in (int(timezone.now().timestamp()), None):
            with self.subTest(auth_time=auth_time):
                self.client.force_login(self.user)
                session = self.client.session
                session[AUTH_TIME_SESSION_KEY] = auth_time
                session.save()
                response = self.client.get(self.authorize_url, self.params)
                code = parse_qs(urlsplit(response["Location"]).query)["code"][0]
                response = self.exchange(code)
                self.assertEqual(response.status_code, 200, response.content)
                tokens = response.json()
                response = self.refresh(tokens["refresh_token"])
                self.assertEqual(response.status_code, 200, response.content)
                rotated = response.json()
                self.assertNotEqual(tokens["refresh_token"], rotated["refresh_token"])
                User.objects.filter(pk=self.user.pk).update(
                    last_login=timezone.now() + timedelta(hours=1)
                )
                response = self.refresh(tokens["refresh_token"])
                self.assertEqual(response.status_code, 200, response.content)
                retried = response.json()
                self.assertEqual(retried["access_token"], rotated["access_token"])
                self.assertEqual(retried["refresh_token"], rotated["refresh_token"])
                claims = self.id_token_claims(retried)
                if auth_time is None:
                    self.assertNotIn("auth_time", claims)
                else:
                    self.assertEqual(claims["auth_time"], auth_time)
                response = self.refresh(rotated["refresh_token"])
                self.assertEqual(response.status_code, 200, response.content)

    @override_settings(
        OAUTH2_PROVIDER={
            **settings.OAUTH2_PROVIDER,
            "COMPLIANT_BCP_RFC9700_TOKEN_STORAGE": False,
            "REFRESH_TOKEN_GRACE_PERIOD_SECONDS": 60,
        }
    )
    def test_refresh_grace_period_expired(self) -> None:
        tokens = self.issue_tokens()
        response = self.refresh(tokens["refresh_token"])
        self.assertEqual(response.status_code, 200, response.content)
        rotated = response.json()
        with patch(
            "weblate.oidc.validator.timezone.now",
            return_value=timezone.now() + timedelta(seconds=61),
        ):
            self.assertEqual(self.refresh(tokens["refresh_token"]).status_code, 400)
        self.assertEqual(self.refresh(rotated["refresh_token"]).status_code, 400)

    @override_settings(
        OAUTH2_PROVIDER={
            **settings.OAUTH2_PROVIDER,
            "COMPLIANT_BCP_RFC9700_TOKEN_STORAGE": False,
            "REFRESH_TOKEN_GRACE_PERIOD_SECONDS": 60,
        }
    )
    def test_refresh_grace_period_requires_provenance(self) -> None:
        tokens = self.issue_tokens()
        response = self.refresh(tokens["refresh_token"])
        self.assertEqual(response.status_code, 200, response.content)
        IDTokenAuthentication.objects.filter(id_token__user=self.user).delete()
        self.assertEqual(self.refresh(tokens["refresh_token"]).status_code, 400)

    def test_expired_tokens(self) -> None:
        tokens = self.issue_tokens()
        AccessToken.objects.filter(user=self.user).update(
            expires=timezone.now() - timedelta(days=31)
        )
        self.assertEqual(self.userinfo(tokens["access_token"]).status_code, 401)
        self.assertEqual(self.refresh(tokens["refresh_token"]).status_code, 400)

    def test_revocation(self) -> None:
        tokens = self.issue_tokens()
        response = self.client.post(
            reverse("oauth2_provider:revoke-token"),
            {
                "client_id": self.application.client_id,
                "client_secret": "test-secret",
                "token": tokens["refresh_token"],
                "token_type_hint": "refresh_token",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.refresh(tokens["refresh_token"]).status_code, 400)
        self.assertEqual(self.userinfo(tokens["access_token"]).status_code, 401)

    def test_inactive_user(self) -> None:
        tokens = self.issue_tokens()
        code = self.authorize()
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.exchange(code).status_code, 400)
        self.assertEqual(self.refresh(tokens["refresh_token"]).status_code, 400)
        self.assertEqual(self.userinfo(tokens["access_token"]).status_code, 401)

    def test_account_removal(self) -> None:
        tokens = self.issue_tokens()
        self.authorize()
        remove_user(self.user, None)
        self.assertFalse(Grant.objects.filter(user=self.user).exists())
        self.assertFalse(RefreshToken.objects.filter(user=self.user).exists())
        self.assertEqual(self.userinfo(tokens["access_token"]).status_code, 401)

    def test_consent(self) -> None:
        self.application.skip_authorization = False
        self.application.save()
        self.client.force_login(self.user)
        response = self.client.get(self.authorize_url, self.params)
        self.assertContains(response, "Allow Example client to access your account?")
        # Template loop directives are not text children in the rendered list.
        scope_list = BeautifulSoup(response.content, "html.parser").select_one(
            ".main-content ul"
        )
        self.assertIsNotNone(scope_list)
        assert isinstance(scope_list, Tag)
        self.assertEqual(
            [child.name for child in scope_list.children if isinstance(child, Tag)],
            ["li"] * 3,
        )
        self.assertTrue(
            all(
                not child.strip()
                for child in scope_list.children
                if isinstance(child, str)
            )
        )
        data = {
            name: response.context["form"][name].value() or ""
            for name in response.context["form"].fields
        }
        response = self.client.post(self.authorize_url, data)
        self.assertIn("error=access_denied", response["Location"])
        response = self.client.post(self.authorize_url, {**data, "allow": "Authorize"})
        self.assertIn("code=", response["Location"])

    def test_login_session(self) -> None:
        target = f"{self.authorize_url}?{urlencode(self.params)}"
        response = self.client.get(target)
        self.assertIn(reverse("login"), response["Location"])
        target = parse_qs(urlsplit(response["Location"]).query)["next"][0]
        response = self.client.post(
            reverse("login"),
            {
                "username": self.user.username,
                "password": "testpassword",
                "next": target,
            },
        )
        self.assertEqual(response["Location"], target)
        self.assertEqual(self.client.session[SESSION_EXPIRY_SCOPE], "oidc")
        self.assertLessEqual(self.client.session.get_expiry_age(), 60)
        self.assertEqual(self.client.get(target).status_code, 302)
        self.assertFalse(self.client.session.get(OIDC_ATTEMPTS_SESSION_KEY))

    def begin_login(self, **params: str) -> str:
        response = self.client.get(self.authorize_url, {**self.params, **params})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])
        return parse_qs(urlsplit(response["Location"]).query)["next"][0]

    def password_login(self, target: str, **params: str) -> _MonkeyPatchedWSGIResponse:
        return self.client.post(
            reverse("login"),
            {
                "username": self.user.username,
                "password": "testpassword",
                "next": target,
                **params,
            },
        )

    def test_concurrent_password_logins(self) -> None:
        second_client = Application.objects.create(
            name="Second client",
            client_id="second-client",
            client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            algorithm=Application.RS256_ALGORITHM,
            redirect_uris="https://second.example.net/callback",
            skip_authorization=True,
        )
        for first, different_client in product((0, 1), (False, True)):
            with self.subTest(first=first, different_client=different_client):
                self.client.logout()
                targets = [self.begin_login()]
                targets.append(
                    self.begin_login(
                        **(
                            {
                                "client_id": second_client.client_id,
                                "redirect_uri": second_client.redirect_uris,
                            }
                            if different_client
                            else {}
                        )
                    )
                )
                identifiers = [
                    parse_qs(urlsplit(target).query)[OIDC_ATTEMPT_PARAMETER][0]
                    for target in targets
                ]
                self.assertNotEqual(*identifiers)
                self.assertEqual(
                    set(self.client.session[OIDC_ATTEMPTS_SESSION_KEY]),
                    set(identifiers),
                )
                response = self.password_login(targets[first])
                self.assertEqual(response["Location"], targets[first])
                deadline = self.client.session.get_expiry_date()
                self.assertLessEqual(self.client.session.get_expiry_age(), 60)
                for index in (first, 1 - first):
                    response = self.client.get(targets[index])
                    query = parse_qs(urlsplit(response["Location"]).query)
                    self.assertEqual(query["state"], [self.params["state"]])
                    grant = Grant.objects.get(code=query["code"][0])
                    self.assertEqual(grant.user, self.user)
                    self.assertEqual(
                        grant.application,
                        second_client
                        if index == 1 and different_client
                        else self.application,
                    )
                    self.assertNotIn(
                        identifiers[index],
                        self.client.session.get(OIDC_ATTEMPTS_SESSION_KEY, {}),
                    )
                    if index == first:
                        self.assertIn(
                            identifiers[1 - first],
                            self.client.session[OIDC_ATTEMPTS_SESSION_KEY],
                        )
                    self.assertEqual(self.client.session.get_expiry_date(), deadline)
                self.assertFalse(self.client.session.get(OIDC_ATTEMPTS_SESSION_KEY))

    def test_concurrent_twofactor_logins(self) -> None:
        for first in (0, 1):
            with self.subTest(first=first):
                self.client.logout()
                # A new device avoids reusing a TOTP counter between subtests.
                TOTPDevice.objects.filter(user=self.user).delete()
                device = TOTPDevice.objects.create(
                    user=self.user, name="OIDC authenticator", confirmed=True
                )
                targets = [self.begin_login(state=f"tab-{index}") for index in (0, 1)]
                response = self.password_login(targets[first])
                self.assertNotIn("_auth_user_id", self.client.session)
                self.assertEqual(len(self.client.session[OIDC_ATTEMPTS_SESSION_KEY]), 2)
                response = self.client.post(
                    response["Location"], {"otp_token": f"{totp(device.bin_key):06d}"}
                )
                self.assertEqual(response["Location"], targets[first])
                self.assertEqual(self.client.session[SESSION_EXPIRY_SCOPE], "oidc")
                self.assertLessEqual(self.client.session.get_expiry_age(), 60)
                for index in (first, 1 - first):
                    response = self.client.get(targets[index])
                    query = parse_qs(urlsplit(response["Location"]).query)
                    self.assertIn("code", query)
                    self.assertEqual(query["state"], [f"tab-{index}"])
                self.assertFalse(self.client.session.get(OIDC_ATTEMPTS_SESSION_KEY))

    def test_invalid_login_attempt(self) -> None:
        target = self.begin_login()
        for changed in (
            f"{self.authorize_url}?{urlencode(self.params)}",
            target.replace("client-state", "changed-state"),
            target.replace("client-nonce", "changed-nonce"),
            target.replace(self.authorize_url, reverse("profile")),
            f"https://evil.example{target}",
            f"{target}&{OIDC_ATTEMPT_PARAMETER}=another",
            f"{self.authorize_url}?{urlencode(self.params)}&{OIDC_ATTEMPT_PARAMETER}=unknown",
        ):
            with self.subTest(target=changed):
                response = self.password_login(changed)
                self.assertContains(response, "Start signing in again", status_code=400)
                self.assertNotIn("_auth_user_id", self.client.session)
                self.assertFalse(Grant.objects.filter(user=self.user).exists())
        self.assertEqual(self.password_login(target)["Location"], target)
        self.assertLessEqual(self.client.session.get_expiry_age(), 60)

    def test_expired_login_attempt(self) -> None:
        target = self.begin_login()
        with patch(
            "weblate.accounts.oidc.time.time",
            return_value=timezone.now().timestamp() + OIDC_ATTEMPT_LIFETIME + 1,
        ):
            response = self.password_login(target)
        self.assertContains(response, "Start signing in again", status_code=400)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(Grant.objects.filter(user=self.user).exists())
        response = self.password_login(reverse("profile"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session[SESSION_EXPIRY_SCOPE], "authenticated")
        self.assertGreater(self.client.session.get_expiry_age(), 60)

    def test_login_attempt_limit(self) -> None:
        targets = [
            self.begin_login(state=str(index))
            for index in range(OIDC_ATTEMPT_LIMIT + 1)
        ]
        self.assertEqual(
            len(self.client.session[OIDC_ATTEMPTS_SESSION_KEY]), OIDC_ATTEMPT_LIMIT
        )
        response = self.password_login(targets[0])
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.password_login(targets[-1])["Location"], targets[-1])
        self.assertLessEqual(self.client.session.get_expiry_age(), 60)

    def test_concurrent_consent(self) -> None:
        self.application.skip_authorization = False
        self.application.save()
        targets = [self.begin_login(state=f"tab-{index}") for index in (0, 1)]
        self.password_login(targets[0])
        forms = []
        for target in targets:
            response = self.client.get(target)
            self.assertEqual(response.status_code, 200)
            forms.append(
                {
                    name: response.context["form"][name].value() or ""
                    for name in response.context["form"].fields
                }
            )
        self.assertEqual(len(self.client.session[OIDC_ATTEMPTS_SESSION_KEY]), 2)
        response = self.client.post(self.authorize_url, forms[1])
        self.assertEqual(
            parse_qs(urlsplit(response["Location"]).query)["error"], ["access_denied"]
        )
        self.assertEqual(
            list(self.client.session[OIDC_ATTEMPTS_SESSION_KEY]),
            [forms[0][OIDC_ATTEMPT_PARAMETER]],
        )
        self.assertFalse(Grant.objects.filter(user=self.user).exists())
        for field, value in (
            ("state", "changed"),
            ("scope", "openid"),
            ("nonce", "changed"),
            ("code_challenge", "b" * 64),
            (OIDC_ATTEMPT_PARAMETER, forms[1][OIDC_ATTEMPT_PARAMETER]),
        ):
            with self.subTest(field=field):
                response = self.client.post(
                    self.authorize_url, {**forms[0], "allow": "Authorize", field: value}
                )
                self.assertEqual(response.status_code, 400)
                self.assertFalse(Grant.objects.filter(user=self.user).exists())
                self.assertIn(
                    forms[0][OIDC_ATTEMPT_PARAMETER],
                    self.client.session[OIDC_ATTEMPTS_SESSION_KEY],
                )
        response = self.client.post(
            self.authorize_url, {**forms[0], "allow": "Authorize"}
        )
        query = parse_qs(urlsplit(response["Location"]).query)
        self.assertEqual(query["state"], ["tab-0"])
        self.assertEqual(Grant.objects.get(code=query["code"][0]).user, self.user)
        self.assertFalse(self.client.session.get(OIDC_ATTEMPTS_SESSION_KEY))

    def test_abandoned_authorization_password_login(self) -> None:
        for next_url, visit_login in product((None, reverse("profile")), (False, True)):
            with self.subTest(next_url=next_url, visit_login=visit_login):
                self.client.logout()
                response = self.client.get(
                    self.authorize_url, {**self.params, "prompt": "login"}
                )
                self.assertIn(reverse("login"), response["Location"])
                self.assertTrue(self.client.session["oidc_only"])
                self.assertTrue(
                    any(
                        attempt["require_fresh"]
                        for attempt in self.client.session[
                            OIDC_ATTEMPTS_SESSION_KEY
                        ].values()
                    )
                )
                data = {"username": self.user.username, "password": "testpassword"}
                if next_url is not None:
                    data["next"] = next_url
                if visit_login:
                    self.client.get(reverse("login"))
                    self.assertNotIn("oidc_only", self.client.session)
                response = self.client.post(reverse("login"), data)
                self.assertEqual(response.status_code, 302, response.content)
                self.assertNotIn("oidc_only", self.client.session)
                self.assertFalse(self.client.session.get(OIDC_ATTEMPTS_SESSION_KEY))
                self.assertEqual(
                    self.client.session[SESSION_EXPIRY_SCOPE], "authenticated"
                )
                self.assertGreater(self.client.session.get_expiry_age(), 60)
                self.assertFalse(Grant.objects.filter(user=self.user).exists())

    def test_abandoned_authorization_twofactor_login(self) -> None:
        device = TOTPDevice.objects.create(
            user=self.user, name="OIDC authenticator", confirmed=True
        )
        self.client.get(self.authorize_url, self.params)
        target = reverse("profile")
        response = self.client.post(
            reverse("login"),
            {
                "username": self.user.username,
                "password": "testpassword",
                "next": target,
            },
        )
        self.assertNotIn("oidc_only", self.client.session)
        response = self.client.post(
            response["Location"], {"otp_token": f"{totp(device.bin_key):06d}"}
        )
        self.assertEqual(response["Location"], target)
        self.assertEqual(self.client.session[SESSION_EXPIRY_SCOPE], "authenticated")
        self.assertGreater(self.client.session.get_expiry_age(), 60)
        self.assertFalse(self.client.session.get(OIDC_ATTEMPTS_SESSION_KEY))
        self.assertFalse(Grant.objects.filter(user=self.user).exists())

    @override_settings(SESSION_COOKIE_AGE_2FA=300)
    def test_abandoned_authorization_admin_twofactor_login(self) -> None:
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        device = TOTPDevice.objects.create(
            user=self.user, name="OIDC authenticator", confirmed=True
        )
        self.client.get(self.authorize_url, {**self.params, "prompt": "login"})
        self.assertTrue(self.client.session["oidc_only"])
        target = reverse("admin:index")
        response = self.client.post(
            reverse("admin:login"),
            {
                "username": self.user.username,
                "password": "testpassword",
                "next": target,
            },
        )
        self.assertEqual(response.status_code, 302, response.content)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotIn("oidc_only", self.client.session)
        self.assertFalse(self.client.session.get(OIDC_ATTEMPTS_SESSION_KEY))
        self.assertEqual(self.client.session[SESSION_EXPIRY_SCOPE], "2fa")
        self.assertGreater(self.client.session.get_expiry_age(), 60)
        self.assertLessEqual(self.client.session.get_expiry_age(), 300)
        response = self.client.post(
            response["Location"], {"otp_token": f"{totp(device.bin_key):06d}"}
        )
        self.assertEqual(response["Location"], target)
        self.assertEqual(self.client.session[SESSION_EXPIRY_SCOPE], "authenticated")
        self.assertGreater(self.client.session.get_expiry_age(), 60)
        self.assertFalse(Grant.objects.filter(user=self.user).exists())

    def test_consent_max_age(self) -> None:
        self.application.skip_authorization = False
        self.application.save()
        self.client.force_login(self.user)
        response = self.client.get(self.authorize_url, {**self.params, "max_age": "60"})
        self.assertEqual(response.status_code, 200)
        data = {
            name: response.context["form"][name].value() or ""
            for name in response.context["form"].fields
        }
        self.assertEqual(str(data.get("max_age")), "60")
        with patch(
            "weblate.oidc.validator.timezone.now",
            return_value=timezone.now() + timedelta(seconds=61),
        ):
            response = self.client.post(
                self.authorize_url, {**data, "allow": "Authorize"}
            )
        self.assertFalse(Grant.objects.filter(user=self.user).exists())
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertIn(reverse("login"), response["Location"])
        target = parse_qs(urlsplit(response["Location"]).query)["next"][0]
        self.assertEqual(parse_qs(urlsplit(target).query)["max_age"], ["60"])
        response = self.client.post(
            reverse("login"),
            {
                "username": self.user.username,
                "password": "testpassword",
                "next": target,
            },
        )
        self.assertEqual(response.status_code, 302, response.content)
        self.assertEqual(response["Location"], target)
        response = self.client.get(target)
        self.assertEqual(
            response.status_code, 200, response.get("Location") or response.content
        )
        data = {
            name: response.context["form"][name].value() or ""
            for name in response.context["form"].fields
        }
        response = self.client.post(self.authorize_url, {**data, "allow": "Authorize"})
        code = parse_qs(urlsplit(response["Location"]).query)["code"][0]
        tokens = self.exchange(code).json()
        self.assertEqual(
            self.id_token_claims(tokens)["auth_time"],
            self.client.session[AUTH_TIME_SESSION_KEY],
        )

    def test_expired_consent_denial(self) -> None:
        self.application.skip_authorization = False
        self.application.save()
        self.client.force_login(self.user)
        response = self.client.get(self.authorize_url, {**self.params, "max_age": "60"})
        data = {
            name: response.context["form"][name].value() or ""
            for name in response.context["form"].fields
        }
        with patch(
            "weblate.oidc.validator.timezone.now",
            return_value=timezone.now() + timedelta(seconds=61),
        ):
            response = self.client.post(self.authorize_url, data)
        self.assert_authorization_error(response, "access_denied")
        self.assertIn("_auth_user_id", self.client.session)
        self.assertFalse(Grant.objects.filter(user=self.user).exists())

    def test_expired_consent_invalid_redirect(self) -> None:
        self.application.skip_authorization = False
        self.application.save()
        self.client.force_login(self.user)
        response = self.client.get(self.authorize_url, {**self.params, "max_age": "60"})
        data = {
            name: response.context["form"][name].value() or ""
            for name in response.context["form"].fields
        }
        with patch(
            "weblate.oidc.validator.timezone.now",
            return_value=timezone.now() + timedelta(seconds=61),
        ):
            response = self.client.post(
                self.authorize_url,
                {
                    **data,
                    "allow": "Authorize",
                    "redirect_uri": "https://unregistered.example/",
                },
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("_auth_user_id", self.client.session)
        self.assertNotIn("oidc_only", self.client.session)
        self.assertFalse(Grant.objects.filter(user=self.user).exists())

    def test_expired_browser_consent(self) -> None:
        self.application.skip_authorization = False
        self.application.save()
        resources = ["https://one.example.net/", "https://two.example.net/"]
        for allow, freshness in product((False, True), ("login", "max_age")):
            with self.subTest(allow=allow, freshness=freshness):
                self.client = Client(enforce_csrf_checks=True)
                response = self.client.get(
                    self.authorize_url,
                    {
                        **self.params,
                        "resource": resources,
                        "claims": '{"id_token": {"email": null}}',
                        **(
                            {"prompt": "login"}
                            if freshness == "login"
                            else {"max_age": "60"}
                        ),
                    },
                )
                stale: dict[str, Any] = {}
                for expired in (False, True):
                    login_url = response["Location"]
                    target = parse_qs(urlsplit(login_url).query)["next"][0]
                    response = self.client.get(login_url)
                    response = self.password_login(
                        target, csrfmiddlewaretoken=str(response.context["csrf_token"])
                    )
                    self.assertEqual(response["Location"], target)
                    self.assertEqual(self.client.session[SESSION_EXPIRY_SCOPE], "oidc")
                    self.assertLessEqual(self.client.session.get_expiry_age(), 60)
                    response = self.client.get(target)
                    self.assertEqual(response.status_code, 200)
                    data = {
                        name: response.context["form"][name].value() or ""
                        for name in response.context["form"].fields
                    }
                    data["csrfmiddlewaretoken"] = str(response.context["csrf_token"])
                    if expired:
                        # The stale token cannot authorize after login rotated CSRF.
                        self.assertNotEqual(
                            data["csrfmiddlewaretoken"], stale["csrfmiddlewaretoken"]
                        )
                        self.assertEqual(
                            self.client.post(
                                self.authorize_url, {**stale, "allow": "Authorize"}
                            ).status_code,
                            403,
                        )
                        self.assertFalse(Grant.objects.filter(user=self.user).exists())
                        response = self.client.post(
                            self.authorize_url, {**data, "allow": "Authorize"}
                        )
                        code = parse_qs(urlsplit(response["Location"]).query)["code"][0]
                        grant = Grant.objects.get(code=code)
                        self.assertEqual(grant.user, self.user)
                        grant.delete()
                        break
                    stale = data.copy()
                    if allow:
                        stale["allow"] = "Authorize"
                    Session.objects.filter(
                        session_key=self.client.session.session_key
                    ).update(expire_date=timezone.now() - timedelta(seconds=1))
                    response = self.client.post(self.authorize_url, stale)
                    self.assertEqual(response.status_code, 303)
                    query = parse_qs(urlsplit(response["Location"]).query)
                    for name in (
                        "allow",
                        "csrfmiddlewaretoken",
                        "weblate_consent",
                        OIDC_ATTEMPT_PARAMETER,
                    ):
                        self.assertNotIn(name, query)
                    self.assertEqual(query["resource"], resources)
                    self.assertEqual(query["prompt"], ["login"])
                    if freshness == "max_age":
                        self.assertEqual(query["max_age"], ["60"])
                    self.assertEqual(query["claims"], ['{"id_token": {"email": null}}'])
                    self.assertFalse(Grant.objects.filter(user=self.user).exists())
                    self.assertNotIn("_auth_user_id", self.client.session)
                    response = self.client.get(response["Location"])
                    self.assertIn(reverse("login"), response["Location"])

    def test_expired_browser_consent_invalid_redirect(self) -> None:
        self.application.skip_authorization = False
        self.application.save()
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user)
        response = self.client.get(self.authorize_url, self.params)
        data = {
            name: response.context["form"][name].value() or ""
            for name in response.context["form"].fields
        }
        Session.objects.filter(session_key=self.client.session.session_key).update(
            expire_date=timezone.now() - timedelta(seconds=1)
        )
        response = self.client.post(
            self.authorize_url,
            {
                **data,
                "allow": "Authorize",
                "redirect_uri": "https://unregistered.example/",
            },
        )
        self.assertEqual(response.status_code, 303)
        response = self.client.get(response["Location"])
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("oidc_only", self.client.session)
        self.assertFalse(self.client.session.get(OIDC_ATTEMPTS_SESSION_KEY))
        self.assertFalse(Grant.objects.filter(user=self.user).exists())

    def test_consent_after_account_switch(self) -> None:
        self.application.skip_authorization = False
        self.application.save()
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.user)
        response = browser.get(self.authorize_url, self.params)
        data = {
            name: response.context["form"][name].value() or ""
            for name in response.context["form"].fields
        }
        data["csrfmiddlewaretoken"] = str(response.context["csrf_token"])
        other = User.objects.create_user(
            username="other-oidc-user", email="other@example.net"
        )
        browser.force_login(other)
        for allow in (False, True):
            with self.subTest(allow=allow):
                response = browser.post(
                    self.authorize_url,
                    {**data, **({"allow": "Authorize"} if allow else {})},
                )
                self.assertEqual(response.status_code, 403)
                self.assertFalse(
                    Grant.objects.filter(user__in=[self.user, other]).exists()
                )

    def test_invalid_claims(self) -> None:
        self.client.force_login(self.user)
        for claims in (
            '["email"]',
            '"email"',
            "123",
            "true",
            "[]",
            "false",
            "0",
            "null",
            "{",
        ):
            for scope in ("openid profile email", "email"):
                with self.subTest(claims=claims, scope=scope):
                    response = self.client.get(
                        self.authorize_url,
                        {**self.params, "claims": claims, "scope": scope},
                    )
                    self.assertEqual(response.status_code, 302)
                    query = parse_qs(urlsplit(response["Location"]).query)
                    self.assertEqual(query["error"], ["invalid_request"])
                    self.assertEqual(query["state"], ["client-state"])
                    self.assertFalse(Grant.objects.filter(user=self.user).exists())

    def test_invalid_claims_consent_post(self) -> None:
        self.application.skip_authorization = False
        self.application.save()
        self.client.force_login(self.user)
        response = self.client.get(self.authorize_url, self.params)
        data = {
            name: response.context["form"][name].value() or ""
            for name in response.context["form"].fields
        }
        response = self.client.post(
            self.authorize_url, {**data, "allow": "Authorize", "claims": '["email"]'}
        )
        self.assert_authorization_error(response, "invalid_request")
        self.assertFalse(Grant.objects.filter(user=self.user).exists())

    def test_invalid_authorization_preserves_session(self) -> None:
        for authenticated, method in product((False, True), ("get", "post")):
            for params in (
                {},
                {**self.params, "client_id": "unknown"},
                {**self.params, "redirect_uri": "https://unregistered.example/"},
                {**self.params, "scope": "unknown"},
                {**self.params, "prompt": "none login"},
            ):
                with self.subTest(
                    authenticated=authenticated, method=method, params=params
                ):
                    self.client.logout()
                    if authenticated:
                        self.client.force_login(self.user)
                    # Initialize normal middleware expiry and CSRF state first.
                    self.client.get(reverse("login"), follow=True)
                    session = dict(self.client.session)
                    response = getattr(self.client, method)(self.authorize_url, params)
                    if method == "post":
                        self.assertEqual(response.status_code, 303)
                        self.assertEqual(dict(self.client.session), session)
                        self.assertEqual(
                            urlsplit(response["Location"]).path, self.authorize_url
                        )
                        response = self.client.get(response["Location"])
                    self.assertIn(response.status_code, (302, 400))
                    self.assertEqual(dict(self.client.session), session)
                    self.assertFalse(Grant.objects.filter(user=self.user).exists())
        self.client.logout()
        self.client.get(self.authorize_url)
        response = self.client.post(
            reverse("login"),
            {
                "username": self.user.username,
                "password": "testpassword",
                "next": self.authorize_url,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotIn("oidc_only", self.client.session)
        self.assertNotIn(SESSION_EXPIRY_SCOPE, self.client.session)

    def test_authorization_post(self) -> None:
        for authenticated in (False, True):
            with self.subTest(authenticated=authenticated):
                self.client.logout()
                if authenticated:
                    self.client.force_login(self.user)
                response = self.client.post(
                    self.authorize_url,
                    urlencode(self.params),
                    content_type="application/x-www-form-urlencoded",
                )
                self.assertEqual(response.status_code, 303)
                target = response["Location"]
                self.assertEqual(
                    parse_qs(urlsplit(target).query),
                    {key: [value] for key, value in self.params.items()},
                )
                self.assertFalse(Grant.objects.filter(user=self.user).exists())
                response = self.client.get(target)
                if not authenticated:
                    self.assertIn(reverse("login"), response["Location"])
                    target = parse_qs(urlsplit(response["Location"]).query)["next"][0]
                    response = self.client.post(
                        reverse("login"),
                        {
                            "username": self.user.username,
                            "password": "testpassword",
                            "next": target,
                        },
                    )
                    self.assertEqual(response["Location"], target)
                    self.assertEqual(self.client.session[SESSION_EXPIRY_SCOPE], "oidc")
                    response = self.client.get(target)
                query = parse_qs(urlsplit(response["Location"]).query)
                self.assertEqual(query["state"], ["client-state"])
                tokens = self.exchange(query["code"][0])
                self.assertEqual(tokens.status_code, 200, tokens.content)
                self.assertEqual(
                    self.id_token_claims(tokens.json())["nonce"], "client-nonce"
                )
                Grant.objects.filter(user=self.user).delete()

    def test_initial_post_cannot_submit_consent(self) -> None:
        self.application.skip_authorization = False
        self.application.save()
        browser = Client(enforce_csrf_checks=True)
        for authenticated, allow in product((False, True), (None, "Authorize")):
            with self.subTest(authenticated=authenticated, allow=allow):
                browser.logout()
                if authenticated:
                    browser.force_login(self.user)
                params = {**self.params, "csrfmiddlewaretoken": "untrusted"}
                if allow:
                    params["allow"] = allow
                response = browser.post(
                    self.authorize_url,
                    urlencode(params),
                    content_type="application/x-www-form-urlencoded",
                )
                self.assertEqual(response.status_code, 303)
                query = parse_qs(urlsplit(response["Location"]).query)
                self.assertNotIn("allow", query)
                self.assertNotIn("csrfmiddlewaretoken", query)
                response = browser.get(response["Location"])
                if authenticated:
                    self.assertContains(
                        response, "Allow Example client to access your account?"
                    )
                    self.assertTrue(response.context["form"]["weblate_consent"].value())
                else:
                    self.assertIn(reverse("login"), response["Location"])
                self.assertFalse(Grant.objects.filter(user=self.user).exists())

    def test_consent_csrf(self) -> None:
        self.application.skip_authorization = False
        self.application.save()
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.user)
        response = browser.get(self.authorize_url, self.params)
        data = {
            name: response.context["form"][name].value() or ""
            for name in response.context["form"].fields
        }
        csrf_token = str(response.context["csrf_token"])
        for allow, token in product((None, "Authorize"), (None, "invalid")):
            with self.subTest(allow=allow, token=token):
                submission = data.copy()
                if allow:
                    submission["allow"] = allow
                if token:
                    submission["csrfmiddlewaretoken"] = token
                response = browser.post(self.authorize_url, submission)
                self.assertEqual(response.status_code, 403)
                self.assertFalse(Grant.objects.filter(user=self.user).exists())
        data["csrfmiddlewaretoken"] = csrf_token
        response = browser.post(self.authorize_url, data)
        self.assert_authorization_error(response, "access_denied")
        self.assertFalse(Grant.objects.filter(user=self.user).exists())
        response = browser.post(self.authorize_url, {**data, "allow": "Authorize"})
        self.assertIn("code=", response["Location"])

    def test_protocol_endpoints_without_csrf(self) -> None:
        self.client = Client(enforce_csrf_checks=True)
        tokens = self.issue_tokens()
        response = self.refresh(tokens["refresh_token"])
        self.assertEqual(response.status_code, 200, response.content)
        access_token = response.json()["access_token"]
        self.assertEqual(self.userinfo(access_token).json()["sub"], str(self.user.pk))
        response = self.client.post(
            self.userinfo_url, headers={"Authorization": f"Bearer {access_token}"}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["sub"], str(self.user.pk))
        self.assertEqual(self.client.get(self.userinfo_url).status_code, 401)

    def test_authorization_post_parameters(self) -> None:
        params = {
            **self.params,
            "resource": ["https://one.example.net/", "https://two.example.net/"],
            "claims": '{"id_token": {"email": null}}',
            "max_age": "60",
        }
        self.application.skip_authorization = False
        self.application.save()
        self.client.force_login(self.user)
        response = self.client.post(
            self.authorize_url,
            urlencode(params, doseq=True),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(response.status_code, 303)
        query = parse_qs(urlsplit(response["Location"]).query)
        self.assertEqual(query["resource"], params["resource"])
        self.assertEqual(query["claims"], [params["claims"]])
        response = self.client.get(response["Location"])
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form["max_age"].value(), "60")
        self.assertEqual(form["resource"].value(), " ".join(params["resource"]))

    def test_authorization_post_freshness(self) -> None:
        for params in ({"prompt": "login"}, {"max_age": "0"}, {"max_age": "60"}):
            with self.subTest(params=params):
                self.client.force_login(self.user)
                session = self.client.session
                session[AUTH_TIME_SESSION_KEY] = int(timezone.now().timestamp()) - 120
                session.save()
                response = self.client.post(
                    self.authorize_url, {**self.params, **params}
                )
                self.assertEqual(response.status_code, 303)
                response = self.client.get(response["Location"])
                self.assertIn(reverse("login"), response["Location"])
                self.assertNotIn("_auth_user_id", self.client.session)
                self.assertFalse(Grant.objects.filter(user=self.user).exists())

    def test_discovery_grants(self) -> None:
        response = self.client.get(
            reverse("oauth2_provider:oidc-connect-discovery-info")
        )
        self.assertEqual(
            response.json()["grant_types_supported"],
            ["authorization_code", "refresh_token"],
        )
        self.assertTrue(
            response.json()["authorization_response_iss_parameter_supported"]
        )

    def test_twofactor_session(self) -> None:
        device = TOTPDevice.objects.create(
            user=self.user, name="OIDC authenticator", confirmed=True
        )
        response = self.client.post(self.authorize_url, self.params)
        self.assertEqual(response.status_code, 303)
        target = response["Location"]
        response = self.client.get(target)
        target = parse_qs(urlsplit(response["Location"]).query)["next"][0]
        response = self.client.post(
            reverse("login"),
            {
                "username": self.user.username,
                "password": "testpassword",
                "next": target,
            },
        )
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(Grant.objects.filter(user=self.user).exists())
        response = self.client.post(
            response["Location"], {"otp_token": f"{totp(device.bin_key):06d}"}
        )
        self.assertEqual(response["Location"], target)
        self.assertEqual(self.client.session[SESSION_EXPIRY_SCOPE], "oidc")
        self.assertLessEqual(self.client.session.get_expiry_age(), 60)
        self.assertIn("code=", self.client.get(target)["Location"])

    def test_existing_session(self) -> None:
        self.authorize()
        self.assertNotEqual(self.client.session[SESSION_EXPIRY_SCOPE], "oidc")

    def test_session_without_authentication_time(self) -> None:
        self.client.force_login(self.user)
        session = self.client.session
        session.pop(AUTH_TIME_SESSION_KEY)
        session.save()
        response = self.client.get(self.authorize_url, self.params)
        self.assertIn(reverse("login"), response["Location"])
        self.assertNotIn("_auth_user_id", self.client.session)

    @responses.activate
    @social_core_override_settings(
        AUTHENTICATION_BACKENDS=(
            "social_core.backends.github.GithubOAuth2",
            "weblate.accounts.auth.WeblateUserBackend",
        )
    )
    def test_social_login_session(self) -> None:
        target = f"{self.authorize_url}?{urlencode(self.params)}"
        response = self.client.get(target)
        self.assertIn(reverse("login"), response["Location"])
        target = parse_qs(urlsplit(response["Location"]).query)["next"][0]
        response = self.client.get(response["Location"])
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/redirect.html")
        self.assertEqual(response.context["next"], target)
        self.assertTrue(self.client.session["oidc_only"])
        response = self.github_login(target)
        self.assertEqual(response["Location"], target)
        self.assertEqual(self.client.session[SESSION_EXPIRY_SCOPE], "oidc")
        self.assertLessEqual(self.client.session.get_expiry_age(), 60)
        self.assertIsNone(self.client.session[AUTH_TIME_SESSION_KEY])
        response = self.client.get(target)
        code = parse_qs(urlsplit(response["Location"]).query)["code"][0]
        response = self.exchange(code)
        self.assertEqual(response.status_code, 200, response.content)
        tokens = response.json()
        self.assertNotIn("auth_time", self.id_token_claims(tokens))
        response = self.client.get(
            self.authorize_url,
            {**self.params, "prompt": "none", "max_age": "60"},
        )
        self.assert_authorization_error(response, "login_required")
        # A later credential login must not invent a time for this token family.
        self.client.force_login(
            self.user, backend="weblate.accounts.auth.WeblateUserBackend"
        )
        response = self.refresh(tokens["refresh_token"])
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn("auth_time", self.id_token_claims(response.json()))

    @responses.activate
    @social_core_override_settings(
        AUTHENTICATION_BACKENDS=(
            "social_core.backends.github.GithubOAuth2",
            "weblate.accounts.auth.WeblateUserBackend",
        )
    )
    def test_social_login_cannot_claim_fresh_authentication(self) -> None:
        for params, silent in (
            ({"prompt": "login"}, False),
            ({"max_age": "0"}, False),
            ({"max_age": "60"}, False),
            ({"max_age": "0"}, True),
        ):
            with self.subTest(params=params, silent=silent):
                token_count = IDTokenAuthentication.objects.count()
                self.client.force_login(
                    self.user, backend="weblate.accounts.auth.WeblateUserBackend"
                )
                session = self.client.session
                session[AUTH_TIME_SESSION_KEY] = int(timezone.now().timestamp()) - 120
                session.save()
                response = self.client.get(
                    self.authorize_url, {**self.params, **params}
                )
                self.assertIn(reverse("login"), response["Location"])
                target = parse_qs(urlsplit(response["Location"]).query)["next"][0]
                response = self.github_login(target)
                self.assertEqual(response["Location"], target)
                self.assertIsNone(self.client.session[AUTH_TIME_SESSION_KEY])
                if silent:
                    response = self.client.get(
                        self.authorize_url, {**self.params, "prompt": "none"}
                    )
                    # An independent silent request must not inherit another
                    # attempt's failed freshness requirement.
                    code = parse_qs(urlsplit(response["Location"]).query)["code"][0]
                    response = self.exchange(code)
                    self.assertEqual(response.status_code, 200)
                    self.assertNotIn("auth_time", self.id_token_claims(response.json()))
                    token_count = IDTokenAuthentication.objects.count()
                response = self.client.get(target)
                self.assert_authorization_error(response, "login_required")
                self.assertFalse(Grant.objects.filter(user=self.user).exists())
                self.assertEqual(IDTokenAuthentication.objects.count(), token_count)
                # A finished failed attempt must not block ordinary federation.
                response = self.client.get(self.authorize_url, self.params)
                code = parse_qs(urlsplit(response["Location"]).query)["code"][0]
                response = self.exchange(code)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertNotIn("auth_time", self.id_token_claims(response.json()))

    @responses.activate
    @social_core_override_settings(
        AUTHENTICATION_BACKENDS=(
            "social_core.backends.github.GithubOAuth2",
            "weblate.accounts.auth.WeblateUserBackend",
        )
    )
    def test_concurrent_social_logins(self) -> None:
        for first in (0, 1):
            with self.subTest(first=first):
                self.client.logout()
                targets = [self.begin_login(state=f"tab-{index}") for index in (0, 1)]
                response = self.github_login(targets[first])
                self.assertEqual(response["Location"], targets[first])
                self.assertEqual(self.client.session[SESSION_EXPIRY_SCOPE], "oidc")
                self.assertLessEqual(self.client.session.get_expiry_age(), 60)
                self.assertIsNone(self.client.session[AUTH_TIME_SESSION_KEY])
                for index in (first, 1 - first):
                    response = self.client.get(targets[index])
                    query = parse_qs(urlsplit(response["Location"]).query)
                    self.assertEqual(query["state"], [f"tab-{index}"])
                    response = self.exchange(query["code"][0])
                    self.assertEqual(response.status_code, 200)
                    self.assertNotIn("auth_time", self.id_token_claims(response.json()))
                self.assertFalse(self.client.session.get(OIDC_ATTEMPTS_SESSION_KEY))

    @responses.activate
    @social_core_override_settings(
        AUTHENTICATION_BACKENDS=(
            "social_core.backends.github.GithubOAuth2",
            "weblate.accounts.auth.WeblateUserBackend",
        )
    )
    def test_concurrent_fresh_social_login(self) -> None:
        for fresh_first in (False, True):
            with self.subTest(fresh_first=fresh_first):
                self.client.logout()
                ordinary = self.begin_login()
                fresh = self.begin_login(prompt="login")
                ordinary_id = parse_qs(urlsplit(ordinary).query)[
                    OIDC_ATTEMPT_PARAMETER
                ][0]
                fresh_id = parse_qs(urlsplit(fresh).query)[OIDC_ATTEMPT_PARAMETER][0]
                self.github_login(fresh if fresh_first else ordinary)
                if fresh_first:
                    response = self.client.get(fresh)
                    self.assert_authorization_error(response, "login_required")
                    self.assertIn(
                        ordinary_id, self.client.session[OIDC_ATTEMPTS_SESSION_KEY]
                    )
                else:
                    # Reauthentication flushes credentials but preserves both
                    # continuations, including the one already signed in.
                    response = self.client.get(fresh)
                    self.assertIn(reverse("login"), response["Location"])
                    self.assertNotIn("_auth_user_id", self.client.session)
                    self.assertEqual(
                        set(self.client.session[OIDC_ATTEMPTS_SESSION_KEY]),
                        {ordinary_id, fresh_id},
                    )
                    self.github_login(fresh)
                    self.assert_authorization_error(
                        self.client.get(fresh), "login_required"
                    )
                response = self.client.get(ordinary)
                code = parse_qs(urlsplit(response["Location"]).query)["code"][0]
                response = self.exchange(code)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("auth_time", self.id_token_claims(response.json()))
                self.assertFalse(self.client.session.get(OIDC_ATTEMPTS_SESSION_KEY))

    @responses.activate
    @social_core_override_settings(
        AUTHENTICATION_BACKENDS=(
            "social_core.backends.github.GithubOAuth2",
            "weblate.accounts.auth.WeblateUserBackend",
        )
    )
    def test_abandoned_authorization_social_login(self) -> None:
        for target in (None, reverse("profile")):
            with self.subTest(target=target):
                self.client.logout()
                response = self.client.get(self.authorize_url, self.params)
                oidc_target = parse_qs(urlsplit(response["Location"]).query)["next"][0]
                # Abandon after social-auth has also saved the OIDC redirect.
                response = self.client.post(
                    reverse("social:begin", args=["github"]), {"next": oidc_target}
                )
                self.assertEqual(response.status_code, 302)
                self.assertEqual(self.client.session["next"], oidc_target)
                response = self.github_login(target)
                self.assertEqual(
                    response["Location"], target or settings.LOGIN_REDIRECT_URL
                )
                self.assertNotIn("oidc_only", self.client.session)
                self.assertFalse(self.client.session.get(OIDC_ATTEMPTS_SESSION_KEY))
                self.assertNotEqual(self.client.session[SESSION_EXPIRY_SCOPE], "oidc")
                self.assertGreater(self.client.session.get_expiry_age(), 60)
                self.assertFalse(Grant.objects.filter(user=self.user).exists())

    def github_login(self, target: str | None) -> _MonkeyPatchedWSGIResponse:
        self.user.social_auth.get_or_create(
            provider="github", uid="123", defaults={"id_key": "id"}
        )
        responses.post(
            "https://github.com/login/oauth/access_token",
            json={"access_token": "github-token", "token_type": "bearer"},
        )
        responses.get(
            "https://api.github.com/user",
            json={
                "id": 123,
                "login": self.user.username,
                "name": self.user.full_name,
                "email": self.user.email,
            },
        )
        responses.get(
            "https://api.github.com/user/emails",
            json=[{"email": self.user.email, "primary": True, "verified": True}],
        )
        response = self.client.post(
            reverse("social:begin", args=["github"]),
            {"next": target} if target is not None else {},
        )
        state = parse_qs(urlsplit(response["Location"]).query)["state"][0]
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.get(
                reverse("social:complete", args=["github"]),
                {"state": state, "code": "github-code"},
            )

    def test_fixed_session_deadline(self) -> None:
        target = f"{self.authorize_url}?{urlencode(self.params)}"
        response = self.client.get(target)
        target = parse_qs(urlsplit(response["Location"]).query)["next"][0]
        self.client.post(
            reverse("login"),
            {
                "username": self.user.username,
                "password": "testpassword",
                "next": target,
            },
        )
        deadline = self.client.session.get_expiry_date()
        self.client.get(target)
        self.assertEqual(self.client.session.get_expiry_date(), deadline)

    @override_settings(URL_PREFIX="/prefix/")
    def test_url_prefix(self) -> None:
        urlconf = load_urlconf()
        provider = {
            **settings.OAUTH2_PROVIDER,
            "OIDC_ISS_ENDPOINT": get_provider_settings()["OIDC_ISS_ENDPOINT"],
        }
        with override_settings(
            ROOT_URLCONF=urlconf,
            OAUTH2_PROVIDER=provider,
            LOGIN_URL="/prefix/accounts/login/",
        ):
            discovery = self.client.get(
                reverse("oauth2_provider:oidc-connect-discovery-info")
            ).json()
            self.assertEqual(discovery["issuer"], "http://example.com/prefix/oidc")
            self.assertEqual(
                discovery["authorization_endpoint"],
                "http://example.com/prefix/oidc/authorize/",
            )
            target = reverse("oauth2_provider:authorize") + "?" + urlencode(self.params)
            response = self.client.get(target)
            target = parse_qs(urlsplit(response["Location"]).query)["next"][0]
            response = self.client.post(
                reverse("login"),
                {
                    "username": self.user.username,
                    "password": "testpassword",
                    "next": target,
                },
            )
            self.assertEqual(response["Location"], target)
            self.assertEqual(self.client.session[SESSION_EXPIRY_SCOPE], "oidc")
            response = self.client.get(target)
            query = parse_qs(urlsplit(response["Location"]).query)
            self.assertIn("code", query)
            self.assertEqual(query["iss"], ["http://example.com/prefix/oidc"])
            response = self.client.get(
                reverse("oauth2_provider:authorize"),
                {**self.params, "scope": "invalid"},
            )
            query = parse_qs(urlsplit(response["Location"]).query)
            self.assertEqual(query["error"], ["invalid_scope"])
            self.assertEqual(query["iss"], ["http://example.com/prefix/oidc"])

    @override_settings(OIDC_PROVIDER_ENABLED=False)
    def test_disabled_routes(self) -> None:
        with override_settings(ROOT_URLCONF=load_urlconf()):
            self.assertEqual(
                self.client.get("/oidc/.well-known/openid-configuration").status_code,
                404,
            )
            self.assertEqual(self.client.post("/oidc/token/").status_code, 404)

    def test_disabled_startup_without_dependency(self) -> None:
        script = dedent("""
            import sys
            from importlib.abc import MetaPathFinder
            from django.conf import settings

            settings.OIDC_PROVIDER_ENABLED = False
            settings.INSTALLED_APPS = [
                app for app in settings.INSTALLED_APPS
                if app not in {"weblate.oidc", "oauth2_provider"}
            ]

            class BlockProvider(MetaPathFinder):
                def find_spec(self, fullname, path=None, target=None):
                    if fullname.startswith("oauth2_provider"):
                        raise ImportError("OIDC dependency is unavailable")

            sys.meta_path.insert(0, BlockProvider())
            import django
            django.setup()
            from django.urls import resolve, Resolver404
            try:
                resolve("/oidc/token/")
            except Resolver404:
                pass
            else:
                raise AssertionError("Disabled provider exposes endpoints")
            assert "oauth2_provider" not in sys.modules
        """)
        result = subprocess.run(
            [sys.executable, "-c", script],
            env={**os.environ, "DJANGO_SETTINGS_MODULE": "weblate.settings_test"},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_saml_coexistence(self) -> None:
        # App installation registers admin models for the life of the process.
        # Check a real startup without leaving SAML registrations in this worker.
        script = dedent("""
            import warnings
            from cryptography.utils import CryptographyDeprecationWarning
            from django.conf import settings

            warnings.filterwarnings("ignore", category=CryptographyDeprecationWarning)
            settings.INSTALLED_APPS = [*settings.INSTALLED_APPS, "djangosaml2idp"]
            settings.ALLOWED_HOSTS = ["testserver"]

            import django
            django.setup()
            from django.test import RequestFactory
            from django.urls import resolve, reverse

            assert reverse("saml_login_binding", args=["redirect"]) == "/idp/sso/redirect/"
            path = reverse("oauth2_provider:oidc-connect-discovery-info")
            response = resolve(path).func(RequestFactory().get(path))
            assert response.status_code == 200, response.content
        """)
        result = subprocess.run(
            [sys.executable, "-c", script],
            env={**os.environ, "DJANGO_SETTINGS_MODULE": "weblate.settings_test"},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_fresh_authentication(self) -> None:
        for params in (
            {"prompt": "login"},
            {"max_age": "0"},
            {"max_age": "00"},
            {"max_age": "60"},
        ):
            with self.subTest(params=params):
                self.client.force_login(self.user)
                session = self.client.session
                old_auth_time = int(timezone.now().timestamp()) - 120
                session[AUTH_TIME_SESSION_KEY] = old_auth_time
                session.save()
                response = self.client.get(
                    self.authorize_url, {**self.params, **params}
                )
                self.assertIn(reverse("login"), response["Location"])
                self.assertNotIn("_auth_user_id", self.client.session)
                target = parse_qs(urlsplit(response["Location"]).query)["next"][0]
                response = self.client.post(
                    reverse("login"),
                    {
                        "username": self.user.username,
                        "password": "testpassword",
                        "next": target,
                    },
                )
                self.assertEqual(response["Location"], target)
                self.assertEqual(self.client.session[SESSION_EXPIRY_SCOPE], "oidc")
                response = self.client.get(target)
                code = parse_qs(urlsplit(response["Location"]).query)["code"][0]
                tokens = self.exchange(code).json()
                self.assertGreater(
                    self.id_token_claims(tokens)["auth_time"], old_auth_time
                )

    def test_max_age_current_session(self) -> None:
        tokens = self.issue_tokens(max_age="3600")
        self.assertEqual(
            self.id_token_claims(tokens)["auth_time"],
            self.client.session[AUTH_TIME_SESSION_KEY],
        )
        self.assertNotIn("oidc_only", self.client.session)

    def assert_authorization_error(
        self, response: _MonkeyPatchedWSGIResponse, error: str
    ) -> None:
        self.assertEqual(response.status_code, 302)
        location = urlsplit(response["Location"])
        self.assertEqual(
            location._replace(query="").geturl(), self.application.redirect_uris
        )
        query = parse_qs(location.query)
        query.pop("error_description", None)
        self.assertEqual(
            query,
            {
                "state": ["client-state"],
                "error": [error],
                "iss": ["http://example.com/oidc"],
            },
        )

    def test_invalid_max_age(self) -> None:
        self.client.force_login(self.user)
        for value, method in product(
            ("", "-1", "invalid", "1.5", "9" * 5000), ("get", "post")
        ):
            with self.subTest(value=value[:20], method=method):
                response = getattr(self.client, method)(
                    self.authorize_url, {**self.params, "max_age": value}
                )
                if method == "post":
                    self.assertEqual(response.status_code, 303)
                    response = self.client.get(response["Location"])
                self.assertEqual(response.status_code, 302)
                query = parse_qs(urlsplit(response["Location"]).query)
                self.assertEqual(query["error"], ["invalid_request"])
                self.assertEqual(query["state"], ["client-state"])
                self.assertIn("_auth_user_id", self.client.session)
                self.assertNotIn("oidc_only", self.client.session)
        self.assertFalse(Grant.objects.filter(user=self.user).exists())

    def test_prompt_none_requires_login(self) -> None:
        for state in (
            "anonymous",
            "missing_auth_time",
            "expired_auth_time",
            "zero_age",
            "twofactor",
        ):
            with self.subTest(state=state):
                self.client.logout()
                if state != "anonymous":
                    self.client.force_login(self.user)
                params = {**self.params, "prompt": "none"}
                session = self.client.session
                if state == "missing_auth_time":
                    session.pop(AUTH_TIME_SESSION_KEY)
                elif state == "expired_auth_time":
                    session[AUTH_TIME_SESSION_KEY] = (
                        int(timezone.now().timestamp()) - 120
                    )
                    params["max_age"] = "60"
                elif state == "zero_age":
                    params["max_age"] = "0"
                elif state == "twofactor":
                    TOTPDevice.objects.create(user=self.user, confirmed=True)
                session.save()
                recorded = {
                    key: session.get(key)
                    for key in ("_auth_user_id", AUTH_TIME_SESSION_KEY, "oidc_only")
                }
                for method in (self.client.get, self.client.post):
                    response = method(
                        self.authorize_url,
                        params,
                        weblate_oidc_context="untrusted",
                        headers={"weblate-oidc-context": "untrusted"},
                    )
                    if response.status_code == 303:
                        response = self.client.get(response["Location"])
                    self.assert_authorization_error(response, "login_required")
                    self.assertEqual(
                        {key: self.client.session.get(key) for key in recorded},
                        recorded,
                    )
                self.assertFalse(Grant.objects.filter(user=self.user).exists())

    def test_prompt_none_requires_consent(self) -> None:
        self.application.skip_authorization = False
        self.application.save()
        self.client.force_login(self.user)
        response = self.client.get(
            self.authorize_url, {**self.params, "prompt": "none"}
        )
        self.assert_authorization_error(response, "consent_required")
        self.assertFalse(Grant.objects.filter(user=self.user).exists())

    def test_prompt_none_preapproved(self) -> None:
        self.authorize(prompt="none")

    def test_prompt_none_previous_consent(self) -> None:
        self.issue_tokens(scope="openid")
        self.application.skip_authorization = False
        self.application.save()
        params = {**self.params, "prompt": "none", "approval_prompt": "auto"}
        response = self.client.get(self.authorize_url, {**params, "scope": "openid"})
        self.assertIn("code=", response["Location"])
        response = self.client.get(self.authorize_url, params)
        self.assert_authorization_error(response, "consent_required")

    @override_settings(
        REQUIRE_LOGIN=True,
        MIDDLEWARE=[
            *settings.MIDDLEWARE,
            "django.contrib.auth.middleware.LoginRequiredMiddleware",
        ],
    )
    def test_public_protocol_endpoints(self) -> None:
        for name in ("oidc-connect-discovery-info", "jwks-info"):
            self.assertEqual(
                self.client.get(reverse(f"oauth2_provider:{name}")).status_code, 200
            )
        self.assertEqual(self.client.get(self.userinfo_url).status_code, 401)
        self.assertEqual(self.client.post(self.token_url).status_code, 400)
        self.assertEqual(self.client.get(self.authorize_url).status_code, 400)
        self.assertNotIn("oidc_only", self.client.session)
        response = self.client.get(
            self.authorize_url, {**self.params, "prompt": "none"}
        )
        self.assert_authorization_error(response, "login_required")
        self.assertNotIn("oidc_only", self.client.session)
        target = f"{self.authorize_url}?{urlencode(self.params)}"
        response = self.client.get(target)
        self.assertIn(reverse("login"), response["Location"])
        target = parse_qs(urlsplit(response["Location"]).query)["next"][0]
        self.assertTrue(self.client.session["oidc_only"])
        response = self.client.post(
            reverse("login"),
            {
                "username": self.user.username,
                "password": "testpassword",
                "next": target,
            },
        )
        self.assertEqual(response["Location"], target)
        self.assertEqual(self.client.session[SESSION_EXPIRY_SCOPE], "oidc")
        self.assertLessEqual(self.client.session.get_expiry_age(), 60)
        self.assertIn("code=", self.client.get(target)["Location"])

    def test_admin_only(self) -> None:
        self.client.force_login(self.user)
        response = self.client.get(reverse("admin:oauth2_provider_application_add"))
        self.assertEqual(response.status_code, 302)
        self.user.is_superuser = True
        self.user.save()
        response = self.client.get(reverse("admin:oauth2_provider_application_add"))
        self.assertEqual(response.status_code, 200)
        for path in ("applications/register/", "register/", "logout/", "introspect/"):
            self.assertEqual(self.client.get(f"/oidc/{path}").status_code, 404)

    @override_settings(OAUTH2_PROVIDER={"OIDC_RSA_PRIVATE_KEY": "invalid-secret"})
    def test_invalid_signing_key(self) -> None:
        errors = check_signing_key()
        self.assertEqual(len(errors), 1)
        self.assertNotIn("invalid-secret", str(errors[0]))
