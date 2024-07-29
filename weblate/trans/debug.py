# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Wrapper to include useful information in error mails."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.views.debug import SafeExceptionReporterFilter

from weblate.utils.requirements import get_versions_list

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


class WeblateExceptionReporterFilter(SafeExceptionReporterFilter):
    def get_post_parameters(self, request: AuthenticatedHttpRequest):
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

            try:
                for name, _url, version in get_versions_list():
                    meta[f"WEBLATE_VERSION:{name}"] = version
            except FileNotFoundError:
                # Can happen during upgrade - the module is installed
                # in newer version and different path
                pass
            except OSError:
                # Out of memory or too many open files
                pass

        return super().get_post_parameters(request)
