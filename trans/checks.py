from django.utils.translation import ugettext_lazy as _

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
