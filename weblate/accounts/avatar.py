# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2014 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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

import urllib2
import urllib
import hashlib
import os.path
from django.core.cache import get_cache, InvalidCacheBackendError
from django.conf import settings

import weblate
from weblate import appsettings

try:
    import libravatar
    HAS_LIBRAVATAR = True
except ImportError:
    HAS_LIBRAVATAR = False

PLURAL_SEPARATOR = '\x1e\x1e'


def avatar_for_email(email, size=80):
    '''
    Generates url for avatar.
    '''

    # Safely handle blank email
    if email == '':
        email = 'noreply@weblate.org'

    # Retrieve from cache
    cache_key = 'avatar-%s-%s' % (email, size)
    cache = get_cache('default')
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
        mail_hash = hashlib.md5(email.lower()).hexdigest()

        url = "%savatar/%s?" % (appsettings.AVATAR_URL_PREFIX, mail_hash)

        url += urllib.urlencode({
            's': str(size),
            'd': appsettings.AVATAR_DEFAULT_IMAGE
        })

    # Store result in cache
    cache.set(cache_key, url, 3600 * 24)

    return url


def get_avatar_image(user, size):
    '''
    Returns avatar image from cache (if available) or downloads it.
    '''

    cache_key = 'avatar-img-{0}-{1}'.format(
        user.username,
        size
    )

    # Try using avatar specific cache if available
    try:
        cache = get_cache('avatar')
    except InvalidCacheBackendError:
        cache = get_cache('default')

    image = cache.get(cache_key)
    if image is None:
        try:
            image = download_avatar_image(user, size)
            cache.set(cache_key, image)
        except IOError as error:
            weblate.logger.error(
                'Failed to fetch avatar for %s: %s',
                user.username,
                str(error)
            )
            fallback = os.path.join(
                appsettings.WEB_ROOT,
                'media/weblate-{0}.png'.format(size)
            )
            with open(fallback, 'r') as handle:
                return handle.read()

    return image


def download_avatar_image(user, size):
    '''
    Downloads avatar image from remote server.
    '''
    url = avatar_for_email(user.email, size)
    request = urllib2.Request(url)
    request.timeout = 0.5
    request.add_header('User-Agent', 'Weblate/%s' % weblate.VERSION)

    # Fire request
    handle = urllib2.urlopen(request)

    # Read and possibly convert response
    return handle.read()
