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

from django.utils.encoding import force_text
from django.utils.functional import cached_property

from zeep import Client

from weblate.machinery.base import MachineTranslation
from weblate.lang.data import DEFAULT_LANGS

WSDL_URL = 'http://api.terminology.microsoft.com/Terminology.svc?wsdl'
WSDL_URL = 'http://api.terminology.microsoft.com/Terminology.svc?singleWsdl'


class MicrosoftTerminologyService(MachineTranslation):
    """
    The Microsoft Terminology Service API.

    Allows you to programmatically access the terminology,
    definitions and user interface (UI) strings available
    on the MS Language Portal through a web service (SOAP).
    """
    name = 'Microsoft Terminology'

    SERVICE = None

    @cached_property
    def soap(self):
        if MicrosoftTerminologyService.SERVICE is None:
            MicrosoftTerminologyService.SERVICE = Client(WSDL_URL)
        return MicrosoftTerminologyService.SERVICE

    def soap_req(self, name, **kwargs):
        self.request_url = name
        self.request_params = kwargs
        return getattr(self.soap.service, name)(**kwargs)

    def download_languages(self):
        """Get list of supported languages."""
        languages = self.soap_req('GetLanguages')
        if not languages:
            return []
        return [lang['Code'] for lang in languages]

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from the service."""
        args = {
            'text': text,
            'from': source,
            'to': language,
            'maxTranslations': 20,
            'sources': ['Terms', 'UiStrings'],
            'searchOperator': 'AnyWord'
        }
        result = self.soap_req('GetTranslations', **args)
        translations = []
        if not result:
            return translations

        for item in result:
            target = force_text(
                item['Translations']['Translation'][0]['TranslatedText']
            )
            translations.append((
                target,
                self.comparer.similarity(text, target),
                self.name,
                item['OriginalText'],
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
