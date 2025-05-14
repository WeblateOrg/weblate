# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from weblate.lang.models import Language

from .base import MachineTranslation, TranslationResultDict

if TYPE_CHECKING:
    from weblate.trans.models import Translation

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
    replacement_start = "[___"
    replacement_end = "___]"

    def download_languages(self):
        """List of supported languages."""
        return list(CYRTRANSLIT_TO_WEBLATE_LANGS.keys())

    def get_default_source_language(self, translation: Translation) -> Language:
        """Return default source language for the translation."""
        mapped_code = self.map_language_code(translation.language.code)

        # Invert alphabet
        if mapped_code.endswith("@latin"):
            mapped_code = mapped_code.replace("@latin", "@cyrillic")
        else:
            mapped_code = mapped_code.replace("@cyrillic", "@latin")

        if mapped_code in CYRTRANSLIT_TO_WEBLATE_LANGS:
            languages = Language.objects.filter(
                code__in=CYRTRANSLIT_TO_WEBLATE_LANGS[mapped_code],
                translation__component=translation.component,
            )

            # Try finding best fit based on the base code
            for language in languages:
                if language.code.startswith(translation.language.base_code):
                    return language

            # Return any if we failed to match
            if languages:
                return languages[0]
        return super().get_default_source_language(translation)

    def download_translations(
        self,
        source_language,
        target_language,
        text: str,
        unit,
        user,
        threshold: int = 75,
    ):
        """Download list of possible translations from a service."""
        import cyrtranslit

        target_language, script = target_language.split("@")

        translated_text = (
            cyrtranslit.to_cyrillic(text, target_language)
            if script == "cyrillic"
            else cyrtranslit.to_latin(text, target_language)
        )

        yield TranslationResultDict(
            text=translated_text,
            quality=self.max_score,
            service=self.name,
            source=text,
        )

    def is_supported(self, source_language, target_language):
        """Check whether given language combination is supported."""
        if super().is_supported(source_language, target_language):
            return source_language.split("@")[0] == target_language.split("@")[0]
        return False

    def map_language_code(self, code: str) -> str:
        """Map language code to service specific code."""
        for key, values in CYRTRANSLIT_TO_WEBLATE_LANGS.items():
            if code in values:
                return key
        return code
