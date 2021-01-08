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
"""Wrapper to include useful information in error mails."""

from django.views.debug import SafeExceptionReporterFilter

from weblate.utils.requirements import get_versions_list


class WeblateExceptionReporterFilter(SafeExceptionReporterFilter):
    def get_post_parameters(self, request):
        if hasattr(request, "META"):
            meta = request.META
            if hasattr(request, "user"):
                meta["WEBLATE_USER"] = repr(request.user.username)
            else:
                meta["WEBLATE_USER"] = ""
            if hasattr(request, "session") and "django_language" in request.session:
                meta["WEBLATE_LANGUAGE"] = request.session["django_language"]
            else:
                meta["WEBLATE_LANGUAGE"] = ""

            for name, _url, version in get_versions_list():
                meta[f"WEBLATE_VERSION:{name}"] = version

        return super().get_post_parameters(request)
