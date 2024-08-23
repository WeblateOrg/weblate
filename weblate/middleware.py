# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_ipv46_address
from django.http import Http404, HttpResponse, HttpResponsePermanentRedirect
from django.shortcuts import redirect
from django.urls import is_valid_path, reverse
from django.urls.exceptions import NoReverseMatch
from django.utils.http import escape_leading_slashes
from django.utils.translation import gettext_lazy
from social_core.backends.oauth import OAuthAuth
from social_core.backends.open_id import OpenIdAuth
from social_django.utils import load_strategy

from weblate.auth.models import AuthenticatedHttpRequest, get_auth_backends
from weblate.lang.models import Language
from weblate.trans.models import Change, Component, Project
from weblate.utils.errors import report_error
from weblate.utils.site import get_site_url
from weblate.utils.views import parse_path

if TYPE_CHECKING:
    from weblate.accounts.strategy import WeblateStrategy

CSP_DIRECTIVES: dict[str, set[str]] = {
    "default-src": {"'none'"},
    "style-src": {"'self'", "'unsafe-inline'"},
    "img-src": {"'self'"},
    "script-src": {"'self'"},
    "connect-src": {"'self'"},
    "object-src": {"'none'"},
    "font-src": {"'self'"},
    "frame-src": {"'none'"},
    "frame-ancestors": {"'none'"},
    "base-uri": {"'none'"},
    "form-action": {"'self'"},
    "manifest-src": {"'self'"},
}

# URLs requiring inline javascript
INLINE_PATHS = {"social:begin", "djangosaml2idp:saml_login_process"}


class ProxyMiddleware:
    """
    Middleware that updates REMOTE_ADDR from proxy.

    Note that this can have security implications and settings have to match your actual
    proxy setup.
    """

    def __init__(self, get_response=None) -> None:
        self.get_response = get_response

    def __call__(self, request: AuthenticatedHttpRequest):
        # Fake HttpRequest attribute to inject configured
        # site name into build_absolute_uri
        request._current_scheme_host = get_site_url()  # noqa: SLF001

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
                report_error("Invalid IP address")

        return self.get_response(request)


class RedirectMiddleware:
    """
    Middleware that handles URL redirecting.

    This used for fuzzy lookups of projects, for example case insensitive
    or after renaming.
    """

    def __init__(self, get_response=None) -> None:
        self.get_response = get_response

    def __call__(self, request: AuthenticatedHttpRequest):
        response = self.get_response(request)
        # This is based on APPEND_SLASH handling in Django
        if response.status_code == 404 and self.should_redirect_with_slash(request):
            new_path = request.get_full_path(force_append_slash=True)
            # Prevent construction of scheme relative urls.
            new_path = escape_leading_slashes(new_path)
            return HttpResponsePermanentRedirect(new_path)
        return response

    def should_redirect_with_slash(self, request: AuthenticatedHttpRequest):
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

    def fixup_language(self, lang: str) -> Language | None:
        return Language.objects.fuzzy_get_strict(code=lang)

    def fixup_project(self, slug, request: AuthenticatedHttpRequest):
        try:
            project = Project.objects.get(slug__iexact=slug)
        except Project.MultipleObjectsReturned:
            return None
        except Project.DoesNotExist:
            project = Change.objects.lookup_project_rename(slug)
            if project is None:
                return None

        request.user.check_access(project)
        return project

    def fixup_component(self, slug, request: AuthenticatedHttpRequest, project):
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

    def process_exception(self, request: AuthenticatedHttpRequest, exception):  # noqa: C901
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


