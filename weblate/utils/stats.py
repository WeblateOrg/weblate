# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import time
from datetime import datetime, timedelta
from itertools import chain
from operator import itemgetter
from types import GeneratorType
from typing import TYPE_CHECKING

import sentry_sdk
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Count, F, Model, Q
from django.db.models.functions import Length
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property

from weblate.checks.models import CHECKS
from weblate.lang.models import Language
from weblate.trans.mixins import BaseURLMixin
from weblate.trans.util import translation_percent
from weblate.utils.random import get_random_identifier
from weblate.utils.site import get_site_url
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_READONLY,
    STATE_TRANSLATED,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from weblate.trans.models import Component, Project

StatItem = int | float | str | datetime | None
StatDict = dict[str, StatItem]

BASICS = {
    "all",
    "fuzzy",
    "todo",
    "readonly",
    "nottranslated",
    "translated",
    "approved",
    "allchecks",
    "translated_checks",
    "dismissed_checks",
    "suggestions",
    "nosuggestions",
    "comments",
    "approved_suggestions",
    "unlabeled",
    "unapproved",
}
BASIC_KEYS = frozenset(
    (
        *(f"{x}_words" for x in BASICS),
        *(f"{x}_chars" for x in BASICS),
        *BASICS,
        "languages",
        "last_changed",
        "last_author",
        "recent_changes",
        "monthly_changes",
        "total_changes",
        "stats_timestamp",
    )
)
SOURCE_KEYS = frozenset(
    (
        *BASIC_KEYS,
        "source_strings",
        "source_words",
        "source_chars",
    )
)

# TODO: Drop in Weblate 6
LEGACY_KEYS = {
    "unapproved",
    "unapproved_chars",
    "unapproved_words",
    "recent_changes",
    "monthly_changes",
    "total_changes",
    "stats_timestamp",
}

SOURCE_MAP = {
    "source_chars": "all_chars",
    "source_words": "all_words",
    "source_strings": "all",
}


def zero_stats(keys):
    stats: StatDict = dict.fromkeys(keys, 0)
    stats["last_changed"] = None
    stats["last_author"] = None
    stats["stats_timestamp"] = 0
    return stats


def prefetch_stats(queryset):
    """Fetch stats from cache for a queryset."""
    # Force evaluating queryset/iterator, we need all objects
    objects = list(queryset)

    # This function can either accept queryset, in which case it is
    # returned with prefetched stats, or iterator, in which case new list
    # is returned.
    # This is needed to allow using such querysets further and to support
    # processing iterator when it is more effective.
    result = objects if isinstance(queryset, chain | GeneratorType) else queryset

    # Bail out in case the query is empty
    if not objects:
        return result

    # Use stats prefetch
    objects[0].stats.prefetch_many([i.stats for i in objects])

    return result


def get_non_glossary_stats(
    stats_obj: ProjectLanguageStats | ProjectStats | GlobalStats,
) -> dict[str, int]:
    """Return a dictionary with all, source_strings, and translated strings count excluding glossary content."""
    result = {
        "all": stats_obj.all,
        "translated": stats_obj.translated,
        "source_strings": getattr(stats_obj, "source_strings", stats_obj.all),
    }

    if isinstance(stats_obj, ProjectLanguageStats):
        from weblate.trans.models import Translation

        glossaries = Translation.objects.filter(
            language=stats_obj.language, component__in=stats_obj.project.glossaries
        ).prefetch()
    elif isinstance(stats_obj, ProjectStats):
        glossaries = stats_obj._object.glossaries  # noqa: SLF001
    elif isinstance(stats_obj, GlobalStats):
        from weblate.trans.models import Component

        glossaries = Component.objects.filter(is_glossary=True)
    else:
        # other stat types do not concern glossaries
        return result

    for glossary in prefetch_stats(glossaries):
        result["all"] -= glossary.stats.all
        result["translated"] -= glossary.stats.translated
        result["source_strings"] -= getattr(
            glossary.stats, "source_strings", glossary.stats.all
        )

    return result


