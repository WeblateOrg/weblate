#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#


from copy import copy
from datetime import timedelta
from types import GeneratorType

from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, Sum
from django.db.models.functions import Length
from django.utils import timezone
from django.utils.functional import cached_property

from weblate.trans.filter import get_filter_choice
from weblate.trans.util import translation_percent
from weblate.utils.query import conditional_sum
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_TRANSLATED,
)

BASICS = {
    "all",
    "fuzzy",
    "todo",
    "nottranslated",
    "translated",
    "approved",
    "allchecks",
    "suggestions",
    "comments",
    "approved_suggestions",
    "languages",
}
BASIC_KEYS = frozenset(
    ["{}_words".format(x) for x in BASICS if x != "languages"]
    + ["{}_chars".format(x) for x in BASICS if x != "languages"]
    + [
        "translated_percent",
        "approved_percent",
        "fuzzy_percent",
        "allchecks_percent",
        "translated_words_percent",
        "approved_words_percent",
        "fuzzy_words_percent",
        "allchecks_words_percent",
    ]
    + list(BASICS)
    + ["last_changed", "last_author"]
)
SOURCE_KEYS = frozenset(
    list(BASIC_KEYS) + ["source_strings", "source_words", "source_chars"]
)


def aggregate(stats, item, stats_obj):
    if item == "last_changed":
        last = stats["last_changed"]
        if stats_obj.last_changed and (not last or last < stats_obj.last_changed):
            stats["last_changed"] = stats_obj.last_changed
            stats["last_author"] = stats_obj.last_author
    elif item == "last_author":
        # Already handled above
        return
    else:
        stats[item] += getattr(stats_obj, item)


def zero_stats(keys):
    stats = {item: 0 for item in keys}
    if "last_changed" in keys:
        stats["last_changed"] = None
        stats["last_author"] = None
    return stats


def prefetch_stats(queryset):
    """Fetch stats from cache for a queryset."""
    # Force evaluating queryset/iterator, we need all objects
    objects = list(queryset)

    # This function can either accept queryset, in which case it is
    # returned with prefetched stats, or iterator, in which case new list
    # is returned.
    # This is needed to allow using such querysets futher and to support
    # processing iterator when it is more effective.
    result = objects if isinstance(queryset, GeneratorType) else queryset

    # Bail out in case the query is empty
    if not objects:
        return result

    # Use stats prefetch
    objects[0].stats.prefetch_many([i.stats for i in objects])

    return result


class ParentStats:
    def __init__(self, stats, parent):
        self.translated_percent = stats.calculate_percents(
            "translated_percent", parent.source_strings
        )
        self.all = parent.source_strings
        self.translated = stats.translated


class BaseStats:
    """Caching statistics calculator."""

    basic_keys = BASIC_KEYS

    def __init__(self, obj):
        self._object = obj
        self._data = None
        self._pending_save = False

    @property
    def pk(self):
        return self._object.pk

    @property
    def obj(self):
        return self._object

    @property
    def stats(self):
        return self

    @staticmethod
    def get_badges():
        return []

    @property
    def is_loaded(self):
        return self._data is not None

    def set_data(self, data):
        self._data = data

    def get_data(self):
        return copy(self._data)

    def get_parent_stats(self, parent):
        return ParentStats(self, parent)

    def prefetch_many(self, stats):
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
        return "stats-{}-{}".format(self._object.__class__.__name__, self._object.pk)

    def __getattr__(self, name):
        if self._data is None:
            self._data = self.load()
        if name not in self._data:
            was_pending = self._pending_save
            self._pending_save = True
            if name in self.basic_keys:
                self.prefetch_basic()
            elif name.endswith("_percent"):
                self.store_percents(name)
            else:
                self.calculate_item(name)
            if not was_pending:
                self.save()
                self._pending_save = False
        return self._data[name]

    def load(self):
        return cache.get(self.cache_key, {})

    def save(self):
        """Save stats to cache."""
        cache.set(self.cache_key, self._data, 30 * 86400)

    def invalidate(self, language=None):
        """Invalidate local and cache data."""
        self._data = {}
        cache.delete(self.cache_key)

    def store(self, key, value):
        if self._data is None:
            self._data = self.load()
        if value is None and not key.startswith("last_"):
            self._data[key] = 0
        else:
            self._data[key] = value

    def calculate_item(self, item):
        """Calculate stats for translation."""
        raise NotImplementedError()

    def ensure_basic(self, save=True):
        """Ensure we have basic stats."""
        # Prefetch basic stats at once
        if self._data is None:
            self._data = self.load()
        if "all" not in self._data:
            self.prefetch_basic()
            if save:
                self.save()
            return True
        return False

    def prefetch_basic(self):
        raise NotImplementedError()

    def calculate_percents(self, item, total=None):
        """Calculate percent value for given item."""
        base = item[:-8]
        if total is None:
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
        return translation_percent(getattr(self, base), total, base in completed)

    def store_percents(self, item, total=None):
        """Calculate percent value for given item."""
        self.store(item, self.calculate_percents(item))

    def calculate_basic_percents(self):
        """Calculate basic percents."""
        self.store_percents("translated_percent")
        self.store_percents("approved_percent")
        self.store_percents("fuzzy_percent")
        self.store_percents("allchecks_percent")

        self.store_percents("translated_words_percent")
        self.store_percents("approved_words_percent")
        self.store_percents("fuzzy_words_percent")
        self.store_percents("allchecks_words_percent")


