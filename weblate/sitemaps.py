# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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
from weblate.trans.models import Project, SubProject, Translation
from weblate.accounts.models import Profile

project_dict = {
    'queryset': Project.objects.all_acl(None),
    'date_field': 'get_last_change',
}

subproject_dict = {
    'queryset': SubProject.objects.all_acl(None),
    'date_field': 'get_last_change',
}

translation_dict = {
    'queryset': Translation.objects.all_acl(None),
    'date_field': 'get_last_change',
}

user_dict = {
    'queryset': Profile.objects.all(),
    'date_field': 'get_last_change',
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
        from weblate.trans.models import Change
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
        from django.core.urlresolvers import reverse
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
        from django.core.urlresolvers import reverse
        return reverse(
            'engage-lang',
            kwargs={'project': item[0].slug, 'lang': item[1].code}
        )


sitemaps = {
    'project': GenericSitemap(project_dict, priority=0.8),
    'engage': EngageSitemap(project_dict, priority=1.0),
    'engagelang': EngageLangSitemap(),
    'subproject': GenericSitemap(subproject_dict, priority=0.6),
    'translation': GenericSitemap(translation_dict, priority=0.2),
    'user': GenericSitemap(user_dict, priority=0.1),
    'pages': PagesSitemap(),
}
