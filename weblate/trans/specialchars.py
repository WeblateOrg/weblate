# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
"""
Helper code to get user special chars specific for given language.
"""

from __future__ import unicode_literals
from django.utils.translation import ugettext as _, ugettext_lazy

# Hard coded list of special chars
SPECIAL_CHARS = ('→', '↵', '…')

# Names of hardcoded chars
CHAR_NAMES = {
    '→': ugettext_lazy('Insert tab character'),
    '↵': ugettext_lazy('Insert new line'),
    '…': ugettext_lazy('Insert horizontal ellipsis'),
    '।': ugettext_lazy('Danda'),
    '॥': ugettext_lazy('Double danda'),
}

# Quotes definition for each language, based on CLDR data
SINGLE_OPEN = {
    'ja': '『',
    'zh': '『',
    'ar': '’',
    'fi': '’',
    'fo': '’',
    'lag': '’',
    'rn': '’',
    'se': '’',
    'sn': '’',
    'sv': '’',
    'ur': '’',
    'eo': '‘',
    'vo': '‘',
    'ALL': '‘',
    'agq': '‚',
    'bs': '‚',
    'cs': '‚',
    'de': '‚',
    'dsb': '‚',
    'et': '‚',
    'ff': '‚',
    'hr': '‚',
    'hsb': '‚',
    'is': '‚',
    'ksh': '‚',
    'lb': '‚',
    'luy': '‚',
    'mk': '‚',
    'sk': '‚',
    'sl': '‚',
    'ast': '“',
    'bm': '“',
    'ca': '“',
    'cy': '“',
    'dyo': '“',
    'es': '“',
    'ewo': '“',
    'fur': '“',
    'ia': '“',
    'it': '“',
    'kab': '“',
    'mg': '“',
    'mua': '“',
    'nnh': '“',
    'nr': '“',
    'nso': '“',
    'pt': '“',
    'sg': '“',
    'sq': '“',
    'ss': '“',
    'ti': '“',
    'tn': '“',
    'ts': '“',
    've': '“',
    'bas': '„',
    'bg': '„',
    'ky': '„',
    'lt': '„',
    'os': '„',
    'ru': '„',
    'shi': '„',
    'uk': '„',
    'zgh': '„',
    'el': '"',
    'eu': '"',
    'uz': '\'',
    'yi': '\'',
    'hy': '«',
    'ka': '«',
    'nmg': '«',
    'pl': '«',
    'ro': '«',
    'yav': '«',
    'he': '׳',
    'am': '‹',
    'az': '‹',
    'be': '‹',
    'br': '‹',
    'fa': '‹',
    'fr': '‹',
    'gsw': '‹',
    'jgo': '‹',
    'kkj': '‹',
    'rm': '‹',
    'wae': '‹',
    'hu': '»',
    'kl': '›',
    'ug': '›',
}

SINGLE_CLOSE = {
    'ja': '』',
    'zh': '』',
    'eo': '’',
    'vo': '’',
    'ALL': '’',
    'ar': '‘',
    'bs': '‘',
    'cs': '‘',
    'de': '‘',
    'dsb': '‘',
    'et': '‘',
    'hr': '‘',
    'hsb': '‘',
    'is': '‘',
    'ksh': '‘',
    'lb': '‘',
    'luy': '‘',
    'mk': '‘',
    'sk': '‘',
    'sl': '‘',
    'sr': '‘',
    'ur': '‘',
    'ast': '”',
    'bm': '”',
    'ca': '”',
    'cy': '”',
    'dyo': '”',
    'es': '”',
    'ewo': '”',
    'fur': '”',
    'ia': '”',
    'it': '”',
    'kab': '”',
    'mg': '”',
    'mua': '”',
    'nnh': '”',
    'nr': '”',
    'nso': '”',
    'pt': '”',
    'sg': '”',
    'shi': '”',
    'sq': '”',
    'ss': '”',
    'ti': '”',
    'tn': '”',
    'ts': '”',
    've': '”',
    'zgh': '”',
    'bas': '“',
    'bg': '“',
    'ky': '“',
    'lt': '“',
    'os': '“',
    'ru': '“',
    'uk': '“',
    'el': '"',
    'eu': '"',
    'uz': '\'',
    'yi': '\'',
    'hu': '«',
    'he': '׳',
    'kl': '‹',
    'ug': '‹',
    'hy': '»',
    'ka': '»',
    'nmg': '»',
    'pl': '»',
    'ro': '»',
    'yav': '»',
    'am': '›',
    'az': '›',
    'be': '›',
    'br': '›',
    'fa': '›',
    'fr': '›',
    'gsw': '›',
    'jgo': '›',
    'kkj': '›',
    'rm': '›',
    'wae': '›',
}

