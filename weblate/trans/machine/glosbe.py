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

from __future__ import unicode_literals

from weblate.trans.machine.base import MachineTranslation


class GlosbeTranslation(MachineTranslation):
    '''
    Glosbe machine translation support.
    '''
    name = 'Glosbe'

    def convert_language(self, language):
        '''
        Converts language to service specific code.
        '''
        return language.replace('_', '-').split('-')[0].lower()

    def is_supported(self, source, language):
        '''
        Any language is supported.
        '''
        return True

    def download_translations(self, source, language, text, unit, user):
        '''
        Downloads list of possible translations from a service.
        '''
        params = {
            'from': source,
            'dest': language,
            'format': 'json',
            'phrase': text,
        }
        response = self.json_req(
            'https://glosbe.com/gapi/translate',
            **params
        )

        if 'tuc' not in response:
            return []

        return [(match['phrase']['text'], 100, self.name, text)
                for match in response['tuc']
                if 'phrase' in match and match['phrase'] is not None]
