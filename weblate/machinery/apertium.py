# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from functools import reduce

from .base import (
    DownloadTranslations,
    ResponseStatusMachineTranslation,
)
from .forms import URLMachineryForm

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
    "se": "sme",  # codespell:ignore sme
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
    "te": "tel",  # codespell:ignore te
    "hy": "hye",
    "th": "tha",  # codespell:ignore tha
    "mk": "mkd",
    "la": "lat",
    "ga": "gle",
    "sw": "swa",
    "hu": "hun",
    "ml": "mal",
}


class ApertiumAPYTranslation(ResponseStatusMachineTranslation):
    """Apertium machine translation support."""

    name = "Apertium APy"
    max_score = 88
    settings_form = URLMachineryForm
    request_timeout = 20

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
        data = self.request("get", self.get_api_url("listPairs")).json()
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
        threshold: int = 75,
    ) -> DownloadTranslations:
        """Download list of possible translations from Apertium."""
        args = {
            "langpair": f"{source}|{language}",
            "q": text,
            "markUnknown": "no",
        }
        response = self.request(
            "get", self.get_api_url("translate"), params=args
        ).json()

        yield {
            "text": response["responseData"]["translatedText"],
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }
