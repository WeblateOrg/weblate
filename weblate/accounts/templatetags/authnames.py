# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Provide user friendly names for social authentication methods."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from django.utils.html import format_html
from django.utils.translation import gettext_lazy
from social_core.backends.utils import get_backend
from social_core.exceptions import AuthConfigurationError

from weblate.accounts.utils import get_key_name

if TYPE_CHECKING:
    from django.template import Context
    from django_otp.models import Device
    from django_stubs_ext import StrOrPromise

    from weblate.accounts.types import DeviceType

register = template.Library()

# Local authentication methods.
LOCAL_METHODS: dict[str, dict[str, StrOrPromise]] = {
    "password": {"name": gettext_lazy("Password"), "image": "password.svg"},
    "email": {"name": gettext_lazy("E-mail"), "image": "email.svg"},
}

SECOND_FACTORS: dict[DeviceType, StrOrPromise] = {
    "webauthn": gettext_lazy("Use a passkey or security key (WebAuthn)"),
    "totp": gettext_lazy("Use authentication app (TOTP)"),
    "recovery": gettext_lazy("Use recovery codes"),
}

IMAGE_SOCIAL_TEMPLATE = (
    """<img class="auth-image" src="{image}" alt="" aria-hidden="true" />"""
)

SOCIAL_TEMPLATE = """{icon}<span class="auth-name">{name}</span>"""


def get_auth_params(auth: str) -> dict[str, StrOrPromise]:
    """Generate authentication parameters."""
    # Fallback values
    params: dict[str, StrOrPromise] = {
        "name": auth.title(),
        "image": "password.svg",
    }
    if auth in LOCAL_METHODS:
        params.update(LOCAL_METHODS[auth])
    else:
        try:
            backend = get_backend(settings.AUTHENTICATION_BACKENDS, auth)
        except AuthConfigurationError as error:
            if error.code != "backend_missing":
                raise
        else:
            params["name"] = backend.title or auth.title()
            if backend.icon:
                params["image"] = f"social_auth/icons/{backend.icon}"

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


@register.simple_tag
def auth_name(auth: str, only: str = "") -> StrOrPromise:
    """Create HTML markup for social authentication method."""
    params = get_auth_params(auth)

    if not params["image"].startswith(("http", "data:")):
        image = str(params["image"])
        if not image.startswith("social_auth/icons/"):
            legacy_path = f"auth/{image}"
            shared_path = f"social_auth/icons/{image}"
            # Existing custom files take precedence over bundled provider artwork.
            image = legacy_path
            if not finders.find(legacy_path) and finders.find(shared_path):
                image = shared_path
        params["image"] = staticfiles_storage.url(image)
    params["icon"] = format_html(IMAGE_SOCIAL_TEMPLATE, **params)

    if only:
        return params[only]

    return format_html(SOCIAL_TEMPLATE, **params)


def get_auth_name(auth: str) -> StrOrPromise:
    """Get nice name for authentication backend."""
    return get_auth_params(auth)["name"]


@register.simple_tag
def key_name(device: Device) -> str:
    return format_html('<span class="key-name">{}</span>', get_key_name(device))


@register.simple_tag
def second_factor_name(name: DeviceType) -> StrOrPromise:
    return SECOND_FACTORS[name]


@register.simple_tag(takes_context=True)
def format_site_title(context: Context) -> str:
    style = ""
    site_title = context["site_title"]
    if context["support_status"]["is_hosted_weblate"]:
        style = "text-info"
        site_title = "Weblate cloud"

    return format_html('<span class="{}">{}</span>', style, site_title)
