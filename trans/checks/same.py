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
    'admin',
    'administration',
    'ah',
    'alarm',
    'album',
    'aliasing',
    'alt',
    'amazon',
    'antialias',
    'antialiasing',
    'applet',
    'appliance',
    'appliances',
    'attribute',
    'atom',
    'audio',
    'auto',
    'avatar',
    'balance',
    'bios',
    'bit',
    'bitcoin',
    'block',
    'blog',
    'bluetooth',
    'bootloader',
    'browser',
    'buffer',
    'byte',
    'bytes',
    'bzip',
    'bzip2',
    'cache',
    'chat',
    'cm',
    'code',
    'color',
    'commit',
    'contact',
    'control',
    'copyright',
    'criteria',
    'csv',
    'ctrl',
    'ctrl+d',
    'ctrl+z',
    'cvs',
    'data',
    'database',
    'dbm',
    'debian',
    'debug',
    'definition',
    'del',
    'delete',
    'description',
    'design',
    'designer',
    'detail',
    'details',
    'distribution',
    'distro',
    'dm',
    'doctor',
    'document',
    'documentation',
    'download',
    'downloads',
    'dpkg',
    'dpi',
    'drizzle',
    'dummy',
    'dump',
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
    'fauna',
    'fax',
    'fedora',
    'feeds',
    'filter',
    'filters',
    'firmware',
    'flash',
    'flattr',
    'flora',
    'font',
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
    'hyperlink',
    'icon',
    'icons',
    'id',
    'idea',
    'ignore',
    'irc',
    'irda',
    'image',
    'imei',
    'imsi',
    'import',
    'in',
    'index',
    'info',
    'information',
    'infrastructure',
    'inline',
    'innodb',
    'ins',
    'insert',
    'interlingua',
    'internet',
    'ion',
    'ios',
    'irix',
    'isbn',
    'ismn',
    'issn',
    'isrc',
    'item',
    'jabber',
    'java',
    'join',
    'joins',
    'jpeg',
    'kernel',
    'kib',
    'km',
    'knoppix',
    'label',
    'latex',
    'latin',
    'latitude',
    'layout',
    'level',
    'logo',
    'longitude',
    'lord',
    'libgammu',
    'linestring',
    'link',
    'links',
    'linux',
    'list',
    'lithium',
    'lithium',
    'local',
    'locales',
    'ltr',
    'ma',
    'mah',
    'manager',
    'mailbox',
    'mailboxes',
    'maildir',
    'markdown',
    'master',
    'max',
    'maximum',
    'media',
    'mediawiki',
    'meta',
    'metal',
    'microsoft',
    'minute',
    'model',
    'module',
    'modules',
    'monitor',
    'motif',
    'mib',
    'min',
    'minimum',
    'mint',
    'mm',
    'multiplayer',
    'musicbottle',
    'mv',
    'n/a',
    'name',
    'neutral',
    'nimh',
    'no',
    'node',
    'none',
    'normal',
    'notify',
    'nt',
    'null',
    'office',
    'ok',
    'online',
    'open',
    'opendocument',
    'opensuse',
    'openvpn',
    'opera',
    'operator',
    'option',
    'options',
    'orientation',
    'output',
    'overhead',
    'package',
    'pager',
    'partition',
    'party',
    'pause',
    'paypal',
    'pdf',
    'pdu',
    'personal',
    'pib',
    'plan',
    'playlist',
    'plugin',
    'plugins',
    'plural',
    'png',
    'po',
    'point',
    'polygon',
    'polymer',
    'pool',
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
    'question',
    'questions',
    'realm',
    'rebase',
    'reset',
    'resource',
    'rich-text',
    'richtext',
    'roadmap',
    'routine',
    'routines',
    'rss',
    'rtl',
    'saver',
    'scalable',
    'scenario',
    'screen',
    'screenshot',
    'screensaver',
    'script',
    'scripts',
    'scripting',
    'sergeant',
    'server',
    'servers',
    'shell',
    'sim',
    'singular',
    'smsc',
    'software',
    'solaris',
    'spatial',
    'spline',
    'sql',
    'standard',
    'start',
    'status',
    'stop',
    'string',
    'style',
    'sum',
    'sunos',
    'support',
    'svg',
    'symbol',
    'syndication',
    'system',
    'swap',
    'table',
    'tables',
    'tbx',
    'termbase',
    'test',
    'texy',
    'text',
    'tib',
    'timer',
    'todo',
    'todos',
    'total',
    'trigger',
    'triggers',
    'ts',
    'tutorial',
    'tour',
    'type',
    'twiki',
    'ubuntu',
    'ukolovnik',
    'unicode',
    'unique',
    'variable',
    'variables',
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
    'website',
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

    # Week names shotrcuts
    'mo',
    'tu',
    'we',
    'th',
    'fr',
    'sa',
    'su',

    # Architectures
    'alpha',
    'amd',
    'amd64',
    'arm',
    'aarch',
    'aarch64',
    'hppa',
    'i386',
    'i586',
    'm68k',
    'powerpc',
    'sparc',
    'x86_64',

    # Language names
    'thai',
))

URL_RE = re.compile(
    r'(?:http|ftp)s?://'  # http:// or https://
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
            '&amp;', '&'
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
        stripped = self.strip_chars(stripped)

        return stripped

    def strip_chars(self, word):
        '''
        Strip chars not useful for translating.
        '''
        return word.strip(
            u' ,./<>?;\'\\:"|[]{}`~!@#$%^&*()-=_+0123456789\n\r✓—'
        )

    def test_word(self, word):
        '''
        Test whether word should be ignored.
        '''
        stripped = self.strip_chars(word)
        return len(stripped) <= 1 or stripped in SAME_BLACKLIST

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
                    (self.test_word(word) for word in stripped.split())
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
