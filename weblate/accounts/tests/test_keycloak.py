# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os
from pathlib import Path
from runpy import run_module
from typing import TYPE_CHECKING
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse
from social_core.backends.keycloak import KeycloakOAuth2
from social_core.exceptions import AuthAssociationError, AuthResponseError
from social_core.pipeline.social_auth import associate_user, social_uid, social_user
from social_django.models import DjangoStorage

from weblate.accounts.strategy import WeblateStrategy
from weblate.auth.models import User
from weblate.trans.tests.utils import social_core_override_settings

if TYPE_CHECKING:
    from typing import Any


def docker_keycloak_settings(**overrides: str) -> dict[str, Any]:
    environment = {
        "WEBLATE_SITE_DOMAIN": "example.com",
        "WEBLATE_DATABASES": "0",
        "WEBLATE_SOCIAL_AUTH_KEYCLOAK_KEY": "weblate",
        "WEBLATE_SOCIAL_AUTH_KEYCLOAK_SECRET": "test-secret",
        "WEBLATE_SOCIAL_AUTH_KEYCLOAK_PUBLIC_KEY": "test-key",
        "WEBLATE_SOCIAL_AUTH_KEYCLOAK_AUTHORIZATION_URL": "https://idp.example.com/auth",
        "WEBLATE_SOCIAL_AUTH_KEYCLOAK_ACCESS_TOKEN_URL": "https://idp.example.com/token",
    }
    with (
        patch.dict(os.environ, environment | overrides, clear=True),
        patch.object(
            Path, "read_text", autospec=True, return_value="test-secret"
        ) as read_secret,
    ):
        configuration = run_module("weblate.settings_docker")
    read_secret.assert_called_once_with(Path("/app/data/secret"), encoding="utf-8")
    return {
        key: value
        for key, value in configuration.items()
        if key.startswith(("SOCIAL_AUTH_KEYCLOAK_", "SOCIAL_AUTH_OLD_ID_KEYS"))
    }


class KeycloakDockerSettingsTest(SimpleTestCase):
    def test_default_and_explicit_identifiers(self) -> None:
        for identifier in (None, "sub", "email", "custom_id"):
            with self.subTest(identifier=identifier):
                overrides = (
                    {"WEBLATE_SOCIAL_AUTH_KEYCLOAK_ID_KEY": identifier}
                    if identifier is not None
                    else {}
                )
                configuration = docker_keycloak_settings(**overrides)
                self.assertEqual(
                    configuration["SOCIAL_AUTH_KEYCLOAK_ID_KEY"], identifier or "sub"
                )
                self.assertEqual(
                    configuration["SOCIAL_AUTH_OLD_ID_KEYS"],
                    {"keycloak": identifier or "email"},
                )
                self.assertEqual(
                    configuration["SOCIAL_AUTH_KEYCLOAK_LEGACY_ID_KEYS"], ["email"]
                )
                self.assertIs(
                    configuration[
                        "SOCIAL_AUTH_KEYCLOAK_ALLOW_UNVERIFIED_LEGACY_UID_MIGRATION"
                    ],
                    identifier is None,
                )

    def test_legacy_migration_override(self) -> None:
        for identifier in (None, "sub", "email", "custom_id"):
            for value, expected in (("0", False), ("1", True)):
                with self.subTest(identifier=identifier, value=value):
                    overrides = (
                        {"WEBLATE_SOCIAL_AUTH_KEYCLOAK_ID_KEY": identifier}
                        if identifier is not None
                        else {}
                    )
                    configuration = docker_keycloak_settings(
                        **overrides,
                        WEBLATE_SOCIAL_AUTH_KEYCLOAK_ALLOW_UNVERIFIED_LEGACY_UID_MIGRATION=value,
                    )
                    self.assertIs(
                        configuration[
                            "SOCIAL_AUTH_KEYCLOAK_ALLOW_UNVERIFIED_LEGACY_UID_MIGRATION"
                        ],
                        expected,
                    )