DOUBLE_OPEN = {
    'eu': '"',
    'uz': '"',
    'yi': '"',
    'ja': '「',
    'zh': '「',
    'cy': '‘',
    'fur': '‘',
    'ia': '‘',
    'nr': '‘',
    'nso': '‘',
    'ss': '‘',
    'ti': '‘',
    'tn': '‘',
    'ts': '‘',
    've': '‘',
    'am': '«',
    'ast': '«',
    'az': '«',
    'bas': '«',
    'be': '«',
    'bm': '«',
    'br': '«',
    'ca': '«',
    'dua': '«',
    'dyo': '«',
    'el': '«',
    'es': '«',
    'ewo': '«',
    'fa': '«',
    'fr': '«',
    'gsw': '«',
    'hy': '«',
    'it': '«',
    'jgo': '«',
    'kab': '«',
    'kkj': '«',
    'ksf': '«',
    'ky': '«',
    'mg': '«',
    'mua': '«',
    'nb': '«',
    'nn': '«',
    'nnh': '«',
    'os': '«',
    'pt': '«',
    'rm': '«',
    'ru': '«',
    'rw': '«',
    'sg': '«',
    'shi': '«',
    'sq': '«',
    'uk': '«',
    'wae': '«',
    'yav': '«',
    'zgh': '«',
    'he': '״',
    'ar': '”',
    'fi': '”',
    'fo': '”',
    'lag': '”',
    'rn': '”',
    'se': '”',
    'sn': '”',
    'sv': '”',
    'ur': '”',
    'eo': '“',
    'vo': '“',
    'ALL': '“',
    'kl': '»',
    'ug': '»',
    'agq': '„',
    'bg': '„',
    'bs': '„',
    'cs': '„',
    'de': '„',
    'dsb': '„',
    'et': '„',
    'ff': '„',
    'hr': '„',
    'hsb': '„',
    'hu': '„',
    'is': '„',
    'ka': '„',
    'ksh': '„',
    'lb': '„',
    'lt': '„',
    'luy': '„',
    'mk': '„',
    'nmg': '„',
    'pl': '„',
    'sk': '„',
    'sl': '„',
    'sr': '„',
}

DOUBLE_CLOSE = {
    'eu': '"',
    'kk': '"',
    'uz': '"',
    'yi': '"',
    'he': '״',
    'cy': '’',
    'fur': '’',
    'ia': '’',
    'nr': '’',
    'nso': '’',
    'ss': '’',
    'ti': '’',
    'tn': '’',
    'ts': '’',
    've': '’',
    'ja': '」',
    'zh': '」',
    'kl': '«',
    'ug': '«',
    'eo': '”',
    'vo': '”',
    'ALL': '”',
    'ar': '“',
    'bg': '“',
    'bs': '“',
    'cs': '“',
    'de': '“',
    'dsb': '“',
    'et': '“',
    'hr': '“',
    'hsb': '“',
    'is': '“',
    'ka': '“',
    'ksh': '“',
    'lb': '“',
    'lt': '“',
    'luy': '“',
    'mk': '“',
    'sk': '“',
    'sl': '“',
    'sr': '“',
    'ur': '“',
    'am': '»',
    'ast': '»',
    'az': '»',
    'bas': '»',
    'be': '»',
    'bm': '»',
    'br': '»',
    'ca': '»',
    'dua': '»',
    'dyo': '»',
    'el': '»',
    'es': '»',
    'ewo': '»',
    'fa': '»',
    'fr': '»',
    'gsw': '»',
    'hy': '»',
    'it': '»',
    'jgo': '»',
    'kab': '»',
    'kkj': '»',
    'ksf': '»',
    'ky': '»',
    'mg': '»',
    'mua': '»',
    'nb': '»',
    'nn': '»',
    'nnh': '»',
    'os': '»',
    'pt': '»',
    'rm': '»',
    'ru': '»',
    'rw': '»',
    'sg': '»',
    'shi': '»',
    'sq': '»',
    'uk': '»',
    'wae': '»',
    'yav': '»',
    'zgh': '»',
}

