# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import Any

from django.apps import apps
from django.conf import settings
from django.utils.translation import gettext_lazy

from weblate.utils.site import get_site_url

AUTH_TIME_SESSION_KEY = "weblate:oidc_auth_time"


def get_provider_settings() -> dict[str, Any]:
    """Return defaults for Weblate's optional identity provider."""
    prefix = settings.URL_PREFIX.strip("/")
    issuer_path = f"/{prefix}/oidc" if prefix else "/oidc"
    scopes = {
        "openid": gettext_lazy("Identify your account"),
        "profile": gettext_lazy("Read your name and username"),
        "email": gettext_lazy("Read your e-mail address"),
    }
    if apps.is_installed("weblate.legal"):
        scopes["weblate:legal"] = gettext_lazy(
            "Read the version of the legal documents you accepted"
        )
    return {
        "OIDC_ENABLED": True,
        "OIDC_ISS_ENDPOINT": get_site_url(issuer_path),
        "OAUTH2_VALIDATOR_CLASS": "weblate.oidc.validator.WeblateOAuth2Validator",
        "OAUTH2_BACKEND_CLASS": "weblate.oidc.backends.WeblateOAuthLibCore",
        "SCOPES": scopes,
        "DEFAULT_SCOPES": ["openid"],
        "OIDC_RESPONSE_TYPES_SUPPORTED": ["code"],
        "OIDC_TOKEN_ENDPOINT_AUTH_METHODS_SUPPORTED": [
            "client_secret_basic",
            "client_secret_post",
            "none",
        ],
        "PKCE_REQUIRED": True,
        "COMPLIANT_BCP_RFC9700_IMPLICIT_GRANT": True,
        "COMPLIANT_BCP_RFC9700_PASSWORD_GRANT": True,
        "COMPLIANT_BCP_RFC9700_PKCE_METHOD": True,
        "COMPLIANT_BCP_RFC9700_ACCESS_TOKEN_TRANSPORT": True,
        "COMPLIANT_BCP_RFC9700_AUTHZ_RESPONSE_ISS": True,
        "COMPLIANT_BCP_RFC9700_TOKEN_STORAGE": True,
        "COMPLIANT_BCP_RFC9700_REFRESH_TOKEN": True,
        "COMPLIANT_BCP_RFC9700_REDIRECT_URI_SCHEME": True,
        "COMPLIANT_BCP_RFC9700_REDIRECT_URI_MATCHING": True,
        "COMPLIANT_BCP_RFC9700_PKCE_REQUIRED": True,
        "ALLOWED_REDIRECT_URI_SCHEMES": ["https"],
        "ALLOW_URI_WILDCARDS": False,
        "ACCESS_TOKEN_EXPIRE_SECONDS": 3600,
        "ID_TOKEN_EXPIRE_SECONDS": 3600,
        "REFRESH_TOKEN_EXPIRE_SECONDS": 30 * 86400,
        "ROTATE_REFRESH_TOKEN": True,
        "REFRESH_TOKEN_REUSE_PROTECTION": True,
        "REFRESH_TOKEN_GRACE_PERIOD_SECONDS": 0,
        "DCR_ENABLED": False,
        "CIMD_ENABLED": False,
        "OIDC_RP_INITIATED_LOGOUT_ENABLED": False,
    }
