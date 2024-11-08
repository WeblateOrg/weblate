# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django import template

from weblate.auth.models import User
from weblate.lang.models import Language
from weblate.metrics.models import Metric
from weblate.metrics.wrapper import MetricsWrapper
from weblate.trans.models import (
    Category,
    Component,
    ComponentList,
    Project,
    Translation,
)
from weblate.utils.stats import CategoryLanguage, ProjectLanguage

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
    if isinstance(obj, Category):
        return MetricsWrapper(obj, Metric.SCOPE_CATEGORY, obj.pk)
    if isinstance(obj, CategoryLanguage):
        return MetricsWrapper(
            obj, Metric.SCOPE_CATEGORY_LANGUAGE, obj.category.id, obj.language.id
        )
    if isinstance(obj, Language):
        return MetricsWrapper(obj, Metric.SCOPE_LANGUAGE, obj.id)
    if isinstance(obj, User):
        return MetricsWrapper(obj, Metric.SCOPE_USER, obj.id)
    msg = f"Unsupported type for metrics: {obj!r}"
    raise ValueError(msg)