HYPHEN_LANGS = frozenset((
    'af', 'am', 'ar', 'ast', 'az', 'bg', 'bs', 'ca', 'cs', 'cy', 'da', 'de',
    'dsb', 'dz', 'ee', 'el', 'en', 'eo', 'es', 'fa', 'fi', 'fr', 'fy', 'gd',
    'gl', 'gu', 'he', 'hr', 'hsb', 'id', 'is', 'ja', 'ka', 'kk', 'kn', 'ko',
    'ksh', 'ky', 'lb', 'lkt', 'lt', 'lv', 'mk', 'mn', 'mr', 'nl', 'os', 'pa',
    'pl', 'pt', 'ro', 'ru', 'sk', 'sr', 'sv', 'ta', 'th', 'to', 'tr', 'uz',
    'vi', 'vo', 'yi', 'zh',
))

EN_DASH_LANGS = frozenset((
    'af', 'am', 'ar', 'ast', 'az', 'bg', 'bs', 'ca', 'cs', 'cy', 'da', 'de',
    'dsb', 'dz', 'ee', 'el', 'en', 'eo', 'es', 'fi', 'fr', 'fy', 'gd', 'gl',
    'gu', 'he', 'hr', 'hsb', 'hu', 'id', 'is', 'ka', 'kk', 'kn', 'ksh', 'ky',
    'lb', 'lkt', 'lt', 'lv', 'mk', 'mn', 'mr', 'nb', 'nl', 'os', 'pa', 'pl',
    'pt', 'ro', 'ru', 'sk', 'sr', 'sv', 'ta', 'th', 'to', 'tr', 'uk', 'uz',
    'vi', 'vo', 'yi', 'zh',
))

EM_DASH_LANGS = frozenset((
    'af', 'ar', 'ast', 'az', 'bg', 'bs', 'ca', 'cy', 'de', 'dsb', 'dz', 'ee',
    'el', 'en', 'eo', 'es', 'fr', 'fy', 'gd', 'gl', 'gu', 'he', 'hr', 'hsb',
    'id', 'is', 'it', 'ja', 'ka', 'kk', 'kn', 'ko', 'ksh', 'ky', 'lb', 'lkt',
    'lt', 'lv', 'mk', 'mn', 'mr', 'nl', 'os', 'pa', 'pl', 'pt', 'ro', 'ru',
    'sv', 'ta', 'th', 'to', 'tr', 'uz', 'vi', 'vo', 'yi', 'zh',
))

EXTRA_CHARS = {
    'brx': ('।', '॥'),
}


def get_quote(code, data, name):
    """
    Returns special char for quote.
    """
    if code in data:
        return name, data[code]
    return name, data['ALL']


def get_char_description(char):
    """Returns verbose description of a character."""
    if char in CHAR_NAMES:
        return CHAR_NAMES[char]
    else:
        return _('Insert character {0}').format(char)


def get_special_chars(language):
    """
    Returns list of special characters.
    """
    for char in SPECIAL_CHARS:
        yield get_char_description(char), char
    code = language.code.replace('_', '-').split('-')[0]

    if code in EXTRA_CHARS:
        for char in EXTRA_CHARS[code]:
            yield get_char_description(char), char

    yield get_quote(code, DOUBLE_OPEN, _('Opening double quote'))
    yield get_quote(code, DOUBLE_CLOSE, _('Closing double quote'))
    yield get_quote(code, SINGLE_OPEN, _('Opening single quote'))
    yield get_quote(code, SINGLE_CLOSE, _('Closing single quote'))

    if code in HYPHEN_LANGS:
        yield _('Hyphen'), '-'

    if code in EN_DASH_LANGS:
        yield _('En dash'), '–'

    if code in EM_DASH_LANGS:
        yield _('Em dash'), '—'
