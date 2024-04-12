# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.conf import settings

# List of default domain names on which warn user
DEFAULT_DOMAINS = ("", "*")


def get_site_domain():
    """Return current site domain."""
    return settings.SITE_DOMAIN


def get_site_url(url="") -> str:
    """Return root url of current site with domain."""
    protocol = "https" if settings.ENABLE_HTTPS else "http"
    return f"{protocol}://{get_site_domain()}{url}"


def check_domain(domain):
    """Check whether site domain is correctly set."""
    return (
        domain not in DEFAULT_DOMAINS
        and not domain.startswith("http:")
        and not domain.startswith("https:")
        and not domain.endswith("/")
    )
