# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import timedelta
from itertools import chain
from time import monotonic
from types import GeneratorType

import sentry_sdk
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import Length
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property

from weblate.checks.models import CHECKS
from weblate.lang.models import Language
from weblate.trans.mixins import BaseURLMixin
from weblate.trans.util import translation_percent
from weblate.utils.db import conditional_sum
from weblate.utils.random import get_random_identifier
from weblate.utils.site import get_site_url
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_READONLY,
    STATE_TRANSLATED,
)

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

SOURCE_MAP = {
    "source_chars": "all_chars",
    "source_words": "all_words",
    "source_strings": "all",
}


def zero_stats(keys):
    stats = {item: 0 for item in keys}
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
    result = objects if isinstance(queryset, GeneratorType) else queryset

    # Bail out in case the query is empty
    if not objects:
        return result

    # Use stats prefetch
    objects[0].stats.prefetch_many([i.stats for i in objects])

    return result


class BaseStats:
    """Caching statistics calculator."""

    basic_keys = BASIC_KEYS
    is_ghost = False

    def __init__(self, obj):
        self._object = obj
        self._data = None
        self._pending_save = False
        self.last_change_cache = None

    @property
    def pk(self):
        return self._object.pk

    def get_absolute_url(self):
        return self._object.get_absolute_url()

    def get_translate_url(self):
        return self._object.get_translate_url()

    @property
    def obj(self):
        return self._object

    @property
    def stats(self):
        return self

    @property
    def is_loaded(self):
        return self._data is not None

    def set_data(self, data):
        self._data = data

    def get_data(self):
        """
        Return a copy of data including percents.

        Used in stats endpoints.
        """
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
        data = {percent: self.calculate_percent(percent) for percent in percents}
        data.update(self._data)
        return data

    @staticmethod
    def prefetch_many(stats):
        lookup = {i.cache_key: i for i in stats if not i.is_loaded}
        if not lookup:
            return
        data = cache.get_many(lookup.keys())
        for item, value in data.items():
            lookup[item].set_data(value)
        for item in set(lookup.keys()) - set(data.keys()):
            lookup[item].set_data({})

    @cached_property
    def has_review(self):
        return True

    @cached_property
    def cache_key(self):
        return f"stats-{self._object.cache_key}"

    def ensure_loaded(self):
        """Load from cache if not already done."""
        if self._data is None:
            self._data = self.load()

    def aggregate_get(self, name: str):
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
            raise

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(f"Invalid stats for {self}: {name}")

        self.ensure_loaded()

        # Calculate virtual percents
        if name.endswith("_percent"):
            return self.calculate_percent(name)

        if name == "stats_timestamp":
            # TODO: Drop in Weblate 5.3
            # Migration path for legacy stat data
            return self._data.get(name, 0)

        # Calculate missing data
        if name not in self._data:
            was_pending = self._pending_save
            self._pending_save = True
            self.calculate_by_name(name)
            if name not in self._data:
                raise AttributeError(f"Unsupported stats for {self}: {name}")
            if not was_pending:
                self.save()
                self._pending_save = False

        return self._data[name]

    def calculate_by_name(self, name: str):
        if name in self.basic_keys:
            self.calculate_basic()
            self.save()

    def load(self):
        return cache.get(self.cache_key, {})

    def save(self, update_parents: bool = True):
        """Save stats to cache."""
        cache.set(self.cache_key, self._data, 30 * 86400)

    def get_update_objects(self):
        yield GlobalStats()

    def update_parents(self, extra_objects: list[BaseStats] | None = None):
        # Get unique list of stats to update.
        # This preserves ordering so that closest ones are updated first.
        stat_objects = {stat.cache_key: stat for stat in self.get_update_objects()}
        if extra_objects:
            for stat in extra_objects:
                stat_objects[stat.cache_key] = stat

        # Update stats
        for stat in prefetch_stats(stat_objects.values()):
            if self.stats_timestamp and self.stats_timestamp <= stat.stats_timestamp:
                continue
            self._object.log_debug("updating stats for %s", stat._object)
            stat.update_stats()

    def clear(self):
        """Clear local cache."""
        self._data = {}

    def store(self, key, value):
        if value is None and not key.startswith("last_"):
            self._data[key] = 0
        else:
            self._data[key] = value

    def update_stats(self, update_parents: bool = True):
        self.clear()
        if settings.STATS_LAZY:
            self.save(update_parents=update_parents)
        else:
            self.calculate_basic()
            self.save(update_parents=update_parents)

    def calculate_basic(self):
        with sentry_sdk.start_span(
            op="stats", description=f"CALCULATE {self.cache_key}"
        ):
            self.ensure_loaded()
            self._calculate_basic()
            # Store timestamp
            self.store("stats_timestamp", monotonic())

    def _calculate_basic(self):
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

    def __init__(self, obj):
        super().__init__(obj)
        self.language = obj

    @property
    def pk(self):
        return f"l-{self.language.pk}"

    def cache_key(self):
        return None

    def save(self, update_parents: bool = True):
        return

    def load(self):
        return {}

    def _calculate_basic(self):
        self._data = zero_stats(self.basic_keys)


