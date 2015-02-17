# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.core.cache import cache
import weblate


class Check(object):
    '''
    Basic class for checks.
    '''
    check_id = ''
    name = ''
    description = ''
    target = False
    source = False
    ignore_untranslated = True
    severity = 'info'

    def __init__(self):
        id_dash = self.check_id.replace('_', '-')
        self.doc_id = 'check-%s' % id_dash
        self.ignore_string = 'ignore-%s' % id_dash

    def check_target(self, sources, targets, unit):
        '''
        Checks target strings.
        '''
        # Is this check ignored
        if self.ignore_string in unit.all_flags:
            return False
        # No checking of not translated units
        if self.ignore_untranslated and not unit.translated:
            return False
        return self.check_target_unit(sources, targets, unit)

    def check_target_unit(self, sources, targets, unit):
        '''
        Checks single unit, handling plurals.
        '''
        # Check singular
        if self.check_single(sources[0], targets[0], unit, 0):
            return True
        # Do we have more to check?
        if len(sources) == 1:
            return False
        # Check plurals against plural from source
        for target in targets[1:]:
            if self.check_single(sources[1], target, unit, 1):
                return True
        # Check did not fire
        return False

    def check_single(self, source, target, unit, cache_slot):
        '''
        Check for single phrase, not dealing with plurals.
        '''
        raise NotImplementedError()

    def check_source(self, source, unit):
        '''
        Checks source string
        '''
        raise NotImplementedError()

    def check_chars(self, source, target, pos, chars):
        '''
        Generic checker for chars presence.
        '''
        try:
            src = source[pos]
            tgt = target[pos]
        except IndexError:
            return False
        return (
            (src in chars and tgt not in chars) or
            (src not in chars and tgt in chars)
        )

    def is_language(self, unit, vals):
        '''
        Detects whether language is in given list, ignores language
        variants.
        '''
        return unit.translation.language.code.split('_')[0] in vals

    def get_doc_url(self):
        '''
        Returns link to documentation.
        '''
        return weblate.get_doc_url('user/checks', self.doc_id)

    def get_cache_key(self, unit, cache_slot=0):
        '''
        Generates key for a cache.
        '''
        return 'check-%s-%d-%s-%d' % (
            self.check_id,
            unit.translation.subproject.project.id,
            unit.checksum,
            cache_slot
        )

    def get_cache(self, unit, cache_slot=0):
        '''
        Returns cached result.
        '''
        return cache.get(self.get_cache_key(unit, cache_slot))

    def set_cache(self, unit, value, cache_slot=0):
        '''
        Sets cache.
        '''
        return cache.set(self.get_cache_key(unit, cache_slot), value)


class TargetCheck(Check):
    '''
    Basic class for target checks.
    '''
    target = True

    def check_source(self, source, unit):
        '''
        We don't check source strings here.
        '''
        return False

    def check_single(self, source, target, unit, cache_slot):
        '''
        Check for single phrase, not dealing with plurals.
        '''
        raise NotImplementedError()


class SourceCheck(Check):
    '''
    Basic class for source checks.
    '''
    source = True

    def check_single(self, source, target, unit, cache_slot):
        '''
        We don't check target strings here.
        '''
        return False

    def check_source(self, source, unit):
        '''
        Checks source string
        '''
        raise NotImplementedError()


class CountingCheck(TargetCheck):
    '''
    Check whether there is same count of given string.
    '''
    string = None

    def check_single(self, source, target, unit, cache_slot):
        if len(target) == 0 or len(source) == 0:
            return False
        return source.count(self.string) != target.count(self.string)
