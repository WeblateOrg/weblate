# -*- coding: utf-8 -*-


class AutoFix(object):
    '''
    Base class for AutoFixes
    '''
    def fix_single_target(self, target, unit):
        '''
        Fix a single target, implement this method in subclasses.
        '''
        raise NotImplementedError()

    def fix_target(self, target, unit):
        '''
        Returns a target translation array with a single fix applied.
        '''
        return [self.fix_single_target(t, unit) for t in target]
