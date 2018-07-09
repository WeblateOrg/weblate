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

from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from weblate.trans.models import Project, Component, Translation, Change


class PagesSitemap(Sitemap):
    def items(self):
        return (
            ('/', 1.0, 'daily'),
            ('/about/', 0.8, 'daily'),
        )

    def location(self, obj):
        return obj[0]

    def lastmod(self, item):
        return Change.objects.values_list('timestamp', flat=True)[0]

    def priority(self, item):
        return item[1]

    def changefreq(self, item):
        return item[2]


class WeblateSitemap(Sitemap):
    priority = None
    changefreq = None

    def items(self):
        raise NotImplementedError()

    def lastmod(self, item):
        return item.last_change


class ProjectSitemap(WeblateSitemap):
    priority = 0.8

    def items(self):
        return Project.objects.filter(
            access_control__lt=Project.ACCESS_PRIVATE
        )


class ComponentSitemap(WeblateSitemap):
    priority = 0.6

    def items(self):
        return Component.objects.prefetch().filter(
            project__access_control__lt=Project.ACCESS_PRIVATE
        )


class TranslationSitemap(WeblateSitemap):
    priority = 0.2

    def items(self):
        return Translation.objects.prefetch().filter(
            component__project__access_control__lt=Project.ACCESS_PRIVATE
        )


class EngageSitemap(ProjectSitemap):
    """Wrapper around ProjectSitemap to point to engage page."""
    priority = 1.0

    def location(self, obj):
        return reverse('engage', kwargs={'project': obj.slug})


class EngageLangSitemap(Sitemap):
    """Wrapper to generate sitemap for all per language engage pages."""
    priority = 0.9

    def items(self):
        """Return list of existing project, language tuples."""
        ret = []
        projects = Project.objects.filter(
            access_control__lt=Project.ACCESS_PRIVATE
        )
        for project in projects:
            for lang in project.get_languages():
                ret.append((project, lang))
        return ret

    def location(self, obj):
        return reverse(
            'engage',
            kwargs={'project': obj[0].slug, 'lang': obj[1].code}
        )


SITEMAPS = {
    'project': ProjectSitemap(),
    'engage': EngageSitemap(),
    'engagelang': EngageLangSitemap(),
    'component': ComponentSitemap(),
    'translation': TranslationSitemap(),
    'pages': PagesSitemap(),
}
