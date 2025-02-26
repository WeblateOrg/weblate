# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING, Literal
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
from weblate.logger import LOGGER
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Change, Component, Project
from weblate.utils.errors import report_error
from weblate.utils.site import get_site_url
from weblate.utils.views import parse_path

if TYPE_CHECKING:
    from weblate.accounts.strategy import WeblateStrategy

    CSP_KIND = Literal[
        "default-src",
        "style-src",
        "img-src",
        "script-src",
        "connect-src",
        "object-src",
        "font-src",
        "frame-src",
        "frame-ancestors",
        "base-uri",
        "form-action",
        "manifest-src",
        "worker-src",
    ]
    CSP_TYPE = dict[CSP_KIND, set[str]]

CSP_DIRECTIVES: CSP_TYPE = {
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
    # Used by altcha
    "worker-src": {"'self'", "blob:"},
}

# URLs requiring inline javascript
INLINE_PATHS = {
    "social:begin",
    "djangosaml2idp:saml_login_process",
}


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

    def __call__(self, request: AuthenticatedHttpRequest) -> HttpResponse:
        response = self.get_response(request)
        # This is based on APPEND_SLASH handling in Django
        if response.status_code == 404 and self.should_redirect_with_slash(request):
            new_path = request.get_full_path(force_append_slash=True)
            # Prevent construction of scheme relative urls.
            new_path = escape_leading_slashes(new_path)
            return HttpResponsePermanentRedirect(new_path)
        return response

    def should_redirect_with_slash(self, request: AuthenticatedHttpRequest) -> bool:
        path = request.path_info
        # Avoid redirecting non GET requests, these would fail anyway due to
        # missing parameters.
        # Redirecting on API removes authentication headers in many cases,
        # so avoid that as well.
        # Redirecting requests for Sourcemap files will not do anything good
        if (
            path.endswith(("/", ".map"))
            or request.method != "GET"
            or (
                path.startswith(f"{settings.URL_PREFIX}/api")
                and not path.startswith(f"{settings.URL_PREFIX}/api/doc")
                and not path.startswith(f"{settings.URL_PREFIX}/api/schema")
            )
        ):
            return False
        urlconf = getattr(request, "urlconf", None)
        slash_path = f"{path}/"
        return not is_valid_path(path, urlconf) and bool(
            is_valid_path(slash_path, urlconf)
        )

    def fixup_language(self, lang: str) -> Language | None:
        return Language.objects.fuzzy_get_strict(code=lang)

    def fixup_project(self, slug, request: AuthenticatedHttpRequest) -> Project | None:
        project: Project | None
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

    def fixup_component(
        self, slug: str, request: AuthenticatedHttpRequest, project: Project
    ) -> Component | None:
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
                            action=ActionEvents.RENAME_COMPONENT, old=slug
                        )
                        .order()[0]
                        .component
                    )
                except IndexError:
                    return None

        request.user.check_access_component(component)
        return component

    def check_existing_translations(self, name: str, project: Project) -> bool:
        """
        Check in existing translations for specific language.

        Return False if language translation not present, else True.
        """
        return any(lang.name == name for lang in project.languages)

    def process_exception(  # noqa: C901
        self, request: AuthenticatedHttpRequest, exception
    ) -> HttpResponse | None:
        from weblate.utils.views import UnsupportedPathObjectError

        if not isinstance(exception, Http404):
            return None

        try:
            resolver_match = request.resolver_match
        except AttributeError:
            return None

        if resolver_match is None:
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
    directives: CSP_TYPE
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
        self.build_csp_sentry()
        self.build_csp_piwik()
        self.build_csp_google_analytics()
        self.build_csp_media_url()
        self.build_csp_static_url()
        self.build_csp_cdn()
        self.build_csp_auth()
        self.build_csp_redoc()

    def apply_csp_settings(self) -> None:
        setting_names: dict[str, CSP_KIND] = {
            "CSP_STYLE_SRC": "style-src",
            "CSP_SCRIPT_SRC": "script-src",
            "CSP_IMG_SRC": "img-src",
            "CSP_CONNECT_SRC": "connect-src",
            "CSP_FONT_SRC": "font-src",
            "CSP_FORM_SRC": "form-action",
        }
        for name, rule in setting_names.items():
            value = getattr(settings, name)
            if value:
                self.directives[rule].update(value)

    def add_csp_host(self, url: str, *directives: CSP_KIND) -> str | None:
        domain = urlparse(url).hostname
        # Handle domain only URLs (OpenInfraOpenId uses that)
        if not domain and ":" not in url and "/" not in url:
            domain = url
        if domain:
            for directive in directives:
                self.directives[directive].add(domain)
        else:
            LOGGER.error(
                "could not parse domain from '%s', not adding to Content-Security-Policy",
                url,
            )

        return domain

    def build_csp_redoc(self) -> None:
        if (
            self.request.resolver_match
            and self.request.resolver_match.view_name == "redoc"
        ):
            self.directives["script-src"].add("'unsafe-inline'")
            self.directives["img-src"].add("data:")

    def build_csp_inline(self) -> None:
        if (
            self.request.resolver_match
            and self.request.resolver_match.view_name in INLINE_PATHS
        ):
            self.directives["script-src"].add("'unsafe-inline'")

    def build_csp_sentry(self) -> None:
        # Sentry user feedback
        if settings.SENTRY_DSN and self.response.status_code == 500:
            domain = self.add_csp_host(settings.SENTRY_DSN, "script-src", "connect-src")
            # Add appropriate frontend servers for sentry.io
            if domain.endswith(".de.sentry.io"):
                self.directives["connect-src"].add("de.sentry.io")
                self.directives["script-src"].add("de.sentry.io")
            elif domain.endswith(".sentry.io"):
                self.directives["script-src"].add("sentry.io")
                self.directives["connect-src"].add("sentry.io")
            self.directives["script-src"].add("'unsafe-inline'")
            self.directives["img-src"].add("data:")

    def build_csp_piwik(self) -> None:
        # Matomo (Piwik) analytics
        if settings.MATOMO_URL:
            self.add_csp_host(
                settings.MATOMO_URL, "script-src", "img-src", "connect-src"
            )

    def build_csp_google_analytics(self) -> None:
        # Google Analytics
        if settings.GOOGLE_ANALYTICS_ID:
            self.directives["script-src"].add("'unsafe-inline'")
            self.directives["script-src"].add("www.google-analytics.com")
            self.directives["img-src"].add("www.google-analytics.com")

    def build_csp_media_url(self) -> None:
        # External media URL
        if "://" in settings.MEDIA_URL:
            self.add_csp_host(settings.MEDIA_URL, "img-src")

    def build_csp_static_url(self) -> None:
        # External static URL
        if "://" in settings.STATIC_URL:
            self.add_csp_host(
                settings.STATIC_URL, "script-src", "img-src", "style-src", "font-src"
            )

    def build_csp_cdn(self) -> None:
        # CDN for fonts
        if settings.FONTS_CDN_URL:
            self.add_csp_host(settings.FONTS_CDN_URL, "style-src", "font-src")

    def build_csp_auth(self) -> None:
        # When using external image for Auth0 provider, add it here
        if "://" in settings.SOCIAL_AUTH_AUTH0_IMAGE:
            self.add_csp_host(settings.SOCIAL_AUTH_AUTH0_IMAGE, "img-src")

        # Third-party login flow extensions
        if self.request.resolver_match and (
            self.request.resolver_match.view_name.startswith("social:")
            or self.request.resolver_match.view_name in {"login", "profile", "register"}
        ):
            social_strategy: WeblateStrategy
            if hasattr(self.request, "social_strategy"):
                social_strategy = self.request.social_strategy
            else:
                social_strategy = load_strategy(self.request)
            for backend in get_auth_backends().values():
                urls: list[str] = []

                # Handle OpenId redirect flow
                if issubclass(backend, OpenIdAuth):
                    urls = [backend(social_strategy).openid_url()]

                # Handle OAuth redirect flow
                elif issubclass(backend, OAuthAuth):
                    urls = [backend(social_strategy).authorization_url()]

                # Handle SAML redirect flow
                elif hasattr(backend, "get_idp"):
                    # Lazily import here to avoid pulling in xmlsec
                    from social_core.backends.saml import SAMLAuth

                    assert issubclass(backend, SAMLAuth)  # noqa: S101

                    saml_auth = backend(social_strategy)
                    urls = [
                        saml_auth.get_idp(idp_name).sso_url
                        for idp_name in getattr(
                            settings, "SOCIAL_AUTH_SAML_ENABLED_IDPS", {}
                        )
                    ]

                for url in urls:
                    domain = self.add_csp_host(url, "form-action")
                    if domain.endswith(".amazonaws.com"):
                        self.directives["form-action"].add("*.awsapps.com")


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
