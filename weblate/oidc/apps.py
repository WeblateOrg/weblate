# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from django.apps import AppConfig
from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.core.checks import Error, register
from django.core.exceptions import ImproperlyConfigured
from oauth2_provider.settings import oauth2_settings

from weblate.oidc.settings import get_provider_settings


def check_signing_key(**kwargs: object) -> list[Error]:
    """Check signing configuration without including secrets in errors."""
    try:
        keys = [
            oauth2_settings.OIDC_RSA_PRIVATE_KEY,
            *oauth2_settings.OIDC_RSA_PRIVATE_KEYS_INACTIVE,
        ]
        valid = all(is_valid_signing_key(pem) for pem in keys)
    except (ValueError, TypeError, AttributeError, UnsupportedAlgorithm):
        valid = False
    if not valid:
        return [
            Error(
                "OIDC requires RSA private signing keys of at least 2048 bits.",
                id="weblate_oidc.E001",
            )
        ]
    return []


def is_valid_signing_key(pem: str) -> bool:
    key = load_pem_private_key(pem.encode(), password=None)
    return isinstance(key, RSAPrivateKey) and key.key_size >= 2048


class OIDCConfig(AppConfig):
    name = "weblate.oidc"
    verbose_name = "OpenID Connect provider"

    def ready(self) -> None:
        # ruff: ignore[import-outside-top-level]
        from weblate.oidc.signals import (
            record_authentication_time,
            revoke_user_credentials,
        )
        from weblate.trans.signals import user_pre_delete  # ruff: ignore[import-outside-top-level]

        if not settings.OIDC_PROVIDER_ENABLED:
            msg = "Enable OIDC_PROVIDER_ENABLED when installing weblate.oidc."
            raise ImproperlyConfigured(msg)
        settings.OAUTH2_PROVIDER = {
            **get_provider_settings(),
            **getattr(settings, "OAUTH2_PROVIDER", {}),
        }
        oauth2_settings.reload()
        register(check_signing_key)
        user_pre_delete.connect(
            revoke_user_credentials, dispatch_uid="oidc-user-remove"
        )
        user_logged_in.connect(
            record_authentication_time, dispatch_uid="oidc-auth-time"
        )
