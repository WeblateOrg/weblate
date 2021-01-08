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

from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_ipv46_address
from django.http import Http404, HttpResponsePermanentRedirect
from django.urls import is_valid_path, reverse
from django.utils.http import escape_leading_slashes

from weblate.lang.models import Language
from weblate.trans.models import Change, Component, Project
from weblate.utils.errors import report_error
from weblate.utils.site import get_site_url

CSP_TEMPLATE = (
    "default-src 'self'; style-src {0}; img-src {1}; script-src {2}; "
    "connect-src {3}; object-src 'none'; font-src {4};"
    "frame-src 'none'; frame-ancestors 'none';"
)

# URLs requiring inline javascipt
INLINE_PATHS = {"social:begin", "djangosaml2idp:saml_login_process"}


class ProxyMiddleware:
    """Middleware that updates REMOTE_ADDR from proxy.

    Note that this can have security implications and settings have to match your actual
    proxy setup.
    """

    def __init__(self, get_response=None):
        self.get_response = get_response

    def __call__(self, request):
        # Fake HttpRequest attribute to inject configured
        # site name into build_absolute_uri
        request._current_scheme_host = get_site_url()

        # Actual proxy handling
        proxy = None
        if settings.IP_BEHIND_REVERSE_PROXY:
            proxy = request.META.get(settings.IP_PROXY_HEADER)
        if proxy:
            # X_FORWARDED_FOR returns client1, proxy1, proxy2,...
            address = proxy.split(", ")[settings.IP_PROXY_OFFSET].strip()
            try:
                validate_ipv46_address(address)
                request.META["REMOTE_ADDR"] = address
            except ValidationError:
                report_error(cause="Invalid IP address")

        return self.get_response(request)


class RedirectMiddleware:
    """
    Middleware that handles URL redirecting.

    This used for fuzzy lookups of projects, for example case insensitive
    or after renaming.
    """

    def __init__(self, get_response=None):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # This is based on APPEND_SLASH handling in Django
        if response.status_code == 404:
            if self.should_redirect_with_slash(request):
                new_path = request.get_full_path(force_append_slash=True)
                # Prevent construction of scheme relative urls.
                new_path = escape_leading_slashes(new_path)
                return HttpResponsePermanentRedirect(new_path)
        return response

    def should_redirect_with_slash(self, request):
        path = request.path_info
        # Avoid redirecting non GET requests, these would fail anyway
        if path.endswith("/") or request.method != "GET":
            return False
        urlconf = getattr(request, "urlconf", None)
        slash_path = f"{path}/"
        return not is_valid_path(path, urlconf) and is_valid_path(slash_path, urlconf)

    def fixup_language(self, lang):
        return Language.objects.fuzzy_get(code=lang, strict=True)

    def fixup_project(self, slug, request):
        try:
            project = Project.objects.get(slug__iexact=slug)
        except Project.DoesNotExist:
            try:
                project = (
                    Change.objects.filter(
                        action=Change.ACTION_RENAME_PROJECT,
                        old=slug,
                    )
                    .order()[0]
                    .project
                )
            except IndexError:
                return None

        request.user.check_access(project)
        return project

    def fixup_component(self, slug, request, project):
        try:
            component = Component.objects.get(project=project, slug__iexact=slug)
        except Component.DoesNotExist:
            try:
                component = (
                    Change.objects.filter(
                        action=Change.ACTION_RENAME_COMPONENT, old=slug
                    )
                    .order()[0]
                    .component
                )
            except IndexError:
                return None

        request.user.check_access_component(component)
        return component

    def process_exception(self, request, exception):
        if not isinstance(exception, Http404):
            return None

        try:
            resolver_match = request.resolver_match
        except AttributeError:
            return None

        resolver_match = request.resolver_match

        kwargs = dict(resolver_match.kwargs)

        if "lang" in kwargs:
            language = self.fixup_language(kwargs["lang"])
            if language is None:
                return None
            kwargs["lang"] = language.code

        if "project" in kwargs:
            project = self.fixup_project(kwargs["project"], request)
            if project is None:
                return None
            kwargs["project"] = project.slug

            if "component" in kwargs:
                component = self.fixup_component(kwargs["component"], request, project)
                if component is None:
                    return None
                kwargs["component"] = component.slug

        if kwargs != resolver_match.kwargs:
            query = request.META["QUERY_STRING"]
            if query:
                query = f"?{query}"
            return HttpResponsePermanentRedirect(
                reverse(resolver_match.url_name, kwargs=kwargs) + query
            )

        return None


