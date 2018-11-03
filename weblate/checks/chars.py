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

from django.utils.translation import ugettext_lazy as _

from weblate.checks.base import (
    TargetCheck, TargetCheckWithFlag, CountingCheck
)


class BeginNewlineCheck(TargetCheck):
    """Check for newlines at beginning."""
    check_id = 'begin_newline'
    name = _('Starting newline')
    description = _('Source and translation do not both start with a newline')
    severity = 'warning'

    def check_single(self, source, target, unit):
        return self.check_chars(source, target, 0, ['\n'])


class EndNewlineCheck(TargetCheck):
    """Check for newlines at end."""
    check_id = 'end_newline'
    name = _('Trailing newline')
    description = _('Source and translation do not both end with a newline')
    severity = 'warning'

    def check_single(self, source, target, unit):
        return self.check_chars(source, target, -1, ['\n'])


class BeginSpaceCheck(TargetCheck):
    """Whitespace check, starting whitespace usually is important for UI"""
    check_id = 'begin_space'
    name = _('Starting spaces')
    description = _(
        'Source and translation do not both start with same number of spaces'
    )
    severity = 'warning'

    def check_single(self, source, target, unit):
        # One letter things are usually decimal/thousand separators
        if len(source) <= 1 and len(target) <= 1:
            return False

        stripped_target = target.lstrip(' ')
        stripped_source = source.lstrip(' ')

        # String translated to spaces only
        if not stripped_target:
            return False

        # Count space chars in source and target
        source_space = len(source) - len(stripped_source)
        target_space = len(target) - len(stripped_target)

        # Compare numbers
        return source_space != target_space


class EndSpaceCheck(TargetCheck):
    """Whitespace check"""
    check_id = 'end_space'
    name = _('Trailing space')
    description = _('Source and translation do not both end with a space')
    severity = 'warning'

    def check_single(self, source, target, unit):
        # One letter things are usually decimal/thousand separators
        if len(source) <= 1 and len(target) <= 1:
            return False
        if not source or not target:
            return False
        if (self.is_language(unit, ('fr', 'br')) and
                source[-1] in [':', '!', '?'] and target[-1] == ' '):
            return False

        stripped_target = target.rstrip(' ')
        stripped_source = source.rstrip(' ')

        # String translated to spaces only
        if not stripped_target:
            return False

        # Count space chars in source and target
        source_space = len(source) - len(stripped_source)
        target_space = len(target) - len(stripped_target)

        # Compare numbers
        return source_space != target_space


class EndStopCheck(TargetCheck):
    """Check for final stop"""
    check_id = 'end_stop'
    name = _('Trailing stop')
    description = _('Source and translation do not both end with a full stop')
    severity = 'warning'

    def check_single(self, source, target, unit):
        if len(source) <= 4:
            # Might need to use shortcut in translation
            return False
        if not target:
            return False
        # Thai does not have a full stop
        if self.is_language(unit, ('th', )):
            return False
        # Allow ... to be translated into ellipsis
        if source.endswith('...') and target[-1] == '…':
            return False
        if self.is_language(unit, ('ja', )) and source[-1] in (':', ';'):
            # Japanese sentence might need to end with full stop
            # in case it's used before list.
            return self.check_chars(
                source, target, -1, (';', ':', '：', '.', '。')
            )
        if self.is_language(unit, ('hy', )):
            return self.check_chars(
                source, target, -1,
                (
                    '.', '。', '।', '۔', '։', '·',
                    '෴', '។', ':', '՝', '?', '!', '`',
                )
            )
        if self.is_language(unit, ('hi', 'bn')):
            # Using | instead of । is not typographically correct, but
            # seems to be quite usual
            return self.check_chars(
                source, target, -1, ('.', '।', '|')
            )
        return self.check_chars(
            source, target, -1,
            ('.', '。', '।', '۔', '։', '·', '෴', '។')
        )


class EndColonCheck(TargetCheck):
    """Check for final colon"""
    check_id = 'end_colon'
    name = _('Trailing colon')
    description = _(
        'Source and translation do not both end with a colon '
        'or colon is not correctly spaced'
    )
    colon_fr = (
        ' :', ' : ',
        '&nbsp;:', '&nbsp;: ',
        '\u00A0:', '\u00A0: ',
        '\u202F:' '\u202F: '
    )
    severity = 'warning'

    def _check_fr(self, source, target):
        if source[-1] != ':':
            return False
        return not self.check_ends(target, self.colon_fr)

    def _check_hy(self, source, target):
        if source[-1] == ':':
            return self.check_chars(
                source,
                target,
                -1,
                (':', '՝', '`')
            )
        return False

    def _check_ja(self, source, target):
        # Japanese sentence might need to end with full stop
        # in case it's used before list.
        if source[-1] in (':', ';'):
            return self.check_chars(
                source,
                target,
                -1,
                (';', ':', '：', '.', '。')
            )
        return False

    def check_single(self, source, target, unit):
        if not source or not target:
            return False
        if self.is_language(unit, ('fr', 'br')):
            return self._check_fr(source, target)
        if self.is_language(unit, ('hy', )):
            return self._check_hy(source, target)
        if self.is_language(unit, ('ja', )):
            return self._check_ja(source, target)
        return self.check_chars(source, target, -1, (':', '：', '៖'))