class DummyTranslationStats(BaseStats):
    """Dummy stats to report 0 in all cases.

    Used when given language does not exist in a component.
    """

    def __init__(self, obj):
        super().__init__(obj)
        self.language = obj

    @property
    def pk(self):
        return "l-{}".format(self.language.pk)

    def cache_key(self):
        return None

    def save(self):
        return

    def load(self):
        return {}

    def calculate_item(self, item):
        return

    def prefetch_basic(self):
        self._data = zero_stats(self.basic_keys)


class TranslationStats(BaseStats):
    """Per translation stats."""

    def invalidate(self, language=None):
        super().invalidate()
        self._object.component.stats.invalidate(language=self._object.language)
        self._object.language.stats.invalidate()

    @property
    def language(self):
        return self._object.language

    @cached_property
    def has_review(self):
        return self._object.enable_review

    def prefetch_basic(self):
        stats = self._object.unit_set.aggregate(
            all=Count("id"),
            all_words=Sum("num_words"),
            all_chars=Sum(Length("source")),
            fuzzy=conditional_sum(1, state=STATE_FUZZY),
            fuzzy_words=conditional_sum("num_words", state=STATE_FUZZY),
            fuzzy_chars=conditional_sum(Length("source"), state=STATE_FUZZY),
            translated=conditional_sum(1, state__gte=STATE_TRANSLATED),
            translated_words=conditional_sum("num_words", state__gte=STATE_TRANSLATED),
            translated_chars=conditional_sum(
                Length("source"), state__gte=STATE_TRANSLATED
            ),
            todo=conditional_sum(1, state__lt=STATE_TRANSLATED),
            todo_words=conditional_sum("num_words", state__lt=STATE_TRANSLATED),
            todo_chars=conditional_sum(Length("source"), state__lt=STATE_TRANSLATED),
            nottranslated=conditional_sum(1, state=STATE_EMPTY),
            nottranslated_words=conditional_sum("num_words", state=STATE_EMPTY),
            nottranslated_chars=conditional_sum(Length("source"), state=STATE_EMPTY),
            approved=conditional_sum(1, state__gte=STATE_APPROVED),
            approved_words=conditional_sum("num_words", state__gte=STATE_APPROVED),
            approved_chars=conditional_sum(Length("source"), state__gte=STATE_APPROVED),
            allchecks=conditional_sum(1, has_failing_check=True),
            allchecks_words=conditional_sum("num_words", has_failing_check=True),
            allchecks_chars=conditional_sum(Length("source"), has_failing_check=True),
            suggestions=conditional_sum(1, has_suggestion=True),
            suggestions_words=conditional_sum("num_words", has_suggestion=True),
            suggestions_chars=conditional_sum(Length("source"), has_suggestion=True),
            comments=conditional_sum(1, has_comment=True),
            comments_words=conditional_sum("num_words", has_comment=True),
            comments_chars=conditional_sum(Length("source"), has_comment=True),
            approved_suggestions=conditional_sum(
                1, state__gte=STATE_APPROVED, has_suggestion=True
            ),
            approved_suggestions_words=conditional_sum(
                "num_words", state__gte=STATE_APPROVED, has_suggestion=True
            ),
            approved_suggestions_chars=conditional_sum(
                Length("source"), state__gte=STATE_APPROVED, has_suggestion=True
            ),
        )
        for key, value in stats.items():
            self.store(key, value)

        # Calculate some values
        self.store("languages", 1)

        # Calculate percents
        self.calculate_basic_percents()

        # Last change timestamp
        self.fetch_last_change()

    def get_last_change_obj(self):
        from weblate.trans.models import Change

        change_pk = cache.get("last-content-change-{}".format(self._object.pk))
        if change_pk:
            try:
                return Change.objects.get(pk=change_pk)
            except Change.DoesNotExist:
                pass
        try:
            last_change = self._object.change_set.content().order()[0]
        except IndexError:
            return None

        cache.set(
            "last-content-change-{}".format(last_change.translation.pk),
            last_change.pk,
            180 * 86400,
        )
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
            content = self._object.change_set.content()
            self.store("recent_changes", content.filter(timestamp__gt=recently).count())
            self.store("monthly_changes", content.filter(timestamp__gt=monthly).count())
            self.store("total_changes", self._object.change_set.count())
        else:
            self.store("recent_changes", 0)
            self.store("monthly_changes", 0)
            self.store("total_changes", 0)

    def calculate_item(self, item):
        """Calculate stats for translation."""
        if item.endswith("_changes"):
            self.count_changes()
            return
        if item.endswith("_words"):
            item = item[:-6]
        if item.endswith("_chars"):
            item = item[:-6]
        translation = self._object
        stats = translation.unit_set.filter_type(item).aggregate(
            strings=Count("pk"), words=Sum("num_words"), chars=Sum(Length("source"))
        )
        self.store(item, stats["strings"])
        self.store("{}_words".format(item), stats["words"])
        self.store("{}_chars".format(item), stats["chars"])

    def ensure_all(self):
        """Ensure we have complete set."""
        # Prefetch basic stats at once
        save = self.ensure_basic(save=False)
        # Fetch remaining ones
        for item, _unused in get_filter_choice(self.obj.component.project):
            if item not in self._data:
                self.calculate_item(item)
                save = True
        if save:
            self.save()


