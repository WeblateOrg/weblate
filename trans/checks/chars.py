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
from trans.checks.base import TargetCheck, CountingCheck


class BeginNewlineCheck(TargetCheck):
    '''
    Checks for newlines at beginning.
    '''
    check_id = 'begin_newline'
    name = _('Starting newline')
    description = _('Source and translation do not both start with a newline')

    def check_single(self, source, target, unit, cache_slot):
        return self.check_chars(source, target, 0, ['\n'])


class EndNewlineCheck(TargetCheck):
    '''
    Checks for newlines at end.
    '''
    check_id = 'end_newline'
    name = _('Trailing newline')
    description = _('Source and translation do not both end with a newline')

    def check_single(self, source, target, unit, cache_slot):
        return self.check_chars(source, target, -1, ['\n'])


class BeginSpaceCheck(TargetCheck):
    '''
    Whitespace check, starting whitespace usually is important for UI
    '''
    check_id = 'begin_space'
    name = _('Starting spaces')
    description = _(
        'Source and translation do not both start with same number of spaces'
    )

    def check_single(self, source, target, unit, cache_slot):
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

    def check_single(self, source, target, unit, cache_slot):
        # One letter things are usually decimal/thousand separators
        if len(source) <= 1 and len(target) <= 1:
            return False
        if not source or not target:
                return False
        if self.is_language(unit, ['fr', 'br']):
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

    def check_single(self, source, target, unit, cache_slot):
        if len(source) <= 4 and len(target) <= 4:
            return False
        if not source:
            return False
        if self.is_language(unit, ['ja']) and source[-1] in [':', ';']:
            # Japanese sentence might need to end with full stop
            # in case it's used before list.
            return self.check_chars(
                source, target, -1, [u':', u'：', u'.', u'。']
            )
        if self.is_language(unit, ['hi']):
            # Using | instead of । is not typographically correct, but
            # seems to be quite usual
            return self.check_chars(
                source, target, -1, [u'.', u'।', u'|']
            )
        return self.check_chars(
            source, target, -1, [u'.', u'。', u'।', u'۔', u'։', u'·']
        )


class EndColonCheck(TargetCheck):
    '''
    Check for final colon
    '''
    check_id = 'end_colon'
    name = _('Trailing colon')
    description = _(
        'Source and translation do not both end with a colon '
        'or colon is not correctly spaced'
    )
    colon_fr = (' :', '&nbsp;:', u' :')

    def check_single(self, source, target, unit, cache_slot):
        if not source or not target:
            return False
        if self.is_language(unit, ['fr', 'br']):
            if source[-1] == ':':
                # Accept variant with trailing space as well
                if target[-1] == ' ':
                    check_string = target[-3:-1]
                else:
                    check_string = target[-2:]
                if check_string not in self.colon_fr:
                    return True
            return False
        if self.is_language(unit, ['ja']):
            # Japanese sentence might need to end with full stop
            # in case it's used before list.
            if source[-1] in [':', ';']:
                return self.check_chars(
                    source,
                    target,
                    -1,
                    [u':', u'：', u'.', u'。']
                )
            return False
        return self.check_chars(source, target, -1, [u':', u'：'])


class EndQuestionCheck(TargetCheck):
    '''
    Check for final question mark
    '''
    check_id = 'end_question'
    name = _('Trailing question')
    description = _(
        'Source and translation do not both end with a question mark '
        'or it is not correctly spaced'
    )
    question_fr = (' ?', ' ? ', '&nbsp;? ', '&nbsp;?', u' ?', u' ? ')
    question_el = ('?', ';', ';')

    def check_single(self, source, target, unit, cache_slot):
        if not source or not target:
            return False
        if self.is_language(unit, ['fr', 'br']):
            if source[-1] != '?':
                return False
            return target[-2:] not in self.question_fr

        if self.is_language(unit, ['el']):
            if source[-1] != '?':
                return False
            return target[-1] not in self.question_el

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
    description = _(
        'Source and translation do not both end with an exclamation mark '
        'or it is not correctly spaced'
    )
    exclamation_fr = (' !', '&nbsp;!', u' !', ' ! ', '&nbsp;! ', u' ! ')

    def check_single(self, source, target, unit, cache_slot):
        if not source or not target:
            return False
        if self.is_language(unit, ['eu']):
            if source[-1] == '!':
                if u'¡' in target and u'!' in target:
                    return False
        if self.is_language(unit, ['fr', 'br']):
            if source[-1] == '!':
                if target[-2:] not in self.exclamation_fr:
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

    def check_single(self, source, target, unit, cache_slot):
        if not target:
            return False
        # Allow ... to be translated into ellipsis
        if source.endswith('...') and target[-1] == u'…':
            return False
        return self.check_chars(source, target, -1, [u'…'])


class NewlineCountingCheck(CountingCheck):
    '''
    Check whether there is same amount of \n strings
    '''
    string = '\\n'
    check_id = 'escaped_newline'
    name = _('Mismatched \\n')
    description = _('Number of \\n in translation does not match source')


class ZeroWidthSpaceCheck(TargetCheck):
    '''
    Check for zero width space char (<U+200B>).
    '''
    check_id = 'zero-width-space'
    name = _('Zero-width space')
    description = _('Translation contains extra zero-width space character')

    def check_single(self, source, target, unit, cache_slot):
        return (u'\u200b' in target) != (u'\u200b' in source)
