# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.contrib.sitemaps import GenericSitemap, Sitemap
from django.core.urlresolvers import reverse
from weblate.trans.models import Project, SubProject, Translation, Change
from weblate.accounts.models import Profile

PROJECT_DICT = {
    'queryset': Project.objects.all_acl(None),
    'date_field': 'last_change',
}

SUBPROJECT_DICT = {
    'queryset': SubProject.objects.filter(
        project__in=Project.objects.all_acl(None)
    ),
    'date_field': 'last_change',
}

TRANSLATION_DICT = {
    'queryset': Translation.objects.filter(
        subproject__project__in=Project.objects.all_acl(None)
    ),
    'date_field': 'last_change',
}

USER_DICT = {
    'queryset': Profile.objects.all(),
    'date_field': 'last_change',
}


class PagesSitemap(Sitemap):
    def items(self):
        return (
            ('/', 1.0, 'daily'),
            ('/about/', 0.8, 'daily'),
            ('/contact/', 0.2, 'monthly'),
        )

    def location(self, item):
        return item[0]

    def lastmod(self, item):
        return Change.objects.all()[0].timestamp

    def priority(self, item):
        return item[1]

    def changefreq(self, item):
        return item[2]


class EngageSitemap(GenericSitemap):
    '''
    Wrapper around GenericSitemap to point to engage page.
    '''
    def location(self, obj):
        return reverse('engage', kwargs={'project': obj.slug})


class EngageLangSitemap(Sitemap):
    '''
    Wrapper to generate sitemap for all per language engage pages.
    '''
    priority = 0.9

    def items(self):
        '''
        Return list of existing project, langauge tuples.
        '''
        ret = []
        for project in Project.objects.all_acl(None):
            for lang in project.get_languages():
                ret.append((project, lang))
        return ret

    def location(self, item):
        return reverse(
            'engage-lang',
            kwargs={'project': item[0].slug, 'lang': item[1].code}
        )


SITEMAPS = {
    'project': GenericSitemap(PROJECT_DICT, priority=0.8),
    'engage': EngageSitemap(PROJECT_DICT, priority=1.0),
    'engagelang': EngageLangSitemap(),
    'subproject': GenericSitemap(SUBPROJECT_DICT, priority=0.6),
    'translation': GenericSitemap(TRANSLATION_DICT, priority=0.2),
    'user': GenericSitemap(USER_DICT, priority=0.1),
    'pages': PagesSitemap(),
}
