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

from weblate.trans.machine.base import (
    MachineTranslation, MissingConfiguration
)
import urllib

from weblate import appsettings


class TMServerTranslation(MachineTranslation):
    '''
    tmserver machine translation support.
    '''
    name = 'tmserver'

    def __init__(self):
        '''
        Checks configuration.
        '''
        super(TMServerTranslation, self).__init__()
        self.url = self.get_server_url()

    def get_server_url(self):
        '''
        Returns URL of a server.
        '''
        if appsettings.MT_TMSERVER is None:
            raise MissingConfiguration(
                'Not configured tmserver URL'
            )

        return appsettings.MT_TMSERVER.rstrip('/')

    def convert_language(self, language):
        '''
        Converts language to service specific code.
        '''
        return language.replace('-', '_').lower()

    def is_supported(self, language):
        '''
        Any language is supported.
        '''
        return True

    def download_translations(self, language, text, unit, user):
        '''
        Downloads list of possible translations from a service.
        '''
        url = '%s/tmserver/%s/%s/unit/%s' % (
            self.url,
            urllib.quote(appsettings.SOURCE_LANGUAGE),
            urllib.quote(language),
            urllib.quote(text[:500].encode('utf-8').replace('\r', ' ')),
        )
        response = self.json_req(url)

        return [(line['target'], line['quality'], self.name, line['source'])
                for line in response]


class AmagamaTranslation(TMServerTranslation):
    '''
    Specific instance of tmserver ran by Virtaal authors.
    '''
    name = 'Amagama'

    def get_server_url(self):
        return 'http://amagama.locamotion.org'
