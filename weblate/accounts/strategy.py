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

from importlib import import_module

from django.conf import settings
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from social_django.strategy import DjangoStrategy

from weblate.utils.site import get_site_url


def create_session(*args):
    engine = import_module(settings.SESSION_ENGINE)
    return engine.SessionStore(*args)


class WeblateStrategy(DjangoStrategy):
    def __init__(self, storage, request=None, tpl=None):
        """Restore session data based on passed ID."""
        super().__init__(storage, request, tpl)
        if request and "verification_code" in request.GET and "id" in request.GET:
            self.session = create_session(request.GET["id"])

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
            self.request.__dict__["_current_scheme_host"] = get_site_url()
        return super().build_absolute_uri(path)

    def clean_partial_pipeline(self, token):
        # The cleanup somehow breaks our partial pipelines, simply skip
        # it for now
        # See https://github.com/python-social-auth/social-core/issues/287
        return

    def really_clean_partial_pipeline(self, token):
        super().clean_partial_pipeline(token)