class EndQuestionCheck(TargetCheck):
    """Check for final question mark"""
    check_id = 'end_question'
    name = _('Trailing question')
    description = _(
        'Source and translation do not both end with a question mark '
        'or it is not correctly spaced'
    )
    question_fr = (
        ' ?', ' ? ',
        '&nbsp;?', '&nbsp;? ',
        '\u00A0?', '\u00A0? ',
        '\u202F?', '\u202F? '
    )
    question_el = ('?', ';', ';')
    severity = 'warning'

    def _check_fr(self, source, target):
        if source[-1] != '?':
            return False
        return not self.check_ends(target, self.question_fr)

    def _check_hy(self, source, target):
        if source[-1] == '?':
            return self.check_chars(
                source,
                target,
                -1,
                ('?', '՞', '։')
            )
        return False

    def _check_el(self, source, target):
        if source[-1] != '?':
            return False
        return target[-1] not in self.question_el

    def check_single(self, source, target, unit):
        if not source or not target:
            return False
        if self.is_language(unit, ('fr', 'br')):
            return self._check_fr(source, target)
        if self.is_language(unit, ('hy', )):
            return self._check_hy(source, target)
        if self.is_language(unit, ('el', )):
            return self._check_el(source, target)

        return self.check_chars(
            source,
            target,
            -1,
            ('?', '՞', '؟', '⸮', '？', '፧', '꘏', '⳺')
        )


class EndExclamationCheck(TargetCheck):
    """Check for final exclamation mark"""
    check_id = 'end_exclamation'
    name = _('Trailing exclamation')
    description = _(
        'Source and translation do not both end with an exclamation mark '
        'or it is not correctly spaced'
    )
    exclamation_fr = (
        ' !', ' ! ',
        '&nbsp;!', '&nbsp;! ',
        '\u00A0!', '\u00A0! ',
        '\u202F!', '\u202F! ',
    )
    severity = 'warning'

    def _check_fr(self, source, target):
        if source[-1] != '!':
            return False
        return not self.check_ends(target, self.exclamation_fr)

    def check_single(self, source, target, unit):
        if not source or not target:
            return False
        if (self.is_language(unit, ('eu', )) and source[-1] == '!' and
                '¡' in target and '!' in target):
            return False
        if self.is_language(unit, ('hy', )):
            return False
        if self.is_language(unit, ('fr', 'br')):
            return self._check_fr(source, target)
        if source.endswith('Texy!') or target.endswith('Texy!'):
            return False
        return self.check_chars(
            source,
            target,
            -1,
            ('!', '！', '՜', '᥄', '႟', '߹')
        )


class EndEllipsisCheck(TargetCheck):
    """Check for ellipsis at the end of string."""
    check_id = 'end_ellipsis'
    name = _('Trailing ellipsis')
    description = _('Source and translation do not both end with an ellipsis')
    severity = 'warning'

    def check_single(self, source, target, unit):
        if not target:
            return False
        # Allow ... to be translated into ellipsis
        if source.endswith('...') and target[-1] == '…':
            return False
        return self.check_chars(source, target, -1, ('…', ))


class NewlineCountingCheck(CountingCheck):
    """Check whether there is same amount of \n strings"""
    string = '\\n'
    check_id = 'escaped_newline'
    name = _('Mismatched \\n')
    description = _('Number of \\n in translation does not match source')
    severity = 'warning'


class ZeroWidthSpaceCheck(TargetCheck):
    """Check for zero width space char (<U+200B>)."""
    check_id = 'zero-width-space'
    name = _('Zero-width space')
    description = _('Translation contains extra zero-width space character')
    severity = 'warning'

    def check_single(self, source, target, unit):
        if self.is_language(unit, ('km', )):
            return False
        return ('\u200b' in target) != ('\u200b' in source)


class MaxLengthCheck(TargetCheckWithFlag):
    """Check for maximum length of translation."""
    check_id = 'max-length'
    name = _('Maximum length of translation')
    description = _('Translation should not exceed given length')
    severity = 'danger'
    default_disabled = True

    FLAGS_PAIR_RE = re.compile(r'\b([-\w]+):(\w+)\b')

    def check_target_unit_with_flag(self, sources, targets, unit):
        check_pair = set(self.FLAGS_PAIR_RE.findall('\n'.join(unit.all_flags)))
        if check_pair:
            check_value = max(
                {(x) for x in check_pair if x[0] == self.check_id},
                key=lambda v: int(v[1])
            )[1]
            return len(targets[0]) > int(check_value)
        return False


class EndSemicolonCheck(TargetCheck):
    """Check for semicolon at end."""
    check_id = 'end_semicolon'
    name = _('Trailing semicolon')
    description = _('Source and translation do not both end with a semicolon')
    severity = 'warning'

    def check_single(self, source, target, unit):
        if self.is_language(unit, ('el', )) and source and source[-1] == '?':
            # Complement to question mark check
            return False
        return self.check_chars(source, target, -1, [';'])