class BaseStats:
    """Caching statistics calculator."""

    basic_keys = BASIC_KEYS
    is_ghost = False

    def __init__(self, obj) -> None:
        self._object = obj
        self._data: StatDict = {}
        self._loaded: bool = False
        self._pending_save: bool = False
        self.last_change_cache = None
        self._collected_update_objects: list[BaseStats] | None = None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}:{self.cache_key}>"

    @property
    def pk(self) -> int:
        return self._object.pk

    def get_absolute_url(self) -> str:
        return self._object.get_absolute_url()

    def get_translate_url(self) -> str:
        return self._object.get_translate_url()

    @property
    def obj(self):
        return self._object

    @property
    def stats(self):
        return self

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def set_data(self, data: StatDict) -> None:
        self._loaded = True
        self._data = data

    def get_data(self) -> StatDict:
        """
        Return a copy of data including percents.

        Used in stats endpoints.
        """
        self.ensure_loaded()
        percents = [
            "translated_percent",
            "approved_percent",
            "fuzzy_percent",
            "readonly_percent",
            "allchecks_percent",
            "translated_checks_percent",
            "translated_words_percent",
            "approved_words_percent",
            "fuzzy_words_percent",
            "readonly_words_percent",
            "allchecks_words_percent",
            "translated_checks_words_percent",
        ]
        data: StatDict = {
            percent: self.calculate_percent(percent) for percent in percents
        }
        data.update(self._data)
        return data

    @staticmethod
    def prefetch_many(stats) -> None:
        lookup = {i.cache_key: i for i in stats if not i.is_loaded}
        if not lookup:
            return
        data = cache.get_many(lookup.keys())
        for item, value in data.items():
            lookup[item].set_data(value)
        for item in set(lookup.keys()) - set(data.keys()):
            lookup[item].set_data({})

    @cached_property
    def has_review(self) -> bool:
        return True

    @cached_property
    def cache_key(self) -> str:
        return f"stats-{self._object.cache_key}"

    def remove_stats(self, *names: str) -> None:
        self.ensure_loaded()
        if not self._data:
            return
        changed = False
        for name in names:
            if name in self._data:
                del self._data[name]
                changed = True
        if changed:
            self.save()

    def ensure_loaded(self) -> None:
        """Load from cache if not already done."""
        if not self._loaded:
            self._data = self.load()
            self._loaded = True

    def aggregate_get(self, name: str) -> StatItem:
        """
        Fast getter for aggregation.

        - expects data is present
        - expects valid basic keys only
        - maps source keys
        """
        try:
            return self._data[name]
        except KeyError:
            # Handle source_* keys as virtual on translation level for easier aggregation
            if name.startswith("source_"):
                return self._data[SOURCE_MAP[name]]
            # Legacy keys were calculated on demand before and are precalculated
            # since Weblate 5.2, so they are missing on stats calculated before.
            # Using zero here is most likely a wrong value, but safe and cheap.
            # TODO: Drop in Weblate 6
            if name in LEGACY_KEYS:
                return 0
            raise

    def __getattr__(self, name: str):
        if name.startswith("_"):
            msg = f"Invalid stats for {self}: {name}"
            raise AttributeError(msg)

        self.ensure_loaded()

        # Calculate virtual percents
        if name.endswith("_percent"):
            return self.calculate_percent(name)

        if name == "stats_timestamp":
            # TODO: Drop in Weblate 6
            # Migration path for legacy stat data
            return self._data.get(name, 0)

        # Virtual fields
        if name == "translated_without_checks":
            return self.translated - self.translated_checks
        if name == "translated_without_checks_words":
            return self.translated_words - self.translated_checks_words
        if name == "translated_without_checks_chars":
            return self.translated_chars - self.translated_checks_chars

        # Calculate missing data
        if name not in self._data:
            was_pending = self._pending_save
            self._pending_save = True
            self.calculate_by_name(name)
            if name not in self._data:
                msg = f"Unsupported stats for {self}: {name}"
                raise AttributeError(msg)
            if not was_pending:
                self.save()
                self._pending_save = False

        return self._data[name]

    def calculate_by_name(self, name: str) -> None:
        if name in self.basic_keys:
            self.calculate_basic()
            self.save()

    def load(self) -> StatDict:
        return cache.get(self.cache_key, {})

    def delete(self):
        return cache.delete(self.cache_key)

    def save(self, update_parents: bool = True) -> None:
        """Save stats to cache."""
        cache.set(self.cache_key, self._data, 30 * 86400)

    def get_update_objects(self):
        yield GlobalStats()

    def collect_update_objects(self) -> None:
        # Use list to force materializing the generator
        self._collected_update_objects = list(self.get_update_objects())

    def _iterate_update_objects(
        self, *, extra_objects: Iterable[BaseStats] | None = None
    ):
        """Get list of stats to update."""
        stat_objects: Iterable[BaseStats]
        if self._collected_update_objects is not None:
            stat_objects = self._collected_update_objects
            self._collected_update_objects = None
        else:
            stat_objects = self.get_update_objects()
        if extra_objects:
            stat_objects = chain(stat_objects, extra_objects)

        # Prefetch stats data from cache
        fetched_stat_objects: list[BaseStats] = prefetch_stats(stat_objects)

        # Discard references to no longer needed objects
        while fetched_stat_objects:
            yield fetched_stat_objects.pop(0)

    def update_parents(
        self, *, extra_objects: Iterable[BaseStats] | None = None
    ) -> None:
        """Update parent statistics."""
        for stat in self._iterate_update_objects(extra_objects=extra_objects):
            if self.stats_timestamp and self.stats_timestamp <= stat.stats_timestamp:
                self._object.log_debug("skipping update of %s", stat)
            else:
                self._object.log_debug("updating stats %s", stat)
                stat.update_stats()

    def clear(self) -> None:
        """Clear local cache."""
        self._loaded = True
        self._data = {}

    def store(self, key: str, value: StatItem) -> None:
        if value is None and not key.startswith("last_"):
            self._data[key] = 0
        else:
            self._data[key] = value

    def update_stats(self, update_parents: bool = True) -> None:
        self.clear()
        if settings.STATS_LAZY:
            self.save(update_parents=update_parents)
        else:
            self.calculate_basic()
            self.save(update_parents=update_parents)

    def calculate_basic(self) -> None:
        with sentry_sdk.start_span(op="stats", name=f"CALCULATE {self.cache_key}"):
            self.ensure_loaded()
            self._calculate_basic()

    def _calculate_basic(self) -> None:
        raise NotImplementedError

    def calculate_percent(self, item: str) -> float:
        """Calculate percent value for given item."""
        base = item[:-8]

        if base.endswith("_words"):
            total = self.all_words
        elif base.endswith("_chars"):
            total = self.all_chars
        else:
            total = self.all

        if self.has_review:
            completed = {"approved", "approved_words", "approved_chars"}
        else:
            completed = {"translated", "translated_words", "translated_chars"}

        return translation_percent(
            getattr(self, base), total, zero_complete=(base in completed)
        )

    @property
    def waiting_review_percent(self):
        return self.translated_percent - self.approved_percent - self.readonly_percent

    @property
    def waiting_review(self):
        return self.translated - self.approved - self.readonly

    @property
    def waiting_review_words_percent(self):
        return (
            self.translated_words_percent
            - self.approved_words_percent
            - self.readonly_words_percent
        )

    @property
    def waiting_review_words(self):
        return self.translated_words - self.approved_words - self.readonly_words

    @property
    def waiting_review_chars_percent(self):
        return (
            self.translated_chars_percent
            - self.approved_chars_percent
            - self.readonly_chars_percent
        )

    @property
    def waiting_review_chars(self):
        return self.translated_chars - self.approved_chars - self.readonly_chars


