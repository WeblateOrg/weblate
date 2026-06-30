# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from urllib.parse import urlparse

from django.conf import settings
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.http import url_has_allowed_host_and_scheme
from social_django.strategy import DjangoStrategy

from weblate.accounts.flows import PASSWORD_RESET_EMAIL_SESSION
from weblate.utils.site import get_site_url


class WeblateStrategy(DjangoStrategy):
    @cached_property
    def _site_url(self):
        return urlparse(get_site_url())

    def request_data(self, merge=True):
        if not self.request:
            return {}
        if merge:
            data = self.request.GET.copy()
            data.update(self.request.POST)
        elif self.request.method == "POST":
            data = self.request.POST.copy()
        else:
            data = self.request.GET.copy()
        if (
            self.session.get("password_reset")
            and self.session.get(PASSWORD_RESET_EMAIL_SESSION)
            and "email" not in data
            and "partial_token" not in data
        ):
            data["email"] = self.session[PASSWORD_RESET_EMAIL_SESSION]
        # Weblate defaults invalid return URLs to the account page.
        if "next" in data and not url_has_allowed_host_and_scheme(
            data["next"], allowed_hosts=None
        ):
            data["next"] = f"{reverse('profile')}#account"
        return data

    def build_absolute_uri(self, path=None):
        if self.request:
            # ruff: ignore[private-member-access]
            self.request._current_scheme_host = get_site_url()
        return super().build_absolute_uri(path)

    def request_is_secure(self):
        return settings.ENABLE_HTTPS

    def request_port(self):
        return self._site_url.port

    def request_host(self):
        return self._site_url.hostname
