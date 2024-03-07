# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_ipv46_address
from django.http import Http404, HttpResponsePermanentRedirect
from django.shortcuts import redirect
from django.urls import is_valid_path, reverse
from django.urls.exceptions import NoReverseMatch
from django.utils.http import escape_leading_slashes
from django.utils.translation import gettext_lazy

from weblate.lang.models import Language
from weblate.trans.models import Change, Component, Project
from weblate.utils.errors import report_error
from weblate.utils.site import get_site_url
from weblate.utils.views import parse_path

CSP_TEMPLATE = (
    "default-src 'self'; style-src {0}; img-src {1}; script-src {2}; "
    "connect-src {3}; object-src 'none'; font-src {4};"
    "frame-src 'none'; frame-ancestors 'none';"
)

# URLs requiring inline javascript
INLINE_PATHS = {"social:begin", "djangosaml2idp:saml_login_process"}


class ProxyMiddleware:
    """
    Middleware that updates REMOTE_ADDR from proxy.

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
            address = proxy.split(",")[settings.IP_PROXY_OFFSET].strip()
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
        if response.status_code == 404 and self.should_redirect_with_slash(request):
            new_path = request.get_full_path(force_append_slash=True)
            # Prevent construction of scheme relative urls.
            new_path = escape_leading_slashes(new_path)
            return HttpResponsePermanentRedirect(new_path)
        return response

    def should_redirect_with_slash(self, request):
        path = request.path_info
        # Avoid redirecting non GET requests, these would fail anyway due to
        # missing parameters.
        # Redirecting on API removes authentication headers in many cases,
        # so avoid that as well.
        # Redirecting requests for Sourcemap files will not do anything good
        if (
            path.endswith(("/", ".map"))
            or request.method != "GET"
            or path.startswith(f"{settings.URL_PREFIX}/api")
        ):
            return False
        urlconf = getattr(request, "urlconf", None)
        slash_path = f"{path}/"
        return not is_valid_path(path, urlconf) and is_valid_path(slash_path, urlconf)

    def fixup_language(self, lang):
        return Language.objects.fuzzy_get(code=lang, strict=True)

    def fixup_project(self, slug, request):
        try:
            project = Project.objects.get(slug__iexact=slug)
        except Project.MultipleObjectsReturned:
            return None
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
            # Try uncategorized component first
            component = project.component_set.get(category=None, slug__iexact=slug)
        except Component.DoesNotExist:
            try:
                # Fallback to any such named component in project
                component = project.component_set.filter(slug__iexact=slug)[0]
            except IndexError:
                try:
                    # Look for renamed components in a project
                    component = (
                        project.change_set.filter(
                            action=Change.ACTION_RENAME_COMPONENT, old=slug
                        )
                        .order()[0]
                        .component
                    )
                except IndexError:
                    return None

        request.user.check_access_component(component)
        return component

    def check_existing_translations(self, name: str, project: Project):
        """
        Check in existing translations for specific language.

        Return False if language translation not present, else True.
        """
        return any(lang.name == name for lang in project.languages)

    def process_exception(self, request, exception):  # noqa: C901
        from weblate.utils.views import UnsupportedPathObjectError

        if not isinstance(exception, Http404):
            return None

        try:
            resolver_match = request.resolver_match
        except AttributeError:
            return None

        kwargs = dict(resolver_match.kwargs)
        path = list(kwargs.get("path", ()))
        language_name = None
        if not path:
            return None

        if isinstance(exception, UnsupportedPathObjectError):
            # Redirect to parent for unsupported locations
            path = path[:-1]
        else:
            # Try using last part as a language
            language_len = 0
            if len(path) >= 3:
                language = self.fixup_language(path[-1])
                if language is not None:
                    path[-1] = language.code
                    language_name = language.name
                    language_len = 1

            try:
                # Check if project exists
                project = parse_path(request, path[:1], (Project,))
            except UnsupportedPathObjectError:
                return None
            except Http404:
                project = self.fixup_project(path[0], request)
                if project is None:
                    return None
                path[0] = project.slug

            if len(path) >= 2:
                if path[1] != "-":
                    path_offset = len(path) - (language_len)
                    try:
                        # Check if component exists
                        component = parse_path(
                            request, path[:path_offset], (Component,)
                        )
                    except UnsupportedPathObjectError:
                        return None
                    except Http404:
                        component = self.fixup_component(
                            path[-1 - language_len], request, project
                        )
                        if component is None:
                            return None
                        path[:path_offset] = component.get_url_path()

                if language_name:
                    existing_trans = self.check_existing_translations(
                        language_name, project
                    )
                    if not existing_trans:
                        messages.add_message(
                            request,
                            messages.INFO,
                            gettext_lazy(
                                "%s translation is currently not available, "
                                "but can be added."
                            )
                            % language_name,
                        )
                        return redirect(reverse("show", kwargs={"path": path[:-1]}))

        if path != kwargs["path"]:
            kwargs["path"] = path
            query = request.META["QUERY_STRING"]
            if query:
                query = f"?{query}"
            try:
                new_url = reverse(resolver_match.url_name, kwargs=kwargs)
            except NoReverseMatch:
                return None
            return HttpResponsePermanentRedirect(f"{new_url}{query}")

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
            script.add("care.weblate.org")
            connect.add("care.weblate.org")
            style.add("care.weblate.org")

        # Rollbar client errors reporting
        if (
            (rollbar_settings := getattr(settings, "ROLLBAR", None)) is not None
            and "client_token" in rollbar_settings
            and "environment" in rollbar_settings
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
            response["Content-Security-Policy"] += (
                f" report-uri {settings.SENTRY_SECURITY}"
            )
            response["Expect-CT"] = (
                f'max-age=86400, enforce, report-uri="{settings.SENTRY_SECURITY}"'
            )

        # Opt-out from Google FLoC
        response["Permissions-Policy"] = "interest-cohort=()"

        return response
