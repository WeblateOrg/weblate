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

"""
Tests for notification hooks.
"""

from django.core.urlresolvers import reverse
from django.utils import simplejson
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans import appsettings

GITHUB_PAYLOAD = '''
{
"before": "5aef35982fb2d34e9d9d4502f6ede1072793222d",
"repository": {
"url": "http://github.com/defunkt/github",
"name": "github",
"description": "You're lookin' at it.",
"watchers": 5,
"forks": 2,
"private": 1,
"owner": {
"email": "chris@ozmm.org",
"name": "defunkt"
}
},
"commits": [
{
"id": "41a212ee83ca127e3c8cf465891ab7216a705f59",
"url": "http://github.com/defunkt/github/commit/41a212ee83ca127e3c8cf465891ab7216a705f59",
"author": {
"email": "chris@ozmm.org",
"name": "Chris Wanstrath"
},
"message": "okay i give in",
"timestamp": "2008-02-15T14:57:17-08:00",
"added": ["filepath.rb"]
},
{
"id": "de8251ff97ee194a289832576287d6f8ad74e3d0",
"url": "http://github.com/defunkt/github/commit/de8251ff97ee194a289832576287d6f8ad74e3d0",
"author": {
"email": "chris@ozmm.org",
"name": "Chris Wanstrath"
},
"message": "update pricing a tad",
"timestamp": "2008-02-15T14:36:34-08:00"
}
],
"after": "de8251ff97ee194a289832576287d6f8ad74e3d0",
"ref": "refs/heads/master"
}
'''


class HooksViewTest(ViewTestCase):
    def test_view_hook_project(self):
        appsettings.BACKGROUND_HOOKS = False
        response = self.client.get(
            reverse('hook-project', kwargs={
                'project': self.subproject.project.slug
            })
        )
        self.assertContains(response, 'update triggered')

    def test_view_hook_subproject(self):
        appsettings.BACKGROUND_HOOKS = False
        response = self.client.get(
            reverse('hook-subproject', kwargs={
                'project': self.subproject.project.slug,
                'subproject': self.subproject.slug,
            })
        )
        self.assertContains(response, 'update triggered')

    def test_view_hook_github(self):
        appsettings.BACKGROUND_HOOKS = False
        response = self.client.post(
            reverse('hook-github'),
            {'payload': GITHUB_PAYLOAD}
        )
        self.assertContains(response, 'update triggered')
