#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from django.conf import settings
from django.urls import include, path

import weblate.accounts.views
import weblate.utils.urls

# Follows copy of social_django.urls with few changes:
# - authentication requires POST (issue submitted upstream)
# - authentication stores current user (to avoid CSRF on complete)
# - removed some configurability (just to avoid additional deps)
# - the association_id has to be numeric (patch accepted upstream)
social_urls = [
    # authentication / association
    path("login/<slug:backend>/", weblate.accounts.views.social_auth, name="begin"),
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
    path("watch/<name:project>/", weblate.accounts.views.watch, name="watch"),
    path(
        "watch/<name:project>/<name:component>/",
        weblate.accounts.views.watch,
        name="watch",
    ),
    path("unwatch/<name:project>/", weblate.accounts.views.unwatch, name="unwatch"),
    path(
        "mute/<name:project>/<name:component>/",
        weblate.accounts.views.mute_component,
        name="mute",
    ),
    path("mute/<name:project>/", weblate.accounts.views.mute_project, name="mute"),
    path("remove/", weblate.accounts.views.user_remove, name="remove"),
    path("confirm/", weblate.accounts.views.confirm, name="confirm"),
    path("login/", weblate.accounts.views.WeblateLoginView.as_view(), name="login"),
    path("register/", weblate.accounts.views.register, name="register"),
    path("email/", weblate.accounts.views.email_login, name="email_login"),
    path("", include((social_urls, "social_auth"), namespace="social")),
]

if "simple_sso.sso_server" in settings.INSTALLED_APPS:
    # pylint: disable=wrong-import-position
    from simple_sso.sso_server.server import Server

    server = Server()
    urlpatterns.append(path("sso/", include(server.get_urls())))
