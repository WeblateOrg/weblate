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
import re

# We ignore some words which are usually not translated
SAME_BLACKLIST = frozenset((
    'accelerator',
    'action',
    'actions',
    'active',
    'add-ons',
    'addons',
    'ah',
    'alarm',
    'amazon',
    'applet',
    'appliance',
    'appliances',
    'attribute',
    'atom',
    'audio',
    'auto',
    'avatar',
    'balance',
    'bit',
    'bitcoin',
    'block',
    'blog',
    'bluetooth',
    'bootloader',
    'byte',
    'bytes',
    'bzip2',
    'cache',
    'chat',
    'cm',
    'code',
    'color',
    'commit',
    'contact',
    'copyright',
    'criteria',
    'csv',
    'cvs',
    'data',
    'database',
    'dbm',
    'debian',
    'description',
    'design',
    'designer',
    'dm',
    'doctor',
    'document',
    'documentation',
    'download',
    'downloads',
    'dpi',
    'dummy',
    'e-mail',
    'editor',
    'eib',
    'email',
    'engine',
    'engines',
    'esperanto',
    'exchange',
    'expert',
    'export',
    'extra',
    'farm',
    'fax',
    'fedora',
    'feeds',
    'filter',
    'firmware',
    'flash',
    'flattr',
    'format',
    'freemind',
    'freeplane',
    'fulltext',
    'gammu',
    'general',
    'gettext',
    'global',
    'google',
    'gib',
    'git',
    'graphic',
    'graphics',
    'gtk',
    'gzip',
    'headset',
    'hardware',
    'help',
    'hmpf',
    'horizontal',
    'host',
    'hosting',
    'html',
    'http',
    'icon',
    'id',
    'in',
    'infrastructure',
    'inline',
    'internet',
    'irc',
    'irda',
    'image',
    'imei',
    'imsi',
    'import',
    'index',
    'info',
    'information',
    'ion',
    'isbn',
    'issn',
    'jabber',
    'java',
    'jpeg',
    'kernel',
    'kib',
    'km',
    'latex',
    'latin',
    'layout',
    'level',
    'logo',
    'linestring',
    'link',
    'linux',
    'lithium',
    'lithium',
    'local',
    'locales',
    'ltr',
    'ma',
    'mah',
    'manager',
    'mailbox',
    'maildir',
    'max',
    'maximum',
    'media',
    'mediawiki',
    'metal',
    'microsoft',
    'minute',
    'model',
    'monitor',
    'motif',
    'mib',
    'min',
    'minimum',
    'mm',
    'multiplayer',
    'mv',
    'n/a',
    'name',
    'neutral',
    'nimh',
    'no',
    'node',
    'none',
    'normal',
    'null',
    'office',
    'ok',
    'online',
    'open',
    'opendocument',
    'opensuse',
    'operator',
    'orientation',
    'package',
    'pager',
    'partition',
    'party',
    'pause',
    'paypal',
    'pdf',
    'personal',
    'pib',
    'plugin',
    'plugins',
    'plural',
    'png',
    'po',
    'point',
    'polygon',
    'polymer',
    'port',
    'portable',
    'position',
    'prince',
    'python',
    'python-gammu',
    'program',
    'promotion',
    'proxy',
    'pt',
    'px',
    'realm',
    'rebase',
    'reset',
    'rich-text',
    'richtext',
    'roadmap',
    'routine',
    'routines',
    'rss',
    'rtl',
    'scalable',
    'scenario',
    'screenshot',
    'script',
    'sergeant',
    'server',
    'shell',
    'sim',
    'singular',
    'smsc',
    'software',
    'spatial',
    'spline',
    'sql',
    'sql dump',
    'standard',
    'start',
    'status',
    'stop',
    'string',
    'style',
    'sum',
    'support',
    'svg',
    'syndication',
    'system',
    'table',
    'tables',
    'tbx',
    'termbase',
    'test',
    'texy',
    'text',
    'tib',
    'timer',
    'total',
    'trigger',
    'triggers',
    'ts',
    'tutorial',
    'tour',
    'type',
    'twiki',
    'ukolovnik',
    'unicode',
    'vcalendar',
    'vcard',
    'vector',
    'version',
    'versions',
    'vertical',
    'video',
    'view',
    'views',
    'wammu',
    'web',
    'weblate',
    'widget',
    'widgets',
    'wiki',
    'windows',
    'word',
    'www',
    'xhtml',
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

URL_RE = re.compile(
    r'^(?:http|ftp)s?://'  # http:// or https://
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+'
    r'(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
    r'localhost|'  # localhost...
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
    r'(?::\d+)?'  # optional port
    r'(?:/?|[/?]\S+)$',
    re.IGNORECASE
)

HASH_RE = re.compile(r'#[A-Za-z0-9_-]*')

DOMAIN_RE = re.compile(
    r'(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+'
    r'(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)',
    re.IGNORECASE
)

PATH_RE = re.compile(r'(/[a-zA-Z0-9=:?._-]+)+')

TEMPLATE_RE = re.compile(r'{[a-z_-]+}')


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

        # Strip full URLs
        stripped = URL_RE.sub('', stripped)

        # Strip hash tags / IRC channels
        stripped = HASH_RE.sub('', stripped)

        # Strip domain names/URLs
        stripped = DOMAIN_RE.sub('', stripped)

        # Strip file/URL paths
        stripped = PATH_RE.sub('', stripped)

        # Strip template markup
        stripped = TEMPLATE_RE.sub('', stripped)

        # Remove some html entities
        stripped = stripped.replace(
            '&nbsp;', ' '
        ).replace(
            '&rsaquo;', '"'
        ).replace(
            '&lt;', '<'
        ).replace(
            '&gt;', '>'
        ).replace(
            '&ldquo;', '"'
        ).replace(
            '&rdquo;', '"'
        ).replace(
            '&times;', '.'
        ).replace(
            '&quot;', '"'
        )

        # Cleanup trailing/leading chars
        stripped = stripped.strip(
            u' ,./<>?;\'\\:"|[]{}`~!@#$%^&*()-=_+0123456789\n\r✓—'
        )

        return stripped

    def should_ignore(self, source, unit, cache_slot):
        '''
        Check whether given unit should be ignored.
        '''
        # Use cache if available
        result = self.get_cache(unit, cache_slot)
        if result is not None:
            return result

        # Lower case source
        lower_source = source.lower()

        # Check special things like 1:4 1/2 or copyright
        if (len(source.strip('0123456789:/,.')) <= 1
                or '(c) copyright' in lower_source
                or u'©' in source):
            result = True
        else:
            # Strip format strings
            stripped = self.strip_string(lower_source, unit.flags.split(', '))

            # Ignore strings which don't contain any string to translate
            # or just single letter (usually unit or something like that)
            if len(stripped) <= 1:
                result = True
            else:
                # Check if we have any word which is not in blacklist
                # (words which are often same in foreign language)
                result = min(
                    (word in SAME_BLACKLIST for word in stripped.split())
                )

        # Store in cache
        self.set_cache(unit, result, cache_slot)

        return result

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

        # Check for ignoring
        if self.should_ignore(source, unit, cache_slot):
            return False

        return (source == target)
