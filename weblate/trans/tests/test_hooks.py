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

"""
Tests for notification hooks.
"""

from django.core.urlresolvers import reverse
from weblate.trans.tests.test_views import ViewTestCase
from weblate import appsettings

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
"url": "http://github.com/defunkt/github/commit/41a212ee83",
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
"url": "http://github.com/defunkt/github/commit/de8251ff97",
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

GITLAB_PAYLOAD = '''
{
  "before": "95790bf891e76fee5e1747ab589903a6a1f80f22",
  "after": "da1560886d4f094c3e6c9ef40349f7d38b5d27d7",
  "ref": "refs/heads/master",
  "user_id": 4,
  "user_name": "John Smith",
  "project_id": 15,
  "repository": {
    "name": "Diaspora",
    "url": "git@example.com:diaspora.git",
    "description": "",
    "homepage": "http://example.com/diaspora"
  },
  "commits": [
    {
      "id": "b6568db1bc1dcd7f8b4d5a946b0b91f9dacd7327",
      "message": "Update Catalan translation to e38cb41.",
      "timestamp": "2011-12-12T14:27:31+02:00",
      "url": "http://example.com/diaspora/commits/b6568db1b",
      "author": {
        "name": "Jordi Mallach",
        "email": "jordi@softcatala.org"
      }
    },
    {
      "id": "da1560886d4f094c3e6c9ef40349f7d38b5d27d7",
      "message": "fixed readme",
      "timestamp": "2012-01-03T23:36:29+02:00",
      "url": "http://example.com/diaspora/commits/da1560886",
      "author": {
        "name": "GitLab dev user",
        "email": "gitlabdev@dv6700.(none)"
      }
    }
  ],
  "total_commits_count": 4
}
'''

BITBUCKET_PAYLOAD_GIT = '''
{
    "canon_url": "https://bitbucket.org",
    "commits": [
        {
            "author": "marcus",
            "branch": "master",
            "files": [
                {
                    "file": "somefile.py",
                    "type": "modified"
                }
            ],
            "message": "Added some more things to somefile.py\\n",
            "node": "620ade18607a",
            "parents": [
                "702c70160afc"
            ],
            "raw_author": "Marcus Bertrand <marcus@somedomain.com>",
            "raw_node": "620ade18607ac42d872b568bb92acaa9a28620e9",
            "revision": null,
            "size": -1,
            "timestamp": "2012-05-30 05:58:56",
            "utctimestamp": "2012-05-30 03:58:56+00:00"
        }
    ],
    "repository": {
        "absolute_url": "/marcus/project-x/",
        "fork": false,
        "is_private": true,
        "name": "Project X",
        "owner": "marcus",
        "scm": "git",
        "slug": "project-x",
        "website": "https://atlassian.com/"
    },
    "user": "marcus"
}
'''


BITBUCKET_PAYLOAD_HG = '''
{
    "canon_url": "https://bitbucket.org",
    "commits": [
        {
            "author": "marcus",
            "branch": "featureA",
            "files": [
                {
                    "file": "somefile.py",
                    "type": "modified"
                }
            ],
            "message": "Added some featureA things",
            "node": "d14d26a93fd2",
            "parents": [
                "1b458191f31a"
            ],
            "raw_author": "Marcus Bertrand <marcus@somedomain.com>",
            "raw_node": "d14d26a93fd28d3166fa81c0cd3b6f339bb95bfe",
            "revision": 3,
            "size": -1,
            "timestamp": "2012-05-30 06:07:03",
            "utctimestamp": "2012-05-30 04:07:03+00:00"
        }
    ],
    "repository": {
        "absolute_url": "/marcus/project-x/",
        "fork": false,
        "is_private": true,
        "name": "Project X",
        "owner": "marcus",
        "scm": "hg",
        "slug": "project-x",
        "website": ""
    },
    "user": "marcus"
}
'''


BITBUCKET_PAYLOAD_HG_NO_COMMIT = '''
{
    "canon_url": "https://bitbucket.org",
    "commits": [],
    "repository": {
        "absolute_url": "/marcus/project-x/",
        "fork": false,
        "is_private": true,
        "name": "Project X",
        "owner": "marcus",
        "scm": "hg",
        "slug": "project-x",
        "website": ""
    },
    "user": "marcus"
}
'''