class LanguageStats(BaseStats):
    basic_keys = SOURCE_KEYS

    @cached_property
    def translation_set(self):
        return prefetch_stats(self._object.translation_set.iterator())

    def calculate_source(self, stats_obj, stats):
        stats["source_chars"] += stats_obj.all_chars
        stats["source_words"] += stats_obj.all_words
        stats["source_strings"] += stats_obj.all

    def prefetch_source(self):
        return

    def prefetch_basic(self):
        stats = zero_stats(self.basic_keys)
        for translation in self.translation_set:
            stats_obj = translation.stats
            stats_obj.ensure_basic()
            for item in BASIC_KEYS:
                aggregate(stats, item, stats_obj)
            self.calculate_source(stats_obj, stats)

        for key, value in stats.items():
            self.store(key, value)

        self.prefetch_source()

        # Calculate percents
        self.calculate_basic_percents()

    def calculate_item(self, item):
        """Calculate stats for translation."""
        result = 0
        for translation in self.translation_set:
            result += getattr(translation.stats, item)
        self.store(item, result)


class ComponentStats(LanguageStats):
    @cached_property
    def has_review(self):
        return (
            self._object.project.source_review
            or self._object.project.translation_review
        )

    def calculate_source(self, stats_obj, stats):
        return

    def prefetch_source(self):
        source_translation = self._object.get_source_translation()
        if source_translation is None:
            self.store("source_chars", 0)
            self.store("source_words", 0)
            self.store("source_strings", 0)
        else:
            stats_obj = source_translation.stats
            self.store("source_chars", stats_obj.all_chars)
            self.store("source_words", stats_obj.all_words)
            self.store("source_strings", stats_obj.all)

    def invalidate(self, language=None):
        super().invalidate()
        self._object.project.stats.invalidate(language=language)
        for clist in self._object.componentlist_set.iterator():
            clist.stats.invalidate()

    def get_language_stats(self):
        yield from (
            TranslationStats(translation) for translation in self.translation_set
        )

    def get_single_language_stats(self, language):
        try:
            return TranslationStats(self._object.translation_set.get(language=language))
        except ObjectDoesNotExist:
            return DummyTranslationStats(language)