class DummyTranslationStats(BaseStats):
    """
    Dummy stats to report 0 in all cases.

    Used when given language does not exist in a component.
    """

    def __init__(self, obj) -> None:
        super().__init__(obj)
        self.language = obj

    @property
    def pk(self) -> int:
        return 100000 + self.language.pk

    @cached_property
    def cache_key(self) -> str:
        return ""

    def save(self, update_parents: bool = True) -> None:
        return

    def load(self) -> StatDict:
        return {}

    def _calculate_basic(self) -> None:
        self._data = zero_stats(self.basic_keys)


class TranslationStats(BaseStats):
    """Per translation stats."""

    @cached_property
    def is_source(self):
        return self._object.is_source

    def save(self, update_parents: bool = True) -> None:
        from weblate.utils.tasks import update_translation_stats_parents

        super().save()

        if update_parents:
            if settings.CELERY_TASK_ALWAYS_EAGER:
                transaction.on_commit(self.update_parents)
            else:
                pk = self._object.pk
                update_translation_stats_parents.delay_on_commit(pk)

    def get_update_objects(self, *, full: bool = True):
        translation = self._object
        component = translation.component

        # Language
        yield translation.language.stats

        # Project / language
        yield component.project.stats.get_single_language_stats(translation.language)

        # Category / language
        category = component.category
        while category:
            yield category.stats.get_single_language_stats(translation.language)
            category = category.category

        if full:
            # Component
            yield component.stats
            # Component list, category, project and global
            yield from component.stats.get_update_objects()

    @property
    def language(self):
        return self._object.language

    @cached_property
    def has_review(self):
        return self._object.enable_review

    def _calculate_basic(self) -> None:  # noqa: PLR0914
        values = (
            "state",
            "num_words",
            "active_checks_count",
            "dismissed_checks_count",
            "suggestion_count",
            "source_label_count",
            "label_count",
            "comment_count",
            "num_chars",
        )

        # Calculate summary for each unit in the database.
        # We only need presence check, not actual count, but using Exists(OuterRef())
        # creates a subquery for each field, while Count() creates a single join
        # and calculates based on that, what performs better.
        units = self._object.unit_set.annotate(
            active_checks_count=Count("check", filter=Q(check__dismissed=False)),
            dismissed_checks_count=Count("check", filter=Q(check__dismissed=True)),
            suggestion_count=Count("suggestion"),
            source_label_count=Count("source_unit__labels"),
            label_count=Count("source_unit__labels"),
            comment_count=Count("comment", filter=Q(comment__resolved=False)),
            num_chars=Length("source"),
        ).values_list(*values)

        (
            get_state,
            get_num_words,
            get_active_checks_count,
            get_dismissed_checks_count,
            get_suggestion_count,
            get_source_label_count,
            get_label_count,
            get_comment_count,
            get_num_chars,
        ) = (itemgetter(i) for i in range(len(values)))

        # Sum stats in Python, this is way faster than conditional sums in the database
        units_all = units
        units_fuzzy = [unit for unit in units if get_state(unit) == STATE_FUZZY]
        units_readonly = [unit for unit in units if get_state(unit) == STATE_READONLY]
        units_nottranslated = [unit for unit in units if get_state(unit) == STATE_EMPTY]
        units_unapproved = [
            unit for unit in units if get_state(unit) == STATE_TRANSLATED
        ]
        units_approved = [unit for unit in units if get_state(unit) == STATE_APPROVED]
        units_translated = [
            unit for unit in units if get_state(unit) >= STATE_TRANSLATED
        ]
        units_todo = [unit for unit in units if get_state(unit) < STATE_TRANSLATED]
        units_unlabeled = [
            unit
            for unit in units
            if not get_source_label_count(unit) and not get_label_count(unit)
        ]
        units_allchecks = [unit for unit in units if get_active_checks_count(unit)]
        units_translated_checks = [
            unit
            for unit in units
            if get_active_checks_count(unit)
            and get_state(unit) in {STATE_TRANSLATED, STATE_APPROVED}
        ]
        units_dismissed_checks = [
            unit for unit in units if get_dismissed_checks_count(unit)
        ]
        units_suggestions = [unit for unit in units if get_suggestion_count(unit)]
        units_nosuggestions = [
            unit
            for unit in units
            if not get_suggestion_count(unit) and get_state(unit) < STATE_TRANSLATED
        ]
        units_approved_suggestions = [
            unit
            for unit in units
            if get_suggestion_count(unit) and get_state(unit) == STATE_APPROVED
        ]
        units_comments = [unit for unit in units if get_comment_count(unit)]

        # Store in a cache
        self.store("all", len(units_all))
        self.store("all_words", sum(get_num_words(unit) for unit in units_all))
        self.store("all_chars", sum(get_num_chars(unit) for unit in units_all))
        self.store("fuzzy", len(units_fuzzy))
        self.store("fuzzy_words", sum(get_num_words(unit) for unit in units_fuzzy))
        self.store("fuzzy_chars", sum(get_num_chars(unit) for unit in units_fuzzy))
        self.store("readonly", len(units_readonly))
        self.store(
            "readonly_words", sum(get_num_words(unit) for unit in units_readonly)
        )
        self.store(
            "readonly_chars", sum(get_num_chars(unit) for unit in units_readonly)
        )
        self.store("translated", len(units_translated))
        self.store(
            "translated_words", sum(get_num_words(unit) for unit in units_translated)
        )
        self.store(
            "translated_chars", sum(get_num_chars(unit) for unit in units_translated)
        )
        self.store("todo", len(units_todo))
        self.store("todo_words", sum(get_num_words(unit) for unit in units_todo))
        self.store("todo_chars", sum(get_num_chars(unit) for unit in units_todo))
        self.store("nottranslated", len(units_nottranslated))
        self.store(
            "nottranslated_words",
            sum(get_num_words(unit) for unit in units_nottranslated),
        )
        self.store(
            "nottranslated_chars",
            sum(get_num_chars(unit) for unit in units_nottranslated),
        )
        # Review workflow
        self.store("approved", len(units_approved))
        self.store(
            "approved_words", sum(get_num_words(unit) for unit in units_approved)
        )
        self.store(
            "approved_chars", sum(get_num_chars(unit) for unit in units_approved)
        )
        self.store("unapproved", len(units_unapproved))
        self.store(
            "unapproved_words", sum(get_num_words(unit) for unit in units_unapproved)
        )
        self.store(
            "unapproved_chars", sum(get_num_chars(unit) for unit in units_unapproved)
        )
        # Labels
        self.store("unlabeled", len(units_unlabeled))
        self.store(
            "unlabeled_words", sum(get_num_words(unit) for unit in units_unlabeled)
        )
        self.store(
            "unlabeled_chars", sum(get_num_chars(unit) for unit in units_unlabeled)
        )
        # Checks
        self.store("allchecks", len(units_allchecks))
        self.store(
            "allchecks_words", sum(get_num_words(unit) for unit in units_allchecks)
        )
        self.store(
            "allchecks_chars", sum(get_num_chars(unit) for unit in units_allchecks)
        )
        self.store("translated_checks", len(units_translated_checks))
        self.store(
            "translated_checks_words",
            sum(get_num_words(unit) for unit in units_translated_checks),
        )
        self.store(
            "translated_checks_chars",
            sum(get_num_chars(unit) for unit in units_translated_checks),
        )
        self.store("dismissed_checks", len(units_dismissed_checks))
        self.store(
            "dismissed_checks_words",
            sum(get_num_words(unit) for unit in units_dismissed_checks),
        )
        self.store(
            "dismissed_checks_chars",
            sum(get_num_chars(unit) for unit in units_dismissed_checks),
        )
        # Suggestions
        self.store("suggestions", len(units_suggestions))
        self.store(
            "suggestions_words", sum(get_num_words(unit) for unit in units_suggestions)
        )
        self.store(
            "suggestions_chars", sum(get_num_chars(unit) for unit in units_suggestions)
        )
        self.store("nosuggestions", len(units_nosuggestions))
        self.store(
            "nosuggestions_words",
            sum(get_num_words(unit) for unit in units_nosuggestions),
        )
        self.store(
            "nosuggestions_chars",
            sum(get_num_chars(unit) for unit in units_nosuggestions),
        )
        self.store("approved_suggestions", len(units_approved_suggestions))
        self.store(
            "approved_suggestions_words",
            sum(get_num_words(unit) for unit in units_approved_suggestions),
        )
        self.store(
            "approved_suggestions_chars",
            sum(get_num_chars(unit) for unit in units_approved_suggestions),
        )
        # Comments
        self.store("comments", len(units_comments))
        self.store(
            "comments_words", sum(get_num_words(unit) for unit in units_comments)
        )
        self.store(
            "comments_chars", sum(get_num_chars(unit) for unit in units_comments)
        )

        # There is single language here, but it is aggregated at higher levels
        self.store("languages", 1)

        # Last change timestamp
        self.fetch_last_change()

        self.count_changes()

        # Store timestamp
        self.store("stats_timestamp", time.time())

    def get_last_change_obj(self):
        from weblate.trans.models import Change

        # This is set in Change.save
        if self.last_change_cache is not None:
            return self.last_change_cache

        cache_key = Change.get_last_change_cache_key(self._object.pk)
        change_pk = cache.get(cache_key)
        if change_pk == 0:
            # No change
            return None
        if change_pk is not None:
            try:
                return Change.objects.get(pk=change_pk)
            except Change.DoesNotExist:
                pass
        try:
            last_change = self._object.change_set.order()[0]
        except IndexError:
            Change.store_last_change(self._object, None)
            return None
        last_change.update_cache_last_change()
        return last_change

    def fetch_last_change(self) -> None:
        last_change = self.get_last_change_obj()

        if last_change is None:
            self.store("last_changed", None)
            self.store("last_author", None)
        else:
            self.store("last_changed", last_change.timestamp)
            self.store("last_author", last_change.author_id)

    def count_changes(self) -> None:
        if self.last_changed:
            monthly = timezone.now() - timedelta(days=30)
            recently = self.last_changed - timedelta(hours=6)
            changes = self._object.change_set.content().aggregate(
                total=Count("id"),
                recent=Count("id", filter=Q(timestamp__gt=recently)),
                monthly=Count("id", filter=Q(timestamp__gt=monthly)),
            )
            self.store("recent_changes", changes["recent"])
            self.store("monthly_changes", changes["monthly"])
            self.store("total_changes", changes["total"])
        else:
            self.store("recent_changes", 0)
            self.store("monthly_changes", 0)
            self.store("total_changes", 0)

    def calculate_by_name(self, name: str) -> None:
        super().calculate_by_name(name)
        if name.startswith("check:"):
            self.calculate_checks()
        elif name.startswith("label:"):
            self.calculate_labels()

    def calculate_checks(self) -> None:
        """Prefetch check stats."""
        self.ensure_loaded()
        allchecks = {check.url_id for check in CHECKS.values()}
        stats = (
            self._object.unit_set.filter(check__dismissed=False)
            .values("check__name")
            .annotate_stats()
        )
        for check, strings, words, chars in stats.values_list(
            "check__name", "strings", "words", "chars"
        ):
            # Filtering here is way more effective than in SQL
            if check is None:
                continue
            check = f"check:{check}"
            self.store(check, strings)
            self.store(f"{check}_words", words)
            self.store(f"{check}_chars", chars)
            allchecks.discard(check)
        for check in allchecks:
            self.store(check, 0)
            self.store(f"{check}_words", 0)
            self.store(f"{check}_chars", 0)
        self.save()

    def calculate_labels(self) -> None:
        """Prefetch check stats."""
        from weblate.trans.models.label import TRANSLATION_LABELS

        self.ensure_loaded()
        alllabels = set(
            self._object.component.project.label_set.values_list("name", flat=True)
        )
        stats = (
            self._object.unit_set.values("source_unit__labels__name")
            .annotate_stats()
            .values_list("source_unit__labels__name", "strings", "words", "chars")
        )
        translation_stats = (
            self._object.unit_set.filter(labels__name__in=TRANSLATION_LABELS)
            .values("labels__name")
            .annotate_stats()
            .values_list("labels__name", "strings", "words", "chars")
        )

        for label_name, strings, words, chars in chain(stats, translation_stats):
            # Filtering here is way more effective than in SQL
            if label_name is None:
                continue
            label = f"label:{label_name}"
            self.store(label, strings)
            self.store(f"{label}_words", words)
            self.store(f"{label}_chars", chars)
            alllabels.discard(label_name)
        for label_name in alllabels:
            label = f"label:{label_name}"
            self.store(label, 0)
            self.store(f"{label}_words", 0)
            self.store(f"{label}_chars", 0)
        self.save()


