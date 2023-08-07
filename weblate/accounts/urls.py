# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.conf import settings
from django.urls import include, path

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
    path("", include((social_urls, "social_auth"), namespace="social")),
]

if "simple_sso.sso_server" in settings.INSTALLED_APPS:
    from simple_sso.sso_server.server import Server

    server = Server()
    urlpatterns.append(path("sso/", include(server.get_urls())))
