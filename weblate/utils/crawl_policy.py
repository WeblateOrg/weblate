# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared path policy for robots.txt and verified crawler exemptions."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.http import HttpResponse
from django.template.loader import get_template
from django.urls import reverse
from django.views.decorators.cache import cache_control

from weblate.utils.site import get_site_url

if TYPE_CHECKING:
    from django.http import HttpRequest

# A trailing $ marks an exact path; * matches a variable part of a path.
CRAWL_RULES = (
    "/engage/",
    "/projects/",
    "/languages/",
    "/widget/",
    "/exports/",
    "/$",
    "/sitemap.xml$",
    "/sitemap-*.xml$",
)
CRAWL_PATTERNS = tuple(
    re.compile(re.escape(rule).replace(r"\*", ".*").replace(r"\$", r"\Z"))
    for rule in CRAWL_RULES
)


def deployment_prefix() -> str:
    value = settings.URL_PREFIX.strip("/")
    return "/" + value if value else ""


def crawl_allowed(path: str) -> bool:
    """Match a deployment-relative path, without its query string."""
    return any(pattern.match(path) for pattern in CRAWL_PATTERNS)


@cache_control(max_age=86400)
@login_not_required
def robots(_request: HttpRequest) -> HttpResponse:
    # Avoid application context processors and their database/session access.
    content = get_template("robots.txt").render(
        {
            "crawl_rules": [deployment_prefix() + rule for rule in CRAWL_RULES],
            "sitemap_url": get_site_url(reverse("sitemap-index")),
        }
    )
    return HttpResponse(content, content_type="text/plain")
