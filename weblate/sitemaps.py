# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from itertools import chain
from typing import NoReturn

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from weblate.trans.models import Change, Component, Project, Translation
from weblate.utils.stats import prefetch_stats


class PagesSitemap(Sitemap):
    def items(self):
        return (
            ("/", 1.0, "daily"),
            ("/about/", 0.4, "weekly"),
            ("/keys/", 0.4, "weekly"),
        )

    def location(self, obj):
        return obj[0]

    def lastmod(self, item):
        try:
            return Change.objects.values_list("timestamp", flat=True).order()[0]
        except Change.DoesNotExist:
            return None

    def priority(self, item):
        return item[1]

    def changefreq(self, item):
        return item[2]


class WeblateSitemap(Sitemap):
    priority = 0.0
    changefreq = None

    def items(self) -> NoReturn:
        raise NotImplementedError

    def lastmod(self, item):
        return item.stats.last_changed

    def get_latest_lastmod(self) -> None:
        # Finding latest lastmod is expensive as it needs fetching
        # stats for all objects
        return None


class ProjectSitemap(WeblateSitemap):
    priority = 0.8

    def items(self):
        return prefetch_stats(
            Project.objects.filter(access_control__lt=Project.ACCESS_PRIVATE).order_by(
                "id"
            )
        )


class ComponentSitemap(WeblateSitemap):
    priority = 0.6

    def items(self):
        return prefetch_stats(
            Component.objects.prefetch_related("project")
            .filter(project__access_control__lt=Project.ACCESS_PRIVATE)
            .order_by("id")
        )


class TranslationSitemap(WeblateSitemap):
    priority = 0.2

    def items(self):
        return prefetch_stats(
            Translation.objects.prefetch_related(
                "component",
                "component__project",
                "language",
            )
            .filter(component__project__access_control__lt=Project.ACCESS_PRIVATE)
            .order_by("id")
        )


class EngageSitemap(ProjectSitemap):
    """Wrapper around ProjectSitemap to point to engage page."""

    priority = 1.0

    def location(self, obj):
        return reverse("engage", kwargs={"path": obj.get_url_path()})


class EngageLangSitemap(EngageSitemap):
    """Wrapper to generate sitemap for all per language engage pages."""

    priority = 0.9

    def items(self):
        """Return list of existing project, language tuples."""
        projects = (
            Project.objects.filter(access_control__lt=Project.ACCESS_PRIVATE)
            .order_by("id")
            .prefetch_languages()
        )
        return prefetch_stats(
            chain.from_iterable(
                project.project_languages.preload() for project in projects
            )
        )


SITEMAPS = {
    "project": ProjectSitemap(),
    "engage": EngageSitemap(),
    "engagelang": EngageLangSitemap(),
    "component": ComponentSitemap(),
    "translation": TranslationSitemap(),
    "pages": PagesSitemap(),
}