class TranslationStats(BaseStats):
    """Per translation stats."""

    def save(self, update_parents: bool = True):
        from weblate.utils.tasks import update_translation_stats_parents

        super().save()

        if update_parents:
            if settings.CELERY_TASK_ALWAYS_EAGER:
                transaction.on_commit(self.update_parents)
            else:
                pk = self._object.pk
                transaction.on_commit(
                    lambda: update_translation_stats_parents.delay(pk)
                )

    def get_update_objects(self):
        yield self._object.language.stats
        yield from self._object.language.stats.get_update_objects()

        yield self._object.component.stats
        yield from self._object.component.stats.get_update_objects()

        project_language = ProjectLanguage(
            project=self._object.component.project, language=self._object.language
        )
        yield project_language.stats
        yield from project_language.stats.get_update_objects()

        yield from super().get_update_objects()

    @property
    def language(self):
        return self._object.language

    @cached_property
    def has_review(self):
        return self._object.enable_review

    def _calculate_basic(self):
        # Calculate summary for each unit in the database
        base = self._object.unit_set.annotate(
            active_checks_count=Count("check", filter=Q(check__dismissed=False)),
            dismissed_checks_count=Count("check", filter=Q(check__dismissed=True)),
            suggestion_count=Count("suggestion"),
            label_count=Count("source_unit__labels"),
            comment_count=Count("comment", filter=Q(comment__resolved=False)),
            num_chars=Length("source"),
        )

        # Use local variables instead of dict for improved performance
        stat_all = 0
        stat_all_words = 0
        stat_all_chars = 0
        stat_fuzzy = 0
        stat_fuzzy_words = 0
        stat_fuzzy_chars = 0
        stat_readonly = 0
        stat_readonly_words = 0
        stat_readonly_chars = 0
        stat_translated = 0
        stat_translated_words = 0
        stat_translated_chars = 0
        stat_todo = 0
        stat_todo_words = 0
        stat_todo_chars = 0
        stat_nottranslated = 0
        stat_nottranslated_words = 0
        stat_nottranslated_chars = 0
        # Review workflow
        stat_approved = 0
        stat_approved_words = 0
        stat_approved_chars = 0
        stat_unapproved = 0
        stat_unapproved_words = 0
        stat_unapproved_chars = 0
        # Labels
        stat_unlabeled = 0
        stat_unlabeled_words = 0
        stat_unlabeled_chars = 0
        # Checks
        stat_allchecks = 0
        stat_allchecks_words = 0
        stat_allchecks_chars = 0
        stat_translated_checks = 0
        stat_translated_checks_words = 0
        stat_translated_checks_chars = 0
        stat_dismissed_checks = 0
        stat_dismissed_checks_words = 0
        stat_dismissed_checks_chars = 0
        # Suggestions
        stat_suggestions = 0
        stat_suggestions_words = 0
        stat_suggestions_chars = 0
        stat_nosuggestions = 0
        stat_nosuggestions_words = 0
        stat_nosuggestions_chars = 0
        stat_approved_suggestions = 0
        stat_approved_suggestions_words = 0
        stat_approved_suggestions_chars = 0
        # Comments
        stat_comments = 0
        stat_comments_words = 0
        stat_comments_chars = 0

        # Sum stats in Python, this is way faster than conditional sums in the database
        for (
            num_words,
            num_chars,
            state,
            active_checks_count,
            dismissed_checks_count,
            suggestion_count,
            comment_count,
            label_count,
        ) in base.values_list(
            "num_words",
            "num_chars",
            "state",
            "active_checks_count",
            "dismissed_checks_count",
            "suggestion_count",
            "comment_count",
            "label_count",
        ):
            stat_all += 1
            stat_all_words += num_words
            stat_all_chars += num_chars

            if state == STATE_FUZZY:
                stat_fuzzy += 1
                stat_fuzzy_words += num_words
                stat_fuzzy_chars += num_chars
            elif state == STATE_READONLY:
                stat_readonly += 1
                stat_readonly_words += num_words
                stat_readonly_chars += num_chars
            elif state == STATE_EMPTY:
                stat_nottranslated += 1
                stat_nottranslated_words += num_words
                stat_nottranslated_chars += num_chars
            elif state == STATE_APPROVED:
                stat_approved += 1
                stat_approved_words += num_words
                stat_approved_chars += num_chars
            elif state == STATE_TRANSLATED:
                stat_unapproved += 1
                stat_unapproved_words += num_words
                stat_unapproved_chars += num_chars

            if state >= STATE_TRANSLATED:
                stat_translated += 1
                stat_translated_words += num_words
                stat_translated_chars += num_chars
            else:
                stat_todo += 1
                stat_todo_words += num_words
                stat_todo_chars += num_chars

            if label_count == 0:
                stat_unlabeled += 1
                stat_unlabeled_words += num_words
                stat_unlabeled_chars += num_chars

            if active_checks_count > 0:
                stat_allchecks += 1
                stat_allchecks_words += num_words
                stat_allchecks_chars += num_chars
                if state in (STATE_TRANSLATED, STATE_APPROVED):
                    stat_translated_checks += 1
                    stat_translated_checks_words += num_words
                    stat_translated_checks_chars += num_chars

            if dismissed_checks_count > 0:
                stat_dismissed_checks += 1
                stat_dismissed_checks_words += num_words
                stat_dismissed_checks_chars += num_chars

            if suggestion_count > 0:
                stat_suggestions += 1
                stat_suggestions_words += num_words
                stat_suggestions_chars += num_chars
                if state == STATE_APPROVED:
                    stat_approved_suggestions += 1
                    stat_approved_suggestions_words += num_words
                    stat_approved_suggestions_chars += num_chars
            else:
                stat_nosuggestions += 1
                stat_nosuggestions_words += num_words
                stat_nosuggestions_chars += num_chars

            if comment_count > 0:
                stat_comments += 1
                stat_comments_words += num_words
                stat_comments_chars += num_chars

        # Store in a cache
        self.store("all", stat_all)
        self.store("all_words", stat_all_words)
        self.store("all_chars", stat_all_chars)
        self.store("fuzzy", stat_fuzzy)
        self.store("fuzzy_words", stat_fuzzy_words)
        self.store("fuzzy_chars", stat_fuzzy_chars)
        self.store("readonly", stat_readonly)
        self.store("readonly_words", stat_readonly_words)
        self.store("readonly_chars", stat_readonly_chars)
        self.store("translated", stat_translated)
        self.store("translated_words", stat_translated_words)
        self.store("translated_chars", stat_translated_chars)
        self.store("todo", stat_todo)
        self.store("todo_words", stat_todo_words)
        self.store("todo_chars", stat_todo_chars)
        self.store("nottranslated", stat_nottranslated)
        self.store("nottranslated_words", stat_nottranslated_words)
        self.store("nottranslated_chars", stat_nottranslated_chars)
        # Review workflow
        self.store("approved", stat_approved)
        self.store("approved_words", stat_approved_words)
        self.store("approved_chars", stat_approved_chars)
        self.store("unapproved", stat_unapproved)
        self.store("unapproved_words", stat_unapproved_words)
        self.store("unapproved_chars", stat_unapproved_chars)
        # Labels
        self.store("unlabeled", stat_unlabeled)
        self.store("unlabeled_words", stat_unlabeled_words)
        self.store("unlabeled_chars", stat_unlabeled_chars)
        # Checks
        self.store("allchecks", stat_allchecks)
        self.store("allchecks_words", stat_allchecks_words)
        self.store("allchecks_chars", stat_allchecks_chars)
        self.store("translated_checks", stat_translated_checks)
        self.store("translated_checks_words", stat_translated_checks_words)
        self.store("translated_checks_chars", stat_translated_checks_chars)
        self.store("dismissed_checks", stat_dismissed_checks)
        self.store("dismissed_checks_words", stat_dismissed_checks_words)
        self.store("dismissed_checks_chars", stat_dismissed_checks_chars)
        # Suggestions
        self.store("suggestions", stat_suggestions)
        self.store("suggestions_words", stat_suggestions_words)
        self.store("suggestions_chars", stat_suggestions_chars)
        self.store("nosuggestions", stat_nosuggestions)
        self.store("nosuggestions_words", stat_nosuggestions_words)
        self.store("nosuggestions_chars", stat_nosuggestions_chars)
        self.store("approved_suggestions", stat_approved_suggestions)
        self.store("approved_suggestions_words", stat_approved_suggestions_words)
        self.store("approved_suggestions_chars", stat_approved_suggestions_chars)
        # Comments
        self.store("comments", stat_comments)
        self.store("comments_words", stat_comments_words)
        self.store("comments_chars", stat_comments_chars)

        # There is single language here, but it is aggregated at higher levels
        self.store("languages", 1)

        # Last change timestamp
        self.fetch_last_change()

        self.count_changes()

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
            last_change = self._object.change_set.content().order()[0]
        except IndexError:
            Change.store_last_change(self._object, None)
            return None
        last_change.update_cache_last_change()
        return last_change

    def fetch_last_change(self):
        last_change = self.get_last_change_obj()

        if last_change is None:
            self.store("last_changed", None)
            self.store("last_author", None)
        else:
            self.store("last_changed", last_change.timestamp)
            self.store("last_author", last_change.author_id)

    def count_changes(self):
        if self.last_changed:
            monthly = timezone.now() - timedelta(days=30)
            recently = self.last_changed - timedelta(hours=6)
            changes = self._object.change_set.content().aggregate(
                total=Count("id"),
                recent=conditional_sum(timestamp__gt=recently),
                monthly=conditional_sum(timestamp__gt=monthly),
            )
            self.store("recent_changes", changes["recent"])
            self.store("monthly_changes", changes["monthly"])
            self.store("total_changes", changes["total"])
        else:
            self.store("recent_changes", 0)
            self.store("monthly_changes", 0)
            self.store("total_changes", 0)

    def calculate_by_name(self, name: str):
        super().calculate_by_name(name)
        if name.startswith("check:"):
            self.calculate_checks()
        elif name.startswith("label:"):
            self.calculate_labels()

    def calculate_checks(self):
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

    def calculate_labels(self):
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

    @cached_property
    def object_set(self):
        raise NotImplementedError

    @cached_property
    def category_set(self):
        return []

    def calculate_source(self, stats: dict):
        return

    def _calculate_basic(self):
        stats = zero_stats(self.basic_keys)
        object_stats = [obj.stats for obj in self.object_set]
        category_stats = [cat.stats for cat in self.category_set]
        all_stats = object_stats + category_stats

        # Ensure all objects have data available so that we can use _dict directly
        for stats_obj in all_stats:
            if "all" not in stats_obj._data:
                stats_obj.calculate_basic()
                stats_obj.save()

        for item in self.basic_keys:
            if not self.sum_source_keys and item.startswith("source_"):
                # Handle in calculate_source when logic for source strings differs
                continue

            # Extract all values by dedicated getter
            values = (stats_obj.aggregate_get(item) for stats_obj in all_stats)

            if item == "stats_timestamp":
                stats[item] = max(values, default=stats[item])
            elif item == "last_changed":
                # We need to access values twice here
                values = list(values)
                stats[item] = max_last_changed = max(
                    (value for value in values if value is not None), default=None
                )
                if max_last_changed is not None:
                    offset = values.index(max_last_changed)
                    stats["last_author"] = all_stats[offset].last_author
            elif item == "last_author":
                # The last_author is calculated together with last_changed
                continue
            else:
                stats[item] = sum(values)

        if not self.sum_source_keys:
            self.calculate_source(stats)

        for key, value in stats.items():
            self.store(key, value)


