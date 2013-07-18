# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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

from django.utils.translation import ugettext_lazy as _
from trans.checks.base import TargetCheck


class PluralsCheck(TargetCheck):
    '''
    Check for incomplete plural forms
    '''
    check_id = 'plurals'
    name = _('Missing plurals')
    description = _('Some plural forms are not translated')

    def check(self, sources, targets, unit):
        # Is this plural?
        if len(sources) == 1:
            return False
        # Is at least something translated?
        if targets == len(targets) * ['']:
            return False
        # Check for empty translation
        return ('' in targets)


class ConsistencyCheck(TargetCheck):
    '''
    Check for inconsistent translations
    '''
    check_id = 'inconsistent'
    name = _('Inconsistent')
    description = _(
        'This message has more than one translation in this project'
    )

    def check(self, sources, targets, unit):
        from trans.models import Unit
        # Do not check consistency if user asked not to have it
        if not unit.translation.subproject.allow_translation_propagation:
            return False
        related = Unit.objects.same(unit).exclude(
            id=unit.id,
            translation__subproject__allow_translation_propagation=False,
        )
        if not unit.translated:
            related = related.filter(translated=True)
        for unit2 in related.iterator():
            if unit2.target != unit.target:
                return True

        return False


class DirectionCheck(TargetCheck):
    '''
    Check for text direction values
    '''
    check_id = 'direction'
    name = _('Invalid text direction')
    description = _('Text direction can be either LTR or RTL')

    def check(self, sources, targets, unit):
        # Is this plural?
        if len(sources) > 1:
            return False
        if not sources[0].lower() in ['ltr', 'rtl']:
            return False
        return targets[0].lower() != unit.translation.language.direction
