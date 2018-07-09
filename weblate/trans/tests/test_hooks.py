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

"""Test for notification hooks."""

from django.urls import reverse
from django.test.utils import override_settings

from weblate.trans.tests.test_views import ViewTestCase

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

GITHUB_NEW_PAYLOAD = '''
{
"before": "5aef35982fb2d34e9d9d4502f6ede1072793222d",
"repository": {
"url": "http://github.com/defunkt/github",
"git_url": "git://github.com/defunkt/github.git",
"ssh_url": "git@github.com:defunkt/github.git",
"clone_url": "https://github.com/defunkt/github.git",
"svn_url": "https://github.com/defunkt/github",
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
    "url": "git@example.com:mike/diasporadiaspora.git",
    "description": "",
    "homepage": "http://example.com/mike/diaspora",
    "git_http_url":"http://example.com/mike/diaspora.git",
    "git_ssh_url":"git@example.com:mike/diaspora.git"
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

BITBUCKET_PAYLOAD_WEBHOOK = r'''
{
  "actor": {
    "username": "emmap1",
    "display_name": "Emma",
    "uuid": "{a54f16da-24e9-4d7f-a3a7-b1ba2cd98aa3}",
    "links": {
      "self": {
        "href": "https://api.bitbucket.org/api/2.0/users/emmap1"
      },
      "html": {
        "href": "https://api.bitbucket.org/emmap1"
      },
      "avatar": {
        "href": "https://bitbucket-api-assetroot/emmap1-avatar_avatar.png"
      }
    }
  },
  "repository": {
    "links": {
      "self": {
        "href": "https://api.bitbucket.org/api/2.0/repositories/bitbucket/bit"
      },
      "html": {
        "href": "https://api.bitbucket.org/bitbucket/bitbucket"
      },
      "avatar": {
        "href": "https://api-staging-assetroot/2629490769-3_avatar.png"
      }
    },
    "uuid": "{673a6070-3421-46c9-9d48-90745f7bfe8e}",
    "full_name": "team_name/repo_name",
    "name": "repo_name"
  },
  "push": {
    "changes": [
      {
        "new": {
          "type": "branch",
          "name": "name-of-branch",
          "target": {
            "type": "commit",
            "hash": "709d658dc5b6d6afcd46049c2f332ee3f515a67d",
            "author": {},
            "message": "new commit message\n",
            "date": "2015-06-09T03:34:49+00:00",
            "parents": [
              {
              "hash": "1e65c05c1d5171631d92438a13901ca7dae9618c",
              "type": "commit"
              }
            ]
          }
        },
        "old": {
          "type": "branch",
          "name": "name-of-branch",
          "target": {
            "type": "commit",
            "hash": "1e65c05c1d5171631d92438a13901ca7dae9618c",
            "author": {},
            "message": "old commit message\n",
            "date": "2015-06-08T21:34:56+00:00",
            "parents": [
              {
              "hash": "e0d0c2041e09746be5ce4b55067d5a8e3098c843",
              "type": "commit"
              }
            ]
          }
        },
        "created": false,
        "forced": false,
        "closed": false
      }
    ]
  }
}
'''

BITBUCKET_PAYLOAD_HOSTED = r'''
{
  "actor":{
    "username":"DSnoeck",
    "displayName":"Snoeck, Damien"
  },
  "repository":{
    "scmId":"git",
    "project":{
      "key":"~DSNOECK",
      "name":"Snoeck, Damien"
    },
    "slug":"weblate-training",
    "links":{
      "self":[
        {
          "href":"https://bitbucket.example.com/weblate-training/browse"
        }
      ]
    },
    "fullName":"~DSNOECK/weblate-training",
    "public":false,
    "ownerName":"~DSNOECK",
    "owner":{
      "username":"~DSNOECK",
      "displayName":"~DSNOECK"
    }
  },
  "push":{
    "changes":[
      {
        "created":false,
        "closed":false,
        "old":{
          "type":"branch",
          "name":"develop",
          "target":{
            "type":"commit",
            "hash":"2b44604898704e301a07dda936158a7ae96b1ab6"
          }
        },
        "new":{
          "type":"branch",
          "name":"develop",
          "target":{
            "type":"commit",
            "hash":"5371124bf9db76cd6c9386048ef3e821d1f59ff3"
          }
        }
      }
    ]
  }
}
'''

BITBUCKET_PAYLOAD_WEBHOOK_CLOSED = r'''
{
  "actor": {
    "username": "emmap1",
    "display_name": "Emma",
    "uuid": "{a54f16da-24e9-4d7f-a3a7-b1ba2cd98aa3}",
    "links": {
      "self": {
        "href": "https://api.bitbucket.org/api/2.0/users/emmap1"
      },
      "html": {
        "href": "https://api.bitbucket.org/emmap1"
      },
      "avatar": {
        "href": "https://bitbucket-api-assetroot/emmap1-avatar_avatar.png"
      }
    }
  },
  "repository": {
    "links": {
      "self": {
        "href": "https://api.bitbucket.org/api/2.0/repositories/bitbucket/bit"
      },
      "html": {
        "href": "https://api.bitbucket.org/bitbucket/bitbucket"
      },
      "avatar": {
        "href": "https://api-staging-assetroot/2629490769-3_avatar.png"
      }
    },
    "uuid": "{673a6070-3421-46c9-9d48-90745f7bfe8e}",
    "full_name": "team_name/repo_name",
    "name": "repo_name"
  },
  "push": {
    "changes": [
      {
        "new": null,
        "old": {
          "type": "branch",
          "name": "name-of-branch",
          "target": {
            "type": "commit",
            "hash": "1e65c05c1d5171631d92438a13901ca7dae9618c",
            "author": {},
            "message": "old commit message\n",
            "date": "2015-06-08T21:34:56+00:00",
            "parents": [
              {
              "hash": "e0d0c2041e09746be5ce4b55067d5a8e3098c843",
              "type": "commit"
              }
            ]
          }
        },
        "created": false,
        "forced": false,
        "closed": true
      }
    ]
  }
}
'''


class HooksViewTest(ViewTestCase):
    @override_settings(ENABLE_HOOKS=True, BACKGROUND_HOOKS=False)
    def test_hook_project(self):
        response = self.client.get(
            reverse('hook-project', kwargs=self.kw_project)
        )
        self.assertContains(response, 'Update triggered')

    @override_settings(ENABLE_HOOKS=True, BACKGROUND_HOOKS=False)
    def test_hook_component(self):
        response = self.client.get(
            reverse('hook-component', kwargs=self.kw_component)
        )
        self.assertContains(response, 'Update triggered')

    @override_settings(ENABLE_HOOKS=True, BACKGROUND_HOOKS=False)
    def test_hook_github_exists(self):
        # Adjust matching repo
        self.component.repo = 'git://github.com/defunkt/github.git'
        self.component.save()
        response = self.client.post(
            reverse('hook-github'),
            {'payload': GITHUB_PAYLOAD}
        )
        self.assertContains(response, 'Update triggered')

    @override_settings(ENABLE_HOOKS=True, BACKGROUND_HOOKS=False)
    def test_hook_github_new(self):
        # Adjust matching repo
        self.component.repo = 'git://github.com/defunkt/github.git'
        self.component.save()
        response = self.client.post(
            reverse('hook-github'),
            {'payload': GITHUB_NEW_PAYLOAD}
        )
        self.assertContains(response, 'Update triggered')

    @override_settings(ENABLE_HOOKS=True, BACKGROUND_HOOKS=False)
    def test_hook_github_ping(self):
        response = self.client.post(
            reverse('hook-github'),
            {'payload': '{"zen": "Approachable is better than simple."}'}
        )
        self.assertContains(response, 'Hook working')

    @override_settings(ENABLE_HOOKS=True, BACKGROUND_HOOKS=False)
    def test_hook_github_auth(self):
        # Adjust matching repo
        self.component.repo = 'https://user:pwd@github.com/defunkt/github.git'
        self.component.save()
        response = self.client.post(
            reverse('hook-github'),
            {'payload': GITHUB_PAYLOAD}
        )
        self.assertContains(response, 'Update triggered')

    @override_settings(ENABLE_HOOKS=True, BACKGROUND_HOOKS=False)
    def test_hook_github_disabled(self):
        # Adjust matching repo
        self.component.repo = 'git://github.com/defunkt/github.git'
        self.component.save()
        self.project.enable_hooks = False
        self.project.save()
        response = self.client.post(
            reverse('hook-github'),
            {'payload': GITHUB_PAYLOAD}
        )
        self.assertContains(response, 'No matching repositories found!')

    @override_settings(ENABLE_HOOKS=True, BACKGROUND_HOOKS=False)
    def test_hook_github(self):
        response = self.client.post(
            reverse('hook-github'),
            {'payload': GITHUB_PAYLOAD}
        )
        self.assertContains(response, 'No matching repositories found!')

    @override_settings(ENABLE_HOOKS=True, BACKGROUND_HOOKS=False)
    def test_hook_gitlab(self):
        response = self.client.post(
            reverse('hook-gitlab'), GITLAB_PAYLOAD,
            content_type="application/json"
        )
        self.assertContains(response, 'No matching repositories found!')

    @override_settings(ENABLE_HOOKS=True, BACKGROUND_HOOKS=False)
    def test_hook_bitbucket_ping(self):
        response = self.client.post(
            reverse('hook-bitbucket'),
            HTTP_X_EVENT_KEY='diagnostics:ping',
        )
        self.assertContains(response, 'Hook working')

    @override_settings(ENABLE_HOOKS=True, BACKGROUND_HOOKS=False)
    def test_hook_bitbucket_git(self):
        response = self.client.post(
            reverse('hook-bitbucket'),
            {'payload': BITBUCKET_PAYLOAD_GIT}
        )
        self.assertContains(response, 'No matching repositories found!')

    @override_settings(ENABLE_HOOKS=True, BACKGROUND_HOOKS=False)
    def test_hook_bitbucket_hg(self):
        response = self.client.post(
            reverse('hook-bitbucket'),
            {'payload': BITBUCKET_PAYLOAD_HG}
        )
        self.assertContains(response, 'No matching repositories found!')

    @override_settings(ENABLE_HOOKS=True, BACKGROUND_HOOKS=False)
    def test_hook_bitbucket_hg_no_commit(self):
        response = self.client.post(
            reverse('hook-bitbucket'),
            {'payload': BITBUCKET_PAYLOAD_HG_NO_COMMIT}
        )
        self.assertContains(response, 'No matching repositories found!')

    @override_settings(ENABLE_HOOKS=True, BACKGROUND_HOOKS=False)
    def test_hook_bitbucket_webhook(self):
        response = self.client.post(
            reverse('hook-bitbucket'),
            {'payload': BITBUCKET_PAYLOAD_WEBHOOK}
        )
        self.assertContains(response, 'No matching repositories found!')

    @override_settings(ENABLE_HOOKS=True, BACKGROUND_HOOKS=False)
    def test_hook_bitbucket_hosted(self):
        response = self.client.post(
            reverse('hook-bitbucket'),
            {'payload': BITBUCKET_PAYLOAD_HOSTED}
        )
        self.assertContains(response, 'No matching repositories found!')

    @override_settings(ENABLE_HOOKS=True, BACKGROUND_HOOKS=False)
    def test_hook_bitbucket_webhook_closed(self):
        response = self.client.post(
            reverse('hook-bitbucket'),
            {'payload': BITBUCKET_PAYLOAD_WEBHOOK_CLOSED}
        )
        self.assertContains(response, 'No matching repositories found!')

    @override_settings(ENABLE_HOOKS=False, BACKGROUND_HOOKS=False)
    def test_disabled(self):
        """Test for hooks disabling."""
        self.assert_disabled()

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

    def test_project_disabled(self):
        self.project.enable_hooks = False
        self.project.save()
        self.assert_disabled()

    def assert_disabled(self):
        response = self.client.get(
            reverse('hook-project', kwargs=self.kw_project)
        )
        self.assertEqual(response.status_code, 405)
        response = self.client.get(
            reverse('hook-component', kwargs=self.kw_component)
        )
        self.assertEqual(response.status_code, 405)

    @override_settings(ENABLE_HOOKS=True, BACKGROUND_HOOKS=False)
    def test_wrong_payload_github(self):
        """Test for invalid payloads with github."""
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

    @override_settings(ENABLE_HOOKS=True, BACKGROUND_HOOKS=False)
    def test_wrong_payload_gitlab(self):
        """Test for invalid payloads with gitlab."""
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
