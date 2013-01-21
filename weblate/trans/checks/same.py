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
from django.core.exceptions import ImproperlyConfigured
from django.conf import settings
from django.core.cache import cache
from xml.etree import cElementTree
import weblate
from weblate.trans.checks.base import TargetCheck
from weblate.trans.checks.format import (
    PYTHON_PRINTF_MATCH, PHP_PRINTF_MATCH, C_PRINTF_MATCH
)
import re

# We ignore some words which are usually not translated
SAME_BLACKLIST = frozenset((
    'alarm',
    'audio',
    'auto',
    'avatar',
    'bitcoin',
    'blog',
    'bluetooth',
    'bzip2',
    'cm',
    'csv',
    'cvs',
    'data',
    'dm',
    'dpi',
    'e-mail',
    'eib',
    'email',
    'esperanto',
    'expert',
    'export',
    'firmware',
    'flash',
    'fulltext',
    'gib',
    'git',
    'gzip',
    'headset',
    'hardware',
    'id',
    'in',
    'irc',
    'irda',
    'imei',
    'import',
    'info',
    'information',
    'jabber',
    'kib',
    'km',
    'latex',
    'model',
    'mib',
    'mm',
    'n/a',
    'name',
    'normal',
    'ok',
    'open document',
    'pager',
    'pdf',
    'pib',
    'port',
    'program',
    'proxy',
    'pt',
    'px',
    'rss',
    'server',
    'sim',
    'smsc',
    'software',
    'standard',
    'sql',
    'status',
    'text',
    'tib',
    'unicode',
    'vcalendar',
    'vcard',
    'version',
    'video',
    'web',
    'wiki',
    'www',
    'xml',
    'zip',
))

class SameCheck(TargetCheck):
    '''
    Check for not translated entries.
    '''
    check_id = 'same'
    name = _('Not translated')
    description = _('Source and translated strings are same')

    def is_format_only(self, msg, flags):
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
            return False
        stripped = regex.sub('', msg)
        return stripped.strip(' ,./<>?;\'\\:"|[]{}`~!@#$%^&*()-=_+') == ''

    def check_single(self, source, target, flags, language, unit, cache_slot):
        # Ignore strings which don't contain any string to translate
        if self.is_format_only(source, flags):
            return False

        # One letter things are usually labels or decimal/thousand separators
        if len(source) == 1 and len(target) == 1:
            return False

        # English variants will have most things not translated
        if self.is_language(language, ['en']):
            return False

        # Probably shortcut
        if source.isupper() and target.isupper():
            return False

        # Ignore words which are often same in foreigh language
        if source.lower().strip('_&: ') in SAME_BLACKLIST:
            return False

        return (source == target)
