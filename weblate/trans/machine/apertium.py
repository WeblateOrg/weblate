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
from weblate import appsettings


class ApertiumTranslation(MachineTranslation):
    '''
    Apertium machine translation support.
    '''
    name = 'Apertium'

    def convert_language(self, language):
        '''
        Converts language to service specific code.
        '''
        return language.replace('_', '-').lower()

    def download_languages(self):
        '''
        Downloads list of supported languages from a service.
        '''
        data = self.json_status_req('http://api.apertium.org/json/listPairs')
        return [item['targetLanguage']
                for item in data['responseData']
                if item['sourceLanguage'] == appsettings.SOURCE_LANGUAGE]

    def download_translations(self, language, text, unit, user):
        '''
        Downloads list of possible translations from Apertium.
        '''
        args = {
            'langpair': '%s|%s' % (appsettings.SOURCE_LANGUAGE, language),
            'q': text.encode('utf-8'),
        }
        if appsettings.MT_APERTIUM_KEY is not None:
            args['key'] = appsettings.MT_APERTIUM_KEY
        response = self.json_status_req(
            'http://api.apertium.org/json/translate',
            **args
        )

        return [(
            response['responseData']['translatedText'],
            100,
            self.name,
            text
        )]
