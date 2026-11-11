# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from itertools import batched
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.postgres.search import TrigramSimilarity, TrigramWordSimilarity
from django.db.models import Case, F, IntegerField, Q, Value, When
from django.db.models.functions import MD5, Length, Lower

from weblate.formats.models import FILE_FORMATS
from weblate.glossary.models import iter_glossary_alternatives
from weblate.trans.models import Translation, Unit, WorkflowSetting
from weblate.trans.util import PLURAL_SEPARATOR
from weblate.utils.db import adjust_similarity_threshold, use_trgm_fallback
from weblate.utils.state import STATE_TRANSLATED

from .base import InternalMachineTranslation

if TYPE_CHECKING:
    from weblate.auth.models import User

    from .base import DownloadTranslations


class WeblateTranslation(InternalMachineTranslation):
    """Translation service using strings already translated in Weblate."""

    name = "Weblate"
    rank_boost = 1
    # Results depend on the user's access and must not be shared through the cache.
    cache_translations = False
    candidate_limit = 50

    def download_translations(
        self,
        source_language,
        target_language,
        text: str,
        unit: Unit | None,
        user: User | None,
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
            multivalue = munit.is_multivalue
            alternatives = (
                iter_glossary_alternatives([munit], effective_source=True)
                if multivalue
                else [munit]
            )
            for alternative in alternatives:
                source = (
                    alternative.source if multivalue else munit.effective_source_string
                )
                if "forbidden" in alternative.all_flags or not alternative.target:
                    continue
                quality = self.comparer.similarity(text, source)
                if quality < threshold:
                    continue
                yield {
                    "text": alternative.get_target_plurals()[0],
                    "quality": quality,
                    "show_quality": True,
                    "service": self.name,
                    "origin": str(munit.translation.component),
                    "origin_url": munit.get_absolute_url(),
                    "source": source,
                }
                yielded += 1
                if yielded >= self.candidate_limit:
                    return

    def get_base_queryset(self, user, source_language, target_language):
        alias = "memory_db" if "memory_db" in settings.DATABASES else "default"

        translations = Translation.objects.using(alias).all()
        if user is not None:
            translations = translations.filter_access(user)

        custom_sources = (
            WorkflowSetting.objects.using(alias)
            .filter(
                source_language=source_language,
                project__component__translation__in=translations.filter(
                    language=target_language
                ),
            )
            .exists()
        )
        if not custom_sources:
            translations = translations.filter(
                component__source_language=source_language
            )
        translation_ids = translations.filter(language=target_language).values("id")
        units = (
            Unit.objects.using(alias)
            .filter(
                state__gte=STATE_TRANSLATED,
                translation_id__in=translation_ids,
            )
            .exclude_blocked()
        )
        if custom_sources:
            # Use native language columns without the plural-rule joins added
            # by with_effective_source().
            return units.filter(
                Q(
                    translation_parent__isnull=True,
                    translation__component__source_language=source_language,
                )
                | Q(translation_parent__translation__language=source_language),
                details__translation_parent__missing__isnull=True,
            )
        return units.alias(check_source=F("source")).filter(
            translation_parent__isnull=True
        )

    def get_matching_units(self, base, text: str, threshold: int):
        if threshold < 100:
            adjust_similarity_threshold(0.98)
        # Keep both searches on real, indexed columns. A CASE/COALESCE over
        # parent.target and source prevents using their trigram indexes.
        ordinary = self.get_matching_queryset(
            base.filter(translation_parent__isnull=True).alias(
                check_source=F("source")
            ),
            text,
            threshold,
        )
        custom = self.get_matching_queryset(
            base.filter(translation_parent__isnull=False).alias(
                check_source=F("translation_parent__target")
            ),
            text,
            threshold,
        )
        ordering = ordinary.query.order_by
        fields = (
            "pk",
            *(field.removeprefix("-") for field in ordering if field != "pk"),
        )
        # Sort only IDs and ranks, rather than complete units (including text
        # and JSON). The branches are disjoint, so UNION ALL needs no deduplication.
        candidates = (
            ordinary.order_by()
            .values_list(*fields)
            .union(custom.order_by().values_list(*fields), all=True)
            .order_by(*ordering)
        )
        for batch in batched(
            candidates.iterator(chunk_size=self.candidate_limit), self.candidate_limit
        ):
            ids = [row[0] for row in batch]
            units = self.prepare_queryset(
                Unit.objects.using(base.db).filter(pk__in=ids)
            ).in_bulk()
            for pk in ids:
                if pk in units:
                    yield units[pk]

    def get_matching_queryset(self, base, text: str, threshold: int):
        if threshold < 100:
            if use_trgm_fallback(text):
                queryset = self.get_short_query_matches(base, text)
            else:
                # Joined aliases dilute full-string similarity. Word matches
                # admit candidates; each alias is scored when yielding results.
                queryset = base.filter(
                    Q(check_source__trgm_search=text)
                    | (
                        self.multivalue_query()
                        & Q(check_source__trigram_word_similar=text)
                    )
                ).annotate(
                    match_similarity=Case(
                        When(
                            self.multivalue_query(),
                            then=TrigramWordSimilarity(text, "check_source"),
                        ),
                        default=TrigramSimilarity("check_source", text),
                    )
                )
                queryset = queryset.order_by("-match_similarity", "pk")
        else:
            queryset = base.filter(
                Q(check_source__lower__md5=MD5(Lower(Value(text))), check_source=text)
                | (
                    self.multivalue_query()
                    & Q(
                        check_source__regex=rf"(^|{PLURAL_SEPARATOR}){re.escape(text)}({PLURAL_SEPARATOR}|$)"
                    )
                )
            ).order_by("pk")

        return queryset.exclude(target="")

    def prepare_queryset(self, queryset):
        return queryset.exclude(target="").prefetch().prefetch_translation_parent()

    @staticmethod
    def multivalue_query() -> Q:
        return Q(
            translation__component__file_format__in=[
                key
                for key, format_cls in FILE_FORMATS.items()
                if format_cls.has_multiple_strings
            ]
        )

    def get_short_query_matches(self, base, text: str):
        max_source_length = max(len(text) + 4, len(text) * 2, 8)
        exact_source = Q(check_source__iexact=text) | (
            self.multivalue_query()
            & Q(
                check_source__iregex=rf"(^|{PLURAL_SEPARATOR}){re.escape(text)}({PLURAL_SEPARATOR}|$)"
            )
        )
        return (
            base.filter(Q(check_source__trgm_search=text) | exact_source)
            .annotate(
                short_query_rank=Case(
                    When(exact_source, then=Value(0)),
                    When(check_source__istartswith=text, then=Value(1)),
                    default=Value(2),
                    output_field=IntegerField(),
                ),
                source_length=Case(
                    When(exact_source, then=Value(len(text))),
                    default=Length("check_source"),
                ),
            )
            .filter(Q(source_length__lte=max_source_length) | self.multivalue_query())
            .order_by("short_query_rank", "source_length", "pk")
        )
