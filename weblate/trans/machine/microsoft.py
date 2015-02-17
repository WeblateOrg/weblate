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

from datetime import datetime, timedelta
from weblate.trans.machine.base import (
    MachineTranslation, MachineTranslationError, MissingConfiguration
)
from weblate import appsettings

BASE_URL = 'http://api.microsofttranslator.com/V2/Ajax.svc/'
TRANSLATE_URL = BASE_URL + 'Translate'
LIST_URL = BASE_URL + 'GetLanguagesForTranslate'
TOKEN_EXPIRY = timedelta(minutes=9)


def microsoft_translation_supported():
    '''
    Checks whether service is supported.
    '''
    return (
        appsettings.MT_MICROSOFT_ID is not None and
        appsettings.MT_MICROSOFT_SECRET is not None
    )


class MicrosoftTranslation(MachineTranslation):
    '''
    Microsoft Translator machine translation support.
    '''
    name = 'Microsoft Translator'

    def __init__(self):
        '''
        Checks configuration.
        '''
        super(MicrosoftTranslation, self).__init__()
        self._access_token = None
        self._token_expiry = None
        if not microsoft_translation_supported():
            raise MissingConfiguration(
                'Microsoft Translator requires credentials'
            )

    def is_token_expired(self):
        '''
        Checks whether token is about to expire.
        '''
        return self._token_expiry <= datetime.now()

    @property
    def access_token(self):
        '''
        Obtains and caches access token.
        '''
        if self._access_token is None or self.is_token_expired():
            data = self.json_req(
                'https://datamarket.accesscontrol.windows.net/v2/OAuth2-13',
                skip_auth=True,
                http_post=True,
                client_id=appsettings.MT_MICROSOFT_ID,
                client_secret=appsettings.MT_MICROSOFT_SECRET,
                scope='http://api.microsofttranslator.com',
                grant_type='client_credentials',
            )

            if 'error' in data:
                raise MachineTranslationError(
                    data.get('error', 'Unknown Error') +
                    data.get('error_description', 'No Error Description')
                )

            self._access_token = data['access_token']
            self._token_expiry = datetime.now() + TOKEN_EXPIRY

        return self._access_token

    def authenticate(self, request):
        '''
        Hook for backends to allow add authentication headers to request.
        '''
        request.add_header(
            'Authorization',
            'Bearer %s' % self.access_token
        )

    def convert_language(self, language):
        '''
        Converts language to service specific code.
        '''
        language = language.replace('_', '-').lower()
        if language == 'zh-tw':
            return 'zh-CHT'
        if language == 'zh-cn':
            return 'zh-CHS'
        if language == 'nb':
            return 'no'
        if language == 'pt-br':
            return 'pt'
        return language

    def download_languages(self):
        '''
        Downloads list of supported languages from a service.
        '''
        return self.json_req(LIST_URL)

    def download_translations(self, language, text, unit, user):
        '''
        Downloads list of possible translations from a service.
        '''
        args = {
            'text': text[:5000].encode('utf-8'),
            'from': appsettings.SOURCE_LANGUAGE,
            'to': language,
            'contentType': 'text/plain',
            'category': 'general',
        }
        response = self.json_req(TRANSLATE_URL, **args)
        return [(response, 100, self.name, text)]
