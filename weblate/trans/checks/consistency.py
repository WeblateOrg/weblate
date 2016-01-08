# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
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
from weblate.trans.checks.base import TargetCheck


class PluralsCheck(TargetCheck):
    '''
    Check for incomplete plural forms
    '''
    check_id = 'plurals'
    name = _('Missing plurals')
    description = _('Some plural forms are not translated')
    severity = 'danger'

    def check_target_unit(self, sources, targets, unit):
        # Is this plural?
        if len(sources) == 1:
            return False
        # Is at least something translated?
        if targets == len(targets) * ['']:
            return False
        # Check for empty translation
        return '' in targets

    def check_single(self, source, target, unit):
        '''
        We don't check target strings here.
        '''
        return False


class ConsistencyCheck(TargetCheck):
    '''
    Check for inconsistent translations
    '''
    check_id = 'inconsistent'
    name = _('Inconsistent')
    description = _(
        'This message has more than one translation in this project'
    )
    ignore_untranslated = False
    severity = 'warning'

    def check_target_unit(self, sources, targets, unit):
        from weblate.trans.models import Unit
        # Do not check consistency if user asked not to have it
        if not unit.translation.subproject.allow_translation_propagation:
            return False
        related = Unit.objects.same(
            unit
        ).exclude(
            target=unit.target
        ).filter(
            translation__subproject__allow_translation_propagation=True
        )

        if not unit.translated:
            related = related.filter(translated=True)

        return related.exists()

    def check_single(self, source, target, unit):
        '''
        We don't check target strings here.
        '''
        return False
