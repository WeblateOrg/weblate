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

from django import template

from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.metrics.models import Metric
from weblate.metrics.wrapper import MetricsWrapper
from weblate.trans.models import Component, ComponentList, Project, Translation
from weblate.utils.stats import ProjectLanguage

register = template.Library()


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
    if isinstance(obj, User):
        return MetricsWrapper(obj, Metric.SCOPE_USER, obj.id)
    raise ValueError(f"Unsupported type for metrics: {obj!r}")
