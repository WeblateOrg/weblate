# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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

from __future__ import unicode_literals

import json

from django.test import SimpleTestCase
from django.test.utils import override_settings
from django.urls import reverse

from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.views.hooks import HOOK_HANDLERS

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
          "href":"https://example.com/weblate-training/browse"
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

BITBUCKET_PAYLOAD_SERVER = r'''
{
    "eventKey": "repo:refs_changed",
    "date": "2019-02-20T03:28:49+0000",
    "actor": {
        "name": "joe.blogs",
        "emailAddress": "joe.bloggs@example.com",
        "id": 160,
        "displayName": "Joe Bloggs",
        "active": true,
        "slug": "joe.blogs",
        "type": "NORMAL",
        "links": {
            "self": [
                {
                    "href": "https://example.com/users/joe.blogs"
                }
            ]
        }
    },
    "repository": {
        "slug": "my-repo",
        "id": 3944,
        "name": "my-repo",
        "scmId": "git",
        "state": "AVAILABLE",
        "statusMessage": "Available",
        "forkable": true,
        "project": {
            "key": "SANDPIT",
            "id": 205,
            "name": "Sandpit",
            "description": "sandpit project",
            "public": false,
            "type": "NORMAL",
            "links": {
                "self": [
                    {
                        "href": "https://example.com/projects/SANDPIT"
                    }
                ]
            }
        },
        "public": false,
        "links": {
            "clone": [
                {
                    "href": "https://example.com/scm/sandpit/my-repo.git",
                    "name": "http"
                },
                {
                    "href": "ssh://git@example.com:7999/sandpit/my-repo.git",
                    "name": "ssh"
                }
            ],
            "self": [
                {
                    "href": "https://example.com/projects/SANDPIT/repos/my-repo/browse"
                }
            ]
        }
    },
    "changes": [
        {
            "ref": {
                "id": "refs/heads/master",
                "displayId": "master",
                "type": "BRANCH"
            },
            "refId": "refs/heads/master",
            "fromHash": "fdff3f418a8e3d25d6c8cb80776d6ac142bef800",
            "toHash": "7cb42185f7d8eab95f5fac3de2648a16361ecf34",
            "type": "UPDATE"
        }
    ]
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

PAGURE_PAYLOAD = r'''
{
    "i": 17,
    "msg": {
        "agent": "nijel",
        "authors": [
            {
                "fullname": "Michal \u010ciha\u0159",
                "name": "nijel"
            }
        ],
        "branch": "master",
        "end_commit": "4d0f02a0282c5fcd10a396624d3f6b950dc16296",
        "forced": false,
        "pagure_instance": "https://pagure.io/",
        "project_fullname": "nijel-test",
        "repo": {
            "access_groups": {
                "admin": [],
                "commit": [],
                "ticket": []
            },
            "access_users": {
                "admin": [],
                "commit": [],
                "owner": [
                    "nijel"
                ],
                "ticket": []
            },
            "close_status": [],
            "custom_keys": [],
            "date_created": "1539762879",
            "date_modified": "1539763111",
            "description": "Test",
            "fullname": "nijel-test",
            "id": 5075,
            "milestones": {},
            "name": "nijel-test",
            "namespace": null,
            "parent": null,
            "priorities": {},
            "tags": [],
            "url_path": "nijel-test",
            "user": {
                "fullname": "Michal \u010ciha\u0159",
                "name": "nijel"
            }
        },
        "start_commit": "4d0f02a0282c5fcd10a396624d3f6b950dc16296",
        "total_commits": 1
    },
    "msg_id": "2018-8eb272b9-e33b-42f6-af06-fce41a5494de",
    "timestamp": 1539763221,
    "topic": "git.receive"
}
'''


AZURE_PAYLOAD = r'''
{
  "subscriptionId": "00000000-0000-0000-0000-000000000000",
  "notificationId": 1,
  "id": "03c164c2-8912-4d5e-8009-3707d5f83734",
  "eventType": "git.push",
  "publisherId": "tfs",
  "message": {
    "text": "Jamal Hartnett pushed updates to ATEST:master.",
    "html": "Jamal Hartnett pushed updates to ATEST:master.",
    "markdown": "Jamal Hartnett pushed updates to `ATEST`:`master`."
  },
  "detailedMessage": {
    "text": "Jamal Hartnett pushed a commit to ATEST:master.",
    "html": "Jamal Hartnett pushed a commit to ",
    "markdown": "Jamal Hartnett pushed a commit to [ATEST])"
  },
  "resource": {
    "commits": [
      {
        "commitId": "33b55f7cb7e7e245323987634f960cf4a6e6bc74",
        "author": {
          "name": "Jamal Hartnett",
          "email": "fabrikamfiber4@hotmail.com",
          "date": "2015-02-25T19:01:00Z"
        },
        "committer": {
          "name": "Jamal Hartnett",
          "email": "fabrikamfiber4@hotmail.com",
          "date": "2015-02-25T19:01:00Z"
        },
        "comment": "Fixed bug in web.config file",
        "url": "https://f.visualstudio.com/c/_git/ATEST/commit/33b55f7cb7e7e2453239"
      }
    ],
    "refUpdates": [
      {
        "name": "refs/heads/master",
        "oldObjectId": "aad331d8d3b131fa9ae03cf5e53965b51942618a",
        "newObjectId": "33b55f7cb7e7e245323987634f960cf4a6e6bc74"
      }
    ],
    "repository": {
      "id": "278d5cd2-584d-4b63-824a-2ba458937249",
      "name": "ATEST",
      "url": "https://f.visualstudio.com/c/_apis/git/repositories/278d5cd2-584d-4b63",
      "project": {
        "id": "6ce954b1-ce1f-45d1-b94d-e6bf2464ba2c",
        "name": "ATEST",
        "url": "https://f.visualstudio.com/c/_apis/projects/6ce954b1-ce1f-45d1",
        "state": "wellFormed",
        "visibility": "unchanged",
        "lastUpdateTime": "0001-01-01T00:00:00"
      },
      "defaultBranch": "refs/heads/master",
      "remoteUrl": "https://f.visualstudio.com/c/_git/ATEST"
    },
    "pushedBy": {
      "displayName": "Jamal Hartnett",
      "id": "00067FFED5C7AF52@Live.com",
      "uniqueName": "fabrikamfiber4@hotmail.com"
    },
    "pushId": 14,
    "date": "2014-05-02T19:17:13.3309587Z",
    "url": "https://f.visualstudio.com/c/_apis/git/repositories/278d5cd2/pushes/14"
  },
  "resourceVersion": "1.0",
  "resourceContainers": {
    "collection": {
      "id": "c12d0eb8-e382-443b-9f9c-c52cba5014c2"
    },
    "account": {
      "id": "f844ec47-a9db-4511-8281-8b63f4eaf94e"
    },
    "project": {
      "id": "be9b3917-87e6-42a4-a549-2bc06a7a878f"
    }
  },
  "createdDate": "2019-08-06T12:12:53.3798179Z"
}
'''


class HooksViewTest(ViewTestCase):
    @override_settings(ENABLE_HOOKS=True)
    def test_hook_project(self):
        response = self.client.get(
            reverse('hook-project', kwargs=self.kw_project)
        )
        self.assertContains(response, 'Update triggered')

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_component(self):
        response = self.client.get(
            reverse('hook-component', kwargs=self.kw_component)
        )
        self.assertContains(response, 'Update triggered')

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_github_exists(self):
        # Adjust matching repo
        self.component.repo = 'git://github.com/defunkt/github.git'
        self.component.save()
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'github'}),
            {'payload': GITHUB_PAYLOAD}
        )
        self.assertContains(response, 'Update triggered')

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_github_new(self):
        # Adjust matching repo
        self.component.repo = 'git://github.com/defunkt/github.git'
        self.component.save()
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'github'}),
            {'payload': GITHUB_NEW_PAYLOAD}
        )
        self.assertContains(response, 'Update triggered')

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_github_ping(self):
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'github'}),
            {'payload': '{"zen": "Approachable is better than simple."}'}
        )
        self.assertContains(response, 'Hook working')

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_github_auth(self):
        # Adjust matching repo
        self.component.repo = 'https://user:pwd@github.com/defunkt/github.git'
        self.component.save()
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'github'}),
            {'payload': GITHUB_PAYLOAD}
        )
        self.assertContains(response, 'Update triggered')

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_github_disabled(self):
        # Adjust matching repo
        self.component.repo = 'git://github.com/defunkt/github.git'
        self.component.save()
        self.project.enable_hooks = False
        self.project.save()
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'github'}),
            {'payload': GITHUB_PAYLOAD}
        )
        self.assertContains(response, 'No matching repositories found!')

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_github(self):
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'github'}),
            {'payload': GITHUB_PAYLOAD}
        )
        self.assertContains(response, 'No matching repositories found!')

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_gitlab(self):
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'gitlab'}), GITLAB_PAYLOAD,
            content_type="application/json"
        )
        self.assertContains(response, 'No matching repositories found!')

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_bitbucket_ping(self):
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'bitbucket'}),
            HTTP_X_EVENT_KEY='diagnostics:ping',
        )
        self.assertContains(response, 'Hook working')

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_bitbucket_git(self):
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'bitbucket'}),
            {'payload': BITBUCKET_PAYLOAD_GIT}
        )
        self.assertContains(response, 'No matching repositories found!')

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_bitbucket_hg(self):
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'bitbucket'}),
            {'payload': BITBUCKET_PAYLOAD_HG}
        )
        self.assertContains(response, 'No matching repositories found!')

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_bitbucket_hg_no_commit(self):
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'bitbucket'}),
            {'payload': BITBUCKET_PAYLOAD_HG_NO_COMMIT}
        )
        self.assertContains(response, 'No matching repositories found!')

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_bitbucket_webhook(self):
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'bitbucket'}),
            {'payload': BITBUCKET_PAYLOAD_WEBHOOK}
        )
        self.assertContains(response, 'No matching repositories found!')

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_bitbucket_hosted(self):
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'bitbucket'}),
            {'payload': BITBUCKET_PAYLOAD_HOSTED}
        )
        self.assertContains(response, 'No matching repositories found!')

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_bitbucket_webhook_closed(self):
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'bitbucket'}),
            {'payload': BITBUCKET_PAYLOAD_WEBHOOK_CLOSED}
        )
        self.assertContains(response, 'No matching repositories found!')

    @override_settings(ENABLE_HOOKS=False)
    def test_disabled(self):
        """Test for hooks disabling."""
        self.assert_disabled()

        response = self.client.post(
            reverse('webhook', kwargs={'service': 'github'}),
            {'payload': GITHUB_PAYLOAD}
        )
        self.assertEqual(response.status_code, 405)
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'gitlab'}), GITLAB_PAYLOAD,
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 405)
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'bitbucket'}),
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

    @override_settings(ENABLE_HOOKS=True)
    def test_wrong_payload_github(self):
        """Test for invalid payloads with github."""
        # missing
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'github'}),
        )
        self.assertContains(
            response,
            'Could not parse JSON payload!',
            status_code=400
        )
        # wrong
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'github'}),
            {'payload': 'XX'},
        )
        self.assertContains(
            response,
            'Could not parse JSON payload!',
            status_code=400
        )
        # missing data
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'github'}),
            {'payload': '{}'},
        )
        self.assertContains(
            response,
            'Invalid data in json payload!',
            status_code=400
        )

    @override_settings(ENABLE_HOOKS=True)
    def test_wrong_payload_gitlab(self):
        """Test for invalid payloads with gitlab."""
        # missing
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'gitlab'}),
        )
        self.assertContains(
            response,
            'Could not parse JSON payload!',
            status_code=400
        )
        # missing content-type header
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'gitlab'}),
            {'payload': 'anything'}
        )
        self.assertContains(
            response,
            'Could not parse JSON payload!',
            status_code=400
        )
        # wrong
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'gitlab'}), 'xx',
            content_type="application/json"
        )
        self.assertContains(
            response,
            'Could not parse JSON payload!',
            status_code=400
        )
        # missing params
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'gitlab'}), '{"other":42}',
            content_type="application/json"
        )
        self.assertContains(
            response,
            'Hook working',
            status_code=200
        )
        # missing data
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'gitlab'}), '{}',
            content_type="application/json"
        )
        self.assertContains(
            response,
            'Invalid data in json payload!',
            status_code=400
        )

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_pagure(self):
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'pagure'}),
            {'payload': PAGURE_PAYLOAD}
        )
        self.assertContains(response, 'No matching repositories found!')

        # missing data
        response = self.client.post(
            reverse('webhook', kwargs={'service': 'gitlab'}), '{"msg": ""}',
            content_type="application/json"
        )
        self.assertContains(
            response,
            'Hook working',
            status_code=200
        )


class HookBackendTestCase(SimpleTestCase):
    hook = None

    def assert_hook(self, payload, expected):
        handler = HOOK_HANDLERS[self.hook]
        result = handler(json.loads(payload))
        if result:
            result['repos'] = list(sorted(result['repos']))
        if expected:
            expected['repos'] = list(sorted(expected['repos']))
        self.assertEqual(expected, result)


class BitbucketBackendTest(HookBackendTestCase):
    hook = 'bitbucket'

    def test_ping(self):
        self.assert_hook('{"diagnostics": "ping"}', None)

    def test_git(self):
        self.assert_hook(
            BITBUCKET_PAYLOAD_GIT,
            {
                'branch': 'master',
                'full_name': 'marcus/project-x.git',
                'repo_url': 'https://bitbucket.org/marcus/project-x/',
                'repos': [
                    'ssh://git@bitbucket.org/marcus/project-x.git',
                    'git@bitbucket.org:marcus/project-x.git',
                    'https://bitbucket.org/marcus/project-x.git'
                ],
                'service_long_name': 'Bitbucket'
            }
        )

    def test_hg(self):
        self.assert_hook(
            BITBUCKET_PAYLOAD_HG,
            {
                'branch': 'featureA',
                'full_name': 'marcus/project-x.git',
                'repo_url': 'https://bitbucket.org/marcus/project-x/',
                'repos': [
                    'https://bitbucket.org/marcus/project-x',
                    'ssh://hg@bitbucket.org/marcus/project-x',
                    'hg::ssh://hg@bitbucket.org/marcus/project-x',
                    'hg::https://bitbucket.org/marcus/project-x'
                ],
                'service_long_name': 'Bitbucket'
            }
        )

    def test_hg_no_commit(self):
        self.assert_hook(
            BITBUCKET_PAYLOAD_HG_NO_COMMIT,
            {
                'branch': None,
                'full_name': 'marcus/project-x.git',
                'repo_url': 'https://bitbucket.org/marcus/project-x/',
                'repos': [
                    'https://bitbucket.org/marcus/project-x',
                    'ssh://hg@bitbucket.org/marcus/project-x',
                    'hg::ssh://hg@bitbucket.org/marcus/project-x',
                    'hg::https://bitbucket.org/marcus/project-x'
                ],
                'service_long_name': 'Bitbucket'
            }
        )

    def test_webhook(self):
        self.assert_hook(
            BITBUCKET_PAYLOAD_WEBHOOK,
            {
                'branch': 'name-of-branch',
                'full_name': 'team_name/repo_name.git',
                'repo_url': 'https://api.bitbucket.org/bitbucket/bitbucket',
                'repos': [
                    'ssh://git@api.bitbucket.org/team_name/repo_name.git',
                    'ssh://git@bitbucket.org/team_name/repo_name.git',
                    'git@api.bitbucket.org:team_name/repo_name.git',
                    'git@bitbucket.org:team_name/repo_name.git',
                    'https://api.bitbucket.org/team_name/repo_name.git',
                    'https://bitbucket.org/team_name/repo_name.git',
                    'https://api.bitbucket.org/team_name/repo_name',
                    'https://bitbucket.org/team_name/repo_name',
                    'ssh://hg@api.bitbucket.org/team_name/repo_name',
                    'ssh://hg@bitbucket.org/team_name/repo_name',
                    'hg::ssh://hg@api.bitbucket.org/team_name/repo_name',
                    'hg::ssh://hg@bitbucket.org/team_name/repo_name',
                    'hg::https://api.bitbucket.org/team_name/repo_name',
                    'hg::https://bitbucket.org/team_name/repo_name'
                ],
                'service_long_name': 'Bitbucket'
            }
        )

    def test_hosted(self):
        self.assert_hook(
            BITBUCKET_PAYLOAD_HOSTED,
            {
                'branch': 'develop',
                'full_name': '~DSNOECK/weblate-training.git',
                'repo_url': 'https://example.com/weblate-training/browse',
                'repos': [
                    'ssh://git@bitbucket.org/~DSNOECK/weblate-training.git',
                    'ssh://git@example.com/~DSNOECK/weblate-training.git',
                    'git@bitbucket.org:~DSNOECK/weblate-training.git',
                    'git@example.com:~DSNOECK/weblate-training.git',
                    'https://bitbucket.org/~DSNOECK/weblate-training.git',
                    'https://example.com/~DSNOECK/weblate-training.git',
                    'https://bitbucket.org/~DSNOECK/weblate-training',
                    'https://example.com/~DSNOECK/weblate-training',
                    'ssh://hg@bitbucket.org/~DSNOECK/weblate-training',
                    'ssh://hg@example.com/~DSNOECK/weblate-training',
                    'hg::ssh://hg@bitbucket.org/~DSNOECK/weblate-training',
                    'hg::ssh://hg@example.com/~DSNOECK/weblate-training',
                    'hg::https://bitbucket.org/~DSNOECK/weblate-training',
                    'hg::https://example.com/~DSNOECK/weblate-training'
                ],
                'service_long_name': 'Bitbucket'
            }
        )

    def test_webhook_closed(self):
        self.assert_hook(
            BITBUCKET_PAYLOAD_WEBHOOK_CLOSED,
            {
                'branch': 'name-of-branch',
                'full_name': 'team_name/repo_name.git',
                'repo_url': 'https://api.bitbucket.org/bitbucket/bitbucket',
                'repos': [
                    'ssh://git@api.bitbucket.org/team_name/repo_name.git',
                    'ssh://git@bitbucket.org/team_name/repo_name.git',
                    'git@api.bitbucket.org:team_name/repo_name.git',
                    'git@bitbucket.org:team_name/repo_name.git',
                    'https://api.bitbucket.org/team_name/repo_name.git',
                    'https://bitbucket.org/team_name/repo_name.git',
                    'https://api.bitbucket.org/team_name/repo_name',
                    'https://bitbucket.org/team_name/repo_name',
                    'ssh://hg@api.bitbucket.org/team_name/repo_name',
                    'ssh://hg@bitbucket.org/team_name/repo_name',
                    'hg::ssh://hg@api.bitbucket.org/team_name/repo_name',
                    'hg::ssh://hg@bitbucket.org/team_name/repo_name',
                    'hg::https://api.bitbucket.org/team_name/repo_name',
                    'hg::https://bitbucket.org/team_name/repo_name'
                ],
                'service_long_name': 'Bitbucket'
            }
        )

    def test_server(self):
        self.assert_hook(
            BITBUCKET_PAYLOAD_SERVER,
            {
                'branch': 'master',
                'full_name': 'SANDPIT/my-repo.git',
                'repo_url': 'https://example.com/projects/SANDPIT/repos/my-repo/browse',
                'repos': [
                    'https://example.com/scm/sandpit/my-repo.git',
                    'ssh://git@example.com:7999/sandpit/my-repo.git',
                ],
                'service_long_name': 'Bitbucket'
            }
        )


class AzureBackendTest(HookBackendTestCase):
    hook = 'azure'

    def test_ping(self):
        self.assert_hook('{"diagnostics": "ping"}', None)

    def test_git(self):
        url = 'https://f.visualstudio.com/c/_git/ATEST'
        self.assert_hook(
            AZURE_PAYLOAD,
            {
                'branch': 'master',
                'full_name': 'ATEST',
                'repo_url': url,
                'repos': [url],
                'service_long_name': 'Azure'
            }
        )
