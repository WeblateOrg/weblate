# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib import admin
from django.contrib.admin import AdminSite, sites
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.translation import gettext, gettext_lazy
from django.views.decorators.cache import never_cache

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

    def logout(self, request, extra_context=None):
        from weblate.accounts.views import WeblateLogoutView

        return WeblateLogoutView.as_view()(request)

    @method_decorator(never_cache)
    def login(self, request, extra_context=None):
        """
        Display the login form for the given HttpRequest.

        Essentially a copy of django.contrib.admin.sites.AdminSite.login
        """
        # Since this module gets imported in the application's root package,
        # it cannot import models from other applications at the module level,
        # and django.contrib.admin.forms eventually imports User.

        from weblate.accounts.views import BaseLoginView

        if request.method == "GET" and self.has_permission(request):
            # Already logged-in, redirect to admin index
            index_path = reverse("admin:index", current_app=self.name)
            return HttpResponseRedirect(index_path)

        context = {
            **self.each_context(request),
            "title": gettext("Sign in"),
            "subtitle": None,
            "app_path": request.get_full_path(),
            "username": request.user.get_username(),
        }
        if (
            REDIRECT_FIELD_NAME not in request.GET
            and REDIRECT_FIELD_NAME not in request.POST
        ):
            context[REDIRECT_FIELD_NAME] = reverse("admin:index", current_app=self.name)
        context.update(extra_context or {})

        defaults = {
            "extra_context": context,
            "authentication_form": self.login_form,
            "template_name": self.login_template or "admin/login.html",
        }
        request.current_app = self.name
        return BaseLoginView.as_view(**defaults)(request)

    @property
    def site_url(self):
        if settings.URL_PREFIX:
            return settings.URL_PREFIX
        return "/"

    def each_context(self, request: AuthenticatedHttpRequest):  # type: ignore[override]
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