class AggregatingStats(BaseStats):
    basic_keys = SOURCE_KEYS
    sum_source_keys = True

    def get_child_objects(self) -> Iterable[Model]:
        raise NotImplementedError

    def get_category_objects(self):
        return []

    def calculate_source(self, stats: dict, all_stats: list) -> None:
        return

    def _calculate_basic(self) -> None:
        stats = zero_stats(self.basic_keys)
        all_stats = [
            obj.stats
            for obj in prefetch_stats(
                chain(self.get_child_objects(), self.get_category_objects())
            )
        ]

        # Ensure all objects have data available so that we can use _dict directly
        for stats_obj in all_stats:
            if "all" not in stats_obj._data:  # noqa: SLF001
                stats_obj.calculate_basic()
                stats_obj.save()

        for item in self.basic_keys:
            if not self.sum_source_keys and item.startswith("source_"):
                # Handle in calculate_source when logic for source strings differs
                continue

            # Extract all values by dedicated getter
            values = (stats_obj.aggregate_get(item) for stats_obj in all_stats)

            if item == "stats_timestamp":
                stats[item] = max(values, default=time.time())
            elif item == "last_changed":
                # We need to access values twice here
                values_list = list(values)
                stats[item] = max_last_changed = max(
                    (value for value in values_list if value is not None), default=None
                )
                if max_last_changed is not None:
                    offset = values_list.index(max_last_changed)
                    stats["last_author"] = all_stats[offset].last_author
            elif item == "last_author":
                # The last_author is calculated together with last_changed
                continue
            else:
                stats[item] = sum(values)

        if not self.sum_source_keys:
            self.calculate_source(stats, all_stats)

        for key, value in stats.items():
            self.store(key, value)


