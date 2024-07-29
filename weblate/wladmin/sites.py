# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib import admin
from django.contrib.admin import AdminSite, sites
from django.utils.translation import gettext, gettext_lazy

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest


class WeblateAdminSite(AdminSite):
    site_header = gettext_lazy("Weblate administration")
    site_title = gettext_lazy("Weblate administration")
    index_template = "admin/weblate-index.html"
    enable_nav_sidebar = False

    @property
    def login_form(self):
        from weblate.accounts.forms import AdminLoginForm

        return AdminLoginForm

    @property
    def site_url(self):
        if settings.URL_PREFIX:
            return settings.URL_PREFIX
        return "/"

    def each_context(self, request: AuthenticatedHttpRequest):
        from weblate.wladmin.models import ConfigurationError

        result = super().each_context(request)
        empty = [gettext("Object listing turned off")]
        result["empty_selectable_objects_list"] = [empty]
        result["empty_objects_list"] = empty
        result["configuration_errors"] = ConfigurationError.objects.filter(
            ignored=False
        )
        return result


SITE = WeblateAdminSite()


def patch_admin_site() -> None:
    sites.site = admin.site = SITE