class HooksViewTest(ViewTestCase):
    def test_view_hook_project(self):
        appsettings.BACKGROUND_HOOKS = False
        appsettings.ENABLE_HOOKS = True
        response = self.client.get(
            reverse('hook-project', kwargs={
                'project': self.subproject.project.slug
            })
        )
        self.assertContains(response, 'update triggered')

    def test_view_hook_subproject(self):
        appsettings.BACKGROUND_HOOKS = False
        appsettings.ENABLE_HOOKS = True
        response = self.client.get(
            reverse('hook-subproject', kwargs={
                'project': self.subproject.project.slug,
                'subproject': self.subproject.slug,
            })
        )
        self.assertContains(response, 'update triggered')

    def test_view_hook_github(self):
        appsettings.BACKGROUND_HOOKS = False
        appsettings.ENABLE_HOOKS = True
        response = self.client.post(
            reverse('hook-github'),
            {'payload': GITHUB_PAYLOAD}
        )
        self.assertContains(response, 'update triggered')

    def test_view_hook_gitlab(self):
        appsettings.BACKGROUND_HOOKS = False
        appsettings.ENABLE_HOOKS = True
        response = self.client.post(
            reverse('hook-gitlab'), GITLAB_PAYLOAD,
            content_type="application/json"
        )
        self.assertContains(response, 'update triggered')

    def test_view_hook_bitbucket_git(self):
        appsettings.BACKGROUND_HOOKS = False
        appsettings.ENABLE_HOOKS = True
        response = self.client.post(
            reverse('hook-bitbucket'),
            {'payload': BITBUCKET_PAYLOAD_GIT}
        )
        self.assertContains(response, 'update triggered')

    def test_view_hook_bitbucket_hg(self):
        appsettings.BACKGROUND_HOOKS = False
        appsettings.ENABLE_HOOKS = True
        response = self.client.post(
            reverse('hook-bitbucket'),
            {'payload': BITBUCKET_PAYLOAD_HG}
        )
        self.assertContains(response, 'update triggered')

    def test_view_hook_bitbucket_hg_no_commit(self):
        appsettings.BACKGROUND_HOOKS = False
        appsettings.ENABLE_HOOKS = True
        response = self.client.post(
            reverse('hook-bitbucket'),
            {'payload': BITBUCKET_PAYLOAD_HG_NO_COMMIT}
        )
        self.assertContains(response, 'update triggered')

    def test_disabled(self):
        '''
        Test for hooks disabling.
        '''
        appsettings.ENABLE_HOOKS = False
        response = self.client.get(
            reverse('hook-project', kwargs={
                'project': self.subproject.project.slug
            })
        )
        self.assertEqual(response.status_code, 405)
        response = self.client.get(
            reverse('hook-subproject', kwargs={
                'project': self.subproject.project.slug,
                'subproject': self.subproject.slug,
            })
        )
        self.assertEqual(response.status_code, 405)
        response = self.client.post(
            reverse('hook-github'),
            {'payload': GITHUB_PAYLOAD}
        )
        self.assertEqual(response.status_code, 405)
        response = self.client.post(
            reverse('hook-gitlab'), GITLAB_PAYLOAD,
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 405)
        response = self.client.post(
            reverse('hook-bitbucket'),
            {'payload': BITBUCKET_PAYLOAD_GIT}
        )
        self.assertEqual(response.status_code, 405)

    def test_wrong_payload_github(self):
        '''
        Tests for invalid payloads with github.
        '''
        # missing
        response = self.client.post(
            reverse('hook-github'),
        )
        self.assertContains(
            response,
            'Could not parse JSON payload!',
            status_code=400
        )
        # wrong
        response = self.client.post(
            reverse('hook-github'),
            {'payload': 'XX'},
        )
        self.assertContains(
            response,
            'Could not parse JSON payload!',
            status_code=400
        )
        # missing data
        response = self.client.post(
            reverse('hook-github'),
            {'payload': '{}'},
        )
        self.assertContains(
            response,
            'Invalid data in json payload!',
            status_code=400
        )

    def test_wrong_payload_gitlab(self):
        '''
        Tests for invalid payloads with gitlab.
        '''
        # missing
        response = self.client.post(
            reverse('hook-gitlab'),
        )
        self.assertContains(
            response,
            'Could not parse JSON payload!',
            status_code=400
        )
        # missing content-type header
        response = self.client.post(
            reverse('hook-gitlab'),
            {'payload': 'anything'}
        )
        self.assertContains(
            response,
            'Could not parse JSON payload!',
            status_code=400
        )
        # wrong
        response = self.client.post(
            reverse('hook-gitlab'), 'xx',
            content_type="application/json"
        )
        self.assertContains(
            response,
            'Could not parse JSON payload!',
            status_code=400
        )
        # missing data
        response = self.client.post(
            reverse('hook-gitlab'), '{}',
            content_type="application/json"
        )
        self.assertContains(
            response,
            'Invalid data in json payload!',
            status_code=400
        )
