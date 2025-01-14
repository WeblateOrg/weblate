# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.urls import reverse

from weblate.machinery.base import DownloadTranslations, InternalMachineTranslation
from weblate.memory.models import Memory


class WeblateMemory(InternalMachineTranslation):
    """Translation service using strings already translated in Weblate."""

    name = "Weblate Translation Memory"
    rank_boost = 2
    same_languages = True

    def download_translations(
        self,
        source_language,
        target_language,
        text: str,
        unit,
        user,
        threshold: int = 75,
    ) -> DownloadTranslations:
        """Download list of possible translations from a service."""
        for result in Memory.objects.lookup(
            source_language,
            target_language,
            text,
            user,
            unit.translation.component.project,
            unit.translation.component.project.use_shared_tm,
            threshold=threshold,
        ):
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
