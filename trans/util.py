# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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

import hashlib
from django.core.exceptions import ImproperlyConfigured
from django.contrib.sites.models import Site
from django.utils.translation import pgettext
from django.core.cache import cache
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.core.urlresolvers import reverse
from django.conf import settings
from importlib import import_module
import urllib
import time
import random
import os.path

try:
    import libravatar
    HAS_LIBRAVATAR = True
except ImportError:
    HAS_LIBRAVATAR = False

AVATAR_URL_PREFIX = getattr(
    settings,
    'AVATAR_URL_PREFIX',
    'https://seccdn.libravatar.org/'
)
# See http://wiki.libravatar.org/api/
# for available choices
AVATAR_DEFAULT_IMAGE = getattr(
    settings,
    'AVATAR_DEFAULT_IMAGE',
    'identicon'
)

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
    url = cache.get(cache_key)
    if url is not None:
        return url

    if HAS_LIBRAVATAR:
        # Use libravatar library if available
        url = libravatar.libravatar_url(
            email=email,
            https=True,
            default=AVATAR_DEFAULT_IMAGE,
            size=size
        )

    else:
        # Fallback to standard method
        mail_hash = hashlib.md5(email.lower()).hexdigest()

        url = "%savatar/%s?" % (AVATAR_URL_PREFIX, mail_hash)

        url += urllib.urlencode({
            's': str(size),
            'd': AVATAR_DEFAULT_IMAGE
        })

    # Store result in cache
    cache.set(cache_key, url, 3600 * 24)

    return escape(url)


def get_user_display(user, icon=True, link=False):
    '''
    Nicely formats user for display.
    '''
    # Did we get any user?
    if user is None:
        # None user, probably remotely triggered action
        full_name = pgettext('No known user', 'None')
        email = ''
    else:
        # Get full name
        full_name = user.get_full_name()

        # Use user name if full name is empty
        if full_name.strip() == '':
            full_name = user.username

        email = user.email

    # Escape HTML
    full_name = escape(full_name)

    # Icon requested?
    if icon:
        # Get avatar image
        avatar = avatar_for_email(email, size=32)

        full_name = '<img src="%(avatar)s" class="avatar" /> %(name)s' % {
            'name': full_name,
            'avatar': avatar
        }

    if link and user is not None:
        return mark_safe('<a href="%(link)s">%(name)s</a>' % {
            'name': full_name,
            'link': reverse('user_page', kwargs={'user': user.username}),
        })
    else:
        return mark_safe(full_name)


def is_plural(text):
    '''
    Checks whether string is plural form.
    '''
    return text.find(PLURAL_SEPARATOR) != -1


def split_plural(text):
    return text.split(PLURAL_SEPARATOR)


def join_plural(text):
    return PLURAL_SEPARATOR.join(text)


def get_string(text):
    '''
    Returns correctly formatted string from ttkit unit data.
    '''
    # Check for null target (happens with XLIFF)
    if text is None:
        return ''
    if hasattr(text, 'strings'):
        return join_plural(text.strings)
    return text


def is_repo_link(val):
    '''
    Checks whether repository is just a link for other one.
    '''
    return val.startswith('weblate://')


def get_site_url(url=''):
    '''
    Returns root url of current site with domain.
    '''
    site = Site.objects.get_current()
    return 'http://%s%s' % (
        site.domain,
        url
    )


def sleep_while_git_locked():
    '''
    Random sleep to perform when git repository is locked.
    '''
    time.sleep(random.random() * 2)


def load_class(name):
    '''
    Imports module and creates class given by name in string.
    '''
    module, attr = name.rsplit('.', 1)
    try:
        mod = import_module(module)
    except ImportError as e:
        raise ImproperlyConfigured(
            'Error importing module %s: "%s"' %
            (module, e)
        )
    try:
        cls = getattr(mod, attr)
    except AttributeError:
        raise ImproperlyConfigured(
            'Module "%s" does not define a "%s" class' %
            (module, attr)
        )
    return cls


def get_script_name(name):
    '''
    Returns script name from string possibly containing full path and
    parameters.
    '''
    return os.path.basename(name).split()[0]


def get_distinct_translations(units):
    '''
    Returns list of distinct translations. It should be possible to use
    distinct('target') since Django 1.4, but it is not supported with MySQL, so
    let's emulate that based on presumption we won't get too many results.
    '''
    targets = {}
    result = []
    for unit in units:
        if unit.target in targets:
            continue
        targets[unit.target] = 1
        result.append(unit)
    return result


def translation_percent(translated, total):
    '''
    Returns translation percentage.
    '''
    return (1000 * translated / total) / 10.0
