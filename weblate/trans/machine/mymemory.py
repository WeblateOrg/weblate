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
        Almost any language without modifiers is supported.
        '''
        if language in ('ia', 'tt', 'ug'):
            return False
        return '@' not in language and len(language) == 2

    def format_match(self, match):
        '''
        Reformats match to (translation, quality) tuple.
        '''
        if type(match['quality']) is int:
            quality = match['quality']
        elif match['quality'] is not None and match['quality'].isdigit():
            quality = int(match['quality'])
        else:
            quality = 0

        if match['last-updated-by'] != '':
            source = '%s (%s)' % (
                self.name,
                match['last-updated-by']
            )
        else:
            source = self.name

        return (
            match['translation'],
            quality * match['match'],
            source,
            match['segment'],
        )

    def download_translations(self, language, text, unit, user):
        '''
        Downloads list of possible translations from MyMemory.
        '''
        args = {
            'q': text.split('. ')[0][:500].encode('utf-8'),
            'langpair': '%s|%s' % (appsettings.SOURCE_LANGUAGE, language),
        }
        if appsettings.MT_MYMEMORY_EMAIL is not None:
            args['de'] = appsettings.MT_MYMEMORY_EMAIL
        if appsettings.MT_MYMEMORY_USER is not None:
            args['user'] = appsettings.MT_MYMEMORY_USER
        if appsettings.MT_MYMEMORY_KEY is not None:
            args['key'] = appsettings.MT_MYMEMORY_KEY

        response = self.json_status_req(
            'http://mymemory.translated.net/api/get',
            **args
        )

        return [self.format_match(match) for match in response['matches']]
