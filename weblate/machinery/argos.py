# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .base import MachineTranslation

if TYPE_CHECKING:
    from weblate.auth.models import User
    from weblate.trans.models import Unit

    from .base import DownloadTranslations

try:
    import argostranslate.package
    import argostranslate.translate
except ImportError:
    argostranslate = None

logger = logging.getLogger(__name__)


class ArgosTranslation(MachineTranslation):
    """Argos offline machine translation."""

    name = "Argos Translate"
    settings_form = None
    is_available = bool(argostranslate)

    def is_supported(self, source_language, target_language):
        """Supported if the language model package is installed in argostranslate."""
        if not self.is_available:
            return False

        src = source_language.split("-")[0].lower()
        tgt = target_language.split("-")[0].lower()

        installed_languages = argostranslate.translate.get_installed_languages()

        src_lang = next(
            (lang for lang in installed_languages if lang.code == src), None
        )
        tgt_lang = next(
            (lang for lang in installed_languages if lang.code == tgt), None
        )

        if src_lang and tgt_lang:
            return src_lang.get_translation(tgt_lang) is not None

        return False

    def download_translations(
        self,
        source_language,
        target_language,
        text: str,
        unit: Unit | None,
        user: User | None,
        threshold: int = 75,
    ) -> DownloadTranslations:
        """Translate using argostranslate."""
        if not self.is_available:
            return

        src = source_language.split("-")[0].lower()
        tgt = target_language.split("-")[0].lower()

        try:
            translation = argostranslate.translate.translate(text, src, tgt)
            if translation:
                yield {
                    "text": translation,
                    "quality": self.max_score,
                    "service": self.name,
                    "source": text,
                }
        except Exception as e:
            logger.debug(
                "Argos translation failed for %s to %s: %s",
                source_language,
                target_language,
                e,
            )
            return
