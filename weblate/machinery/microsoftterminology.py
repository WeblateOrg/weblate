#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from django.utils.functional import cached_property
from weblate_language_data.countries import DEFAULT_LANGS
from zeep import Client

from weblate.machinery.base import MachineTranslation

MST_API_URL = "http://api.terminology.microsoft.com/Terminology.svc"
MST_WSDL_URL = f"{MST_API_URL}?wsdl"


class MicrosoftTerminologyService(MachineTranslation):
    """The Microsoft Terminology Service API.

    Allows you to programmatically access the terminology, definitions and user
    interface (UI) strings available on the MS Language Portal through a web service
    (SOAP).
    """

    name = "Microsoft Terminology"

    SERVICE = None

    @cached_property
    def soap(self):
        if MicrosoftTerminologyService.SERVICE is None:
            MicrosoftTerminologyService.SERVICE = Client(MST_WSDL_URL)
        return MicrosoftTerminologyService.SERVICE

    def soap_req(self, name, **kwargs):
        return getattr(self.soap.service, name)(**kwargs)

    def download_languages(self):
        """Get list of supported languages."""
        languages = self.soap_req("GetLanguages")
        if not languages:
            return []
        return [lang["Code"] for lang in languages]

    def download_translations(
        self,
        source,
        language,
        text: str,
        unit,
        user,
        search: bool,
        threshold: int = 75,
    ):
        """Download list of possible translations from the service."""
        args = {
            "text": text,
            "from": source,
            "to": language,
            "maxTranslations": 20,
            "sources": ["Terms", "UiStrings"],
            "searchOperator": "AnyWord",
        }
        result = self.soap_req("GetTranslations", **args)
        # It can return None in some error cases
        if not result:
            return

        for item in result:
            target = item["Translations"]["Translation"][0]["TranslatedText"]
            source = item["OriginalText"]
            yield {
                "text": target,
                "quality": self.comparer.similarity(text, source),
                "service": self.name,
                "source": source,
            }

    def map_language_code(self, code):
        """Convert language to service specific code.

        Add country part of locale if missing.
        """
        code = super().map_language_code(code).replace("_", "-").lower()
        if "-" not in code:
            for lang in DEFAULT_LANGS:
                if lang.split("_")[0] == code:
                    return lang.replace("_", "-").lower()
        return code
