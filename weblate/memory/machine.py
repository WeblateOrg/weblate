# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.urls import reverse

from weblate.machinery.base import MachineTranslation, get_machinery_language
from weblate.memory.models import Memory


class WeblateMemory(MachineTranslation):
    """Translation service using strings already translated in Weblate."""

    name = "Weblate Translation Memory"
    rank_boost = 2
    cache_translations = False
    same_languages = True
    accounting_key = "internal"
    do_cleanup = False

    def convert_language(self, language):
        """No conversion of language object."""
        return get_machinery_language(language)

    def is_supported(self, source, language):
        """Any language is supported."""
        return True

    def is_rate_limited(self):
        """Disable rate limiting."""
        return False

    def download_translations(
        self,
        source,
        language,
        text: str,
        unit,
        user,
        threshold: int = 75,
    ):
        """Download list of possible translations from a service."""
        for result in Memory.objects.lookup(
            source,
            language,
            text,
            user,
            unit.translation.component.project,
            unit.translation.component.project.use_shared_tm,
        ).iterator():
            quality = self.comparer.similarity(text, result.source)
            if quality < threshold:
                continue
            yield {
                "text": result.target,
                "quality": quality,
                "service": self.name,
                "origin": result.get_origin_display(),
                "source": result.source,
                "show_quality": True,
                "delete_url": reverse("api:memory-detail", kwargs={"pk": result.id})
                if user is not None and user.has_perm("memory.delete", result)
                else None,
            }
