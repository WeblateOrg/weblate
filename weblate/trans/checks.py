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
import re

PYTHON_PRINTF_MATCH = re.compile('''
        %(                          # initial %
              (?:\((?P<key>\w+)\))?    # Python style variables, like %(var)s
        (?P<fullvar>
            [+#-]*                  # flags
            (?:\d+)?                # width
            (?:\.\d+)?              # precision
            (hh\|h\|l\|ll)?         # length formatting
            (?P<type>[\w%]))        # type (%s, %d, etc.)
        )''', re.VERBOSE)


PHP_PRINTF_MATCH = re.compile('''
        %(                          # initial %
              (?:(?P<ord>\d+)\$)?   # variable order, like %1$s
        (?P<fullvar>
            [+#-]*                  # flags
            (?:\d+)?                # width
            (?:\.\d+)?              # precision
            (hh\|h\|l\|ll)?         # length formatting
            (?P<type>[\w%]))        # type (%s, %d, etc.)
        )''', re.VERBOSE)


C_PRINTF_MATCH = re.compile('''
        %(                          # initial %
        (?P<fullvar>
            [+#-]*                  # flags
            (?:\d+)?                # width
            (?:\.\d+)?              # precision
            (hh\|h\|l\|ll)?         # length formatting
            (?P<type>[\w%]))        # type (%s, %d, etc.)
        )''', re.VERBOSE)

BBCODE_MATCH = re.compile(
    r'\[(?P<tag>[^]]*)(?=(@[^]]*)?\](.*?)\[\/(?P=tag)\])',
    re.MULTILINE
)

XML_MATCH = re.compile(r'<[^>]+>')
XML_ENTITY_MATCH = re.compile(r'&#?\w+;')

# Matches (s) not followed by alphanumeric chars or at the end
PLURAL_MATCH = re.compile(r'\(s\)(\W|\Z)')

