# -*- coding: utf-8 -*-


class AutoFix(object):
    '''
    basic class for AutoFixes
    '''
    def __init__(self, target, unit):
        '''
        may need to extend this to support multiple targets and sources
        '''
        self.unit = unit
        self.target = target
        self.source = unit.source

    def fix_target(self, single_target):
        '''
        fix a single target, implement this method with subclasses
        '''
        raise NotImplementedError()

    def new_target(self):
        '''
        returns a target translation array with a single fix applied
        '''
        return [self.fix_target(t) for t in self.target]
