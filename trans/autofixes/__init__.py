# -*- coding: utf-8 -*-
from django.conf import settings

from trans.util import load_class

'''
Import all the autofixes defined in settings.  Note, unlike checks, using
a sortable data object so fixes are applied in desired order.
'''
autofixes = []
for path in getattr(settings, 'AUTOFIX_LIST', {}):
    autofixes.append(load_class(path))


def fix_target(target, unit):
    '''
    Apply each autofix to the target translation.
    '''
    for Fix in autofixes:
        fix = Fix(target, unit)
        target = fix.new_target()
    return target