# We ignore some words which are usually not translated
SAME_BLACKLIST = frozenset((
    'audio',
    'auto',
    'avatar',
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
    'kib',
    'km',
    'latex',
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

DEFAULT_CHECK_LIST = (
    'weblate.trans.checks.SameCheck',
    'weblate.trans.checks.BeginNewlineCheck',
    'weblate.trans.checks.EndNewlineCheck',
    'weblate.trans.checks.BeginSpaceCheck',
    'weblate.trans.checks.EndSpaceCheck',
    'weblate.trans.checks.EndStopCheck',
    'weblate.trans.checks.EndColonCheck',
    'weblate.trans.checks.EndQuestionCheck',
    'weblate.trans.checks.EndExclamationCheck',
    'weblate.trans.checks.EndEllipsisCheck',
    'weblate.trans.checks.PythonFormatCheck',
    'weblate.trans.checks.PHPFormatCheck',
    'weblate.trans.checks.CFormatCheck',
    'weblate.trans.checks.PluralsCheck',
    'weblate.trans.checks.ConsistencyCheck',
    'weblate.trans.checks.DirectionCheck',
    'weblate.trans.checks.NewlineCountingCheck',
    'weblate.trans.checks.BBCodeCheck',
    'weblate.trans.checks.ZeroWidthSpaceCheck',
    'weblate.trans.checks.XMLTagsCheck',
    'weblate.trans.checks.OptionalPluralCheck',
    'weblate.trans.checks.EllipsisCheck',
)


class Check(object):
    '''
    Basic class for checks.
    '''
    check_id = ''
    name = ''
    description = ''
    target = False
    source = False

    def check(self, sources, targets, flags, language, unit):
        '''
        Checks single unit, handling plurals.
        '''
        # Check singular
        if self.check_single(sources[0], targets[0], flags, language, unit, 0):
            return True
        # Do we have more to check?
        if len(sources) == 1:
            return False
        # Check plurals against plural from source
        for target in targets[1:]:
            if self.check_single(sources[1], target, flags, language, unit, 1):
                return True
        # Check did not fire
        return False

    def check_single(self, source, target, flags, language, unit, cache_slot):
        '''
        Check for single phrase, not dealing with plurals.
        '''
        return False

    def check_source(self, source, flags, unit):
        '''
        Checks source string
        '''
        return False

    def check_chars(self, source, target, pos, chars):
        '''
        Generic checker for chars presence.
        '''
        if len(target) == 0 or len(source) == 0:
            return False
        src = source[pos]
        tgt = target[pos]
        return (
            (src in chars and tgt not in chars)
            or (src not in chars and tgt in chars)
        )

    def is_language(self, language, vals):
        '''
        Detects whether language is in given list, ignores language
        variants.
        '''
        return language.code.split('_')[0] in vals

    def get_doc_url(self):
        '''
        Returns link to documentation.
        '''
        return weblate.get_doc_url(
            'usage',
            'check-%s' % self.check_id.replace('_', '-')
        )

    def get_cache_key(self, unit, cache_slot=0):
        '''
        Generates key for a cache.
        '''
        return 'check-%s-%s-%d' % (self.check_id, unit.checksum, cache_slot)

    def get_cache(self, unit, cache_slot=0):
        '''
        Returns cached result.
        '''
        return cache.get(self.get_cache_key(unit, cache_slot))

    def set_cache(self, unit, value, cache_slot=0):
        '''
        Sets cache.
        '''
        return cache.set(self.get_cache_key(unit, cache_slot), value)


class TargetCheck(Check):
    '''
    Basic class for target checks.
    '''
    target = True


class SourceCheck(Check):
    '''
    Basic class for source checks.
    '''
    source = True


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


class BeginNewlineCheck(TargetCheck):
    '''
    Checks for newlines at beginning.
    '''
    check_id = 'begin_newline'
    name = _('Starting newline')
    description = _('Source and translation do not both start with a newline')

    def check_single(self, source, target, flags, language, unit, cache_slot):
        return self.check_chars(source, target, 0, ['\n'])


class EndNewlineCheck(TargetCheck):
    '''
    Checks for newlines at end.
    '''
    check_id = 'end_newline'
    name = _('Trailing newline')
    description = _('Source and translation do not both end with a newline')

    def check_single(self, source, target, flags, language, unit, cache_slot):
        return self.check_chars(source, target, -1, ['\n'])


class BeginSpaceCheck(TargetCheck):
    '''
    Whitespace check, starting whitespace usually is important for UI
    '''
    check_id = 'begin_space'
    name = _('Starting spaces')
    description = _('Source and translation do not both start with same number of spaces')

    def check_single(self, source, target, flags, language, unit, cache_slot):
        # One letter things are usually decimal/thousand separators
        if len(source) <= 1 and len(target) <= 1:
            return False

        # Count space chars in source and target
        source_space = len(source) - len(source.lstrip(' '))
        target_space = len(target) - len(target.lstrip(' '))

        # Compare numbers
        return (source_space != target_space)


class EndSpaceCheck(TargetCheck):
    '''
    Whitespace check
    '''
    check_id = 'end_space'
    name = _('Trailing space')
    description = _('Source and translation do not both end with a space')

    def check_single(self, source, target, flags, language, unit, cache_slot):
        # One letter things are usually decimal/thousand separators
        if len(source) <= 1 and len(target) <= 1:
            return False
        if self.is_language(language, ['fr', 'br']):
            if len(target) == 0:
                return False
            if source[-1] in [':', '!', '?'] and target[-1] == ' ':
                return False

        # Count space chars in source and target
        source_space = len(source) - len(source.rstrip(' '))
        target_space = len(target) - len(target.rstrip(' '))

        # Compare numbers
        return (source_space != target_space)


class EndStopCheck(TargetCheck):
    '''
    Check for final stop
    '''
    check_id = 'end_stop'
    name = _('Trailing stop')
    description = _('Source and translation do not both end with a full stop')

    def check_single(self, source, target, flags, language, unit, cache_slot):
        if len(source) == 1 and len(target) == 1:
            return False
        if self.is_language(language, ['ja']) and source[-1] in [':', ';']:
            # Japanese sentence might need to end with full stop
            # in case it's used before list.
            return self.check_chars(
                source, target, -1, [u':', u'：', u'.', u'。']
            )
        return self.check_chars(
            source, target, -1, [u'.', u'。', u'।', u'۔']
        )


class EndColonCheck(TargetCheck):
    '''
    Check for final colon
    '''
    check_id = 'end_colon'
    name = _('Trailing colon')
    description = _('Source and translation do not both end with a colon or colon is not correctly spaced')

    def check_single(self, source, target, flags, language, unit, cache_slot):
        if self.is_language(language, ['fr', 'br']):
            if len(target) == 0 or len(source) == 0:
                return False
            if source[-1] == ':':
                if target[-3:] not in [' : ', '&nbsp;: ', u' : ']:
                    return True
            return False
        if self.is_language(language, ['ja']):
            # Japanese sentence might need to end with full stop
            # in case it's used before list.
            if source[-1] in [':', ';']:
                return self.check_chars(source, target, -1, [u':', u'：', u'.', u'。'])
            return False
        return self.check_chars(source, target, -1, [u':', u'：'])


class EndQuestionCheck(TargetCheck):
    '''
    Check for final question mark
    '''
    check_id = 'end_question'
    name = _('Trailing question')
    description = _('Source and translation do not both end with a question mark or it is not correctly spaced')

    def check_single(self, source, target, flags, language, unit, cache_slot):
        if self.is_language(language, ['fr', 'br']):
            if len(target) == 0 or len(source) == 0:
                return False
            if source[-1] == '?':
                if target[-2:] not in [' ?', '&nbsp;?', u' ?']:
                    return True
            return False
        return self.check_chars(
            source,
            target,
            -1,
            [u'?', u'՞', u'؟', u'⸮', u'？', u'፧', u'꘏', u'⳺']
        )


class EndExclamationCheck(TargetCheck):
    '''
    Check for final exclamation mark
    '''
    check_id = 'end_exclamation'
    name = _('Trailing exclamation')
    description = _('Source and translation do not both end with an exclamation mark or it is not correctly spaced')

    def check_single(self, source, target, flags, language, unit, cache_slot):
        if len(source) == 0:
            return False
        if self.is_language(language, ['eu']):
            if source[-1] == '!':
                if u'¡' in target and u'!' in target:
                    return False
        if self.is_language(language, ['fr', 'br']):
            if len(target) == 0:
                return False
            if source[-1] == '!':
                if target[-2:] not in [' !', '&nbsp;!', u' !']:
                    return True
            return False
        return self.check_chars(
            source,
            target,
            -1,
            [u'!', u'！', u'՜', u'᥄', u'႟', u'߹']
        )


class EndEllipsisCheck(TargetCheck):
    '''
    Check for ellipsis at the end of string.
    '''
    check_id = 'end_ellipsis'
    name = _('Trailing ellipsis')
    description = _('Source and translation do not both end with an ellipsis')

    def check_single(self, source, target, flags, language, unit, cache_slot):
        return self.check_chars(source, target, -1, [u'…'])


class BaseFormatCheck(TargetCheck):
    '''
    Base class for fomat string checks.
    '''
    flag = None
    regexp = None

    def check(self, sources, targets, flags, language, unit):
        '''
        Checks single unit, handling plurals.
        '''
        if not self.flag in flags:
            return False
        # Special case languages with single plural form
        if len(sources) > 1 and len(targets) == 1:
            return self.check_format(sources[1], targets[0], flags, language, unit, 1, False)
        # Check singular
        if self.check_format(sources[0], targets[0], flags, language, unit, 0, len(sources) > 1):
            if len(sources) == 1:
                return True
            if self.check_format(sources[1], targets[0], flags, language, unit, 1, True):
                return True
        # Do we have more to check?
        if len(sources) == 1:
            return False
        # Check plurals against plural from source
        for target in targets[1:]:
            if self.check_format(sources[1], target, flags, language, unit, 1, False):
                return True
        # Check did not fire
        return False

    def check_format(self, source, target, flags, language, unit, cache_slot, ignore_missing):
        '''
        Generic checker for format strings.
        '''
        if len(target) == 0 or len(source) == 0:
            return False
        # Try geting source parsing from cache
        src_matches = self.get_cache(unit, cache_slot)
        # Cache miss
        if src_matches is None:
            src_matches = set([x[0] for x in self.regexp.findall(source)])
            self.set_cache(unit, src_matches, cache_slot)
        tgt_matches = set([x[0] for x in self.regexp.findall(target)])
        # We ignore %% as this is really not relevant. However it needs
        # to be matched to prevent handling %%s as %s.
        if '%' in src_matches:
            src_matches.remove('%')
        if '%' in tgt_matches:
            tgt_matches.remove('%')

        if src_matches != tgt_matches:
            # We can ignore missing format strings
            # for first of plurals
            if ignore_missing and tgt_matches < src_matches:
                return False
            return True

        return False


class PythonFormatCheck(BaseFormatCheck):
    '''
    Check for Python format string
    '''
    check_id = 'python_format'
    name = _('Python format')
    description = _('Format string does not match source')
    flag = 'python-format'
    regexp = PYTHON_PRINTF_MATCH


class PHPFormatCheck(BaseFormatCheck):
    '''
    Check for PHP format string
    '''
    check_id = 'php_format'
    name = _('PHP format')
    description = _('Format string does not match source')
    flag = 'php-format'
    regexp = PHP_PRINTF_MATCH


class CFormatCheck(BaseFormatCheck):
    '''
    Check for C format string
    '''
    check_id = 'c_format'
    name = _('C format')
    description = _('Format string does not match source')
    flag = 'c-format'
    regexp = C_PRINTF_MATCH


class PluralsCheck(TargetCheck):
    '''
    Check for incomplete plural forms
    '''
    check_id = 'plurals'
    name = _('Missing plurals')
    description = _('Some plural forms are not translated')

    def check(self, sources, targets, flags, language, unit):
        # Is this plural?
        if len(sources) == 1:
            return False
        # Is at least something translated?
        if targets == len(targets) * ['']:
            return False
        # Check for empty translation
        return ('' in targets)


class ConsistencyCheck(TargetCheck):
    '''
    Check for inconsistent translations
    '''
    check_id = 'inconsistent'
    name = _('Inconsistent')
    description = _('This message has more than one translation in this project')

    def check(self, sources, targets, flags, language, unit):
        from weblate.trans.models import Unit
        # Do not check consistency if user asked not to have it
        if not unit.translation.subproject.allow_translation_propagation:
            return False
        related = Unit.objects.filter(
            translation__language=language,
            translation__subproject__project=unit.translation.subproject.project,
            checksum=unit.checksum,
        ).exclude(
            id=unit.id,
            translation__subproject__allow_translation_propagation=False,
        )
        if unit.fuzzy:
            related = related.exclude(fuzzy=True)
        for unit2 in related.iterator():
            if unit2.target != unit.target:
                return True

        return False


class DirectionCheck(TargetCheck):
    '''
    Check for text direction values
    '''
    check_id = 'direction'
    name = _('Invalid text direction')
    description = _('Text direction can be either LTR or RTL')

    def check(self, sources, targets, flags, language, unit):
        # Is this plural?
        if len(sources) > 1:
            return False
        if not sources[0].lower() in ['ltr', 'rtl']:
            return False
        return targets[0].lower() != language.direction


class CountingCheck(TargetCheck):
    '''
    Check whether there is same count of given string.
    '''
    string = None

    def check_single(self, source, target, flags, language, unit, cache_slot):
        if len(target) == 0 or len(source) == 0:
            return False
        return source.count(self.string) != target.count(self.string)


class NewlineCountingCheck(CountingCheck):
    '''
    Check whether there is same amount of \n strings
    '''
    string = '\\n'
    check_id = 'escaped_newline'
    name = _('Mismatched \\n')
    description = _('Number of \\n in translation does not match source')


class BBCodeCheck(TargetCheck):
    '''
    Check for matching bbcode tags.
    '''
    check_id = 'bbcode'
    name = _('Mismatched BBcode')
    description = _('BBcode in translation does not match source')

    def check_single(self, source, target, flags, language, unit, cache_slot):
        # Try geting source parsing from cache
        src_match = self.get_cache(unit, cache_slot)
        # Cache miss
        if src_match is None:
            src_match = BBCODE_MATCH.findall(source)
            self.set_cache(unit, src_match, cache_slot)
        # Any BBCode in source?
        if len(src_match) == 0:
            return False
        # Parse target
        tgt_match = BBCODE_MATCH.findall(target)
        if len(src_match) != len(tgt_match):
            return True

        src_tags = set([x[0] for x in src_match])
        tgt_tags = set([x[0] for x in tgt_match])

        return (src_tags != tgt_tags)


class ZeroWidthSpaceCheck(TargetCheck):
    '''
    Check for zero width space char (<U+200B>).
    '''
    check_id = 'zero-width-space'
    name = _('Zero-width space')
    description = _('Translation contains extra zero-width space character')

    def check_single(self, source, target, flags, language, unit, cache_slot):
        return (u'\u200b' in target) != (u'\u200b' in source)


class XMLTagsCheck(TargetCheck):
    '''
    Check whether XML in target matches source.
    '''
    check_id = 'xml-tags'
    name = _('XML tags mismatch')
    description = _('XML tags in translation do not match source')

    def strip_entities(self, text):
        '''
        Strips all HTML entities (we don't care about them).
        '''
        return XML_ENTITY_MATCH.sub('', text)

    def parse_xml(self, text):
        '''
        Wrapper for parsing XML.
        '''
        text = self.strip_entities(text.encode('utf-8'))
        return cElementTree.fromstring('<weblate>%s</weblate>' % text)

    def check_single(self, source, target, flags, language, unit, cache_slot):
        # Try getting source string data from cache
        source_tags = self.get_cache(unit, cache_slot)

        # Source is not XML
        if source_tags == []:
            return False

        # Do we need to process source (cache miss)
        if source_tags is None:
            # Quick check if source looks like XML
            if not '<' in source or len(XML_MATCH.findall(source)) == 0:
                self.set_cache(unit, [], cache_slot)
                return False
            # Check if source is XML
            try:
                source_tree = self.parse_xml(source)
                source_tags = [x.tag for x in source_tree.iter()]
                self.set_cache(unit, source_tags, cache_slot)
            except:
                # Source is not valid XML, we give up
                self.set_cache(unit, [], cache_slot)
                return False

        # Check target
        try:
            target_tree = self.parse_xml(target)
            target_tags = [x.tag for x in target_tree.iter()]
        except:
            # Target is not valid XML
            return True

        # Compare tags
        return source_tags != target_tags


class OptionalPluralCheck(SourceCheck):
    '''
    Check for not used plural form.
    '''
    check_id = 'optional_plural'
    name = _('Optional plural')
    description = _('The string is optionally used as plural, but not using plural forms')

    def check_source(self, source, flags, unit):
        if len(source) > 1:
            return False
        return len(PLURAL_MATCH.findall(source[0])) > 0


class EllipsisCheck(SourceCheck):
    '''
    Check for using ... instead of …
    '''
    check_id = 'ellipsis'
    name = _('Ellipsis')
    description = _(u'The string uses three dots (...) instead of an ellipsis character (…)')

    def check_source(self, source, flags, unit):
        return '...' in source[0]

# Initialize checks list
CHECKS = {}
for path in getattr(settings, 'CHECK_LIST', DEFAULT_CHECK_LIST):
    i = path.rfind('.')
    module, attr = path[:i], path[i + 1:]
    try:
        mod = __import__(module, {}, {}, [attr])
    except ImportError as e:
        raise ImproperlyConfigured(
            'Error importing translation check module %s: "%s"' %
            (module, e)
        )
    try:
        cls = getattr(mod, attr)
    except AttributeError:
        raise ImproperlyConfigured(
            'Module "%s" does not define a "%s" callable check' %
            (module, attr)
        )
    CHECKS[cls.check_id] = cls()
