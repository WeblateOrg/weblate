# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Components list."""

import re

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy

from weblate.trans.fields import RegexField
from weblate.trans.mixins import CacheKeyMixin
from weblate.utils.stats import ComponentListStats


class ComponentListQuerySet(models.QuerySet):
    def order(self):
        return self.order_by("name")


class ComponentList(models.Model, CacheKeyMixin):
    name = models.CharField(
        verbose_name=gettext_lazy("Component list name"),
        max_length=100,
        unique=True,
        help_text=gettext_lazy("Display name"),
    )

    slug = models.SlugField(
        verbose_name=gettext_lazy("URL slug"),
        db_index=True,
        unique=True,
        max_length=100,
        help_text=gettext_lazy("Name used in URLs and filenames."),
    )
    show_dashboard = models.BooleanField(
        verbose_name=gettext_lazy("Show on dashboard"),
        default=True,
        db_index=True,
        help_text=gettext_lazy(
            "When enabled this component list will be shown as a tab on the dashboard"
        ),
    )

    components = models.ManyToManyField("trans.Component", blank=True)

    objects = ComponentListQuerySet.as_manager()

    class Meta:
        verbose_name = "Component list"
        verbose_name_plural = "Component lists"

    def __str__(self) -> str:
        return self.name

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.stats = ComponentListStats(self)

    def get_absolute_url(self) -> str:
        return reverse("component-list", kwargs={"name": self.slug})

    def tab_slug(self):
        return "list-" + self.slug


class AutoComponentList(models.Model):
    project_match = RegexField(
        verbose_name=gettext_lazy("Project regular expression"),
        max_length=200,
        default="^$",
        help_text=gettext_lazy(
            "Regular expression which is used to match project slug."
        ),
    )
    component_match = RegexField(
        verbose_name=gettext_lazy("Component regular expression"),
        max_length=200,
        default="^$",
        help_text=gettext_lazy(
            "Regular expression which is used to match component slug."
        ),
    )
    componentlist = models.ForeignKey(
        ComponentList,
        verbose_name=gettext_lazy("Component list to assign"),
        on_delete=models.deletion.CASCADE,
    )

    class Meta:
        verbose_name = "Automatic component list assignment"
        verbose_name_plural = "Automatic component list assignments"

    def __str__(self) -> str:
        return self.componentlist.name

    def check_match(self, component) -> None:
        if not re.match(self.project_match, component.project.slug):
            return
        if not re.match(self.component_match, component.slug):
            return
        self.componentlist.components.add(component)
