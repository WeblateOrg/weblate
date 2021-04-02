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

from typing import Dict

from django.utils.functional import cached_property

from weblate.metrics.models import Metric


class MetricsWrapper:
    def __init__(self, obj, scope: int, relation: int, secondary: int = 0):
        self.obj = obj
        self.scope = scope
        self.relation = relation
        self.secondary = secondary

    @cached_property
    def current(self):
        return Metric.objects.get_current(
            self.obj, self.scope, self.relation, self.secondary
        )

    @cached_property
    def past_30(self):
        return Metric.objects.get_past(self.scope, self.relation, self.secondary, 30)

    @cached_property
    def past_60(self):
        return Metric.objects.get_past(self.scope, self.relation, self.secondary, 60)

    @property
    def all_words(self):
        return self.current["all_words"]

    @property
    def all(self):
        return self.current["all"]

    @property
    def translated_percent(self):
        total = self.all
        if not total:
            return 0
        return 100 * self.current["translated"] / total

    @property
    def contributors(self):
        return self.current.get("contributors", 0)

    def calculate_trend_percent(self, key, modkey, base: Dict, origin: Dict):
        total = base.get(key, 0)
        if not total:
            return 0
        divisor = base[modkey]
        if not divisor:
            return 0
        total = 100 * total / divisor

        past = origin[key]
        if not past:
            return total

        divisor = origin[modkey]
        if not divisor:
            return total
        past = 100 * past / divisor
        return total - past

    def calculate_trend(self, key, base: Dict, origin: Dict):
        total = base.get(key, 0)
        if not total:
            return 0
        return 100 * (total - origin[key]) / total

    @property
    def trend_30_all(self):
        return self.calculate_trend("all", self.current, self.past_30)

    @property
    def trend_30_all_words(self):
        return self.calculate_trend("all_words", self.current, self.past_30)

    @property
    def trend_30_contributors(self):
        return self.calculate_trend("contributors", self.current, self.past_30)

    @property
    def trend_30_translated_percent(self):
        return self.calculate_trend_percent(
            "translated", "all", self.current, self.past_30
        )

    @property
    def trend_60_all(self):
        return self.calculate_trend("all", self.past_30, self.past_60)

    @property
    def trend_60_all_words(self):
        return self.calculate_trend("all_words", self.past_30, self.past_60)

    @property
    def trend_60_contributors(self):
        return self.calculate_trend("contributors", self.past_30, self.past_60)

    @property
    def trend_60_translated_percent(self):
        return self.calculate_trend_percent(
            "translated", "all", self.past_30, self.past_60
        )

    @property
    def projects(self):
        return self.current["projects"]

    @property
    def languages(self):
        return self.current["languages"]

    @property
    def components(self):
        return self.current["components"]

    @property
    def users(self):
        return self.current["users"]

    @property
    def trend_30_projects(self):
        return self.calculate_trend("projects", self.current, self.past_30)

    @property
    def trend_30_languages(self):
        return self.calculate_trend("languages", self.current, self.past_30)

    @property
    def trend_30_components(self):
        return self.calculate_trend("components", self.current, self.past_30)

    @property
    def trend_30_users(self):
        return self.calculate_trend("users", self.current, self.past_30)

    @property
    def trend_60_projects(self):
        return self.calculate_trend("projects", self.past_30, self.past_60)

    @property
    def trend_60_languages(self):
        return self.calculate_trend("languages", self.past_30, self.past_60)

    @property
    def trend_60_components(self):
        return self.calculate_trend("components", self.past_30, self.past_60)

    @property
    def trend_60_users(self):
        return self.calculate_trend("users", self.past_30, self.past_60)