class CSPBuilder:
    directives: dict[str, set[str]]
    request: AuthenticatedHttpRequest
    response: HttpResponse

    def __init__(
        self, request: AuthenticatedHttpRequest, response: HttpResponse
    ) -> None:
        self.directives = deepcopy(CSP_DIRECTIVES)
        self.request = request
        self.response = response
        self.apply_csp_settings()
        self.build_csp_inline()
        self.build_csp_support()
        self.build_csp_rollbar()
        self.build_csp_sentry()
        self.build_csp_piwik()
        self.build_csp_google_analytics()
        self.build_csp_media_url()
        self.build_csp_static_url()
        self.build_csp_cdn()
        self.build_csp_auth()

    def apply_csp_settings(self) -> None:
        setting_names = (
            "CSP_STYLE_SRC",
            "CSP_SCRIPT_SRC",
            "CSP_IMG_SRC",
            "CSP_CONNECT_SRC",
            "CSP_FONT_SRC",
            "CSP_FORM_SRC",
        )
        for name in setting_names:
            value = getattr(settings, name)
            if value:
                rule = name[4:].lower().replace("_", "-")
                self.directives[rule].update(value)

    def build_csp_inline(self) -> None:
        if (
            self.request.resolver_match
            and self.request.resolver_match.view_name in INLINE_PATHS
        ):
            self.directives["script-src"].add("'unsafe-inline'")

    def build_csp_support(self) -> None:
        # Support form
        if (
            self.request.resolver_match
            and self.request.resolver_match.view_name == "manage"
        ):
            self.directives["script-src"].add("care.weblate.org")
            self.directives["connect-src"].add("care.weblate.org")
            self.directives["style-src"].add("care.weblate.org")
            self.directives["form-action"].add("care.weblate.org")

    def build_csp_rollbar(self) -> None:
        # Rollbar client errors reporting
        if (
            (rollbar_settings := getattr(settings, "ROLLBAR", None)) is not None
            and "client_token" in rollbar_settings
            and "environment" in rollbar_settings
            and self.response.status_code == 500
        ):
            self.directives["script-src"].add("'unsafe-inline'")
            self.directives["script-src"].add("cdnjs.cloudflare.com")
            self.directives["connect-src"].add("api.rollbar.com")

    def build_csp_sentry(self) -> None:
        # Sentry user feedback
        if settings.SENTRY_DSN and self.response.status_code == 500:
            domain = urlparse(settings.SENTRY_DSN).hostname
            self.directives["script-src"].add(domain)
            self.directives["connect-src"].add(domain)
            # Add appropriate frontend servers for sentry.io
            if domain.endswith("de.sentry.io"):
                self.directives["connect-src"].add("de.sentry.io")
                self.directives["script-src"].add("de.sentry.io")
            elif domain.endswith("sentry.io"):
                self.directives["script-src"].add("sentry.io")
                self.directives["connect-src"].add("sentry.io")
            self.directives["script-src"].add("'unsafe-inline'")
            self.directives["img-src"].add("data:")

    def build_csp_piwik(self) -> None:
        # Matomo (Piwik) analytics
        if settings.MATOMO_URL:
            domain = urlparse(settings.MATOMO_URL).hostname
            self.directives["script-src"].add(domain)
            self.directives["img-src"].add(domain)
            self.directives["connect-src"].add(domain)

    def build_csp_google_analytics(self) -> None:
        # Google Analytics
        if settings.GOOGLE_ANALYTICS_ID:
            self.directives["script-src"].add("'unsafe-inline'")
            self.directives["script-src"].add("www.google-analytics.com")
            self.directives["img-src"].add("www.google-analytics.com")

    def build_csp_media_url(self) -> None:
        # External media URL
        if "://" in settings.MEDIA_URL:
            domain = urlparse(settings.MEDIA_URL).hostname
            self.directives["img-src"].add(domain)

    def build_csp_static_url(self) -> None:
        # External static URL
        if "://" in settings.STATIC_URL:
            domain = urlparse(settings.STATIC_URL).hostname
            self.directives["script-src"].add(domain)
            self.directives["img-src"].add(domain)
            self.directives["style-src"].add(domain)
            self.directives["font-src"].add(domain)

    def build_csp_cdn(self) -> None:
        # CDN for fonts
        if settings.FONTS_CDN_URL:
            domain = urlparse(settings.FONTS_CDN_URL).hostname
            self.directives["style-src"].add(domain)
            self.directives["font-src"].add(domain)

    def build_csp_auth(self) -> None:
        # When using external image for Auth0 provider, add it here
        if "://" in settings.SOCIAL_AUTH_AUTH0_IMAGE:
            domain = urlparse(settings.SOCIAL_AUTH_AUTH0_IMAGE).hostname
            self.directives["img-src"].add(domain)

        # Third-party login flow extensions
        if self.request.resolver_match and (
            self.request.resolver_match.view_name.startswith("social:")
            or self.request.resolver_match.view_name in {"login", "profile"}
        ):
            social_strategy: WeblateStrategy
            if hasattr(self.request, "social_strategy"):
                social_strategy = self.request.social_strategy
            else:
                social_strategy = load_strategy(self.request)
            for backend in get_auth_backends().values():
                url = ""
                # Handle OpenId redirect flow
                if issubclass(backend, OpenIdAuth):
                    url = backend(social_strategy).openid_url()
                # Handle OAuth redirect flow
                if issubclass(backend, OAuthAuth):
                    url = backend(social_strategy).authorization_url()
                if url:
                    self.directives["form-action"].add(urlparse(url).hostname)


class SecurityMiddleware:
    """Middleware that sets Content-Security-Policy."""

    def __init__(self, get_response=None) -> None:
        self.get_response = get_response

    def __call__(self, request: AuthenticatedHttpRequest):
        response = self.get_response(request)
        csp_builder = CSPBuilder(request, response)

        response["Content-Security-Policy"] = "; ".join(
            f"{name} {' '.join(rules)}"
            for name, rules in csp_builder.directives.items()
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
