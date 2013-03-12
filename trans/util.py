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
import re
from translate.misc import quote
from translate.storage.properties import propunit
from django.contrib.sites.models import Site
from django.utils.translation import ugettext as _
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.conf import settings
import urllib
import time
import random

GRAVATAR_URL_PREFIX = getattr(
    settings,
    'GRAVATAR_URL_PREFIX',
    'https://secure.gravatar.com/'
)
# See http://cs.gravatar.com/site/implement/images/
# for available choices
GRAVATAR_DEFAULT_IMAGE = getattr(
    settings,
    'GRAVATAR_DEFAULT_IMAGE',
    'identicon'
)

PLURAL_SEPARATOR = '\x00\x00'


def gravatar_for_email(email, size=80):
    '''
    Generates url for gravatar.
    '''
    mail_hash = hashlib.md5(email.lower()).hexdigest()

    url = "%savatar/%s/?" % (GRAVATAR_URL_PREFIX, mail_hash)

    url += urllib.urlencode({
        's': str(size),
        'd': GRAVATAR_DEFAULT_IMAGE
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
        # Get gravatar image
        gravatar = gravatar_for_email(email, size=32)

        full_name = '<img src="%(gravatar)s" class="avatar" /> %(name)s' % {
            'name': full_name,
            'gravatar': gravatar
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


def msg_checksum(source, context):
    '''
    Returns checksum of source string, used for quick lookup.

    We use MD5 as it is faster than SHA1.
    '''
    md5 = hashlib.md5()
    md5.update(source.encode('utf-8'))
    md5.update(context.encode('utf-8'))
    return md5.hexdigest()


def is_unit_key_value(unit):
    '''
    Checks whether unit is key = value based rather than
    translation.

    These are some files like PHP or properties, which for some
    reason do not correctly set source/target attributes.
    '''
    return (
        hasattr(unit, 'name')
        and hasattr(unit, 'value')
        and hasattr(unit, 'translation')
    )


def get_source(unit):
    '''
    Returns source string from a ttkit unit.
    '''
    if is_unit_key_value(unit):
        return unit.name
    else:
        if hasattr(unit.source, 'strings'):
            return join_plural(unit.source.strings)
        else:
            return unit.source


def get_target(unit):
    '''
    Returns target string from a ttkit unit.
    '''
    if unit is None:
        return ''
    if is_unit_key_value(unit):
        # Need to decode property encoded string
        if isinstance(unit, propunit):
            # This is basically stolen from
            # translate.storage.properties.propunit.gettarget
            # which for some reason does not return translation
            value = quote.propertiesdecode(unit.value)
            value = re.sub(u"\\\\ ", u" ", value)
            return value
        return unit.value
    else:
        if hasattr(unit.target, 'strings'):
            return join_plural(unit.target.strings)
        else:
            # Check for null target (happens with XLIFF)
            if unit.target is None:
                return ''
            return unit.target


def get_context(unit):
    '''
    Returns context of message. In some cases we have to use
    ID here to make all backends consistent.
    '''
    if unit is None:
        return ''
    context = unit.getcontext()
    if is_unit_key_value(unit) and context == '':
        return unit.getid()
    return context


def is_translated(unit):
    '''
    Checks whether unit is translated.
    '''
    if unit is None:
        return False
    if is_unit_key_value(unit):
        return not unit.isfuzzy() and unit.value != ''
    else:
        return unit.istranslated()


def is_translatable(unit):
    '''
    Checks whether unit is translatable.

    For some reason, blank string does not mean non translatable
    unit in some formats (XLIFF), so lets skip those as well.
    '''
    return unit.istranslatable() and not unit.isblank()


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
