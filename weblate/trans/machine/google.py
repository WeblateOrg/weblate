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

from weblate.trans.machine.base import (
    MachineTranslation, MachineTranslationError, MissingConfiguration
)
from weblate import appsettings


# Map old codes used by Google to new ones used by Weblate
LANGUAGE_MAP = {
    'he': 'iw',
    'jv': 'jw',
}


class GoogleTranslation(MachineTranslation):
    '''
    Google Translate API v2 machine translation support.
    '''
    name = 'Google Translate'

    def __init__(self):
        '''
        Checks configuration.
        '''
        super(GoogleTranslation, self).__init__()
        if appsettings.MT_GOOGLE_KEY is None:
            raise MissingConfiguration(
                'Google Translate requires API key'
            )

    def convert_language(self, language):
        '''
        Converts language to service specific code.
        '''
        language = language.replace('_', '-').split('@')[0]

        if language in LANGUAGE_MAP:
            return LANGUAGE_MAP[language]

        return language

    def download_languages(self):
        '''
        List of supported languages.
        '''
        response = self.json_req(
            'https://www.googleapis.com/language/translate/v2/languages',
            key=appsettings.MT_GOOGLE_KEY
        )

        if 'error' in response:
            raise MachineTranslationError(response['error']['message'])

        return [d['language'] for d in response['data']['languages']]

    def download_translations(self, source, language, text, unit, user):
        '''
        Downloads list of possible translations from a service.
        '''
        response = self.json_req(
            'https://www.googleapis.com/language/translate/v2/',
            key=appsettings.MT_GOOGLE_KEY,
            q=text,
            source=source,
            target=language,
        )

        if 'error' in response:
            raise MachineTranslationError(response['error']['message'])

        translation = response['data']['translations'][0]['translatedText']

        return [(translation, 100, self.name, text)]
