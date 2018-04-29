# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from uuid import uuid4
from datetime import timedelta

from defusedxml import ElementTree

from six.moves.urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone
from django.template.loader import get_template

from weblate.machinery.base import (
    MachineTranslation, MachineTranslationError, MissingConfiguration
)
from weblate.lang.data import DEFAULT_LANGS

COGNITIVE_BASE_URL = 'https://api.cognitive.microsoft.com/sts/v1.0'
COGNITIVE_TOKEN = COGNITIVE_BASE_URL + '/issueToken?Subscription-Key={0}'

BASE_URL = 'https://api.microsofttranslator.com/V2/Ajax.svc/'
TRANSLATE_URL = BASE_URL + 'Translate'
LIST_URL = BASE_URL + 'GetLanguagesForTranslate'
TOKEN_EXPIRY = timedelta(minutes=9)


class MicrosoftTranslation(MachineTranslation):
    """Microsoft Translator machine translation support."""
    name = 'Microsoft Translator'
    max_score = 90

    def __init__(self):
        """Check configuration."""
        super(MicrosoftTranslation, self).__init__()
        self._access_token = None
        self._token_expiry = None
        if not self.ms_supported():
            raise MissingConfiguration(
                'Microsoft Translator requires credentials'
            )

    def ms_supported(self):
        """Check whether service is supported."""
        return (
            settings.MT_MICROSOFT_ID is not None and
            settings.MT_MICROSOFT_SECRET is not None
        )

    def is_token_expired(self):
        """Check whether token is about to expire."""
        return self._token_expiry <= timezone.now()

    @property
    def access_token(self):
        """Obtain and caches access token."""
        if self._access_token is None or self.is_token_expired():
            data = self.json_req(
                'https://datamarket.accesscontrol.windows.net/v2/OAuth2-13',
                skip_auth=True,
                http_post=True,
                client_id=settings.MT_MICROSOFT_ID,
                client_secret=settings.MT_MICROSOFT_SECRET,
                scope='https://api.microsofttranslator.com',
                grant_type='client_credentials',
            )

            if 'error' in data:
                raise MachineTranslationError(
                    data.get('error', 'Unknown Error') +
                    data.get('error_description', 'No Error Description')
                )

            self._access_token = data['access_token']
            self._token_expiry = timezone.now() + TOKEN_EXPIRY

        return self._access_token

    def authenticate(self, request):
        """Hook for backends to allow add authentication headers to request."""
        request.add_header(
            'Authorization',
            'Bearer {0}'.format(self.access_token)
        )

    def convert_language(self, language):
        """Convert language to service specific code."""
        language = language.replace('_', '-').lower()
        if language in ('zh-tw', 'zh-hant'):
            return 'zh-CHT'
        if language in ('zh-cn', 'zh-hans'):
            return 'zh-CHS'
        if language in ('nb', 'nb-no'):
            return 'no'
        if language == 'pt-br':
            return 'pt'
        return language

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
        return self.json_req(LIST_URL)

    def download_translations(self, source, language, text, unit, user):
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


class MicrosoftCognitiveTranslation(MicrosoftTranslation):
    """Microsoft Cognitive Services Translator API support."""
    name = 'Microsoft Translator'

    LANGUAGE_CONVERTER = {
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

    def ms_supported(self):
        """Check whether service is supported."""
        return settings.MT_MICROSOFT_COGNITIVE_KEY is not None

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
        language = language.replace('_', '-').lower()
        if language in self.LANGUAGE_CONVERTER:
            return self.LANGUAGE_CONVERTER[language]
        return language.split('-')[0]


class MicrosoftTerminologyService(MachineTranslation):
    """
    The Microsoft Terminology Service API.

    Allows you to programmatically access the terminology,
    definitions and user interface (UI) strings available
    on the MS Language Portal through a web service (SOAP).
    """
    name = 'Microsoft Terminology'

    MS_TM_BASE = 'http://api.terminology.microsoft.com'
    MS_TM_API_URL = '{base}/Terminology.svc'.format(base=MS_TM_BASE)
    MS_TM_SOAP_XMLNS = '{base}/terminology'.format(base=MS_TM_BASE)
    MS_TM_SOAP_HEADER = '{xmlns}/Terminology/'.format(xmlns=MS_TM_SOAP_XMLNS)
    MS_TM_XPATH = './/{{{xmlns}}}'.format(xmlns=MS_TM_SOAP_XMLNS)

    def soap_req(self, action, **kwargs):
        template = get_template(
            'machine/microsoft_terminology_{}.xml'.format(action.lower())
        )
        payload = template.render(kwargs)

        request = Request(self.MS_TM_API_URL, payload.encode('utf-8'))
        request.timeout = 0.5
        request.add_header(
            'SOAPAction', '"{}"'.format(self.MS_TM_SOAP_HEADER + action)
        )
        request.add_header('Content-Type', 'text/xml; charset=utf-8')
        return urlopen(request)

    def download_languages(self):
        """Get list of supported languages."""
        xp_code = self.MS_TM_XPATH + 'Code'
        languages = []
        resp = self.soap_req('GetLanguages')
        root = ElementTree.fromstring(resp.read())
        results = root.find(self.MS_TM_XPATH + 'GetLanguagesResult')
        if results is not None:
            for lang in results:
                languages.append(lang.find(xp_code).text)
        return languages

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from the service."""
        translations = []
        xp_translated = self.MS_TM_XPATH + 'TranslatedText'
        xp_confidence = self.MS_TM_XPATH + 'ConfidenceLevel'
        xp_original = self.MS_TM_XPATH + 'OriginalText'
        resp = self.soap_req(
            'GetTranslations',
            uuid=uuid4(),
            text=text,
            from_lang=source,
            to_lang=language,
            max_result=20,
        )
        root = ElementTree.fromstring(resp.read())
        results = root.find(self.MS_TM_XPATH + 'GetTranslationsResult')
        if results is not None:
            for translation in results:
                translations.append((
                    translation.find(xp_translated).text,
                    int(translation.find(xp_confidence).text),
                    self.name,
                    translation.find(xp_original).text,
                ))
        return translations

    def convert_language(self, language):
        """Convert language to service specific code.

        Add country part of locale if missing.
        """
        language = language.replace('_', '-').lower()
        if '-' not in language:
            for lang in DEFAULT_LANGS:
                if lang.split('_')[0] == language:
                    return lang.replace('_', '-').lower()
        return language
