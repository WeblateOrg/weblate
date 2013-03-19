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
from django.contrib.sites.models import Site
from django.utils.translation import ugettext as _
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.conf import settings
import urllib
import time
import random

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

PLURAL_SEPARATOR = '\x00\x00'


def avatar_for_email(email, size=80):
    '''
    Generates url for avatar.
    '''

    # Use libravatar library if available
    if HAS_LIBRAVATAR:
        return escape(libravatar.libravatar_url(email=email, https=True))

    # Fallback to standard method
    mail_hash = hashlib.md5(email.lower()).hexdigest()

    url = "%savatar/%s?" % (AVATAR_URL_PREFIX, mail_hash)

    url += urllib.urlencode({
        's': str(size),
        'd': AVATAR_DEFAULT_IMAGE
    })

    return escape(url)


def get_user_display(user, icon=True, link=False):
    '''
    Nicely formats user for display.
    '''
    # Did we get any user?
    if user is None:
        # None user, probably remotely triggered action
        full_name = _('None')
        email = 'noreply@weblate.org'
        profile = None
    else:
        # Get full name
        full_name = user.get_full_name()

        # Use user name if full name is empty
        if full_name.strip() == '':
            full_name = user.username

        email = user.email
        profile = user.get_profile()

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

    if link and profile is not None:
        return mark_safe('<a href="%(link)s">%(name)s</a>' % {
            'name': full_name,
            'link': profile.get_absolute_url(),
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
    Checks whethere repository is just a link for other one.
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