class SingleLanguageStats(AggregatingStats):
    def _calculate_basic(self):
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
    @cached_property
    def object_set(self):
        return prefetch_stats(self._object.translation_set.only("id", "language"))


class ComponentStats(AggregatingStats):
    sum_source_keys = False

    @cached_property
    def object_set(self):
        return prefetch_stats(
            self._object.translation_set.only("id", "component", "language")
        )

    @cached_property
    def has_review(self):
        return self._object.enable_review

    def calculate_source(self, stats: dict):
        """Fetch source info from source translation."""
        for obj in self.object_set:
            if obj.is_source:
                stats_obj = obj.stats
                stats["source_chars"] = stats_obj.all_chars
                stats["source_words"] = stats_obj.all_words
                stats["source_strings"] = stats_obj.all

    def get_update_objects(self):
        yield self._object.project.stats
        yield from self._object.project.stats.get_update_objects()

        if self._object.category:
            yield self._object.category.stats
            yield from self._object.category.stats.get_update_objects()

        for clist in self._object.componentlist_set.all():
            yield clist.stats
            yield from clist.stats.get_update_objects()

        yield from super().get_update_objects()

    def update_language_stats(self):
        extras = []

        # Update languages
        for translation in self.object_set:
            translation.stats.update_stats(update_parents=False)
            extras.extend(translation.stats.get_update_objects())

        # Update our stats
        self.update_stats()

        # Update all parents
        self.update_parents(extras)

    def get_language_stats(self):
        yield from (TranslationStats(translation) for translation in self.object_set)

    def get_single_language_stats(self, language):
        try:
            return TranslationStats(self._object.translation_set.get(language=language))
        except ObjectDoesNotExist:
            return DummyTranslationStats(language)


