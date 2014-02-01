# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2014 Michal Čihař <michal@cihar.com>
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
import urllib

from weblate import appsettings


class OpenTranTranslation(MachineTranslation):
    '''
    Open-Tran machine translation support.
    '''
    name = 'Open-Tran'

    def convert_language(self, language):
        '''
        Converts language to service specific code.
        '''
        return language.replace('-', '_').replace('@', '_').lower()

    def download_languages(self):
        '''
        Downloads list of supported languages from a service.
        '''
        return self.json_req('http://open-tran.eu/json/supported')

    def format_match(self, match):
        '''
        Reformats match to (translation, quality) tuple.
        '''
        return (
            match['text'],
            100 - (match['value']) * 20,
            '%s (%s)' % (self.name, match['projects'][0]['name']),
            match['projects'][0]['orig_phrase'],
        )

    def download_translations(self, language, text, unit, user):
        '''
        Downloads list of possible translations from a service.
        '''
        response = self.json_req(
            'http://%s.%s.open-tran.eu/json/suggest/%s' % (
                appsettings.SOURCE_LANGUAGE,
                language,
                urllib.quote(text.encode('utf-8'))
            )
        )

        return [self.format_match(match)
                for match in response
                if match['value'] <= 4]
