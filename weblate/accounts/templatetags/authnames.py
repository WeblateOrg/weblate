# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Provide user friendly names for social authentication methods."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django import template
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy

from weblate.accounts.utils import DeviceType, get_key_name

if TYPE_CHECKING:
    from django_otp.models import Device
    from django_stubs_ext import StrOrPromise

register = template.Library()

SOCIALS: dict[str, dict[str, StrOrPromise]] = {
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
    "github-org": {"name": "GitHub Organization", "image": "github.svg"},
    "bitbucket": {"name": "Bitbucket", "image": "bitbucket.svg"},
    "bitbucket-oauth2": {"name": "Bitbucket", "image": "bitbucket.svg"},
    "azuread-oauth2": {"name": "Azure", "image": "azure.svg"},
    "azuread-tenant-oauth2": {"name": "Azure", "image": "azure.svg"},
    "gitlab": {"name": "GitLab", "image": "gitlab.svg"},
    "amazon": {"name": "Amazon", "image": "amazon.svg"},
    "twitter": {"name": "Twitter", "image": "twitter.svg"},
    "stackoverflow": {"name": "Stack Overflow", "image": "stackoverflow.svg"},
    "musicbrainz": {"name": "MusicBrainz", "image": "musicbrainz.svg"},
    "openinfra": {"name": "OpenInfraID"},
}

SECOND_FACTORS: dict[DeviceType, StrOrPromise] = {
    "webauthn": gettext_lazy("Use security key (WebAuthn)"),
    "totp": gettext_lazy("Use authentication app (TOTP)"),
    "recovery": gettext_lazy("Use recovery codes"),
}

IMAGE_SOCIAL_TEMPLATE = """
<img class="auth-image" src="{image}" />
"""

SOCIAL_TEMPLATE = """
{icon}
{separator}
{name}
"""


def get_auth_params(auth: str) -> dict[str, StrOrPromise]:
    """Generate authentication parameters."""
    # Fallback values
    params: dict[str, StrOrPromise] = {"name": auth.title(), "image": "password.svg"}

    # Hardcoded names
    if auth in SOCIALS:
        params.update(SOCIALS[auth])

    # Settings override
    settings_params = {
        "name": f"SOCIAL_AUTH_{auth.upper().replace('-', '_')}_TITLE",
        "image": f"SOCIAL_AUTH_{auth.upper().replace('-', '_')}_IMAGE",
    }
    for target, source in settings_params.items():
        value = getattr(settings, source, None)
        if value:
            params[target] = value

    return params


auth_name_default_separator = mark_safe("<br />")


@register.simple_tag
def auth_name(auth: str, separator: str = auth_name_default_separator, only: str = ""):
    """Create HTML markup for social authentication method."""
    params = get_auth_params(auth)

    if not params["image"].startswith("http"):
        params["image"] = staticfiles_storage.url("auth/" + params["image"])
    params["icon"] = format_html(IMAGE_SOCIAL_TEMPLATE, separator=separator, **params)

    if only:
        return params[only]

    return format_html(SOCIAL_TEMPLATE, separator=separator, **params)


def get_auth_name(auth: str):
    """Get nice name for authentication backend."""
    return get_auth_params(auth)["name"]


@register.simple_tag
def key_name(device: Device) -> str:
    return format_html('<span class="auth-name">{}</span>', get_key_name(device))


@register.simple_tag
def second_factor_name(name: DeviceType) -> str:
    return SECOND_FACTORS[name]
