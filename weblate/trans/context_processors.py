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

from datetime import datetime
from urllib.parse import urlparse

from django.conf import settings
from django.utils.html import escape
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

import weblate.screenshots.views
import weblate.utils.version
from weblate.configuration.views import CustomCSSView
from weblate.utils.site import get_site_domain, get_site_url
from weblate.wladmin.models import ConfigurationError

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
    "STATUS_URL",
    "LEGAL_URL",
    "FONTS_CDN_URL",
    "AVATAR_URL_PREFIX",
    "HIDE_VERSION",
    # Hosted Weblate integration
    "PAYMENT_ENABLED",
]

CONTEXT_APPS = ["billing", "legal", "gitexport"]


def add_error_logging_context(context):
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

    if hasattr(settings, "RAVEN_CONFIG") and "public_dsn" in settings.RAVEN_CONFIG:
        context["sentry_dsn"] = settings.RAVEN_CONFIG["public_dsn"]
    else:
        context["sentry_dsn"] = None


def add_settings_context(context):
    for name in CONTEXT_SETTINGS:
        context[name.lower()] = getattr(settings, name, None)


def add_optional_context(context):
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


def get_bread_image(path):
    if path == "/":
        return "dashboard.svg"
    first = path.split("/", 2)[1]
    if first in ("user", "accounts"):
        return "account.svg"
    if first == "checks":
        return "alert.svg"
    if first == "languages":
        return "language.svg"
    if first == "manage":
        return "wrench.svg"
    if first in ("about", "stats", "keys", "legal"):
        return "weblate.svg"
    if first in (
        "glossaries",
        "upload-glossaries",
        "delete-glossaries",
        "edit-glossaries",
    ):
        return "glossary.svg"
    return "project.svg"


def weblate_context(request):
    """Context processor to inject various useful variables into context."""
    if url_has_allowed_host_and_scheme(request.GET.get("next", ""), allowed_hosts=None):
        login_redirect_url = request.GET["next"]
    else:
        login_redirect_url = request.get_full_path()

    # Load user translations if user is authenticated
    watched_projects = None
    if hasattr(request, "user") and request.user.is_authenticated:
        watched_projects = request.user.watched_projects

    if settings.OFFER_HOSTING:
        description = _("Hosted Weblate, the place to localize your software project.")
    else:
        description = _(
            "This site runs Weblate for localizing various software projects."
        )

    context = {
        "cache_param": f"?v={weblate.utils.version.GIT_VERSION}"
        if not settings.COMPRESS_ENABLED
        else "",
        "version": weblate.utils.version.VERSION,
        "bread_image": get_bread_image(request.path),
        "description": description,
        "weblate_link": mark_safe(
            '<a href="{}">weblate.org</a>'.format(escape(WEBLATE_URL))
        ),
        "weblate_name_link": mark_safe(
            '<a href="{}">Weblate</a>'.format(escape(WEBLATE_URL))
        ),
        "weblate_version_link": mark_safe(
            '<a href="{}">Weblate {}</a>'.format(
                escape(WEBLATE_URL),
                "" if settings.HIDE_VERSION else weblate.utils.version.VERSION,
            )
        ),
        "donate_url": DONATE_URL,
        "site_url": get_site_url(),
        "site_domain": get_site_domain(),
        "current_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "current_year": datetime.utcnow().strftime("%Y"),
        "current_month": datetime.utcnow().strftime("%m"),
        "login_redirect_url": login_redirect_url,
        "has_ocr": weblate.screenshots.views.HAS_OCR,
        "has_antispam": bool(settings.AKISMET_API_KEY),
        "has_sentry": bool(settings.SENTRY_DSN),
        "watched_projects": watched_projects,
        "allow_index": False,
        "configuration_errors": ConfigurationError.objects.filter(
            ignored=False
        ).order_by("-timestamp"),
        "preconnect_list": get_preconnect_list(),
        "custom_css_hash": CustomCSSView.get_hash(request),
    }

    add_error_logging_context(context)
    add_settings_context(context)
    add_optional_context(context)

    return context
