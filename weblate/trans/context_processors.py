# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import random
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from django.conf import settings
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext

import weblate.utils.version
from weblate.configuration.views import CustomCSSView
from weblate.utils.site import get_site_domain, get_site_url
from weblate.wladmin.models import ConfigurationError, get_support_status

if TYPE_CHECKING:
    from weblate.auth.models import AuthenticatedHttpRequest

WEBLATE_URL = "https://weblate.org/"
DONATE_URL = "https://weblate.org/donate/"
SUPPORT_URL = "https://weblate.org/support/"

CONTEXT_SETTINGS = [
    "SITE_TITLE",
    "OFFER_HOSTING",
    "ENABLE_AVATARS",
    "ENABLE_SHARING",
    "MATOMO_SITE_ID",
    "MATOMO_URL",
    "GOOGLE_ANALYTICS_ID",
    "ENABLE_HOOKS",
    "REGISTRATION_OPEN",
    "GET_HELP_URL",
    "STATUS_URL",
    "LEGAL_URL",
    "PRIVACY_URL",
    "FONTS_CDN_URL",
    "AVATAR_URL_PREFIX",
    "HIDE_VERSION",
    "EXTRA_HTML_HEAD",
    "PRIVATE_COMMIT_EMAIL_OPT_IN",
    # Hosted Weblate integration
    "PAYMENT_ENABLED",
    "IP_ADDRESSES",
]

CONTEXT_APPS = ["billing", "legal", "gitexport"]


def add_settings_context(context) -> None:
    for name in CONTEXT_SETTINGS:
        context[name.lower()] = getattr(settings, name, None)


def add_optional_context(context) -> None:
    for name in CONTEXT_APPS:
        appname = f"weblate.{name}"
        context[f"has_{name}"] = appname in settings.INSTALLED_APPS


def get_preconnect_list():
    result = []
    if settings.MATOMO_URL:
        result.append(urlparse(settings.MATOMO_URL).hostname)
    if settings.GOOGLE_ANALYTICS_ID:
        result.append("www.google-analytics.com")
    return result


def get_bread_image(path) -> str:
    if path == "/":
        return "dashboard.svg"
    first = path.split("/", 2)[1]
    if first in {"user", "accounts"}:
        return "account.svg"
    if first == "checks":
        return "alert.svg"
    if first == "languages":
        return "language.svg"
    if first == "manage":
        return "wrench.svg"
    if first in {"about", "stats", "keys", "legal", "donate"}:
        return "weblate.svg"
    if first in {
        "glossaries",
        "upload-glossaries",
        "delete-glossaries",
        "edit-glossaries",
    }:
        return "glossary.svg"
    return "project.svg"


def get_interledger_payment_pointer() -> str:
    interledger_payment_pointers: list[str] = []
    if settings.INTERLEDGER_PAYMENT_BUILTIN:
        # Weblate funding
        interledger_payment_pointers.append("$ilp.uphold.com/ENU7fREdeZi9")

    interledger_payment_pointers.extend(settings.INTERLEDGER_PAYMENT_POINTERS)

    if not interledger_payment_pointers:
        return None

    return random.choice(interledger_payment_pointers)  # noqa: S311


def weblate_context(request: AuthenticatedHttpRequest):
    """Context processor to inject various useful variables into context."""
    if url_has_allowed_host_and_scheme(request.GET.get("next", ""), allowed_hosts=None):
        login_redirect_url = request.GET["next"]
    elif request.resolver_match is None or (
        not request.resolver_match.view_name.startswith("social:")
        and request.resolver_match.view_name != "logout"
    ):
        login_redirect_url = request.get_full_path()
    else:
        login_redirect_url = ""

    # Load user translations if user is authenticated
    watched_projects = None
    theme = "auto"
    if hasattr(request, "user"):
        if request.user.is_authenticated:
            watched_projects = request.user.watched_projects
        theme = request.user.profile.theme

    if settings.OFFER_HOSTING:
        description = gettext(
            "Hosted Weblate, the place to localize your software project."
        )
    else:
        description = gettext(
            "This site runs Weblate for localizing various software projects."
        )

    support_status = get_support_status(request)

    context = {
        "support_status": support_status,
        "cache_param": f"?v={weblate.utils.version.GIT_VERSION}"
        if not settings.COMPRESS_ENABLED
        else "",
        "version": weblate.utils.version.VERSION,
        "bread_image": get_bread_image(request.path),
        "description": description,
        "weblate_link": format_html('<a href="{}">weblate.org</a>', WEBLATE_URL),
        "weblate_name_link": format_html('<a href="{}">Weblate</a>', WEBLATE_URL),
        "weblate_version_link": format_html(
            '<a href="{}">Weblate {}</a>',
            WEBLATE_URL,
            "" if settings.HIDE_VERSION else weblate.utils.version.VERSION,
        ),
        "donate_url": DONATE_URL,
        "support_url": SUPPORT_URL,
        "site_url": get_site_url(),
        "site_domain": get_site_domain(),
        "login_redirect_url": login_redirect_url,
        "has_antispam": bool(settings.AKISMET_API_KEY),
        "has_sentry": bool(settings.SENTRY_DSN),
        "watched_projects": watched_projects,
        "allow_index": False,
        "configuration_errors": ConfigurationError.objects.filter(
            ignored=False
        ).order_by("-timestamp"),
        "preconnect_list": get_preconnect_list(),
        "custom_css_hash": CustomCSSView.get_hash(request),
        "interledger_payment_pointer": get_interledger_payment_pointer(),
        "theme": theme,
    }

    add_settings_context(context)
    add_optional_context(context)

    return context
