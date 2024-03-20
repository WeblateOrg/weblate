# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import random
from urllib.parse import urlparse

from django.conf import settings
from django.core.cache import cache
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext

import weblate.utils.version
from weblate.configuration.views import CustomCSSView
from weblate.utils.const import SUPPORT_STATUS_CACHE_KEY
from weblate.utils.site import get_site_domain, get_site_url
from weblate.wladmin.models import ConfigurationError, SupportStatus

WEBLATE_URL = "https://weblate.org/"
DONATE_URL = "https://weblate.org/donate/"

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
]

CONTEXT_APPS = ["billing", "legal", "gitexport"]


def add_error_logging_context(context) -> None:
    if (
        hasattr(settings, "ROLLBAR")
        and "client_token" in settings.ROLLBAR
        and "environment" in settings.ROLLBAR
    ):
        context["rollbar_token"] = settings.ROLLBAR["client_token"]
        context["rollbar_environment"] = settings.ROLLBAR["environment"]
    else:
        context["rollbar_token"] = None
        context["rollbar_environment"] = None


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
    if first in {"about", "stats", "keys", "legal"}:
        return "weblate.svg"
    if first in {
        "glossaries",
        "upload-glossaries",
        "delete-glossaries",
        "edit-glossaries",
    }:
        return "glossary.svg"
    return "project.svg"


def get_interledger_payment_pointer():
    interledger_payment_pointers = settings.INTERLEDGER_PAYMENT_POINTERS

    if not interledger_payment_pointers:
        return None

    return random.choice(interledger_payment_pointers)  # noqa: S311


def weblate_context(request):
    """Context processor to inject various useful variables into context."""
    if url_has_allowed_host_and_scheme(request.GET.get("next", ""), allowed_hosts=None):
        login_redirect_url = request.GET["next"]
    else:
        login_redirect_url = request.get_full_path()

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

    if hasattr(request, "_weblate_support_status"):
        support_status = request._weblate_support_status
    else:
        support_status = cache.get(SUPPORT_STATUS_CACHE_KEY)
        if support_status is None:
            support_status_instance = SupportStatus.objects.get_current()
            support_status = {
                "has_support": support_status_instance.name != "community",
                "in_limits": support_status_instance.in_limits,
            }
            cache.set(SUPPORT_STATUS_CACHE_KEY, support_status, 86400)
        request._weblate_support_status = support_status

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

    add_error_logging_context(context)
    add_settings_context(context)
    add_optional_context(context)

    return context