class ProjectLanguageStats(LanguageStats):
    def __init__(self, obj, lang):
        self.language = lang
        super().__init__(obj)

    @property
    def pk(self):
        return "{}-{}".format(self._object.pk, self.language.pk)

    @cached_property
    def has_review(self):
        return self._object.source_review or self._object.translation_review

    @cached_property
    def cache_key(self):
        return "{}-{}".format(super().cache_key, self.language.pk)

    @cached_property
    def translation_set(self):
        result = []
        for component in self._object.component_set.iterator():
            result.extend(
                component.translation_set.filter(language_id=self.language.pk)
            )
        return prefetch_stats(result)

    def calculate_source(self, stats_obj, stats):
        return

    def prefetch_source(self):
        chars, words, strings = 0, 0, 0
        for component in prefetch_stats(self._object.component_set.iterator()):
            stats_obj = component.source_translation.stats
            chars += stats_obj.all_chars
            words += stats_obj.all_words
            strings += stats_obj.all
        self.store("source_chars", chars)
        self.store("source_words", words)
        self.store("source_strings", strings)

    def prefetch_basic(self):
        super().prefetch_basic()
        self.store("languages", 1)


class ProjectStats(BaseStats):
    basic_keys = SOURCE_KEYS

    @cached_property
    def has_review(self):
        return self._object.source_review or self._object.translation_review

    def invalidate(self, language=None):
        super().invalidate()
        if language:
            self.get_single_language_stats(language).invalidate()
        else:
            for lang in self._object.languages:
                self.get_single_language_stats(lang).invalidate()
        GlobalStats().invalidate()

    @cached_property
    def component_set(self):
        return prefetch_stats(self._object.component_set.iterator())

    def get_single_language_stats(self, language):
        return ProjectLanguageStats(self._object, language)

    def get_language_stats(self):
        result = []
        for language in self._object.languages:
            result.append(self.get_single_language_stats(language))
        return prefetch_stats(result)

    def prefetch_basic(self):
        stats = zero_stats(self.basic_keys)
        for component in self.component_set:
            stats_obj = component.stats
            stats_obj.ensure_basic()
            for item in self.basic_keys:
                aggregate(stats, item, stats_obj)

        for key, value in stats.items():
            self.store(key, value)

        self.store("languages", self._object.languages.count())

        # Calculate percents
        self.calculate_basic_percents()

    def calculate_item(self, item):
        """Calculate stats for translation."""
        result = 0
        for component in self.component_set:
            result += getattr(component.stats, item)
        self.store(item, result)


class ComponentListStats(BaseStats):
    basic_keys = SOURCE_KEYS

    @cached_property
    def component_set(self):
        return prefetch_stats(self._object.components.iterator())

    def prefetch_basic(self):
        stats = zero_stats(self.basic_keys)
        for component in self.component_set:
            stats_obj = component.stats
            stats_obj.ensure_basic()
            for item in self.basic_keys:
                aggregate(stats, item, stats_obj)

        for key, value in stats.items():
            self.store(key, value)

        # Calculate percents
        self.calculate_basic_percents()

    def calculate_item(self, item):
        """Calculate stats for translation."""
        result = 0
        for component in self.component_set:
            result += getattr(component.stats, item)
        self.store(item, result)


class GlobalStats(BaseStats):
    basic_keys = SOURCE_KEYS

    def __init__(self):
        super().__init__(None)

    @cached_property
    def project_set(self):
        from weblate.trans.models import Project

        return prefetch_stats(Project.objects.iterator())

    def prefetch_basic(self):
        from weblate.lang.models import Language

        stats = zero_stats(self.basic_keys)
        for project in self.project_set:
            stats_obj = project.stats
            stats_obj.ensure_basic()
            for item in self.basic_keys:
                aggregate(stats, item, stats_obj)

        for key, value in stats.items():
            self.store(key, value)

        self.store("languages", Language.objects.have_translation().count())

        # Calculate percents
        self.calculate_basic_percents()

    def calculate_item(self, item):
        """Calculate stats for translation."""
        result = 0
        for project in self.project_set:
            result += getattr(project.stats, item)
        self.store(item, result)

    @cached_property
    def cache_key(self):
        return "stats-global"
