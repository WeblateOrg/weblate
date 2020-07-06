#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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
from django.conf.urls import include, url

import weblate.accounts.views

# Follows copy of social_django.urls with few changes:
# - authentication requires POST (issue submitted upstream)
# - authentication stores current user (to avoid CSRF on complete)
# - removed some configurability (just to avoid additional deps)
# - the association_id has to be numeric (patch accepted upstream)
social_urls = [
    # authentication / association
    url(
        r"^login/(?P<backend>[^/]+)/$", weblate.accounts.views.social_auth, name="begin"
    ),
    url(
        r"^complete/(?P<backend>[^/]+)/$",
        weblate.accounts.views.social_complete,
        name="complete",
    ),
    # disconnection
    url(
        r"^disconnect/(?P<backend>[^/]+)/$",
        weblate.accounts.views.social_disconnect,
        name="disconnect",
    ),
    url(
        r"^disconnect/(?P<backend>[^/]+)/(?P<association_id>\d+)/$",
        weblate.accounts.views.social_disconnect,
        name="disconnect_individual",
    ),
    # SAML
    url(
        r"^metadata/saml/$", weblate.accounts.views.saml_metadata, name="saml-metadata"
    ),
]

urlpatterns = [
    url(
        r"^email-sent/$",
        weblate.accounts.views.EmailSentView.as_view(),
        name="email-sent",
    ),
    url(r"^password/$", weblate.accounts.views.password, name="password"),
    url(
        r"^reset-api-key/$", weblate.accounts.views.reset_api_key, name="reset-api-key"
    ),
    url(r"^reset/$", weblate.accounts.views.reset_password, name="password_reset"),
    url(
        r"^logout/$", weblate.accounts.views.WeblateLogoutView.as_view(), name="logout"
    ),
    url(r"^profile/$", weblate.accounts.views.user_profile, name="profile"),
    url(r"^userdata/$", weblate.accounts.views.userdata, name="userdata"),
    url(r"^unsubscribe/$", weblate.accounts.views.unsubscribe, name="unsubscribe"),
    url(r"^subscribe/$", weblate.accounts.views.subscribe, name="subscribe"),
    url(r"^watch/(?P<project>[^/]+)/$", weblate.accounts.views.watch, name="watch"),
    url(
        r"^unwatch/(?P<project>[^/]+)/$", weblate.accounts.views.unwatch, name="unwatch"
    ),
    url(
        r"^mute/(?P<project>[^/]+)/(?P<component>[^/]+)/$",
        weblate.accounts.views.mute_component,
        name="mute",
    ),
    url(
        r"^mute/(?P<project>[^/]+)/$", weblate.accounts.views.mute_project, name="mute"
    ),
    url(r"^remove/$", weblate.accounts.views.user_remove, name="remove"),
    url(r"^confirm/$", weblate.accounts.views.confirm, name="confirm"),
    url(r"^login/$", weblate.accounts.views.WeblateLoginView.as_view(), name="login"),
    url(r"^register/$", weblate.accounts.views.register, name="register"),
    url(r"^email/$", weblate.accounts.views.email_login, name="email_login"),
    url(r"", include((social_urls, "social_auth"), namespace="social")),
]

if "simple_sso.sso_server" in settings.INSTALLED_APPS:
    # pylint: disable=wrong-import-position
    from simple_sso.sso_server.server import Server

    server = Server()
    urlpatterns.append(url(r"^sso/", include(server.get_urls())))
