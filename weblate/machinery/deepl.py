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

from html import escape, unescape

from django.conf import settings

from weblate.machinery.base import MachineTranslation, MissingConfiguration

DEEPL_TRANSLATE = "{}translate"
DEEPL_LANGUAGES = "{}languages"

# Extracted from https://www.deepl.com/docs-api/translating-text/response/
FORMAL_LANGUAGES = {"DE", "FR", "IT", "ES", "NL", "PL", "PT-PT", "PT-BR", "RU"}


class DeepLTranslation(MachineTranslation):
    """DeepL (Linguee) machine translation support."""

    name = "DeepL"
    # This seems to be currently best MT service, so score it a bit
    # better than other ones.
    max_score = 91
    language_map = {
        "zh_hans": "zh",
    }
    force_uncleanup = True
    hightlight_syntax = True

    def __init__(self):
        """Check configuration."""
        super().__init__()
        if settings.MT_DEEPL_KEY is None:
            raise MissingConfiguration("DeepL requires API key")

    def map_language_code(self, code):
        """Convert language to service specific code."""
        return super().map_language_code(code).replace("_", "-").upper()

    def download_languages(self):
        response = self.request(
            "post",
            DEEPL_LANGUAGES.format(settings.MT_DEEPL_API_URL),
            data={"auth_key": settings.MT_DEEPL_KEY},
        )
        result = {x["language"] for x in response.json()}

        for lang in FORMAL_LANGUAGES:
            if lang in result:
                result.add(f"{lang}@FORMAL")
                result.add(f"{lang}@INFORMAL")
        return result

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
        """Download list of possible translations from a service."""
        params = {
            "auth_key": settings.MT_DEEPL_KEY,
            "text": text,
            "source_lang": source,
            "target_lang": language,
        }
        if language.endswith("@FORMAL"):
            params["target_lang"] = language[:-7]
            params["formality"] = "more"
        elif language.endswith("@INFORMAL"):
            params["target_lang"] = language[:-9]
            params["formality"] = "less"
        response = self.request(
            "post",
            DEEPL_TRANSLATE.format(settings.MT_DEEPL_API_URL),
            data=params,
        )
        payload = response.json()

        for translation in payload["translations"]:
            yield {
                "text": translation["text"],
                "quality": self.max_score,
                "service": self.name,
                "source": text,
                "tag_handling": "xml",
                "ignore_tags": "x",
            }

    def unescape_text(self, text: str):
        """Unescaping of the text with replacements."""
        return unescape(text)

    def escape_text(self, text: str):
        """Escaping of the text with replacements."""
        return escape(text)

    def format_replacement(self, h_start: int, h_end: int, h_text: str):
        """Generates a single replacement."""
        return f'<x id="{h_start}"></x>'
