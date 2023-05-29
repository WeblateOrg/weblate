# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Provide user friendly names for social authentication methods."""

from django import template
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.utils.html import format_html
from django.utils.translation import gettext_lazy

register = template.Library()

SOCIALS = {
    "auth0": {"name": "Auth0", "image": "auth0.svg"},
    "saml": {"name": "SAML", "image": "saml.svg"},
    "google": {"name": "Google", "image": "google.svg"},
    "google-oauth2": {"name": "Google", "image": "google.svg"},
    "google-plus": {"name": "Google+", "image": "google.svg"},
    "password": {"name": gettext_lazy("Password"), "image": "password.svg"},
    "email": {"name": gettext_lazy("E-mail"), "image": "email.svg"},
    "ubuntu": {"name": "Ubuntu", "image": "ubuntu.svg"},
    "opensuse": {"name": "openSUSE", "image": "opensuse.svg"},
    "fedora": {"name": "Fedora", "image": "fedora.svg"},
    "facebook": {"name": "Facebook", "image": "facebook.svg"},
    "github": {"name": "GitHub", "image": "github.svg"},
    "github-enterprise": {"name": "GitHub Enterprise", "image": "github.svg"},
    "bitbucket": {"name": "Bitbucket", "image": "bitbucket.svg"},
    "bitbucket-oauth2": {"name": "Bitbucket", "image": "bitbucket.svg"},
    "azuread-oauth2": {"name": "Azure", "image": "azure.svg"},
    "azuread-tenant-oauth2": {"name": "Azure", "image": "azure.svg"},
    "gitlab": {"name": "GitLab", "image": "gitlab.svg"},
    "amazon": {"name": "Amazon", "image": "amazon.svg"},
    "twitter": {"name": "Twitter", "image": "twitter.svg"},
    "stackoverflow": {"name": "Stack Overflow", "image": "stackoverflow.svg"},
    "musicbrainz": {"name": "MusicBrainz", "image": "musicbrainz.svg"},
}

IMAGE_SOCIAL_TEMPLATE = """
<img class="auth-image" src="{image}" />
"""

SOCIAL_TEMPLATE = """
{icon}
{separator}
{name}
"""


def get_auth_params(auth: str):
    """Returns authentication parameters."""
    # Fallback values
    params = {"name": auth.title(), "image": "password.svg"}

    # Hardcoded names
    if auth in SOCIALS:
        params.update(SOCIALS[auth])

    # Settings override
    settings_params = {
        "name": f"SOCIAL_AUTH_{auth.upper().replace('-','_')}_TITLE",
        "image": f"SOCIAL_AUTH_{auth.upper().replace('-','_')}_IMAGE",
    }
    for target, source in settings_params.items():
        value = getattr(settings, source, None)
        if value:
            params[target] = value

    return params


auth_name_default_separator = format_html("<br />")


@register.simple_tag
def auth_name(auth: str, separator: str = auth_name_default_separator):
    """Create HTML markup for social authentication method."""
    params = get_auth_params(auth)

    if not params["image"].startswith("http"):
        params["image"] = staticfiles_storage.url("auth/" + params["image"])
    params["icon"] = format_html(IMAGE_SOCIAL_TEMPLATE, separator=separator, **params)

    return format_html(SOCIAL_TEMPLATE, separator=separator, **params)


def get_auth_name(auth: str):
    """Get nice name for authentication backend."""
    return get_auth_params(auth)["name"]
