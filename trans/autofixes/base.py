# -*- coding: utf-8 -*-


class AutoFix(object):
    '''
    basic class for AutoFixes
    '''
    def fix_single_target(self, target, unit):
        '''
        fix a single target, implement this method with subclasses
        '''
        raise NotImplementedError()

    def fix_target(self, target, unit):
        '''
        returns a target translation array with a single fix applied
        '''
        return [self.fix_single_target(t, unit) for t in target]