class SingleLanguageStats(AggregatingStats):
    def _calculate_basic(self) -> None:
        super()._calculate_basic()
        self.store("languages", 1)

    def get_single_language_stats(self, language):
        return self

    @cached_property
    def is_source(self):
        return self.obj.is_source


class ParentAggregatingStats(AggregatingStats):
    sum_source_keys = True


class LanguageStats(AggregatingStats):
    def get_child_objects(self):
        return self._object.translation_set.only("id", "language")

    @property
    def language(self):
        return self._object


class ComponentStats(AggregatingStats):
    sum_source_keys = False

    def get_child_objects(self):
        return self._object.translation_set.only("id", "component", "language")

    @cached_property
    def has_review(self):
        return self._object.enable_review

    def calculate_source(self, stats: dict, all_stats: list) -> None:
        """Fetch source info from source translation."""
        for obj in all_stats:
            if obj.is_source:
                stats["source_chars"] = obj.all_chars
                stats["source_words"] = obj.all_words
                stats["source_strings"] = obj.all
                break

    def get_update_objects(self) -> Iterable[BaseStats]:
        # Component lists
        for clist in self._object.componentlist_set.all():
            yield clist.stats

        if self._object.category:
            # Category
            yield self._object.category.stats
            # Category parents, project and global
            yield from self._object.category.stats.get_update_objects()
        else:
            # Project
            yield self._object.project.stats
            # Global
            yield from self._object.project.stats.get_update_objects()

    def update_language_stats_parents(self) -> None:
        # Fetch language stats to update
        extras: Iterable[Iterable[BaseStats]] = (
            translation.stats.get_update_objects(full=False)
            for translation in prefetch_stats(
                self.get_child_objects().select_related("language")
            )
        )

        # Update all parents
        self.update_parents(extra_objects=chain.from_iterable(extras))

    def update_language_stats(self) -> None:
        from weblate.utils.tasks import update_language_stats_parents

        # Update languages
        for translation in prefetch_stats(self.get_child_objects()):
            translation.stats.update_stats(update_parents=False)

        # Update our stats
        self.update_stats()

        # Update all parents
        if settings.CELERY_TASK_ALWAYS_EAGER:
            transaction.on_commit(self.update_language_stats_parents)
        else:
            pk = self._object.pk
            update_language_stats_parents.delay_on_commit(pk)

    def get_language_stats(self):
        return (
            translation.stats
            for translation in prefetch_stats(
                self._object.translation_set.select_related("language")
            )
        )

    def get_single_language_stats(self, language):
        try:
            return TranslationStats(self._object.translation_set.get(language=language))
        except ObjectDoesNotExist:
            return DummyTranslationStats(language)


