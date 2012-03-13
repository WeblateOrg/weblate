# -*- coding: UTF-8 -*-
from django.utils.translation import ugettext_lazy as _
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


CHECKS = {}

def plural_check(f):
    '''
    Generic decorator for working with plural translations.
    '''
    def _plural_check(sources, targets, flags, language):
        if f(sources[0], targets[0], flags, language):
            return True
        if len(sources) == 1:
            return False
        for t in targets[1:]:
            if f(sources[1], t, flags, language):
                return True
        return False

    return _plural_check

# Check for not translated entries

@plural_check
def check_same(source, target, flags, language):
    return (source == target)

CHECKS['same'] = (_('Not translated'), check_same, _('Source and translated strings are same'))

def check_chars(source, target, pos, chars):
    '''
    Generic checker for chars presence.
    '''
    if len(target) == 0:
        return False
    s = source[pos]
    t = target[pos]
    return (s in chars and t not in chars) or (s not in chars and t in chars)

# Checks for newlines at beginning/end

@plural_check
def check_begin_newline(source, target, flags, language):
    return check_chars(source, target, 0, ['\n'])

CHECKS['begin_newline'] = (_('Starting newline'), check_begin_newline, _('Source and translated do not both start with newline'))

@plural_check
def check_end_newline(source, target, flags, language):
    return check_chars(source, target, -1, ['\n'])

CHECKS['end_newline'] = (_('Trailing newline'), check_end_newline, _('Source and translated do not both end with newline'))

@plural_check
def check_end_space(source, target, flags, language):
    return check_chars(source, target, -1, [' '])

CHECKS['end_space'] = (_('Trailing space'), check_end_newline, _('Source and translated do not both end with space'))

@plural_check
def check_end_stop(source, target, flags, language):
    return check_chars(source, target, -1, ['.', '。', '।', '۔'])

CHECKS['end_stop'] = (_('Trailing stop'), check_end_newline, _('Source and translated do not both end with full stop'))

@plural_check
def check_end_question(source, target, flags, language):
    return check_chars(source, target, -1, ['?', '՞', '؟', '⸮', '？', '፧', '꘏', '⳺'])

CHECKS['end_question'] = (_('Trailing question'), check_end_question, _('Source and translated do not both end with question mark'))

# For now all format string checks use generic implementation, but
# it should be switched to language specific
def check_format_strings(source, target, regex):
    '''
    Generic checker for format strings.
    '''
    if len(target) == 0:
        return False
    src_matches = set([x[0] for x in regex.findall(source)])
    tgt_matches = set([x[0] for x in regex.findall(target)])

    if src_matches != tgt_matches:
        return True

    return False

# Check for Python format string

@plural_check
def check_python_format(source, target, flags, language):
    if not 'python-format' in flags:
        return False
    return check_format_strings(source, target, PYTHON_PRINTF_MATCH)

CHECKS['python_format'] = (_('Python format'), check_python_format, _('Format string does not match source'))

# Check for PHP format string

@plural_check
def check_php_format(source, target, flags, language):
    if not 'php-format' in flags:
        return False
    return check_format_strings(source, target, PHP_PRINTF_MATCH)

CHECKS['php_format'] = (_('PHP format'), check_php_format, _('Format string does not match source'))

# Check for C format string

@plural_check
def check_c_format(source, target, flags, language):
    if not 'c-format' in flags:
        return False
    return check_format_strings(source, target, C_PRINTF_MATCH)

CHECKS['c_format'] = (_('C format'), check_c_format, _('Format string does not match source'))

# Check for incomplete plural forms

def check_plurals(sources, targets, flags, language):
    # Is this plural?
    if len(sources) == 1:
        return False
    # Is at least something translated?
    if targets == len(targets) * ['']:
        return False
    # Check for empty translation
    return ('' in targets)

CHECKS['plurals'] = (_('Missing plurals'), check_c_format, _('Some plural forms are not translated'))
