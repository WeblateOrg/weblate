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


import hashlib
import os.path
from ssl import CertificateError
from urllib.parse import quote

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.cache import InvalidCacheBackendError, caches
from django.urls import reverse
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import gettext, pgettext

from weblate.utils.errors import report_error
from weblate.utils.requests import request


def avatar_for_email(email, size=80):
    """Generate url for avatar."""
    # Safely handle blank e-mail
    if not email:
        email = "noreply@weblate.org"

    mail_hash = hashlib.md5(email.lower().encode()).hexdigest()  # nosec

    return "{}avatar/{}?d={}&s={}".format(
        settings.AVATAR_URL_PREFIX,
        mail_hash,
        quote(settings.AVATAR_DEFAULT_IMAGE),
        str(size),
    )


def get_fallback_avatar_url(size):
    """Return URL of fallback avatar."""
    return os.path.join(settings.STATIC_URL, f"weblate-{size}.png")


def get_fallback_avatar(size):
    """Return fallback avatar."""
    filename = finders.find(f"weblate-{size}.png")
    with open(filename, "rb") as handle:
        return handle.read()


def get_avatar_image(user, size):
    """Return avatar image from cache (if available) or download it."""
    cache_key = "-".join(("avatar-img", user.username, str(size)))

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
            report_error(
                extra_data={"avatar": user.username},
                cause="Failed to fetch avatar",
            )
            return get_fallback_avatar(size)

    return image


def download_avatar_image(email, size):
    """Download avatar image from remote server."""
    url = avatar_for_email(email, size)
    response = request("get", url, timeout=1.0)
    return response.content


def get_user_display(user, icon: bool = True, link: bool = False):
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

    # Escape HTML
    full_name = escape(full_name)
    username = escape(username)

    # Icon requested?
    if icon and settings.ENABLE_AVATARS:
        if email == "noreply@weblate.org":
            avatar = get_fallback_avatar_url(32)
        else:
            avatar = reverse("user_avatar", kwargs={"user": user.username, "size": 32})

        alt = escape(gettext("User avatar"))
        username = f'<img src="{avatar}" class="avatar w32" alt="{alt}" /> {username}'

    if link and user is not None:
        return mark_safe(
            f'<a href="{user.get_absolute_url()}" title="{full_name}">{username}</a>'
        )
    return mark_safe(f'<span title="{full_name}">{username}</span>')
