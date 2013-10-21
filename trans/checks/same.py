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
    PYTHON_PRINTF_MATCH, PHP_PRINTF_MATCH, C_PRINTF_MATCH,
    PYTHON_BRACE_MATCH,
)
from django.core.validators import email_re
import re

# We ignore some words which are usually not translated
SAME_BLACKLIST = frozenset((
    'accelerator',
    'account',
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
    'android',
    'antialias',
    'antialiasing',
    'applet',
    'appliance',
    'appliances',
    'aptitude',
    'attribute',
    'attribution',
    'atom',
    'audio',
    'auto',
    'avatar',
    'backend',
    'balance',
    'bb',
    'bios',
    'bit',
    'bitcoin',
    'block',
    'blog',
    'bluetooth',
    'bootloader',
    'branch',
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
    'context',
    'control',
    'copyright',
    'criteria',
    'csv',
    'ctrl',
    'ctrl+d',
    'ctrl+z',
    'cvs',
    'cyrillic',
    'data',
    'database',
    'dbm',
    'debian',
    'debug',
    'definition',
    'del',
    'delete',
    'demo',
    'description',
    'design',
    'designer',
    'detail',
    'details',
    'ding',
    'distribution',
    'distro',
    'dm',
    'doc',
    'docs',
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
    'ellipsis',
    'email',
    'engine',
    'engines',
    'esperanto',
    'exchange',
    'expert',
    'export',
    'extra',
    'fanfare',
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
    'hashed',
    'help',
    'hmpf',
    'horizontal',
    'host',
    'hosting',
    'hostname',
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
    'inconsistent',
    'index',
    'info',
    'information',
    'infrastructure',
    'inline',
    'innodb',
    'ins',
    'insert',
    'installation',
    'interlingua',
    'internet',
    'intro',
    'introduction',
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
    'message',
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
    'performance',
    'php',
    'phpmyadmin',
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
    'pre',
    'pre-commit',
    'prince',
    'process',
    'program',
    'project',
    'promotion',
    'property',
    'properties',
    'proxy',
    'pt',
    'pull',
    'push',
    'px',
    'python',
    'python-gammu',
    'question',
    'questions',
    'realm',
    'rebase',
    'repository',
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
    'service',
    'shell',
    'sim',
    'singular',
    'slug',
    'sms',
    'smsc',
    'smsd',
    'software',
    'solaris',
    'source',
    'spatial',
    'spline',
    'sql',
    'standard',
    'start',
    'status',
    'stop',
    'string',
    'strings',
    'style',
    'subproject',
    'substring',
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
    'tada',
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
    'twitter',
    'ubuntu',
    'ukolovnik',
    'unicode',
    'unique',
    'update',
    'upload',
    'url',
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
    'vote',
    'votes',
    'wammu',
    'web',
    'website',
    'weblate',
    'widget',
    'widgets',
    'wiki',
    'wildcard',
    'windows',
    'word',
    'www',
    'xhtml',
    'xml',
    'zero',
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
    'afrikaans',
    'akan',
    'albanian',
    'amharic',
    'arabic',
    'aragonese',
    'armenian',
    'asturian',
    'azerbaijani',
    'basque',
    'belarusian',
    'bengali',
    'bokmål',
    'bosnian',
    'breton',
    'bulgarian',
    'catalan',
    'chinese',
    'cornish',
    'croatian',
    'czech',
    'danish',
    'dutch',
    'dzongkha',
    'english',
    'esperanto',
    'estonian',
    'faroese',
    'filipino',
    'finnish',
    'flemish',
    'french',
    'frisian',
    'friulian',
    'fulah',
    'gaelic',
    'galician',
    'georgian',
    'german',
    'greek',
    'gujarati',
    'gun',
    'haitian',
    'hausa',
    'hebrew',
    'hindi',
    'hungarian',
    'icelandic',
    'indonesian',
    'interlingua',
    'irish',
    'italian',
    'japanese',
    'javanese',
    'kannada',
    'kashubian',
    'kazakh',
    'khmer',
    'kirghiz',
    'klingon',
    'korean',
    'kurdish',
    'lao',
    'latvian',
    'limburgish',
    'lingala',
    'lithuanian',
    'luxembourgish',
    'macedonian',
    'maithili',
    'malagasy',
    'malay',
    'malayalam',
    'maltese',
    'maori',
    'mapudungun',
    'marathi',
    'mongolian',
    'morisyen',
    'n\'ko',
    'nahuatl',
    'neapolitan',
    'nepali',
    'norwegian',
    'nynorsk',
    'occitan',
    'oriya',
    'papiamento',
    'pedi',
    'persian',
    'piqad',
    'piemontese',
    'polish',
    'portugal',
    'portuguese',
    'punjabi',
    'pushto',
    'romanian',
    'romansh',
    'russian',
    'scots',
    'serbian',
    'sinhala',
    'slovak',
    'slovenian',
    'somali',
    'songhai',
    'sorani',
    'sotho',
    'spanish',
    'sundanese',
    'swahili',
    'swedish',
    'tajik',
    'tagalog',
    'tamil',
    'tatar',
    'telugu',
    'thai',
    'tibetan',
    'tigrinya',
    'turkish',
    'turkmen',
    'uighur',
    'ukrainian',
    'urdu',
    'uzbek',
    'valencian',
    'venda',
    'vietnamese',
    'walloon',
    'welsh',
    'wolof',
    'yakut',
    'yoruba',
    'zulu',
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

RST_MATCH = re.compile(r'(?::ref:`[^`]+`|``[^`]+``)')


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
        elif 'python-brace-format' in flags:
            regex = PYTHON_BRACE_MATCH
        elif 'php-format' in flags:
            regex = PHP_PRINTF_MATCH
        elif 'c-format' in flags:
            regex = C_PRINTF_MATCH
        elif 'rst-text' in flags:
            regex = RST_MATCH
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
            stripped = self.strip_string(lower_source, unit.all_flags)

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
