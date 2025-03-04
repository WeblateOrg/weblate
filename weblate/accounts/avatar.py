# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import hashlib
import os.path
from ssl import CertificateError
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.cache import InvalidCacheBackendError, caches
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext, pgettext

from weblate.utils.errors import report_error
from weblate.utils.requests import request

if TYPE_CHECKING:
    from weblate.auth.models import User


def avatar_for_email(email, size=80) -> str:
    """Generate url for avatar."""
    # Safely handle blank e-mail
    if not email:
        email = "noreply@weblate.org"

    mail_hash = hashlib.md5(email.lower().encode(), usedforsecurity=False).hexdigest()

    querystring = urlencode({"d": settings.AVATAR_DEFAULT_IMAGE, "s": str(size)})

    return f"{settings.AVATAR_URL_PREFIX}avatar/{mail_hash}?{querystring}"


def get_fallback_avatar_url(size: int):
    """Return URL of fallback avatar."""
    return os.path.join(settings.STATIC_URL, f"weblate-{size}.png")


def get_fallback_avatar(size: int):
    """Return fallback avatar."""
    filename = finders.find(f"weblate-{size}.png")
    with open(filename, "rb") as handle:
        return handle.read()


def get_avatar_image(user: User, size: int):
    """Return avatar image from cache (if available) or download it."""
    username = user.username
    cache_key = "-".join(("avatar-img", username, str(size)))

    # Try using avatar specific cache if available
    try:
        cache = caches["avatar"]
    except InvalidCacheBackendError:
        cache = caches["default"]

    image = cache.get(cache_key)
    if image is None:
        try:
            image = download_avatar_image(user.email, size)
            cache.set(cache_key, image)
        except (OSError, CertificateError):
            report_error(f"Could not fetch avatar for {username}")
            return get_fallback_avatar(size)

    return image


def download_avatar_image(email: str, size: int):
    """Download avatar image from remote server."""
    url = avatar_for_email(email, size)
    response = request("get", url, timeout=1.0)
    return response.content


def get_user_display(user: User, icon: bool = True, link: bool = False):
    """Nicely format user for display."""
    # Did we get any user?
    if user is None:
        # None user, probably remotely triggered action
        username = full_name = pgettext("No known user", "None")
        email = "noreply@weblate.org"
    else:
        # Get basic info
        username = user.username
        email = user.email
        full_name = user.full_name.strip()

        if not full_name:
            # Use user name if full name is empty
            full_name = username
        elif username == email:
            # Use full name in case username matches e-mail
            username = full_name

    # Icon requested?
    if icon and settings.ENABLE_AVATARS:
        if email == "noreply@weblate.org":
            avatar = get_fallback_avatar_url(32)
        else:
            avatar = reverse("user_avatar", kwargs={"user": user.username, "size": 32})

        username = format_html(
            '<img src="{}" class="avatar w32" alt="{}" /> {}',
            avatar,
            gettext("User avatar"),
            username,
        )

    if link and user is not None:
        return format_html(
            '<a href="{}" title="{}">{}</a>',
            user.get_absolute_url(),
            full_name,
            username,
        )
    return format_html('<span title="{}">{}</span>', full_name, username)
