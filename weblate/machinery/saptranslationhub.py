# -*- coding: utf-8 -*-
#
# Copyright ©  2018 Manuel Laggner <manuel.laggner@egger.com>
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

import base64
import json

from django.conf import settings

import six
from six.moves.urllib.request import Request, urlopen

from weblate import USER_AGENT
from weblate.utils.site import get_site_url
from weblate.machinery.base import MachineTranslation, MissingConfiguration


class SAPTranslationHub(MachineTranslation):
    # https://api.sap.com/shell/discover/contentpackage/SAPTranslationHub/api/translationhub
    name = 'SAP Translation Hub'

    def __init__(self):
        """Check configuration."""
        super(SAPTranslationHub, self).__init__()
        if settings.MT_SAP_BASE_URL is None:
            raise MissingConfiguration(
                'missing SAP Translation Hub configuration'
            )

    def authenticate(self, request):
        """Hook for backends to allow add authentication headers to request."""
        # to access the sandbox
        if settings.MT_SAP_SANDBOX_APIKEY is not None:
            request.add_header(
                'APIKey',
                settings.MT_SAP_SANDBOX_APIKEY.encode('utf-8')
            )

        # to access the productive API
        if settings.MT_SAP_USERNAME is not None \
           and settings.MT_SAP_PASSWORD is not None:
            credentials = '{}:{}'.format(
                settings.MT_SAP_USERNAME,
                settings.MT_SAP_PASSWORD
            )
            request.add_header(
                'Authorization',
                'Basic ' + base64.b64encode(
                    credentials.encode('utf-8')
                ).decode('utf-8')
            )

    def download_languages(self):
        """Get all available languages from SAP Translation Hub"""

        # get all available languages
        languages_url = settings.MT_SAP_BASE_URL + 'languages'
        response = self.json_req(languages_url)

        lang = [d['id'] for d in response['languages']]
        return lang

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from a service."""

        # should the machine translation service be used?
        # (rather than only the term database)
        enable_mt = False
        if isinstance(settings.MT_SAP_USE_MT, bool):
            enable_mt = settings.MT_SAP_USE_MT

        # build the json body
        request_data_as_bytes = json.dumps(
            {
                'targetLanguages': [language],
                'sourceLanguage': source,
                'enableMT': enable_mt,
                'enableTranslationQualityEstimation': enable_mt,
                'units': [{'value': text}]
            },
            ensure_ascii=False
        ).encode('utf-8')

        # create the request
        translation_url = settings.MT_SAP_BASE_URL + 'translate'
        request = Request(
            translation_url if six.PY3 else translation_url.encode("utf-8")
        )
        request.add_header('User-Agent', USER_AGENT.encode('utf-8'))
        request.add_header('Referer', get_site_url().encode('utf-8'))
        request.add_header('Content-Type', 'application/json; charset=utf-8')
        request.add_header('Content-Length', len(request_data_as_bytes))
        request.add_header('Accept', 'application/json; charset=utf-8')
        self.authenticate(request)

        # Read and possibly convert response
        content = urlopen(
            request, request_data_as_bytes, timeout=0.5
        ).read().decode('utf-8')
        # Replace literal \t
        content = content.strip().replace(
            '\t', '\\t'
        ).replace(
            '\r', '\\r'
        )

        response = json.loads(content)

        translations = []

        # prepare the translations for weblate
        for item in response['units']:
            for translation in item['translations']:
                translations.append((
                    translation['value'],
                    translation.get('qualityIndex', 100),
                    self.name,
                    text
                ))

        return translations
