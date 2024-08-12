# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from .base import MachineTranslation, TranslationResultDict

CYRTRANSLIT_TO_WEBLATE_LANGS = {
    # bulgarian
    "bg@latin": ["bg"],
    "bg@cyrillic": [],
    # montenegrin
    "me@latin": ["me", "cnr"],
    "me@cyrillic": ["cnr_Cyrl"],
    # macedonian
    "mk@latin": ["mk"],
    "mk@cyrillic": [],
    # mongolian
    "mn@latin": [],
    "mn@cyrillic": ["mn"],
    # russian
    "ru@latin": [],
    "ru@cyrillic": ["ru"],
    # serbian
    "sr@latin": ["sr", "sr_Latn", "sr@ijekavian_Latn"],
    "sr@cyrillic": ["sr@ijekavian", "sr_Cyrl"],
    # tajik
    "tj@latin": [],
    "tj@cyrillic": ["tg"],
    # ukrainian
    "ua@latin": [],
    "ua@cyrillic": ["uk"],
}


class CyrTranslitTranslation(MachineTranslation):
    """Machine translation using cyrtranslit library."""

    name = "CyrTranslit"
    max_score = 100
    cache_translations = False

    def download_languages(self):
        """List of supported languages."""
        return list(CYRTRANSLIT_TO_WEBLATE_LANGS.keys())

    def download_translations(
        self, source, language, text: str, unit, user, threshold: int = 75
    ):
        """Download list of possible translations from a service."""
        import cyrtranslit

        language, script = language.split("@")

        translated_text = (
            cyrtranslit.to_cyrillic(text, language)
            if script == "cyrillic"
            else cyrtranslit.to_latin(text, language)
        )

        yield TranslationResultDict(
            text=translated_text,
            quality=self.max_score,
            service=self.name,
            source=text,
        )

    def is_supported(self, source, language):
        """Check whether given language combination is supported."""
        if super().is_supported(source, language):
            return source.split("@")[0] == language.split("@")[0]
        return False

    def map_language_code(self, code: str) -> str:
        """Map language code to service specific code."""
        for key, values in CYRTRANSLIT_TO_WEBLATE_LANGS.items():
            if code in values:
                return key
        return code