class KeycloakIdentifierTest(TestCase):
    def setUp(self) -> None:
        self.enterContext(
            social_core_override_settings(
                **docker_keycloak_settings(),
                AUTHENTICATION_BACKENDS=(
                    "social_core.backends.keycloak.KeycloakOAuth2",
                    "weblate.accounts.auth.WeblateUserBackend",
                ),
            )
        )
        self.user = User.objects.create_user("keycloak-user", "keycloak@example.com")
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        SessionMiddleware(lambda _request: HttpResponse()).process_request(request)
        self.strategy = WeblateStrategy(DjangoStorage, request)
        self.backend = KeycloakOAuth2(self.strategy)
        self.claims = {
            "sub": "original-subject",
            "email": self.user.email,
            "preferred_username": self.user.username,
        }

    def identify(self, **claims: object) -> dict[str, Any]:
        response = self.claims | claims
        return social_uid(
            self.backend, self.backend.get_user_details(response), response
        )

    def lookup(self, **claims: object) -> dict[str, Any]:
        return social_user(self.backend, **self.identify(**claims))

    def callback(self, **claims: object) -> None:
        response = self.client.post(reverse("social:begin", args=("keycloak",)))
        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlparse(response["Location"]).query)
        with (
            patch.object(
                KeycloakOAuth2,
                "request_access_token",
                return_value={"access_token": "test-token"},
            ),
            patch.object(
                KeycloakOAuth2, "user_data", return_value=self.claims | claims
            ),
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.client.get(
                reverse("social:complete", args=("keycloak",)),
                {"state": query["state"][0], "code": "test-code"},
            )

    def test_new_association_uses_subject(self) -> None:
        identifiers = self.identify()
        result = associate_user(self.backend, user=self.user, **identifiers)
        social = result["social"]
        self.assertEqual((social.id_key, social.uid), ("sub", self.claims["sub"]))
        self.assertEqual(social.user, self.user)

    def test_legacy_association_migrates_and_logs_in(self) -> None:
        for key, uid in (
            ("email", self.user.email),
            ("", self.user.email),
            ("username", self.user.username),
        ):
            for evidence in ({}, {"sub": self.claims["sub"]}):
                with self.subTest(key=key, evidence=evidence):
                    self.check_legacy_migration(key, uid, evidence)

    def check_legacy_migration(
        self, key: str, uid: str, evidence: dict[str, str]
    ) -> None:
        social = self.user.social_auth.create(
            provider="keycloak",
            id_key=key,
            uid=uid,
            extra_data=evidence,
        )
        self.callback()
        self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))
        social.refresh_from_db()
        self.assertEqual((social.id_key, social.uid), ("sub", self.claims["sub"]))
        self.assertEqual(social.user_id, self.user.pk)
        self.assertEqual(self.user.social_auth.get(provider="keycloak").pk, social.pk)
        self.client.logout()
        self.callback()
        self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))
        self.client.logout()
        self.callback(sub="different-subject")
        self.assertNotIn(SESSION_KEY, self.client.session)
        social.refresh_from_db()
        self.assertEqual((social.id_key, social.uid), ("sub", self.claims["sub"]))
        self.assertEqual(self.user.social_auth.count(), 1)
        social.delete()

    def test_reused_email_cannot_authenticate_another_subject(self) -> None:
        social = self.user.social_auth.create(
            provider="keycloak",
            id_key="email",
            uid=self.user.email,
            extra_data={"sub": self.claims["sub"]},
        )
        for verification in ({}, {"email_verified": False}, {"email_verified": True}):
            with self.subTest(verification=verification):
                self.callback(sub="different-subject", **verification)
                self.assertNotIn(SESSION_KEY, self.client.session)
                social.refresh_from_db()
                self.assertEqual(
                    (social.id_key, social.uid), ("email", self.user.email)
                )
                self.assertEqual(social.extra_data, {"sub": self.claims["sub"]})
                self.assertEqual(self.user.social_auth.count(), 1)

    def test_migration_evidence_policy(self) -> None:
        for allow_missing in (True, False):
            with self.settings(
                **docker_keycloak_settings(
                    WEBLATE_SOCIAL_AUTH_KEYCLOAK_ALLOW_UNVERIFIED_LEGACY_UID_MIGRATION=(
                        "1" if allow_missing else "0"
                    )
                )
            ):
                self.check_rejected_migration_evidence(allow_missing=allow_missing)

    def check_rejected_migration_evidence(self, *, allow_missing: bool) -> None:
        for key in ("email", "", "username"):
            evidence_values = [{"sub": "different-subject"}]
            if not allow_missing:
                evidence_values.append({})
            for evidence in evidence_values:
                with self.subTest(key=key, evidence=evidence):
                    uid = self.user.username if key == "username" else self.user.email
                    social = self.user.social_auth.create(
                        provider="keycloak", id_key=key, uid=uid, extra_data=evidence
                    )
                    with self.assertRaises(AuthAssociationError) as error:
                        self.lookup()
                    self.assertEqual(
                        error.exception.code, "identifier_migration_conflict"
                    )
                    social.refresh_from_db()
                    self.assertEqual((social.id_key, social.uid), (key, uid))
                    self.assertEqual(social.extra_data, evidence)
                    social.delete()

    def test_ambiguous_legacy_matches_are_rejected(self) -> None:
        for key, uid in (("email", self.user.email), ("username", self.user.username)):
            self.user.social_auth.create(
                provider="keycloak",
                id_key=key,
                uid=uid,
                extra_data={"sub": self.claims["sub"]},
            )
        with self.assertRaises(AuthAssociationError) as error:
            self.lookup()
        self.assertEqual(error.exception.code, "identifier_migration_conflict")
        self.assertEqual(self.user.social_auth.exclude(id_key="sub").count(), 2)

    def test_subject_login_survives_email_change(self) -> None:
        social = self.user.social_auth.create(
            provider="keycloak", id_key="sub", uid=self.claims["sub"]
        )
        result = self.lookup(email="changed@example.com")
        self.assertEqual(result["user"], self.user)
        self.assertEqual(result["social"].pk, social.pk)

    def test_missing_subject_is_rejected(self) -> None:
        with self.assertRaises(AuthResponseError):
            self.identify(sub=None)
