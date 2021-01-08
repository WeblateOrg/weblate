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

from functools import reduce

from django.conf import settings

from weblate.machinery.base import MachineTranslation, MissingConfiguration

LANGUAGE_MAP = {
    "ca": "cat",
    "cy": "cym",
    "eo": "epo",
    "gl": "glg",
    "bs": "hbs_BS",
    "es": "spa",
    "en": "eng",
    "en_US": "eng",
    "en_UK": "eng",
    "nl": "nld",
    "de": "deu",
    "fr": "fra",
    "sl": "slv",
    "sr": "hbs",
    "nb_NO": "nob",
    "nn": "nno",
    "se": "sme",
    "oc": "oci",
    "pt": "por",
    "co": "cos",
    "fi": "fin",
    "ia": "ina",
    "ro": "ron",
    "cs": "ces",
    "sk": "slk",
    "ru": "rus",
    "av": "ava",
    "is": "isl",
    "pl": "pol",
    "kk": "kaz",
    "tt": "tat",
    "be": "bel",
    "uk": "ukr",
    "gn": "grn",
    "mt": "mlt",
    "it": "ita",
    "zh_Hant": "zho",
    "br": "bre",
    "qu": "qve",
    "an": "arg",
    "mr": "mar",
    "af": "afr",
    "fa": "pes",
    "el": "ell",
    "lv": "lvs",
    "as": "asm",
    "hi": "hin",
    "te": "tel",
    "hy": "hye",
    "th": "tha",
    "mk": "mkd",
    "la": "lat",
    "ga": "gle",
    "sw": "swa",
    "hu": "hun",
    "ml": "mal",
}


class ApertiumAPYTranslation(MachineTranslation):
    """Apertium machine translation support."""

    name = "Apertium APy"
    max_score = 90

    def __init__(self):
        """Check configuration."""
        super().__init__()
        self.url = self.get_server_url()

    @staticmethod
    def get_server_url():
        """Return URL of a server."""
        if settings.MT_APERTIUM_APY is None:
            raise MissingConfiguration("Not configured Apertium APy URL")

        return settings.MT_APERTIUM_APY.rstrip("/")

    @property
    def all_langs(self):
        """Return all language codes known to service."""
        return reduce(lambda acc, x: acc.union(x), self.supported_languages, set())

    def map_language_code(self, code):
        """Convert language to service specific code."""
        code = super().map_language_code(code).replace("-", "_")
        # Force download of supported languages
        if code not in self.all_langs and code in LANGUAGE_MAP:
            return LANGUAGE_MAP[code]
        return code

    def download_languages(self):
        """Download list of supported languages from a service."""
        data = self.request_status("get", f"{self.url}/listPairs")
        return [
            (item["sourceLanguage"], item["targetLanguage"])
            for item in data["responseData"]
        ]

    def is_supported(self, source, language):
        """Check whether given language combination is supported."""
        return (source, language) in self.supported_languages

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
        """Download list of possible translations from Apertium."""
        args = {
            "langpair": f"{source}|{language}",
            "q": text,
            "markUnknown": "no",
        }
        response = self.request_status("get", f"{self.url}/translate", params=args)

        yield {
            "text": response["responseData"]["translatedText"],
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }
