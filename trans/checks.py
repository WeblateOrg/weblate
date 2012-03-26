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
            (?P<type>[\w]))         # type (%s, %d, etc.)
        )''', re.VERBOSE)


PHP_PRINTF_MATCH = re.compile('''
        %(                          # initial %
              (?:(?P<ord>\d+)\$)?   # variable order, like %1$s
        (?P<fullvar>
            [+#-]*                  # flags
            (?:\d+)?                # width
            (?:\.\d+)?              # precision
            (hh\|h\|l\|ll)?         # length formatting
            (?P<type>[\w]))         # type (%s, %d, etc.)
        )''', re.VERBOSE)


C_PRINTF_MATCH = re.compile('''
        %(                          # initial %
        (?P<fullvar>
            [+#-]*                  # flags
            (?:\d+)?                # width
            (?:\.\d+)?              # precision
            (hh\|h\|l\|ll)?         # length formatting
            (?P<type>[\w]))         # type (%s, %d, etc.)
        )''', re.VERBOSE)

# We ignore some words which are usually not translated
SAME_BLACKLIST = frozenset((
    'b',
    'bluetooth',
    'bzip2',
    'csv',
    'cvs',
    'data',
    'e-mail',
    'eib',
    'esperanto',
    'export',
    'firmware',
    'fulltext',
    'gib',
    'git',
    'gzip',
    'id',
    'irc',
    'irda',
    'imei',
    'import',
    'kib',
    'latex',
    'mib',
    'n/a',
    'ok',
    'open document',
    'pdf',
    'pib',
    'port',
    'rss',
    'server',
    'sim',
    'smsc',
    'software',
    'sql',
    'text',
    'tib',
    'vcalendar',
    'vcard',
    'wiki',
    'xml',
    'zip',
    ))

CHECKS = {}

def plural_check(f):
    '''
    Generic decorator for working with plural translations.
    '''
    def _plural_check(sources, targets, flags, language, unit):
        if f(sources[0], targets[0], flags, language, unit):
            return True
        if len(sources) == 1:
            return False
        for t in targets[1:]:
            if f(sources[1], t, flags, language, unit):
                return True
        return False

    return _plural_check

# Check for not translated entries

@plural_check
def check_same(source, target, flags, language, unit):
    if language.code.split('_')[0] == 'en':
        return False
    if source.lower() in SAME_BLACKLIST or source.lower().rstrip(': ') in SAME_BLACKLIST:
        return False
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
def check_begin_newline(source, target, flags, language, unit):
    return check_chars(source, target, 0, ['\n'])

CHECKS['begin_newline'] = (_('Starting newline'), check_begin_newline, _('Source and translated do not both start with a newline'))

@plural_check
def check_end_newline(source, target, flags, language, unit):
    return check_chars(source, target, -1, ['\n'])

CHECKS['end_newline'] = (_('Trailing newline'), check_end_newline, _('Source and translated do not both end with a newline'))

# Whitespace check

@plural_check
def check_end_space(source, target, flags, language, unit):
    if language.code.split('_')[0] in ['fr', 'br']:
        if len(target) == 0:
            return False
        if source[-1] in [':', '!', '?'] and target[-1] == ' ':
            return False
    return check_chars(source, target, -1, [' '])

CHECKS['end_space'] = (_('Trailing space'), check_end_space, _('Source and translated do not both end with a space'))

# Check for punctation

@plural_check
def check_end_stop(source, target, flags, language, unit):
    return check_chars(source, target, -1, [u'.', u'。', u'।', u'۔'])

CHECKS['end_stop'] = (_('Trailing stop'), check_end_stop, _('Source and translated do not both end with a full stop'))

@plural_check
def check_end_colon(source, target, flags, language, unit):
    if language.code.split('_')[0] in ['fr', 'br']:
        if len(target) == 0:
            return False
        if source[-1] == ':':
            if target[-3:] not in [' : ', '&nbsp;: ', u' : ']:
                return True
        return False
    return check_chars(source, target, -1, [u':', u'：'])

CHECKS['end_colon'] = (_('Trailing colon'), check_end_colon, _('Source and translated do not both end with a colon or colon is not correctly spaced'))

@plural_check
def check_end_question(source, target, flags, language, unit):
    if language.code.split('_')[0] in ['fr', 'br']:
        if len(target) == 0:
            return False
        if source[-1] == '?':
            if target[-2:] not in [' ?', '&nbsp;?', u' ?']:
                return True
        return False
    return check_chars(source, target, -1, [u'?', u'՞', u'؟', u'⸮', u'？', u'፧', u'꘏', u'⳺'])

CHECKS['end_question'] = (_('Trailing question'), check_end_question, _('Source and translated do not both end with a question mark or it is not correctly spaced'))

@plural_check
def check_end_exclamation(source, target, flags, language, unit):
    if language.code.split('_')[0] in ['fr', 'br']:
        if len(target) == 0:
            return False
        if source[-1] == '!':
            if target[-2:] not in [' !', '&nbsp;!', u' !']:
                return True
        return False
    return check_chars(source, target, -1, [u'!', u'！', u'՜', u'᥄', u'႟', u'߹'])

CHECKS['end_exclamation'] = (_('Trailing exclamation'), check_end_exclamation, _('Source and translated do not both end with an exclamation mark or it is not correctly spaced'))

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
def check_python_format(source, target, flags, language, unit):
    if not 'python-format' in flags:
        return False
    return check_format_strings(source, target, PYTHON_PRINTF_MATCH)

CHECKS['python_format'] = (_('Python format'), check_python_format, _('Format string does not match source'))

# Check for PHP format string

@plural_check
def check_php_format(source, target, flags, language, unit):
    if not 'php-format' in flags:
        return False
    return check_format_strings(source, target, PHP_PRINTF_MATCH)

CHECKS['php_format'] = (_('PHP format'), check_php_format, _('Format string does not match source'))

# Check for C format string

@plural_check
def check_c_format(source, target, flags, language, unit):
    if not 'c-format' in flags:
        return False
    return check_format_strings(source, target, C_PRINTF_MATCH)

CHECKS['c_format'] = (_('C format'), check_c_format, _('Format string does not match source'))

# Check for incomplete plural forms

def check_plurals(sources, targets, flags, language, unit):
    # Is this plural?
    if len(sources) == 1:
        return False
    # Is at least something translated?
    if targets == len(targets) * ['']:
        return False
    # Check for empty translation
    return ('' in targets)

CHECKS['plurals'] = (_('Missing plurals'), check_c_format, _('Some plural forms are not translated'))

# Check for inconsistent translations

def check_consistency(sources, targets, flags, language, unit):
    from trans.models import Unit
    related = Unit.objects.filter(
        translation__language = language,
        translation__subproject__project = unit.translation.subproject.project,
        checksum = unit.checksum
        ).exclude(
        id = unit.id
        )
    for unit2 in related.iterator():
        if unit2.target != unit.target:
            return True

    return False

CHECKS['inconsistent'] = (_('Inconsistent'), check_consistency, _('Message has more different translations in this project'))
