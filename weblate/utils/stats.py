# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

from django.core.cache import cache
from django.db.models import Sum, Count

from weblate.trans.filter import get_filter_choice
from weblate.utils.query import conditional_sum
from weblate.utils.state import (
    STATE_TRANSLATED, STATE_FUZZY, STATE_APPROVED, STATE_EMPTY,
)
from weblate.trans.util import translation_percent

BASICS = frozenset((
    'all', 'fuzzy', 'translated', 'approved', 'untranslated',
    'allchecks', 'suggestions', 'comments', 'approved_suggestions'
))
BASIC_KEYS = frozenset(['{}_words'.format(i) for i in BASICS] + list(BASICS))


class BaseStats(object):
    """Caching statistics calculator."""
    def __init__(self, obj):
        self._object = obj
        self._key = 'stats-{}-{}'.format(
            obj.__class__.__name__,
            obj.pk
        )
        self._data = cache.get(self._key, {})

    def __getattr__(self, name):
        if name not in self._data:
            if name.endswith('_percent'):
                self.calculate_percents(name)
            else:
                self.fetch_stats(name)
            self.save()
        return self._data[name]

    def save(self):
        """Save stats to cache."""
        cache.set(self._key, self._data)

    def invalidate(self):
        """Invalidate local and cache data."""
        self._data = {}
        cache.delete(self._key)

    def store(self, key, value):
        if value is None:
            self._data[key] = 0
        else:
            self._data[key] = value

    def fetch_stats(self, item):
        """Calculate stats for translation."""
        if item in BASIC_KEYS:
            self.prefetch_basic()
            return
        self.calculate_item(item)

    def calculate_item(self, item):
        """Calculate stats for translation."""
        raise NotImplementedError()

    def ensure_basic(self):
        """Ensure we have basic stats."""
        # Prefetch basic stats at once
        if 'all' not in self._data:
            self.prefetch_basic()

    def prefetch_basic(self):
        raise NotImplementedError()

    def calculate_percents(self, item):
        """Calculate percent value for given item."""
        base = item[:-8]
        if base.endswith('_words'):
            total = self.all_words
        else:
            total = self.all
        self.store(item, translation_percent(getattr(self, base), total))

    def calculate_basic_percents(self):
        """Calculate basic percents."""
        self.calculate_percents('translated_percent')
        self.calculate_percents('approved_percent')
        self.calculate_percents('translated_words_percent')
        self.calculate_percents('approved_words_percent')
        self.calculate_percents('untranslated_percent')
        self.calculate_percents('fuzzy_percent')
        self.calculate_percents('allchecks_percent')


class TranslationStats(BaseStats):
    """Per translation stats."""
    def invalidate(self):
        super(TranslationStats, self).invalidate()
        self._object.subproject.stats.invalidate()
        self._object.language.stats.invalidate()

    def prefetch_basic(self):
        stats = self._object.unit_set.aggregate(
            all=Count('id'),
            all_words=Sum('num_words'),
            fuzzy=conditional_sum(1, state=STATE_FUZZY),
            fuzzy_words=conditional_sum(
                'num_words', state=STATE_FUZZY
            ),
            translated=conditional_sum(1, state__gte=STATE_TRANSLATED),
            translated_words=conditional_sum(
                'num_words', state__gte=STATE_TRANSLATED
            ),
            nottranslated=conditional_sum(1, state=STATE_EMPTY),
            nottranslated_words=conditional_sum(
                'num_words', state=STATE_EMPTY
            ),
            approved=conditional_sum(1, state__gte=STATE_APPROVED),
            approved_words=conditional_sum(
                'num_words', state__gte=STATE_APPROVED
            ),
            allchecks=conditional_sum(1, has_failing_check=True),
            allchecks_words=conditional_sum(
                'num_words', has_failing_check=True
            ),
            suggestions=conditional_sum(1, has_suggestion=True),
            suggestions_words=conditional_sum(
                1, has_suggestion=True
            ),
            comments=conditional_sum(1, has_comment=True),
            comments_words=conditional_sum(
                'num_words', has_comment=True,
            ),
            approved_suggestions=conditional_sum(
                1, state__gte=STATE_APPROVED, has_suggestion=True
            ),
            approved_suggestions_words=conditional_sum(
                'num_words', state__gte=STATE_APPROVED, has_suggestion=True
            ),
        )
        for key, value in stats.items():
            self.store(key, value)

        # Calculate some values
        self.store('untranslated', stats['all'] - stats['translated'])
        self.store('untranslated_words', stats['all_words'] - stats['translated_words'])

        # Calculate percents
        self.calculate_basic_percents()

    def calculate_item(self, item):
        """Calculate stats for translation."""
        if item.endswith('_words'):
            item = item[:-6]
        translation = self._object
        stats = translation.unit_set.filter_type(
            item,
            translation.subproject.project,
            translation.language,
            strict=True
        ).aggregate(Count('pk'), Sum('num_words'))
        self.store(item, stats['pk__count'])
        self.store('{}_words'.format(item), stats['num_words__sum'])

    def ensure_all(self):
        """Ensure we have complete set."""
        # Prefetch basic stats at once
        self.ensure_basic()
        # Fetch remaining ones
        for item, dummy in get_filter_choice():
            if item not in self._data:
                self.calculate_item(item)
        self.save()


class LanguageStats(BaseStats):
    def prefetch_basic(self):
        stats = {item: 0 for item in BASIC_KEYS}
        for translation in self._object.translation_set.all():
            stats_obj = translation.stats
            stats_obj.ensure_basic()
            for item in BASIC_KEYS:
                stats[item] += getattr(stats_obj, item)

        for key, value in stats.items():
            self.store(key, value)

        # Calculate percents
        self.calculate_basic_percents()

    def calculate_item(self, item):
        """Calculate stats for translation."""
        result = 0
        for translation in self._object.translation_set.all():
            result += getattr(translation.stats, item)
        self.store(item, result)


class ComponentStats(LanguageStats):
    def invalidate(self):
        super(ComponentStats, self).invalidate()
        self._object.project.stats.invalidate()


class ProjectStats(BaseStats):
    def prefetch_basic(self):
        stats = {item: 0 for item in BASIC_KEYS}
        for component in self._object.subproject_set.all():
            stats_obj = component.stats
            stats_obj.ensure_basic()
            for item in BASIC_KEYS:
                stats[item] += getattr(stats_obj, item)

        for key, value in stats.items():
            self.store(key, value)

        # Calculate percents
        self.calculate_basic_percents()

    def calculate_item(self, item):
        """Calculate stats for translation."""
        result = 0
        for component in self._object.subproject_set.all():
            result += getattr(component.stats, item)
        self.store(item, result)
