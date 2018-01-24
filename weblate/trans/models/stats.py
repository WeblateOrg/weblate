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


class TranslationStats(object):
    """Caching statistics calculator."""
    def __init__(self, translation):
        self._translation = translation
        self._key = 'stats-{}'.format(translation.pk)
        self._data = cache.get(self._key, {})

    def __getattr__(self, name):
        if name not in self._data:
            self.calculate_stats(name)
            self.save()
        return self._data[name]

    def invalidate(self):
        """Invalidate local and cache data."""
        self._data = {}
        cache.delete(self._key)

    def calculate_stats(self, item):
        """Calculate stats for translation."""
        if item.endswith('_words'):
            item = item[:-6]
        translation = self._translation
        stats = translation.unit_set.filter_type(
            item,
            translation.subproject.project,
            translation.language,
            strict=True
        ).aggregate(Count('pk'), Sum('num_words'))
        self._data[item] = stats['pk__count']
        key = '{}_words'.format(item)
        if stats['num_words__sum'] is None:
            self._data[key] = 0
        else:
            self._data[key] = stats['num_words__sum']

    def ensure_all(self):
        """Ensure we have complete set."""
        for item, dummy in get_filter_choice():
            if item not in self._data:
                self.calculate_stats(item)
        self.save()

    def save(self):
        """Save stats to cache."""
        cache.set(self._key, self._data)
