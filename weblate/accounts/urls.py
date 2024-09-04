# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import django_otp_webauthn.views
from django.conf import settings
from django.urls import include, path
from django.views.i18n import JavaScriptCatalog

import weblate.accounts.views
import weblate.auth.views
from weblate.utils.urls import register_weblate_converters

register_weblate_converters()


# Follows copy of social_django.urls with few changes:
# - authentication requires POST (issue submitted upstream)
# - authentication stores current user (to avoid CSRF on complete)
# - removed some configurability (just to avoid additional deps)
# - the association_id has to be numeric (patch accepted upstream)
social_urls = [
    # user authentication / association
    path("login/<slug:backend>/", weblate.accounts.views.social_auth, name="begin"),
    # partial pipeline completion
    path(
        "complete/<slug:backend>/",
        weblate.accounts.views.social_complete,
        name="complete",
    ),
    # disconnection
    path(
        "disconnect/<slug:backend>/",
        weblate.accounts.views.social_disconnect,
        name="disconnect",
    ),
    path(
        "disconnect/<slug:backend>/<int:association_id>/",
        weblate.accounts.views.social_disconnect,
        name="disconnect_individual",
    ),
    # SAML
    path("metadata/saml/", weblate.accounts.views.saml_metadata, name="saml-metadata"),
]

# WebAuthn views, this is modified django_otp_webauth.urls
webauthn_urls = [
    path(
        "registration/begin/",
        django_otp_webauthn.views.BeginCredentialRegistrationView.as_view(),
        name="credential-registration-begin",
    ),
    path(
        "registration/complete/",
        django_otp_webauthn.views.CompleteCredentialRegistrationView.as_view(),
        name="credential-registration-complete",
    ),
    path(
        "authentication/begin/",
        weblate.accounts.views.WeblateBeginCredentialAuthenticationView.as_view(),
        name="credential-authentication-begin",
    ),
    path(
        "authentication/complete/",
        weblate.accounts.views.WeblateCompleteCredentialAuthenticationView.as_view(),
        name="credential-authentication-complete",
    ),
    path(
        "jsi18n/",
        JavaScriptCatalog.as_view(packages=["django_otp_webauthn"]),
        name="js-i18n-catalog",
    ),
]

urlpatterns = [
    path(
        "email-sent/",
        weblate.accounts.views.EmailSentView.as_view(),
        name="email-sent",
    ),
    path("password/", weblate.accounts.views.password, name="password"),
    path("reset-api-key/", weblate.accounts.views.reset_api_key, name="reset-api-key"),
    path("reset/", weblate.accounts.views.reset_password, name="password_reset"),
    path("logout/", weblate.accounts.views.WeblateLogoutView.as_view(), name="logout"),
    path("profile/", weblate.accounts.views.user_profile, name="profile"),
    path("userdata/", weblate.accounts.views.userdata, name="userdata"),
    path("unsubscribe/", weblate.accounts.views.unsubscribe, name="unsubscribe"),
    path("subscribe/", weblate.accounts.views.subscribe, name="subscribe"),
    path("watch/<object_path:path>/", weblate.accounts.views.watch, name="watch"),
    path("unwatch/<object_path:path>/", weblate.accounts.views.unwatch, name="unwatch"),
    path("mute/<object_path:path>/", weblate.accounts.views.mute, name="mute"),
    path("remove/", weblate.accounts.views.user_remove, name="remove"),
    path("confirm/", weblate.accounts.views.confirm, name="confirm"),
    path("login/", weblate.accounts.views.WeblateLoginView.as_view(), name="login"),
    path("register/", weblate.accounts.views.register, name="register"),
    path("email/", weblate.accounts.views.email_login, name="email_login"),
    path(
        "invitation/<uuid:pk>/",
        weblate.auth.views.InvitationView.as_view(),
        name="invitation",
    ),
    path(
        "auth/second-factor/<slug:backend>/",
        weblate.accounts.views.SecondFactorLoginView.as_view(),
        name="2fa-login",
    ),
    path(
        "auth/tokens/webauthn/<int:pk>/",
        weblate.accounts.views.WebAuthnCredentialView.as_view(),
        name="webauthn-detail",
    ),
    path(
        "auth/tokens/totp/",
        weblate.accounts.views.TOTPView.as_view(),
        name="totp",
    ),
    path(
        "auth/tokens/totp/<int:pk>/",
        weblate.accounts.views.TOTPDetailView.as_view(),
        name="totp-detail",
    ),
    path(
        "auth/tokens/recovery-codes/",
        weblate.accounts.views.RecoveryCodesView.as_view(),
        name="recovery-codes",
    ),
    path("", include((social_urls, "social_auth"), namespace="social")),
    path(
        "auth/webauthn/",
        include((webauthn_urls, "django_otp_webauthn"), namespace="otp_webauthn"),
    ),
]

if "simple_sso.sso_server" in settings.INSTALLED_APPS:
    from simple_sso.sso_server.server import Server

    server = Server()
    urlpatterns.append(path("sso/", include(server.get_urls())))
