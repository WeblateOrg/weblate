# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import Case, IntegerField, Value, When
from django.db.models.functions import MD5, Length, Lower

from weblate.trans.models import Translation, Unit
from weblate.utils.db import adjust_similarity_threshold, use_trgm_fallback
from weblate.utils.state import STATE_TRANSLATED

from .base import InternalMachineTranslation

if TYPE_CHECKING:
    from .base import DownloadTranslations


class WeblateTranslation(InternalMachineTranslation):
    """Translation service using strings already translated in Weblate."""

    name = "Weblate"
    rank_boost = 1
    cache_translations = True
    # Cache results for 1 hour to avoid frequent database hits
    cache_expiry = 3600
    candidate_limit = 50

    def download_translations(
        self,
        source_language,
        target_language,
        text: str,
        unit,
        user,
        threshold: int = 10,
    ) -> DownloadTranslations:
        """Download list of possible translations from a service."""
        yielded = 0
        matching_units = self.get_matching_units(
            self.get_base_queryset(user, source_language, target_language),
            text,
            threshold,
        )

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
            yielded += 1
            if yielded >= self.candidate_limit:
                break

    def get_base_queryset(self, user, source_language, target_language):
        alias = "memory_db" if "memory_db" in settings.DATABASES else "default"

        translations = Translation.objects.using(alias).all()
        if user is not None:
            translations = translations.filter_access(user)

        translation_ids = translations.filter(
            component__source_language=source_language,
            language=target_language,
        ).values("id")

        return Unit.objects.using(alias).filter(
            state__gte=STATE_TRANSLATED,
            translation_id__in=translation_ids,
        )

    def get_matching_units(self, base, text: str, threshold: int):
        if threshold < 100:
            adjust_similarity_threshold(0.98)
            if use_trgm_fallback(text):
                queryset = self.get_short_query_matches(base, text)
            else:
                queryset = base.filter(source__trgm_search=text).annotate(
                    match_similarity=TrigramSimilarity("source", text)
                )
                queryset = queryset.order_by("-match_similarity", "pk")
        else:
            queryset = base.filter(
                source__lower__md5=MD5(Lower(Value(text))),
                source=text,
            ).order_by("pk")

        return self.prepare_queryset(queryset).iterator(chunk_size=self.candidate_limit)

    def prepare_queryset(self, queryset):
        return queryset.exclude(target="").prefetch()

    def get_short_query_matches(self, base, text: str):
        max_source_length = max(len(text) + 4, len(text) * 2, 8)
        return (
            base.filter(source__trgm_search=text)
            .annotate(
                short_query_rank=Case(
                    When(source__iexact=text, then=Value(0)),
                    When(source__istartswith=text, then=Value(1)),
                    default=Value(2),
                    output_field=IntegerField(),
                ),
                source_length=Length("source"),
            )
            .filter(source_length__lte=max_source_length)
            .order_by("short_query_rank", "source_length", "pk")
        )
