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

from django.utils.translation import ugettext_lazy as _
from trans.checks.base import TargetCheck
from trans.checks.format import (
    PYTHON_PRINTF_MATCH, PHP_PRINTF_MATCH, C_PRINTF_MATCH
)
from django.core.validators import email_re

# We ignore some words which are usually not translated
SAME_BLACKLIST = frozenset((
    'accelerator',
    'action',
    'actions',
    'active',
    'alarm',
    'amazon',
    'atom',
    'audio',
    'auto',
    'avatar',
    'bitcoin',
    'blog',
    'bluetooth',
    'bzip2',
    'chat',
    'cm',
    'copyright',
    'csv',
    'cvs',
    'data',
    'dbm',
    'description',
    'dm',
    'download',
    'dpi',
    'dummy',
    'e-mail',
    'eib',
    'email',
    'esperanto',
    'expert',
    'export',
    'fax',
    'feeds',
    'filter',
    'firmware',
    'flash',
    'flattr',
    'fulltext',
    'gammu',
    'general',
    'gettext',
    'google',
    'gib',
    'git',
    'gtk',
    'gzip',
    'headset',
    'hardware',
    'help',
    'horizontal',
    'id',
    'in',
    'irc',
    'irda',
    'imei',
    'import',
    'info',
    'information',
    'isbn',
    'jabber',
    'kib',
    'km',
    'latex',
    'layout',
    'linux',
    'lithium ion',
    'lithium polymer',
    'ltr',
    'ma',
    'mah',
    'mailbox',
    'maildir',
    'media',
    'model',
    'monitor',
    'motif',
    'mib',
    'mm',
    'mv',
    'n/a',
    'name',
    'nimh',
    'normal',
    'null',
    'ok',
    'online',
    'open document',
    'operator',
    'orientation',
    'pager',
    'paypal',
    'pdf',
    'personal',
    'pib',
    'port',
    'position',
    'python-gammu',
    'program',
    'proxy',
    'pt',
    'px',
    'rebase',
    'reset',
    'roadmap',
    'rss',
    'rtl',
    'script',
    'server',
    'sim',
    'smsc',
    'software',
    'sql',
    'standard',
    'start',
    'status',
    'stop',
    'style',
    'syndication',
    'system',
    'text',
    'tib',
    'ukolovnik',
    'unicode',
    'vcalendar',
    'vcard',
    'version',
    'vertical',
    'video',
    'wammu',
    'web',
    'weblate',
    'wiki',
    'windows',
    'www',
    'xml',
    'zip',

    # Months are same in some languages
    'january',
    'february',
    'march',
    'april',
    'may',
    'june',
    'july',
    'august',
    'september',
    'october',
    'november',
    'december',

    'jan',
    'feb',
    'mar',
    'apr',
    'jun',
    'jul',
    'aug',
    'sep',
    'oct',
    'nov',
    'dec',
))


class SameCheck(TargetCheck):
    '''
    Check for not translated entries.
    '''
    check_id = 'same'
    name = _('Not translated')
    description = _('Source and translated strings are same')

    def strip_format(self, msg, flags):
        '''
        Checks whether given string contains only format strings
        and possible punctation. These are quite often not changed
        by translators.
        '''
        if 'python-format' in flags:
            regex = PYTHON_PRINTF_MATCH
        elif 'php-format' in flags:
            regex = PHP_PRINTF_MATCH
        elif 'c-format' in flags:
            regex = C_PRINTF_MATCH
        else:
            return msg
        stripped = regex.sub('', msg)
        return stripped

    def strip_string(self, msg, flags):
        '''
        Strips (usually) not translated parts from the string.
        '''
        # Strip format strings
        stripped = self.strip_format(msg, flags)

        # Remove email addresses
        stripped = email_re.sub('', stripped)

        # Remove some html entities
        stripped = stripped.replace('&nbsp;', ' ')

        # Cleanup trailing/leading chars
        stripped = stripped.strip(
            ' ,./<>?;\'\\:"|[]{}`~!@#$%^&*()-=_+0123456789\n\r'
        )

        return stripped

    def check_single(self, source, target, unit, cache_slot):
        # English variants will have most things not translated
        if self.is_language(unit, ['en']):
            return False

        # One letter things are usually labels or decimal/thousand separators
        if len(source) <= 1 and len(target) <= 1:
            return False

        # Probably shortcut
        if source.isupper() and target.isupper():
            return False

        lower_source = source.lower()

        # Check special things like 1:4 1/2 or copyright
        if (len(source.strip('0123456789:/,.')) <= 1
                or '(c) copyright' in lower_source
                or u'©' in source):
            return False

        # Strip format strings
        stripped = self.strip_string(lower_source, unit.flags)

        # Ignore strings which don't contain any string to translate
        if stripped == '':
            return False

        # Ignore words which are often same in foreigh language
        if stripped in SAME_BLACKLIST:
            return False

        return (source == target)
