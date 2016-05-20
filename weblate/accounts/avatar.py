# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from __future__ import unicode_literals

import sys
import hashlib
import os.path

from six.moves.urllib.request import Request, urlopen
from six.moves.urllib.parse import urlencode

from django.core.cache import caches, InvalidCacheBackendError
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils.translation import pgettext
from django.core.urlresolvers import reverse
from django.conf import settings

try:
    import libravatar  # pylint: disable=import-error
    HAS_LIBRAVATAR = True
except ImportError:
    HAS_LIBRAVATAR = False

from weblate import USER_AGENT
from weblate.logger import LOGGER
from weblate import appsettings
from weblate.trans.util import report_error


def avatar_for_email(email, size=80):
    """
    Generates url for avatar.
    """

    # Safely handle blank email
    if email == '':
        email = 'noreply@weblate.org'

    mail_hash = hashlib.md5(email.lower().encode('utf-8')).hexdigest()

    # Retrieve from cache
    cache_key = '-'.join((
        'avatar',
        mail_hash,
        str(size)
    ))
    cache = caches['default']
    url = cache.get(cache_key)
    if url is not None:
        return url

    if HAS_LIBRAVATAR:
        # Use libravatar library if available
        url = libravatar.libravatar_url(
            email=email,
            https=True,
            default=appsettings.AVATAR_DEFAULT_IMAGE,
            size=size
        )

    else:
        # Fallback to standard method
        url = "{0}avatar/{1}?{2}".format(
            appsettings.AVATAR_URL_PREFIX,
            mail_hash,
            urlencode({
                's': str(size),
                'd': appsettings.AVATAR_DEFAULT_IMAGE
            })
        )

    # Store result in cache
    cache.set(cache_key, url, 3600 * 24)

    return url


def get_fallback_avatar_url(size):
    """
    Returns URL of fallback avatar.
    """
    return os.path.join(
        settings.STATIC_URL,
        'weblate-{0}.png'.format(size)
    )


def get_fallback_avatar(size):
    """
    Returns fallback avatar.
    """
    fallback = os.path.join(
        settings.STATIC_ROOT,
        'weblate-{0}.png'.format(size)
    )
    with open(fallback, 'rb') as handle:
        return handle.read()


def get_avatar_image(user, size):
    """
    Returns avatar image from cache (if available) or downloads it.
    """

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
        except IOError as error:
            report_error(
                error, sys.exc_info(),
                extra_data={'avatar': user.username}
            )
            LOGGER.error(
                'Failed to fetch avatar for %s: %s',
                user.username,
                str(error)
            )
            return get_fallback_avatar(size)

    return image


def download_avatar_image(user, size):
    """
    Downloads avatar image from remote server.
    """
    url = avatar_for_email(user.email, size)
    request = Request(url)
    request.timeout = 0.5
    request.add_header('User-Agent', USER_AGENT)

    # Fire request
    handle = urlopen(request)

    # Read and possibly convert response
    return handle.read()


def get_user_display(user, icon=True, link=False):
    """
    Nicely formats user for display.
    """
    # Did we get any user?
    if user is None:
        # None user, probably remotely triggered action
        full_name = pgettext('No known user', 'None')
    else:
        # Get full name
        full_name = user.first_name

        # Use user name if full name is empty
        if full_name.strip() == '':
            full_name = user.username

    # Escape HTML
    full_name = escape(full_name)

    # Icon requested?
    if icon and appsettings.ENABLE_AVATARS:
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
    else:
        return mark_safe(full_name)