class ProjectLanguageComponent:
    is_glossary = False

    def __init__(self, parent) -> None:
        self.slug = "-"
        self.parent = parent

    @property
    def translation_set(self):
        return self.parent.translation_set

    @property
    def context_label(self):
        return self.translation_set[0].component.context_label

    @property
    def source_language(self):
        return self.translation_set[0].component.source_language


class ProjectLanguage(BaseURLMixin):
    """Wrapper class used in project-language listings and stats."""

    remove_permission = "translation.delete"
    settings_permission = "project.edit"

    def __init__(self, project, language: Language) -> None:
        self.project = project
        self.language = language
        self.component = ProjectLanguageComponent(self)

    def __str__(self) -> str:
        return f"{self.project} - {self.language}"

    @property
    def code(self):
        return self.language.code

    @cached_property
    def stats(self):
        return ProjectLanguageStats(self)

    def get_share_url(self):
        """Return absolute URL usable for sharing."""
        return get_site_url(
            reverse(
                "engage",
                kwargs={"path": self.get_url_path()},
            )
        )

    def get_widgets_url(self) -> str:
        """Return absolute URL for widgets."""
        return f"{self.project.get_widgets_url()}?lang={self.language.code}"

    @cached_property
    def pk(self) -> str:
        return f"{self.project.pk}-{self.language.pk}"

    @cached_property
    def cache_key(self) -> str:
        return f"{self.project.cache_key}-{self.language.pk}"

    def get_url_path(self):
        return [*self.project.get_url_path(), "-", self.language.code]

    def get_absolute_url(self) -> str:
        return reverse("show", kwargs={"path": self.get_url_path()})

    def get_translate_url(self):
        return reverse("translate", kwargs={"path": self.get_url_path()})

    @cached_property
    def translation_set(self):
        all_langs = self.language.translation_set.prefetch()
        result = all_langs.filter(component__project=self.project)
        if self.project.has_shared_components:
            result |= all_langs.filter(component__links=self.project)
        for item in result:
            item.is_shared = (
                None
                if item.component.project == self.project
                else item.component.project
            )
        return sorted(
            result,
            key=lambda trans: (trans.component.priority, trans.component.name.lower()),
        )

    @cached_property
    def is_source(self):
        return self.language.id in self.project.source_language_ids

    @cached_property
    def change_set(self):
        return self.project.change_set.filter(language=self.language)

    @cached_property
    def workflow_settings(self):
        from weblate.trans.models.workflow import WorkflowSetting

        workflow_settings = WorkflowSetting.objects.filter(
            Q(project=None) | Q(project=self.project),
            language=self.language,
        ).order_by(F("project").desc(nulls_last=True))
        if len(workflow_settings) == 0:
            return None
        # Project specific is first, project NULL is last
        return workflow_settings[0]