class ProjectLanguageComponent:
    is_glossary = False

    def __init__(self, parent):
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

    def __init__(self, project, language: Language):
        self.project = project
        self.language = language
        self.component = ProjectLanguageComponent(self)

    def __str__(self):
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

    def get_widgets_url(self):
        """Return absolute URL for widgets."""
        return f"{self.project.get_widgets_url()}?lang={self.language.code}"

    @cached_property
    def pk(self):
        return f"{self.project.pk}-{self.language.pk}"

    @cached_property
    def cache_key(self):
        return f"{self.project.cache_key}-{self.language.pk}"

    def get_url_path(self):
        return [*self.project.get_url_path(), "-", self.language.code]

    def get_absolute_url(self):
        return reverse("show", kwargs={"path": self.get_url_path()})

    def get_translate_url(self):
        return reverse("translate", kwargs={"path": self.get_url_path()})

    @cached_property
    def translation_set(self):
        all_langs = self.language.translation_set.prefetch()
        result = all_langs.filter(component__project=self.project).union(
            all_langs.filter(component__links=self.project)
        )
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
        )
        if len(workflow_settings) == 0:
            return None
        if len(workflow_settings) == 1:
            return workflow_settings[0]
        # We should have two objects here, return project specific one
        for workflow_setting in workflow_settings:
            if workflow_setting.project_id == self.project.id:
                return workflow_setting
        raise WorkflowSetting.DoesNotExist


