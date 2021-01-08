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
"""Provide user friendly names for social authentication methods."""

from django import template
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy

register = template.Library()

SOCIALS = {
    "auth0": {
        "name": settings.SOCIAL_AUTH_AUTH0_TITLE,
        "image": settings.SOCIAL_AUTH_AUTH0_IMAGE,
    },
    "saml": {
        "name": settings.SOCIAL_AUTH_SAML_TITLE,
        "image": settings.SOCIAL_AUTH_SAML_IMAGE,
    },
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
}

IMAGE_SOCIAL_TEMPLATE = """
<img class="auth-image" src="{image}" />
"""

SOCIAL_TEMPLATE = """
{icon}
{separator}
{name}
"""


@register.simple_tag
def auth_name(auth, separator="<br />"):
    """Create HTML markup for social authentication method."""
    params = {"name": auth, "separator": separator, "image": "password.svg"}

    if auth in SOCIALS:
        params.update(SOCIALS[auth])

    if not params["image"].startswith("http"):
        params["image"] = staticfiles_storage.url("auth/" + params["image"])
    params["icon"] = IMAGE_SOCIAL_TEMPLATE.format(**params)

    return mark_safe(SOCIAL_TEMPLATE.format(**params))


def get_auth_name(auth):
    """Get nice name for authentication backend."""
    if auth in SOCIALS:
        return SOCIALS[auth]["name"]
    return auth
