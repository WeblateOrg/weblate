# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from __future__ import unicode_literals

import re

from django.utils.html import strip_tags
from django.utils.translation import ugettext_lazy as _

from weblate.checks.base import TargetCheck
from weblate.checks.format import (
    PYTHON_PRINTF_MATCH, PHP_PRINTF_MATCH, C_PRINTF_MATCH,
    PYTHON_BRACE_MATCH,
)
from weblate.checks.data import SAME_BLACKLIST
from weblate.checks.languages import LANGUAGES

# Email address to ignore
EMAIL_RE = re.compile(
    r'[a-z0-9_.-]+@[a-z0-9_.-]+\.[a-z0-9-]{2,}',
    re.IGNORECASE
)

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

PATH_RE = re.compile(r'(^|[ ])(/[a-zA-Z0-9=:?._-]+)+')

TEMPLATE_RE = re.compile(r'{[a-z_-]+}|@[A-Z_]@')

RST_MATCH = re.compile(
    r'(?::(ref|config:option|file|guilabel):`[^`]+`|``[^`]+``)'
)

SPLIT_RE = re.compile(
    r'(?:\&(?:nbsp|rsaquo|lt|gt|amp|ldquo|rdquo|times|quot);|' +
    r'[() ,.^`"\'\\/_<>!?;:|{}*^@%#&~=+\r\n✓—‑…\[\]0-9-])+'
)

# Docbook tags to ignore
DB_TAGS = (
    'screen',
    'indexterm',
    'programlisting',
)


def strip_format(msg, flags):
    """Check whether given string contains only format strings
    and possible punctation. These are quite often not changed
    by translators.
    """
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


def strip_string(msg, flags):
    """Strip (usually) not translated parts from the string."""
    # Strip HTML markup
    stripped = strip_tags(msg)

    # Strip format strings
    stripped = strip_format(stripped, flags)

    # Remove email addresses
    stripped = EMAIL_RE.sub('', stripped)

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

    # Cleanup trailing/leading chars
    return stripped


def test_word(word):
    """Test whether word should be ignored."""
    return len(word) <= 2 or word in SAME_BLACKLIST or word in LANGUAGES


class SameCheck(TargetCheck):
    """Check for not translated entries."""
    check_id = 'same'
    name = _('Unchanged translation')
    description = _('Source and translation are identical')
    severity = 'warning'

    def should_ignore(self, source, unit):
        """Check whether given unit should be ignored."""
        # Ignore some docbook tags
        if unit.comment.startswith('Tag: ') and unit.comment[5:] in DB_TAGS:
            return True

        # Lower case source
        lower_source = source.lower()

        # Check special things like 1:4 1/2 or copyright
        if (len(source.strip('0123456789:/,.')) <= 1 or
                '(c) copyright' in lower_source or
                '©' in source):
            result = True
        else:
            # Strip format strings
            stripped = strip_string(lower_source, unit.all_flags)

            # Ignore strings which don't contain any string to translate
            # or just single letter (usually unit or something like that)
            if len(stripped) <= 1:
                result = True
            else:
                # Check if we have any word which is not in blacklist
                # (words which are often same in foreign language)
                for word in SPLIT_RE.split(stripped):
                    if not test_word(word):
                        return False
                return True

        return result

    def should_skip(self, unit):
        if super(SameCheck, self).should_skip(unit):
            return True

        source_language = unit.translation.component.project.\
            source_language.code.split('_')[0]

        # Ignore the check for source language,
        # English variants will have most things not translated
        # Interlingua is also quite often similar to English
        if (self.is_language(unit, source_language) or
                (source_language == 'en' and
                 self.is_language(unit, ('en', 'ia')))):
            return True

        return False

    def check_single(self, source, target, unit):
        # One letter things are usually labels or decimal/thousand separators
        if len(source) <= 1 and len(target) <= 1:
            return False

        # Probably shortcut
        if source.isupper() and target.isupper():
            return False

        # Check for ignoring
        if self.should_ignore(source, unit):
            return False

        return source == target
