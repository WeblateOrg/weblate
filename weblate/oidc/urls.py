# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.urls import path
from oauth2_provider import views

from weblate.oidc.views import (
    WeblateAuthorizationView,
    WeblateDiscoveryView,
)

app_name = "oauth2_provider"

urlpatterns = [
    path("authorize/", WeblateAuthorizationView.as_view(), name="authorize"),
    path("token/", views.TokenView.as_view(), name="token"),
    path("revoke_token/", views.RevokeTokenView.as_view(), name="revoke-token"),
    path("userinfo/", views.UserInfoView.as_view(), name="user-info"),
    path(
        ".well-known/openid-configuration",
        WeblateDiscoveryView.as_view(),
        name="oidc-connect-discovery-info",
    ),
    path(".well-known/jwks.json", views.JwksInfoView.as_view(), name="jwks-info"),
]
