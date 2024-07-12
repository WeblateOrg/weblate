# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from importlib import import_module
from urllib.parse import urlparse

from django.conf import settings
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.http import url_has_allowed_host_and_scheme
from social_django.strategy import DjangoStrategy

from weblate.utils.site import get_site_url


def create_session(*args):
    engine = import_module(settings.SESSION_ENGINE)
    return engine.SessionStore(*args)


class WeblateStrategy(DjangoStrategy):
    def __init__(self, storage, request=None, tpl=None) -> None:
        """Restore session data based on passed ID."""
        super().__init__(storage, request, tpl)
        if request and "verification_code" in request.GET and "id" in request.GET:
            self.session = create_session(request.GET["id"])

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
        # This is mostly fix for lack of next validation in Python Social Auth
        # - https://github.com/python-social-auth/social-core/pull/92
        # - https://github.com/python-social-auth/social-core/issues/62
        if "next" in data and not url_has_allowed_host_and_scheme(
            data["next"], allowed_hosts=None
        ):
            data["next"] = "{}#account".format(reverse("profile"))
        return data

    def build_absolute_uri(self, path=None):
        if self.request:
            self.request._current_scheme_host = get_site_url()  # noqa: SLF001
        return super().build_absolute_uri(path)

    def clean_partial_pipeline(self, token) -> None:
        # The cleanup somehow breaks our partial pipelines, simply skip
        # it for now
        # See https://github.com/python-social-auth/social-core/issues/287
        return

    def really_clean_partial_pipeline(self, token) -> None:
        super().clean_partial_pipeline(token)

    def request_is_secure(self):
        return settings.ENABLE_HTTPS

    def request_port(self):
        return self._site_url.port

    def request_host(self):
        return self._site_url.hostname
