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

from trans.machine.base import MachineTranslation


class MyMemoryTranslation(MachineTranslation):
    '''
    MyMemory machine translation support.
    '''
    name = 'MyMemory'

    def convert_language(self, language):
        '''
        Converts language to service specific code.
        '''
        return language.replace('_', '-').lower()

    def is_supported(self, language):
        '''
        Any language is supported.
        '''
        return True

    def format_match(self, match):
        '''
        Reformats match to (translation, quality) tuple.
        '''
        if match['quality'].isdigit():
            quality = int(match['quality'])
        else:
            quality = 0

        return (
            match['translation'],
            quality * match['match']
        )

    def download_translations(self, language, text):
        '''
        Downloads list of possible translations from a service.
        '''
        response = self.json_status_req(
            'http://mymemory.translated.net/api/get',
            q=text,
            langpair='en|%s' % language,
        )

        return [self.format_match(match) for match in response['matches']]
