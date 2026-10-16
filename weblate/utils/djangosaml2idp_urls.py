# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from django.urls import path
from djangosaml2idp import views

from weblate.utils.djangosaml2idp_views import sso_entry

app_name = "djangosaml2idp"

urlpatterns = [
    path("sso/init/", views.SSOInitView.as_view(), name="saml_idp_init"),
    path("sso/<str:binding>/", sso_entry, name="saml_login_binding"),
    path(
        "login/process/",
        views.LoginProcessView.as_view(),
        name="saml_login_process",
    ),
    path(
        "login/process_multi_factor/",
        views.get_multifactor,
        name="saml_multi_factor",
    ),
    path("metadata/", views.metadata, name="saml2_idp_metadata"),
]
