#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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
from typing import Optional
from uuid import uuid4

import sentry_sdk
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count, Q, Sum
from django.db.models.functions import Length
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property

from weblate.checks.models import CHECKS
from weblate.lang.models import Language
from weblate.trans.filter import get_filter_choice
from weblate.trans.util import translation_percent
from weblate.utils.db import conditional_sum
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
    "languages",
    "unlabeled",
}
BASIC_KEYS = frozenset(
    [f"{x}_words" for x in BASICS if x != "languages"]
    + [f"{x}_chars" for x in BASICS if x != "languages"]
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


class BaseStats:
    """Caching statistics calculator."""

    basic_keys = BASIC_KEYS
    is_ghost = False

    def __init__(self, obj):
        self._object = obj
        self._data = None
        self._pending_save = False

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

    @staticmethod
    def get_badges():
        return []

    @property
    def is_loaded(self):
        return self._data is not None

    def set_data(self, data):
        self._data = data

    def get_data(self):
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
        self.ensure_basic()
        data = copy(self._data)
        for percent in percents:
            data[percent] = self.calculate_percents(percent)
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

    def __getattr__(self, name):
        if self._data is None:
            self._data = self.load()
        if name.endswith("_percent"):
            return self.calculate_percents(name)
        if name not in self._data:
            was_pending = self._pending_save
            self._pending_save = True
            if name in self.basic_keys:
                self.prefetch_basic()
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

    def get_invalidate_keys(
        self,
        language: Optional[Language] = None,
        childs: bool = False,
        parents: bool = True,
    ):
        return {self.cache_key, GlobalStats().cache_key}

    def invalidate(self, language: Optional[Language] = None, childs: bool = False):
        """Invalidate local and cache data."""
        self.clear()
        cache.delete_many(self.get_invalidate_keys(language, childs))

    def clear(self):
        """Clear local cache."""
        self._data = {}

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
        with sentry_sdk.start_span(
            op="stats", description=f"PREFETCH {self.cache_key}"
        ):
            self._prefetch_basic()

    def _prefetch_basic(self):
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


class DummyTranslationStats(BaseStats):
    """Dummy stats to report 0 in all cases.

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

    def save(self):
        return

    def load(self):
        return {}

    def calculate_item(self, item):
        return

    def _prefetch_basic(self):
        self._data = zero_stats(self.basic_keys)


class TranslationStats(BaseStats):
    """Per translation stats."""

    def get_invalidate_keys(
        self,
        language: Optional[Language] = None,
        childs: bool = False,
        parents: bool = True,
    ):
        result = super().get_invalidate_keys(language, childs, parents)
        try:
            result.update(self._object.language.stats.get_invalidate_keys())
        except ObjectDoesNotExist:
            # Happens when deleting language from the admin interface
            pass
        if parents:
            result.update(
                self._object.component.stats.get_invalidate_keys(
                    language=self._object.language
                )
            )
        return result

    @property
    def language(self):
        return self._object.language

    @cached_property
    def has_review(self):
        return self._object.enable_review

    def _prefetch_basic(self):
        base = self._object.unit_set.annotate(
            active_checks_count=Count("check", filter=Q(check__dismissed=False)),
            dismissed_checks_count=Count("check", filter=Q(check__dismissed=True)),
            suggestion_count=Count("suggestion"),
            comment_count=Count("comment", filter=Q(comment__resolved=False)),
        )
        stats = base.aggregate(
            all=Count("id"),
            all_words=Sum("num_words"),
            all_chars=Sum(Length("source")),
            fuzzy=conditional_sum(1, state=STATE_FUZZY),
            fuzzy_words=conditional_sum("num_words", state=STATE_FUZZY),
            fuzzy_chars=conditional_sum(Length("source"), state=STATE_FUZZY),
            readonly=conditional_sum(1, state=STATE_READONLY),
            readonly_words=conditional_sum("num_words", state=STATE_READONLY),
            readonly_chars=conditional_sum(Length("source"), state=STATE_READONLY),
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
            # Review workflow
            approved=conditional_sum(1, state=STATE_APPROVED),
            approved_words=conditional_sum("num_words", state=STATE_APPROVED),
            approved_chars=conditional_sum(Length("source"), state=STATE_APPROVED),
            # Labels
            unlabeled=conditional_sum(1, source_unit__labels__isnull=True),
            unlabeled_words=conditional_sum(
                "num_words", source_unit__labels__isnull=True
            ),
            unlabeled_chars=conditional_sum(
                Length("source"), source_unit__labels__isnull=True
            ),
            # Checks
            allchecks=conditional_sum(1, active_checks_count__gt=0),
            allchecks_words=conditional_sum("num_words", active_checks_count__gt=0),
            allchecks_chars=conditional_sum(
                Length("source"), active_checks_count__gt=0
            ),
            translated_checks=conditional_sum(
                1, state=STATE_TRANSLATED, active_checks_count__gt=0
            ),
            translated_checks_words=conditional_sum(
                "num_words", state=STATE_TRANSLATED, active_checks_count__gt=0
            ),
            translated_checks_chars=conditional_sum(
                Length("source"), state=STATE_TRANSLATED, active_checks_count__gt=0
            ),
            dismissed_checks=conditional_sum(1, dismissed_checks_count__gt=0),
            dismissed_checks_words=conditional_sum(
                "num_words", dismissed_checks_count__gt=0
            ),
            dismissed_checks_chars=conditional_sum(
                Length("source"), dismissed_checks_count__gt=0
            ),
            # Suggestions
            suggestions=conditional_sum(1, suggestion_count__gt=0),
            suggestions_words=conditional_sum("num_words", suggestion_count__gt=0),
            suggestions_chars=conditional_sum(Length("source"), suggestion_count__gt=0),
            nosuggestions=conditional_sum(
                1, state__lt=STATE_TRANSLATED, suggestion_count=0
            ),
            nosuggestions_words=conditional_sum(
                "num_words", state__lt=STATE_TRANSLATED, suggestion_count=0
            ),
            nosuggestions_chars=conditional_sum(
                Length("source"), state__lt=STATE_TRANSLATED, suggestion_count=0
            ),
            approved_suggestions=conditional_sum(
                1, state__gte=STATE_APPROVED, suggestion_count__gt=0
            ),
            approved_suggestions_words=conditional_sum(
                "num_words", state__gte=STATE_APPROVED, suggestion_count__gt=0
            ),
            approved_suggestions_chars=conditional_sum(
                Length("source"), state__gte=STATE_APPROVED, suggestion_count__gt=0
            ),
            # Comments
            comments=conditional_sum(1, comment_count__gt=0),
            comments_words=conditional_sum("num_words", comment_count__gt=0),
            comments_chars=conditional_sum(Length("source"), comment_count__gt=0),
        )
        for key, value in stats.items():
            self.store(key, value)

        # Calculate some values
        self.store("languages", 1)

        # Last change timestamp
        self.fetch_last_change()

    def get_last_change_obj(self):
        from weblate.trans.models import Change

        cache_key = f"last-content-change-{self._object.pk}"
        change_pk = cache.get(cache_key)
        if change_pk:
            try:
                return Change.objects.get(pk=change_pk)
            except Change.DoesNotExist:
                pass
        try:
            last_change = self._object.change_set.content().order()[0]
        except IndexError:
            return None

        cache.set(cache_key, last_change.pk, 180 * 86400)
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

    def calculate_item(self, item):
        """Calculate stats for translation."""
        if item.endswith("_changes"):
            self.count_changes()
            return
        if item.startswith("check:"):
            self.prefetch_checks()
            return
        if item.startswith("label:"):
            self.prefetch_labels()
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
        self.store(f"{item}_words", stats["words"])
        self.store(f"{item}_chars", stats["chars"])

    def prefetch_checks(self):
        """Prefetch check stats."""
        allchecks = {check.url_id for check in CHECKS.values()}
        stats = (
            self._object.unit_set.filter(check__dismissed=False)
            .values("check__check")
            .annotate(
                strings=Count("pk"), words=Sum("num_words"), chars=Sum(Length("source"))
            )
        )
        for stat in stats:
            check = stat["check__check"]
            # Filtering here is way more effective than in SQL
            if check is None:
                continue
            check = f"check:{check}"
            self.store(check, stat["strings"])
            self.store(check + "_words", stat["words"])
            self.store(check + "_chars", stat["chars"])
            allchecks.discard(check)
        for check in allchecks:
            self.store(check, 0)
            self.store(check + "_words", 0)
            self.store(check + "_chars", 0)

    def prefetch_labels(self):
        """Prefetch check stats."""
        alllabels = set(
            self._object.component.project.label_set.values_list("name", flat=True)
        )
        stats = self._object.unit_set.values("source_unit__labels__name").annotate(
            strings=Count("pk"), words=Sum("num_words"), chars=Sum(Length("source"))
        )
        for stat in stats:
            label_name = stat["source_unit__labels__name"]
            # Filtering here is way more effective than in SQL
            if label_name is None:
                continue
            label = f"label:{label_name}"
            self.store(label, stat["strings"])
            self.store(label + "_words", stat["words"])
            self.store(label + "_chars", stat["chars"])
            alllabels.discard(label_name)
        for label_name in alllabels:
            label = f"label:{label_name}"
            self.store(label, 0)
            self.store(label + "_words", 0)
            self.store(label + "_chars", 0)

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

    def _prefetch_basic(self):
        stats = zero_stats(self.basic_keys)
        for translation in self.translation_set:
            stats_obj = translation.stats
            stats_obj.ensure_basic()
            for item in BASIC_KEYS:
                aggregate(stats, item, stats_obj)
            self.calculate_source(stats_obj, stats)

        for key, value in stats.items():
            self.store(key, value)

        with sentry_sdk.start_span(op="stats", description=f"SOURCE {self.cache_key}"):
            self.prefetch_source()

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

    @cached_property
    def lazy_translated_percent_key(self):
        return f"{self.cache_key}:lazy_translated"

    @cached_property
    def lazy_translated_percent(self):
        """Translation percent that is not invalidated."""
        result = cache.get(self.lazy_translated_percent_key)
        if result is not None:
            return result
        self.save_lazy_translated_percent()
        return self.translated_percent

    def save_lazy_translated_percent(self):
        cache.set(self.lazy_translated_percent_key, self.translated_percent, 30 * 86400)

    def save(self):
        super().save()
        self.save_lazy_translated_percent()

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

    def get_invalidate_keys(
        self,
        language: Optional[Language] = None,
        childs: bool = False,
        parents: bool = True,
    ):
        result = super().get_invalidate_keys(language, childs, parents)
        if parents:
            result.update(self._object.project.stats.get_invalidate_keys(language))
            for clist in self._object.componentlist_set.iterator():
                result.update(clist.stats.get_invalidate_keys())
        if childs:
            for translation in self.translation_set:
                result.update(translation.stats.get_invalidate_keys(parents=False))
        return result

    def get_language_stats(self):
        yield from (
            TranslationStats(translation) for translation in self.translation_set
        )

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


class ProjectLanguage:
    """Wrapper class used in project-language listings and stats."""

    def __init__(self, project, language: Language):
        self.project = project
        self.language = language
        self.component = ProjectLanguageComponent(self)

    def __str__(self):
        return f"{self.project} - {self.language}"

    @property
    def full_slug(self):
        return f"{self.project.slug}/{self.language.code}"

    @cached_property
    def stats(self):
        return ProjectLanguageStats(self)

    @cached_property
    def pk(self):
        return f"{self.project.pk}-{self.language.pk}"

    @cached_property
    def cache_key(self):
        return f"{self.project.cache_key}-{self.language.pk}"

    def get_absolute_url(self):
        return reverse(
            "project-language",
            kwargs={"lang": self.language.code, "project": self.project.slug},
        )

    def get_remove_url(self):
        return reverse(
            "remove-project-language",
            kwargs={"lang": self.language.code, "project": self.project.slug},
        )

    def get_reverse_url_kwargs(self):
        return {
            "lang": self.language.code,
            "project": self.project.slug,
            "component": "-",
        }

    def get_translate_url(self):
        return reverse(
            "translate",
            kwargs=self.get_reverse_url_kwargs(),
        )

    @cached_property
    def translation_set(self):
        result = (
            self.language.translation_set.prefetch()
            .filter(
                Q(component__project=self.project) | Q(component__links=self.project)
            )
            .order_by("component__priority", "component__name")
        )
        for item in result:
            item.is_shared = (
                None
                if item.component.project == self.project
                else item.component.project
            )
        return result

    @cached_property
    def is_source(self):
        return all(
            self.language.id == component.source_language_id
            for component in self.project.child_components
        )


class ProjectLanguageStats(LanguageStats):
    def __init__(self, obj: ProjectLanguage):
        self.language = obj.language
        self.project = obj.project
        super().__init__(obj)
        obj.stats = self

    @cached_property
    def has_review(self):
        return self.project.source_review or self.project.translation_review

    @cached_property
    def component_set(self):
        return prefetch_stats(self.project.component_set.prefetch_source_stats())

    @cached_property
    def translation_set(self):
        return prefetch_stats(
            self.language.translation_set.filter(component__in=self.component_set)
        )

    def calculate_source(self, stats_obj, stats):
        return

    def prefetch_source(self):
        chars = words = strings = 0
        for component in self.component_set:
            stats_obj = component.source_translation.stats
            chars += stats_obj.all_chars
            words += stats_obj.all_words
            strings += stats_obj.all
        self.store("source_chars", chars)
        self.store("source_words", words)
        self.store("source_strings", strings)

    def _prefetch_basic(self):
        super()._prefetch_basic()
        self.store("languages", 1)

    def get_single_language_stats(self, language):
        return self

    @cached_property
    def is_source(self):
        return all(
            self.language.id == component.source_language_id
            for component in self.project.child_components
        )


class ProjectStats(BaseStats):
    basic_keys = SOURCE_KEYS

    @cached_property
    def has_review(self):
        return self._object.source_review or self._object.translation_review

    def get_invalidate_keys(
        self,
        language: Optional[Language] = None,
        childs: bool = False,
        parents: bool = True,
    ):
        result = super().get_invalidate_keys(language, childs, parents)
        if parents:
            if language:
                result.update(
                    self.get_single_language_stats(language).get_invalidate_keys()
                )
            else:
                for lang in self._object.languages:
                    result.update(
                        self.get_single_language_stats(lang).get_invalidate_keys()
                    )
        return result

    @cached_property
    def component_set(self):
        return prefetch_stats(self._object.component_set.prefetch_source_stats())

    def get_single_language_stats(self, language, prefetch: bool = False):
        result = ProjectLanguageStats(ProjectLanguage(self._object, language))
        if prefetch:
            # Share component set here
            result.__dict__["component_set"] = self.component_set
        return result

    def get_language_stats(self):
        result = []
        for language in self._object.languages:
            result.append(self.get_single_language_stats(language, prefetch=True))
        return prefetch_stats(result)

    def _prefetch_basic(self):
        stats = zero_stats(self.basic_keys)
        for component in self.component_set:
            stats_obj = component.stats
            stats_obj.ensure_basic()
            for item in self.basic_keys:
                aggregate(stats, item, stats_obj)

        for key, value in stats.items():
            self.store(key, value)

        self.store("languages", self._object.languages.count())

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
        return prefetch_stats(self._object.components.prefetch_source_stats())

    def _prefetch_basic(self):
        stats = zero_stats(self.basic_keys)
        for component in self.component_set:
            stats_obj = component.stats
            stats_obj.ensure_basic()
            for item in self.basic_keys:
                aggregate(stats, item, stats_obj)

        for key, value in stats.items():
            self.store(key, value)

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

    def _prefetch_basic(self):

        stats = zero_stats(self.basic_keys)
        for project in self.project_set:
            stats_obj = project.stats
            stats_obj.ensure_basic()
            for item in self.basic_keys:
                aggregate(stats, item, stats_obj)

        for key, value in stats.items():
            self.store(key, value)

        self.store("languages", Language.objects.have_translation().count())

    def calculate_item(self, item):
        """Calculate stats for translation."""
        result = 0
        for project in self.project_set:
            result += getattr(project.stats, item)
        self.store(item, result)

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
        return uuid4().hex

    def _prefetch_basic(self):
        stats = zero_stats(self.basic_keys)
        if self.base is not None:
            for key in "all", "all_words", "all_chars":
                stats[key] = getattr(self.base, key)
            stats["todo"] = stats["all"]
            stats["todo_words"] = stats["all_words"]
            stats["todo_chars"] = stats["all_chars"]
        for key, value in stats.items():
            self.store(key, value)

    def calculate_item(self, item):
        """Calculate stats for translation."""
        return 0

    @cached_property
    def cache_key(self):
        return "stats-zero"

    def save(self):
        return

    def get_absolute_url(self):
        return None


class GhostProjectLanguageStats(GhostStats):
    def __init__(self, component, language, is_shared=None):
        super().__init__(component.stats)
        self.language = language
        self.component = component
        self.is_shared = is_shared