class SecurityMiddleware:
    """Middleware that sets Content-Security-Policy."""

    def __init__(self, get_response=None):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # No CSP for debug mode (to allow djdt or error pages)
        if settings.DEBUG:
            return response

        style = {"'self'", "'unsafe-inline'"} | set(settings.CSP_STYLE_SRC)
        script = {"'self'"} | set(settings.CSP_SCRIPT_SRC)
        image = {"'self'"} | set(settings.CSP_IMG_SRC)
        connect = {"'self'"} | set(settings.CSP_CONNECT_SRC)
        font = {"'self'"} | set(settings.CSP_FONT_SRC)

        if request.resolver_match and request.resolver_match.view_name in INLINE_PATHS:
            script.add("'unsafe-inline'")

        # Support form
        if request.resolver_match and request.resolver_match.view_name == "manage":
            script.add("'care.weblate.org'")

        # Rollbar client errors reporting
        if (
            hasattr(settings, "ROLLBAR")
            and "client_token" in settings.ROLLBAR
            and "environment" in settings.ROLLBAR
            and response.status_code == 500
        ):
            script.add("'unsafe-inline'")
            script.add("cdnjs.cloudflare.com")
            connect.add("api.rollbar.com")

        # Sentry user feedback
        if settings.SENTRY_DSN and response.status_code == 500:
            domain = urlparse(settings.SENTRY_DSN).hostname
            script.add(domain)
            script.add("sentry.io")
            connect.add(domain)
            connect.add("sentry.io")
            script.add("'unsafe-inline'")
            image.add("data:")

        # Matomo (Piwik) analytics
        if settings.MATOMO_URL:
            domain = urlparse(settings.MATOMO_URL).hostname
            script.add(domain)
            image.add(domain)
            connect.add(domain)

        # Google Analytics
        if settings.GOOGLE_ANALYTICS_ID:
            script.add("'unsafe-inline'")
            script.add("www.google-analytics.com")
            image.add("www.google-analytics.com")

        # External media URL
        if "://" in settings.MEDIA_URL:
            domain = urlparse(settings.MEDIA_URL).hostname
            image.add(domain)

        # External static URL
        if "://" in settings.STATIC_URL:
            domain = urlparse(settings.STATIC_URL).hostname
            script.add(domain)
            image.add(domain)
            style.add(domain)
            font.add(domain)

        # CDN for fonts
        if settings.FONTS_CDN_URL:
            domain = urlparse(settings.FONTS_CDN_URL).hostname
            style.add(domain)
            font.add(domain)

        # When using external image for Auth0 provider, add it here
        if "://" in settings.SOCIAL_AUTH_AUTH0_IMAGE:
            domain = urlparse(settings.SOCIAL_AUTH_AUTH0_IMAGE).hostname
            image.add(domain)

        response["Content-Security-Policy"] = CSP_TEMPLATE.format(
            " ".join(style),
            " ".join(image),
            " ".join(script),
            " ".join(connect),
            " ".join(font),
        )
        if settings.SENTRY_SECURITY:
            response["Content-Security-Policy"] += " report-uri {}".format(
                settings.SENTRY_SECURITY
            )
            response["Expect-CT"] = 'max-age=86400, enforce, report-uri="{}"'.format(
                settings.SENTRY_SECURITY
            )

        return response
