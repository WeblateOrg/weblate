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

from django import template

from weblate.lang.models import Language
from weblate.metrics.models import Metric
from weblate.trans.models import Component, ComponentList, Project, Translation
from weblate.utils.stats import ProjectLanguage

register = template.Library()


class MetricsWrapper:
    def __init__(self, obj, scope: int, relation: int, secondary: int = 0):
        self.obj = obj
        self.scope = scope
        self.relation = relation
        self.current = Metric.objects.get_current(obj, scope, relation, secondary)
        self.past_30 = Metric.objects.get_past(scope, relation, secondary, 30)
        self.past_60 = Metric.objects.get_past(scope, relation, secondary, 60)

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
        return self.current["contributors"]

    def calculate_trend_percent(self, key, modkey, base: Dict, origin: Dict):
        total = base[key]
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
        total = base[key]
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


@register.filter
def metrics(obj):
    if obj is None:
        return MetricsWrapper(obj, Metric.SCOPE_GLOBAL, 0)
    if isinstance(obj, Translation):
        return MetricsWrapper(obj, Metric.SCOPE_TRANSLATION, obj.pk)
    if isinstance(obj, Component):
        return MetricsWrapper(obj, Metric.SCOPE_COMPONENT, obj.pk)
    if isinstance(obj, Project):
        return MetricsWrapper(obj, Metric.SCOPE_PROJECT, obj.pk)
    if isinstance(obj, ComponentList):
        return MetricsWrapper(obj, Metric.SCOPE_COMPONENT_LIST, obj.pk)
    if isinstance(obj, ProjectLanguage):
        return MetricsWrapper(
            obj, Metric.SCOPE_PROJECT_LANGUAGE, obj.project.id, obj.language.id
        )
    if isinstance(obj, Language):
        return MetricsWrapper(obj, Metric.SCOPE_LANGUAGE, obj.id)
    raise ValueError(f"Unsupported type for metrics: {obj!r}")
