# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.conf import settings

from weblate.trans.models import Unit
from weblate.utils.db import adjust_similarity_threshold
from weblate.utils.state import STATE_TRANSLATED

from .base import DownloadTranslations, InternalMachineTranslation


class WeblateTranslation(InternalMachineTranslation):
    """Translation service using strings already translated in Weblate."""

    name = "Weblate"
    rank_boost = 1

    def download_translations(
        self,
        source,
        language,
        text: str,
        unit,
        user,
        threshold: int = 10,
    ) -> DownloadTranslations:
        """Download list of possible translations from a service."""
        # Filter based on user access
        base = Unit.objects.filter_access(user) if user else Unit.objects.all()

        # Use memory_db for the query in case it exists. This is supposed
        # to be a read-only replica for offloading expensive translation
        # queries.
        if "memory_db" in settings.DATABASES:
            base = base.using("memory_db")

        lookup_term = "source__search" if threshold < 100 else "source"
        lookup = {lookup_term: text}

        matching_units = base.filter(
            translation__component__source_language=source,
            translation__language=language,
            state__gte=STATE_TRANSLATED,
            **lookup,
        ).prefetch()

        # We want only close matches here
        adjust_similarity_threshold(0.98)

        for munit in matching_units:
            source = munit.source_string
            if "forbidden" in munit.all_flags:
                continue
            quality = self.comparer.similarity(text, source)
            if quality < threshold:
                continue
            yield {
                "text": munit.get_target_plurals()[0],
                "quality": quality,
                "show_quality": True,
                "service": self.name,
                "origin": str(munit.translation.component),
                "origin_url": munit.get_absolute_url(),
                "source": source,
            }