class ProjectLanguageStats(SingleLanguageStats):
    def __init__(self, obj: ProjectLanguage, project_stats=None):
        self.language = obj.language
        self.project = obj.project
        self._project_stats = project_stats
        super().__init__(obj)
        obj.stats = self

    @cached_property
    def has_review(self):
        return self.project.source_review or self.project.translation_review

    @cached_property
    def category_set(self):
        if self._project_stats:
            return self._project_stats.category_set
        return prefetch_stats(self.project.category_set.only("id", "project"))

    @cached_property
    def object_set(self):
        return prefetch_stats(
            self.language.translation_set.filter(component__project=self.project).only(
                "id", "language"
            )
        )


class CategoryLanguage(BaseURLMixin):
    """Wrapper class used in category-language listings and stats."""

    remove_permission = "translation.delete"

    def __init__(self, category, language: Language):
        self.category = category
        self.language = language
        self.component = ProjectLanguageComponent(self)

    def __str__(self):
        return f"{self.category} - {self.language}"

    @property
    def code(self):
        return self.language.code

    @cached_property
    def stats(self):
        return CategoryLanguageStats(self)

    @cached_property
    def pk(self):
        return f"{self.category.pk}-{self.language.pk}"

    @cached_property
    def cache_key(self):
        return f"{self.category.cache_key}-{self.language.pk}"

    def get_url_path(self):
        return [*self.category.get_url_path(), "-", self.language.code]

    def get_absolute_url(self):
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
    def __init__(self, obj: CategoryLanguage, category_stats=None):
        self.language = obj.language
        self.category = obj.category
        self._category_stats = category_stats
        super().__init__(obj)
        obj.stats = self

    @cached_property
    def has_review(self):
        return (
            self.category.project.source_review
            or self.category.project.translation_review
        )

    @cached_property
    def category_set(self):
        if self._category_stats:
            return self._category_stats.category_set
        return prefetch_stats(self.category.category_set.only("id", "category"))

    @cached_property
    def object_set(self):
        return prefetch_stats(
            self.language.translation_set.filter(
                component__category=self.category
            ).only("id", "language")
        )


