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

from weblate.trans.machine.base import MachineTranslation
from weblate.trans.models.unit import Unit


def format_unit_match(unit, quality):
    '''
    Formats unit to translation service result.
    '''
    return (
        unit.get_target_plurals()[0],
        quality,
        'Weblate (%s)' % unicode(unit.translation.subproject),
        unit.get_source_plurals()[0],
    )


class WeblateTranslation(MachineTranslation):
    '''
    Translation service using strings already translated in Weblate.
    '''
    name = 'Weblate'

    def convert_language(self, language):
        '''
        Converts language to service specific code.
        '''
        return language

    def is_supported(self, language):
        '''
        Any language is supported.
        '''
        return True

    def download_translations(self, language, text, unit, user):
        '''
        Downloads list of possible translations from a service.
        '''
        matching_units = Unit.objects.same_source(unit)

        return [
            format_unit_match(munit, 100)
            for munit in matching_units
            if munit.has_acl(user)
        ]


class WeblateSimilarTranslation(MachineTranslation):
    '''
    Translation service using strings already translated in Weblate.
    '''
    name = 'Weblate similarity'

    def convert_language(self, language):
        '''
        Converts language to service specific code.
        '''
        return language

    def is_supported(self, language):
        '''
        Any language is supported.
        '''
        return True

    def download_translations(self, language, text, unit, user):
        '''
        Downloads list of possible translations from a service.
        '''
        matching_units = Unit.objects.more_like_this(unit)

        return [
            format_unit_match(munit, 50)
            for munit in matching_units
            if munit.has_acl(user)
        ]