class ProjectLanguageStats(SingleLanguageStats):
    def __init__(self, obj: ProjectLanguage) -> None:
        self.language = obj.language
        self.project = obj.project
        super().__init__(obj)
        obj.stats = self

    @cached_property
    def has_review(self):
        return self.project.source_review or self.project.translation_review

    def get_child_objects(self):
        return self.language.translation_set.filter(
            component__project=self.project
        ).only("id", "language")


class CategoryLanguage(BaseURLMixin):
    """Wrapper class used in category-language listings and stats."""

    remove_permission = "translation.delete"

    def __init__(self, category, language: Language) -> None:
        self.category = category
        self.language = language
        self.component = ProjectLanguageComponent(self)

    def __str__(self) -> str:
        return f"{self.category} - {self.language}"

    @property
    def code(self):
        return self.language.code

    @property
    def name(self):
        return self.category.name

    @cached_property
    def stats(self):
        return CategoryLanguageStats(self)

    @cached_property
    def pk(self) -> str:
        return f"{self.category.pk}-{self.language.pk}"

    @cached_property
    def cache_key(self) -> str:
        return f"{self.category.cache_key}-{self.language.pk}"

    def get_url_path(self):
        return [*self.category.get_url_path(), "-", self.language.code]

    def get_absolute_url(self) -> str:
        return reverse("show", kwargs={"path": self.get_url_path()})

    def get_translate_url(self):
        return reverse("translate", kwargs={"path": self.get_url_path()})

    @cached_property
    def translation_set(self):
        result = self.language.translation_set.filter(
            component__category=self.category
        ).prefetch()
        for item in result:
            item.is_shared = (
                None
                if item.component.project == self.category.project
                else item.component.project
            )
        return sorted(
            result,
            key=lambda trans: (trans.component.priority, trans.component.name.lower()),
        )

    @cached_property
    def is_source(self):
        return self.language.id in self.category.source_language_ids

    @cached_property
    def change_set(self):
        return self.language.change_set.for_category(self.category)


