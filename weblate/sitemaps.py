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

    def items(self):
        raise NotImplementedError()

    def lastmod(self, item):
        return item.stats.last_changed


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
        return reverse("engage", kwargs={"project": obj.slug})


class EngageLangSitemap(Sitemap):
    """Wrapper to generate sitemap for all per language engage pages."""

    priority = 0.9

    def items(self):
        """Return list of existing project, language tuples."""
        ret = []
        projects = Project.objects.filter(
            access_control__lt=Project.ACCESS_PRIVATE
        ).order_by("id")
        for project in projects:
            for lang in project.languages:
                ret.append((project, lang))
        return ret

    def location(self, obj):
        return reverse("engage", kwargs={"project": obj[0].slug, "lang": obj[1].code})


SITEMAPS = {
    "project": ProjectSitemap(),
    "engage": EngageSitemap(),
    "engagelang": EngageLangSitemap(),
    "component": ComponentSitemap(),
    "translation": TranslationSitemap(),
    "pages": PagesSitemap(),
}
