# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

import six

from weblate.machinery.base import MachineTranslation, MissingConfiguration

COGNITIVE_BASE_URL = 'https://api.cognitive.microsoft.com/sts/v1.0'
COGNITIVE_TOKEN = COGNITIVE_BASE_URL + '/issueToken?Subscription-Key={0}'

BASE_URL = 'https://api.microsofttranslator.com/V2/Ajax.svc/'
TRANSLATE_URL = BASE_URL + 'Translate'
LIST_URL = BASE_URL + 'GetLanguagesForTranslate'
TOKEN_EXPIRY = timedelta(minutes=9)


class MicrosoftCognitiveTranslation(MachineTranslation):
    """Microsoft Cognitive Services Translator API support."""
    name = 'Microsoft Translator'

    language_map = {
        'zh-hant': 'zh-CHT',
        'zh-hans': 'zh-CHS',
        'zh-tw': 'zh-CHT',
        'zh-cn': 'zh-CHS',
        'tlh-qaak': 'tlh-Qaak',
        'nb': 'no',
        'bs-latn': 'bs-Latn',
        'sr-latn': 'sr-Latn',
        'sr-cyrl': 'sr-Cyrl',
    }

    def __init__(self):
        """Check configuration."""
        super(MicrosoftCognitiveTranslation, self).__init__()
        self._access_token = None
        self._token_expiry = None
        if settings.MT_MICROSOFT_COGNITIVE_KEY is None:
            raise MissingConfiguration(
                'Microsoft Translator requires credentials'
            )

    def is_token_expired(self):
        """Check whether token is about to expire."""
        return self._token_expiry <= timezone.now()

    def authenticate(self, request):
        """Hook for backends to allow add authentication headers to request."""
        request.add_header(
           'Authorization',
           'Bearer {0}'.format(self.access_token)
       )

    @property
    def access_token(self):
        """Obtain and caches access token."""
        if self._access_token is None or self.is_token_expired():
            self._access_token = self.json_req(
                COGNITIVE_TOKEN.format(settings.MT_MICROSOFT_COGNITIVE_KEY),
                skip_auth=True,
                http_post=True,
                raw=True,
                fake='1',
            )
            self._token_expiry = timezone.now() + TOKEN_EXPIRY

        return self._access_token

    def convert_language(self, language):
        """Convert language to service specific code.

        Remove second part of locale in most of cases.
        """
        return super(MicrosoftCognitiveTranslation, self).convert_language(
            language.replace('_', '-').lower()
        )

    def download_languages(self):
        """Download list of supported languages from a service.

        Example of the response:
        ['af', 'ar', 'bs-Latn', 'bg', 'ca', 'zh-CHS', 'zh-CHT', 'yue', 'hr',
        'cs', 'da', 'nl', 'en', 'et', 'fj', 'fil', 'fi', 'fr', 'de', 'el',
        'ht', 'he', 'hi', 'mww', 'h', 'id', 'it', 'ja', 'sw', 'tlh',
        'tlh-Qaak', 'ko', 'lv', 'lt', 'mg', 'ms', 'mt', 'yua', 'no', 'otq',
        'fa', 'pl', 'pt', 'ro', 'r', 'sm', 'sr-Cyrl', 'sr-Latn', 'sk', 'sl',
        'es', 'sv', 'ty', 'th', 'to', 'tr', 'uk', 'ur', 'vi', 'cy']
        """
        response = self.json_req(LIST_URL)

        # We should get an object, string usually means an error
        if isinstance(response, six.string_types):
            raise Exception(response)

        return response

    def download_translations(self, source, language, text, unit, request):
        """Download list of possible translations from a service."""
        args = {
            'text': text[:5000],
            'from': source,
            'to': language,
            'contentType': 'text/plain',
            'category': 'general',
        }
        response = self.json_req(TRANSLATE_URL, **args)
        return [(response, self.max_score, self.name, text)]