class CategoryLanguageStats(SingleLanguageStats):
    def __init__(self, obj: CategoryLanguage) -> None:
        self.language = obj.language
        self.category = obj.category
        super().__init__(obj)
        obj.stats = self

    @cached_property
    def has_review(self):
        return (
            self.category.project.source_review
            or self.category.project.translation_review
        )

    def get_category_objects(self):
        return [
            CategoryLanguage(category, self.language)
            for category in self.category.stats.get_category_objects()
        ]

    def get_child_objects(self):
        return self.language.translation_set.filter(
            component__category=self.category
        ).only("id", "language")


class CategoryStats(ParentAggregatingStats):
    def get_update_objects(self):
        if self._object.category:
            yield self._object.category.stats
            yield from self._object.category.stats.get_update_objects()
        else:
            # Global
            yield from self._object.project.stats.get_update_objects()

    def get_child_objects(self):
        return self._object.component_set.only("id", "category", "check_flags")

    def get_category_objects(self):
        return self._object.category_set.only("id", "category")

    def get_single_language_stats(self, language):
        return CategoryLanguageStats(CategoryLanguage(self._object, language))

    def get_language_stats(self):
        return prefetch_stats(
            self.get_single_language_stats(language)
            for language in self._object.languages
        )


class ProjectStats(ParentAggregatingStats):
    @cached_property
    def has_review(self):
        return self._object.enable_review

    def get_child_objects(self):
        return self._object.component_set.only("id", "project", "check_flags")

    def get_single_language_stats(self, language):
        return ProjectLanguageStats(ProjectLanguage(self._object, language))

    def get_language_stats(self):
        return prefetch_stats(
            self.get_single_language_stats(language)
            for language in self._object.languages
        )

    def _calculate_basic(self) -> None:
        super()._calculate_basic()
        self.store("languages", self._object.languages.count())


class ComponentListStats(ParentAggregatingStats):
    def get_child_objects(self):
        return self._object.components.only("id", "componentlist")


class GlobalStats(ParentAggregatingStats):
    def __init__(self) -> None:
        super().__init__(None)

    def get_child_objects(self):
        from weblate.trans.models import Project

        return Project.objects.only("id", "access_control")

    def _calculate_basic(self) -> None:
        super()._calculate_basic()
        self.store("languages", Language.objects.have_translation().count())

    @cached_property
    def cache_key(self) -> str:
        return "stats-global"

    def get_single_language_stats(self, language):
        return LanguageStats(language)

    def get_language_stats(self):
        return prefetch_stats(
            self.get_single_language_stats(language)
            for language in Language.objects.have_translation()
        )

    # The following fields are used in MetricsSerializer in API
    def get_languages(self):
        return Language.objects.count()

    def get_users(self):
        from weblate.auth.models import User

        return User.objects.count()

    def get_projects(self):
        from weblate.trans.models import Project

        return Project.objects.count()

    def get_components(self):
        from weblate.trans.models import Component

        return Component.objects.count()

    def get_translations(self):
        from weblate.trans.models import Translation

        return Translation.objects.count()

    def get_checks(self):
        from weblate.checks.models import Check

        return Check.objects.count()

    def get_configuration_errors(self):
        from weblate.wladmin.models import ConfigurationError

        return ConfigurationError.objects.filter(ignored=False).count()

    def get_suggestions(self):
        from weblate.trans.models import Suggestion

        return Suggestion.objects.count()

    def get_celery_queues(self):
        from weblate.utils.celery import get_queue_stats

        return get_queue_stats()

    def get_name(self):
        return settings.SITE_TITLE


class GhostStats(BaseStats):
    basic_keys = SOURCE_KEYS
    is_ghost = True

    def __init__(self, base=None) -> None:
        super().__init__(None)
        self.base = base

    @cached_property
    def pk(self):
        return get_random_identifier()

    def _calculate_basic(self) -> None:
        stats = zero_stats(self.basic_keys)
        if self.base is not None:
            for key in "all", "all_words", "all_chars":
                stats[key] = getattr(self.base, key)
            stats["todo"] = stats["all"]
            stats["todo_words"] = stats["all_words"]
            stats["todo_chars"] = stats["all_chars"]
        for key, value in stats.items():
            self.store(key, value)

    @cached_property
    def cache_key(self) -> str:
        return "stats-zero"

    def save(self, update_parents: bool = True) -> None:
        pass

    def load(self) -> StatDict:
        return {}

    def get_absolute_url(self) -> str:
        return ""


class GhostProjectLanguageStats(GhostStats):
    language: Language
    component: Component
    is_shared: Project | None
    is_source: bool = False

    def __init__(
        self, component: Component, language: Language, is_shared: Project | None = None
    ) -> None:
        super().__init__(component.stats)
        self.language = language
        self.component = component
        self.is_shared = is_shared
