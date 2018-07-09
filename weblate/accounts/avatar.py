# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

from ssl import CertificateError
import sys
import hashlib
import os.path

from six.moves.urllib.request import Request, urlopen
from six.moves.urllib.parse import quote

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.cache import caches, InvalidCacheBackendError
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import pgettext
from django.urls import reverse

from weblate import USER_AGENT
from weblate.logger import LOGGER
from weblate.utils.errors import report_error


def avatar_for_email(email, size=80):
    """Generate url for avatar."""

    # Safely handle blank email
    if not email:
        email = 'noreply@weblate.org'

    mail_hash = hashlib.md5(email.lower().encode('utf-8')).hexdigest()

    return "{0}avatar/{1}?d={2}&s={3}".format(
        settings.AVATAR_URL_PREFIX,
        mail_hash,
        quote(settings.AVATAR_DEFAULT_IMAGE),
        str(size),
    )


def get_fallback_avatar_url(size):
    """Return URL of fallback avatar."""
    return os.path.join(
        settings.STATIC_URL,
        'weblate-{0}.png'.format(size)
    )


def get_fallback_avatar(size):
    """Return fallback avatar."""
    filename = finders.find('weblate-{0}.png'.format(size))
    with open(filename, 'rb') as handle:
        return handle.read()


def get_avatar_image(request, user, size):
    """Return avatar image from cache (if available) or download it."""

    cache_key = '-'.join((
        'avatar-img',
        user.username,
        str(size)
    ))

    # Try using avatar specific cache if available
    try:
        cache = caches['avatar']
    except InvalidCacheBackendError:
        cache = caches['default']

    image = cache.get(cache_key)
    if image is None:
        try:
            image = download_avatar_image(user, size)
            cache.set(cache_key, image)
        except (IOError, CertificateError) as error:
            report_error(
                error, sys.exc_info(), request,
                extra_data={'avatar': user.username},
                level='debug',
            )
            LOGGER.error(
                'Failed to fetch avatar for %s: %s',
                user.username,
                str(error)
            )
            return get_fallback_avatar(size)

    return image


def download_avatar_image(user, size):
    """Download avatar image from remote server."""
    url = avatar_for_email(user.email, size)
    request = Request(url)
    request.timeout = 0.5
    request.add_header('User-Agent', USER_AGENT)

    # Fire request
    handle = urlopen(request)

    # Read and possibly convert response
    return bytes(handle.read())


def get_user_display(user, icon=True, link=False):
    """Nicely format user for display."""
    # Did we get any user?
    if user is None:
        # None user, probably remotely triggered action
        full_name = pgettext('No known user', 'None')
    else:
        # Get full name
        full_name = user.full_name

        # Use user name if full name is empty
        if full_name.strip() == '':
            full_name = user.username

    # Escape HTML
    full_name = escape(full_name)

    # Icon requested?
    if icon and settings.ENABLE_AVATARS:
        if user is None or user.email == 'noreply@weblate.org':
            avatar = get_fallback_avatar_url(32)
        else:
            avatar = reverse(
                'user_avatar', kwargs={'user': user.username, 'size': 32}
            )

        full_name = '<img src="{avatar}" class="avatar" /> {name}'.format(
            name=full_name,
            avatar=avatar
        )

    if link and user is not None:
        return mark_safe('<a href="{link}">{name}</a>'.format(
            name=full_name,
            link=reverse('user_page', kwargs={'user': user.username}),
        ))
    return mark_safe(full_name)
