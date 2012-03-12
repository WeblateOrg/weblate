from django.utils.translation import ugettext_lazy as _

CHECKS = {}

def plural_check(f):
    def _plural_check(sources, targets):
        if f(sources[0], targets[0]):
            return True
        if len(sources) == 1:
            return False
        for t in targets[1:]:
            if f(sources[1], t):
                return True
        return False

    return _plural_check

@plural_check
def check_same(source, target):
    return (source == target)

CHECKS['same'] = (_('Not translated'), check_same, _('Source and translated strings are same'))

@plural_check
def check_newline(source, target):
    if source[0] == '\n' and target[0] != '\n':
        return True
    if source[-1] == '\n' and target[-1] != '\n':
        return True
    return False

CHECKS['newline'] = (_('Newlines'), check_same, _('Source and translated do not both end/begin with newline'))
