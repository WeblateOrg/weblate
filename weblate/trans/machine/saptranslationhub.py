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

from django.conf import settings
from six.moves.urllib.request import Request, urlopen
from six.moves.urllib.parse import quote
import json
from weblate import USER_AGENT
from weblate.logger import LOGGER
from weblate.utils.site import get_site_url
import base64

from weblate.trans.machine.base import (
    MachineTranslation, MachineTranslationError, MissingConfiguration
)

class SAPTranslationHub(MachineTranslation):
    # https://api.sap.com/shell/discover/contentpackage/SAPTranslationHub/api/translationhub
    name = 'SAP Translation Hub'

    def __init__(self):
        """Check configuration."""
        super(SAPTranslationHub, self).__init__()
        if not self.sth_supported():
            raise MissingConfiguration(
                'missing SAP Translation Hub configuration'
            )

    def sth_supported(self):
        """Check whether service is supported."""       
        return (
            settings.MT_SAP_TRANSLATION_HUB_BASE_URL is not None
        )

    def authenticate(self, request):
        """Hook for backends to allow add authentication headers to request."""
        # to access the sandbox
        if settings.MT_SAP_TRANSLATION_HUB_SANDBOX_APIKEY is not None:
            request.add_header(
                str('APIKey'),
                settings.MT_SAP_TRANSLATION_HUB_SANDBOX_APIKEY.encode('utf-8')
            )
            
        # to access the productive API
        if settings.MT_SAP_TRANSLATION_HUB_USERNAME is not None and settings.MT_SAP_TRANSLATION_HUB_PASSWORD is not None:          
            credentials = settings.MT_SAP_TRANSLATION_HUB_USERNAME + ':' + settings.MT_SAP_TRANSLATION_HUB_PASSWORD
            request.add_header(
                str('Authorization'),
                base64.b64encode(credentials.encode('utf-8'))
            )

    def download_languages(self):
        """Get all available languages from SAP Translation Hub"""

        # get all available languages
        languagesUrl = settings.MT_SAP_TRANSLATION_HUB_BASE_URL + 'languages'
        response = self.json_req(languagesUrl.encode('utf-8'))

        lang = [d['id'] for d in response['languages']]
        return lang

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from a service."""

        # should the machine translation service be used? (rather than only the term database)
        enableMT = False
        if isinstance(settings.MT_SAP_TRANSLATION_HUB_USE_MT, bool):
            enableMT = settings.MT_SAP_TRANSLATION_HUB_USE_MT
        
        # build the json body
        requestData = json.dumps({'targetLanguages': [language], 'enableMT': enableMT, 'enableTranslationQualityEstimation': enableMT, 'units': [ { 'value': text } ] }, ensure_ascii=False)
        requestDataAsBytes = requestData.encode('utf-8')

        # create the request
        translationUrl = settings.MT_SAP_TRANSLATION_HUB_BASE_URL + 'translate'
        request = Request(translationUrl.encode("utf-8"))
        request.timeout = 0.5
        request.add_header(str('User-Agent'), USER_AGENT.encode('utf-8'))
        request.add_header(str('Referer'), get_site_url().encode('utf-8'))
        request.add_header(str('Content-Type'), str('application/json; charset=utf-8'))
        request.add_header(str('Content-Length'), len(requestDataAsBytes))
        request.add_header(str('Accept'), str('application/json; charset=utf-8'))
        self.authenticate(request)

        handle = urlopen(request, requestDataAsBytes)

        # Read and possibly convert response
        content = handle.read().decode('utf-8')
        # Replace literal \t
        content = content.strip().replace(
            '\t', '\\t'
        ).replace(
            '\r', '\\r'
        )

        response = json.loads(content)

        translations = []

        # prepare the translations for weblate
        for unit in response['units']:
            for translation in unit['translations']:
                translations.append((translation['value'], translation.get('qualityIndex', 100), self.name, text))

        return translations