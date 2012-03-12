from django.utils.translation import ugettext_lazy as _
import re

PRINTF_MATCH = re.compile('''
        %(                          # initial %
              (?:(?P<ord>\d+)\$|    # variable order, like %1$s
              \((?P<key>\w+)\))?    # Python style variables, like %(var)s
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
    def _plural_check(sources, targets, flags):
        if f(sources[0], targets[0], flags):
            return True
        if len(sources) == 1:
            return False
        for t in targets[1:]:
            if f(sources[1], t, flags):
                return True
        return False

    return _plural_check

# Check for not translated entries

@plural_check
def check_same(source, target, flags):
    return (source == target)

CHECKS['same'] = (_('Not translated'), check_same, _('Source and translated strings are same'))

# Checks for newlines at beginning/end

def check_newline(source, target, pos):
    if len(target) == 0:
        return False
    s = source[pos]
    t = target[pos]
    return (s == '\n' and t != '\n') or (s != '\n' and t == '\n')

@plural_check
def check_begin_newline(source, target, flags):
    return check_newline(source, target, 0)

CHECKS['begin_newline'] = (_('Starting newline'), check_begin_newline, _('Source and translated do not both start with newline'))

@plural_check
def check_end_newline(source, target, flags):
    return check_newline(source, target, -1)

CHECKS['end_newline'] = (_('Trailing newline'), check_end_newline, _('Source and translated do not both end with newline'))

# For now all format string checks use generic implementation, but
# it should be switched to language specific
def check_format_strings(source, target):
    '''
    Generic checker for format strings.
    '''
    src_matches = set([x[0] for x in PRINTF_MATCH.findall(source)])
    tgt_matches = set([x[0] for x in PRINTF_MATCH.findall(target)])

    if src_matches != tgt_matches:
        return True

    return False

# Check for Python format string

@plural_check
def check_python_format(source, target, flags):
    if not 'python-format' in flags:
        return False
    return check_format_strings(source, target)

CHECKS['python_format'] = (_('Python format'), check_python_format, _('Format string does not match source'))

# Check for PHP format string

@plural_check
def check_php_format(source, target, flags):
    if not 'php-format' in flags:
        return False
    return check_format_strings(source, target)

CHECKS['php_format'] = (_('PHP format'), check_php_format, _('Format string does not match source'))

# Check for C format string

@plural_check
def check_c_format(source, target, flags):
    if not 'c-format' in flags:
        return False
    return check_format_strings(source, target)

CHECKS['c_format'] = (_('C format'), check_c_format, _('Format string does not match source'))
