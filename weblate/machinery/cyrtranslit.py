# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from itertools import chain

import cyrtranslit

from .base import MachineTranslation, TranslationResultDict

CYRTRANSLIT_TO_WEBLATE_LANGS = {
    "bg": {  # bulgarian
        "latin": ["bg"],
        "cyrillic": [],
    },
    "me": {  # montenegrin
        "latin": ["me", "cnr"],
        "cyrillic": ["cnr_Cyrl"],
    },
    "mk": {  # macedonian
        "latin": ["mk"],
        "cyrillic": [],
    },
    "mn": {  # mongolian
        "latin": [],
        "cyrillic": ["mn"],
    },
    "ru": {  # russian
        "latin": [],
        "cyrillic": ["ru"],
    },
    "sr": {  # serbian
        "latin": ["sr", "sr_Latn", "sr@ijekavian_Latn"],
        "cyrillic": ["sr", "sr@ijekavian", "sr_Cyrl"],
    },
    "tj": {  # tajik
        "latin": [],
        "cyrillic": ["tg"],
    },
    "ua": {  # ukrainian
        "latin": [],
        "cyrillic": ["uk"],
    },
}


class CyrTranslitError(Exception):
    pass


class CyrTranslitTranslation(MachineTranslation):
    """Machine translation using cyrtranslit library."""

    name = "CyrTranslit"
    max_score = 100
    cache_translations = False

    def download_languages(self):
        """List of supported languages."""
        return list(
            chain.from_iterable(
                [
                    lang["latin"] + lang["cyrillic"]
                    for lang in CYRTRANSLIT_TO_WEBLATE_LANGS.values()
                ]
            )
        )

    def download_translations(
        self, source, language, text: str, unit, user, threshold: int = 75
    ):
        """Download list of possible translations from a service."""
        cyrtransl_lang = None
        is_cyrillic = False
        for key, values in CYRTRANSLIT_TO_WEBLATE_LANGS.items():
            if source in values["latin"] and language in values["cyrillic"]:
                cyrtransl_lang = key
                is_cyrillic = True
                break
            if source in values["cyrillic"] and language in values["latin"]:
                cyrtransl_lang = key
                is_cyrillic = False
                break

        if cyrtransl_lang is None:
            raise CyrTranslitError

        translated_text = (
            cyrtranslit.to_cyrillic(text, cyrtransl_lang)
            if is_cyrillic
            else cyrtranslit.to_latin(text, cyrtransl_lang)
        )

        yield TranslationResultDict(
            text=translated_text,
            quality=self.max_score,
            service=self.name,
            source=source,
        )

    def download_multiple_translations(
        self, *args, **kwargs
    ) -> dict[str, list[TranslationResultDict]]:
        try:
            return super().download_multiple_translations(*args, **kwargs)()
        except CyrTranslitError:
            return []
