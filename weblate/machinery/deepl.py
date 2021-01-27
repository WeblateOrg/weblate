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

from django.conf import settings

from weblate.machinery.base import MachineTranslation, MissingConfiguration

DEEPL_TRANSLATE = "https://api.deepl.com/{}/translate"
DEEPL_LANGUAGES = "https://api.deepl.com/{}/languages"


class DeepLTranslation(MachineTranslation):
    """DeepL (Linguee) machine translation support."""

    name = "DeepL"
    # This seems to be currently best MT service, so score it a bit
    # better than other ones.
    max_score = 91
    language_map = {
        "zh_hans": "zh",
    }

    def __init__(self):
        """Check configuration."""
        super().__init__()
        if settings.MT_DEEPL_KEY is None:
            raise MissingConfiguration("DeepL requires API key")

    def map_language_code(self, code):
        """Convert language to service specific code."""
        return super().map_language_code(code).replace("_", "-").upper()

    def download_languages(self):
        """List of supported languages is currently hardcoded."""
        response = self.request(
            "post",
            DEEPL_LANGUAGES.format(settings.MT_DEEPL_API_VERSION),
            data={"auth_key": settings.MT_DEEPL_KEY},
        )
        return [x["language"] for x in response.json()]

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
        response = self.request(
            "post",
            DEEPL_TRANSLATE.format(settings.MT_DEEPL_API_VERSION),
            data={
                "auth_key": settings.MT_DEEPL_KEY,
                "text": text,
                "source_lang": source,
                "target_lang": language,
            },
        )
        payload = response.json()

        for translation in payload["translations"]:
            yield {
                "text": translation["text"],
                "quality": self.max_score,
                "service": self.name,
                "source": text,
            }
