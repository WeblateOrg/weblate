from django.utils.translation import ugettext_lazy as _

CHECKS = {}

def check_same(sources, targets):
    if sources[0] == targets[0]:
        return True
    return False

CHECKS['same'] = (_('Not translated'), check_same))