class CategoryStats(ParentAggregatingStats):
    def get_update_objects(self):
        yield self._object.project.stats
        yield from self._object.project.stats.get_update_objects()

        if self._object.category:
            yield self._object.category.stats
            yield from self._object.category.stats.get_update_objects()

        yield from super().get_update_objects()

    @cached_property
    def object_set(self):
        return prefetch_stats(
            self._object.component_set.only("id", "category").prefetch_source_stats()
        )

    @cached_property
    def category_set(self):
        return prefetch_stats(self._object.category_set.only("id", "category"))

    def get_single_language_stats(self, language):
        return CategoryLanguageStats(
            CategoryLanguage(self._object, language), category_stats=self
        )

    def get_language_stats(self):
        result = [
            self.get_single_language_stats(language)
            for language in self._object.languages
        ]
        return prefetch_stats(result)


class ProjectStats(ParentAggregatingStats):
    @cached_property
    def has_review(self):
        return self._object.enable_review

    @cached_property
    def category_set(self):
        return prefetch_stats(
            self._object.category_set.filter(category=None).only("id", "project")
        )

    @cached_property
    def object_set(self):
        return prefetch_stats(
            self._object.component_set.only("id", "project").prefetch_source_stats()
        )

    def get_single_language_stats(self, language):
        return ProjectLanguageStats(
            ProjectLanguage(self._object, language), project_stats=self
        )

    def get_language_stats(self):
        result = [
            self.get_single_language_stats(language)
            for language in self._object.languages
        ]
        return prefetch_stats(result)

    def _calculate_basic(self):
        super()._calculate_basic()
        self.store("languages", self._object.languages.count())


class ComponentListStats(ParentAggregatingStats):
    @cached_property
    def object_set(self):
        return prefetch_stats(
            self._object.components.only("id", "componentlist").prefetch_source_stats()
        )


class GlobalStats(ParentAggregatingStats):
    def __init__(self):
        super().__init__(None)

    @cached_property
    def object_set(self):
        from weblate.trans.models import Project

        return prefetch_stats(Project.objects.only("id", "access_control"))

    def _calculate_basic(self):
        super()._calculate_basic()
        self.store("languages", Language.objects.have_translation().count())

    @cached_property
    def cache_key(self):
        return "stats-global"


class GhostStats(BaseStats):
    basic_keys = SOURCE_KEYS
    is_ghost = True

    def __init__(self, base=None):
        super().__init__(None)
        self.base = base

    @cached_property
    def pk(self):
        return get_random_identifier()

    def _calculate_basic(self):
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
    def cache_key(self):
        return "stats-zero"

    def save(self, update_parents: bool = True):
        return

    def load(self):
        return {}

    def get_absolute_url(self):
        return None


class GhostProjectLanguageStats(GhostStats):
    def __init__(self, component, language, is_shared=None):
        super().__init__(component.stats)
        self.language = language
        self.component = component
        self.is_shared = is_shared
