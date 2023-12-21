# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.urls import path

from weblate.legal.views import (
    ContractsView,
    CookiesView,
    LegalView,
    PrivacyView,
    TermsView,
    tos_confirm,
)

urlpatterns = [
    path("", LegalView.as_view(), name="index"),
    path("terms/", TermsView.as_view(), name="terms"),
    path("cookies/", CookiesView.as_view(), name="cookies"),
    path("privacy/", PrivacyView.as_view(), name="privacy"),
    path("contracts/", ContractsView.as_view(), name="contracts"),
    path("confirm/", tos_confirm, name="confirm"),
]
