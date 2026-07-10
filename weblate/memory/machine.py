# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import reverse

from weblate.machinery.base import (
    MACHINERY_DEFAULT_THRESHOLD,
    InternalMachineTranslation,
)
from weblate.memory.models import (
    MEMORY_LOOKUP_LIMIT,
    Memory,
)

if TYPE_CHECKING:
    from weblate.machinery.base import DownloadTranslations
    from weblate.machinery.types import TranslationResultDict

PENDING_MEMORY_PENALTY_FACTOR = 0.7
DIFFERENT_CONTEXT_PENALTY_FACTOR = 0.95


class WeblateMemory(InternalMachineTranslation):
    """Translation service using strings already translated in Weblate."""

    name = "Weblate Translation Memory"
    rank_boost = 2
    same_languages = True

    def get_quality(self, text: str, result: Memory, unit) -> int:
        quality = self.comparer.similarity(text, result.source)
        if result.status == Memory.STATUS_PENDING:
            quality = round(quality * PENDING_MEMORY_PENALTY_FACTOR)
        # Compare context when translation memory has one
        if result.context and unit.context != result.context:
            quality = round(quality * DIFFERENT_CONTEXT_PENALTY_FACTOR)
        return quality

    def format_result(
        self, result: Memory, quality: int, project, user
    ) -> TranslationResultDict:
        return {
            "text": result.target,
            "quality": quality,
            "service": self.name,
            "origin": result.get_origin_display(project=project, user=user),
            "source": result.source,
            "show_quality": True,
            "delete_url": reverse("api:memory-detail", kwargs={"pk": result.id})
            if user is not None and user.has_perm("memory.delete", result)
            else None,
        }

    def download_translations(
        self,
        source_language,
        target_language,
        text: str,
        unit,
        user,
        threshold: int = MACHINERY_DEFAULT_THRESHOLD,
    ) -> DownloadTranslations:
        """Download list of possible translations from a service."""
        project = unit.translation.component.project
        queryset = Memory.objects.get_lookup_queryset(
            source_language,
            target_language,
            user,
            project,
            project.use_shared_tm,
        )
        if threshold >= self.max_score:
            scored_results = []
            for result in queryset.filter(source=text)[:MEMORY_LOOKUP_LIMIT]:
                quality = self.get_quality(text, result, unit)
                if quality >= threshold:
                    scored_results.append((quality, result))
        else:
            scored_results = queryset.get_scored_fuzzy_candidates(
                text,
                lambda result: self.get_quality(text, result, unit),
                threshold=threshold,
            )

        for quality, result in scored_results:
            yield self.format_result(result, quality, project, user)
