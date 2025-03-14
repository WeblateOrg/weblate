# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Test for notification hooks."""

import json
from abc import ABC, abstractmethod
from typing import Never
from unittest.mock import patch

from django.test import SimpleTestCase
from django.test.utils import override_settings
from django.urls import reverse

from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.views.hooks import HOOK_HANDLERS

GITHUB_PAYLOAD = """
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
"ref": "refs/heads/main"
}
"""

GITHUB_NEW_PAYLOAD = """
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
"ref": "refs/heads/main"
}
"""

GITLAB_PAYLOAD = r"""
{
  "object_kind": "push",
  "event_name": "push",
  "before": "95790bf891e76fee5e1747ab589903a6a1f80f22",
  "after": "da1560886d4f094c3e6c9ef40349f7d38b5d27d7",
  "ref": "refs/heads/main",
  "ref_protected": true,
  "checkout_sha": "da1560886d4f094c3e6c9ef40349f7d38b5d27d7",
  "user_id": 4,
  "user_name": "John Smith",
  "user_username": "jsmith",
  "user_email": "john@example.com",
  "user_avatar": "https://s.gravatar.com/avatar/d4c74594d841139328695756648b6bd6?s=8://s.gravatar.com/avatar/d4c74594d841139328695756648b6bd6?s=80",
  "project_id": 15,
  "project":{
    "id": 15,
    "name":"Diaspora",
    "description":"",
    "web_url":"http://example.com/mike/diaspora",
    "avatar_url":null,
    "git_ssh_url":"git@example.com:mike/diaspora.git",
    "git_http_url":"http://example.com/mike/diaspora.git",
    "namespace":"Mike",
    "visibility_level":0,
    "path_with_namespace":"mike/diaspora",
    "default_branch":"main",
    "homepage":"http://example.com/mike/diaspora",
    "url":"git@example.com:mike/diaspora.git",
    "ssh_url":"git@example.com:mike/diaspora.git",
    "http_url":"http://example.com/mike/diaspora.git"
  },
  "repository":{
    "name": "Diaspora",
    "url": "git@example.com:mike/diaspora.git",
    "description": "",
    "homepage": "http://example.com/mike/diaspora",
    "git_http_url":"http://example.com/mike/diaspora.git",
    "git_ssh_url":"git@example.com:mike/diaspora.git",
    "visibility_level":0
  },
  "commits": [
    {
      "id": "b6568db1bc1dcd7f8b4d5a946b0b91f9dacd7327",
      "message": "Update Catalan translation to e38cb41.\n\nSee https://gitlab.com/gitlab-org/gitlab for more information",
      "title": "Update Catalan translation to e38cb41.",
      "timestamp": "2011-12-12T14:27:31+02:00",
      "url": "http://example.com/mike/diaspora/commit/b6568db1bc1dcd7f8b4d5a946b0b91f9dacd7327",
      "author": {
        "name": "Jordi Mallach",
        "email": "jordi@softcatala.org"
      },
      "added": ["CHANGELOG"],
      "modified": ["app/controller/application.rb"],
      "removed": []
    },
    {
      "id": "da1560886d4f094c3e6c9ef40349f7d38b5d27d7",
      "message": "fixed readme",
      "title": "fixed readme",
      "timestamp": "2012-01-03T23:36:29+02:00",
      "url": "http://example.com/mike/diaspora/commit/da1560886d4f094c3e6c9ef40349f7d38b5d27d7",
      "author": {
        "name": "GitLab dev user",
        "email": "gitlabdev@dv6700.(none)"
      },
      "added": ["CHANGELOG"],
      "modified": ["app/controller/application.rb"],
      "removed": []
    }
  ],
  "total_commits_count": 4
}
"""

BITBUCKET_PAYLOAD_GIT = """
{
    "canon_url": "https://bitbucket.org",
    "commits": [
        {
            "author": "marcus",
            "branch": "main",
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
"""


BITBUCKET_PAYLOAD_HG = """
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
"""


BITBUCKET_PAYLOAD_HG_NO_COMMIT = """
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
"""

BITBUCKET_PAYLOAD_WEBHOOK = r"""
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
"""

BITBUCKET_PAYLOAD_MERGED = r"""
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
  "pullrequest": {
   "id" :  1 ,
   "title" :  "Title of pull request" ,
   "description" :  "Description of pull request" ,
   "state" :  "OPEN|MERGED|DECLINED" ,
   "author" : {},
   "source" : {
     "branch" : {  "name" :  "branch2" },
     "commit" : {  "hash" :  "d3022fc0ca3d" },
     "repository" : {}
   },
   "destination" : {
     "branch" : {  "name" :  "target" },
     "commit" : {  "hash" :  "ce5965ddd289" },
     "repository" : {}
   },
   "merge_commit" : {  "hash" :  "764413d85e29" },
   "participants" : [{}],
   "reviewers" : [{}],
   "close_source_branch" :  true ,
   "closed_by" : {},
   "reason" :  "reason for declining the PR (if applicable)" ,
   "created_on" :  "2015-04-06T15:23:38.179678+00:00" ,
   "updated_on" :  "2015-04-06T15:23:38.205705+00:00",

  "links": {
    "self": {
      "href": "https://api.bitbucket.org/api/2.0/pullrequests/pullrequest_id"
    },
    "html": {
      "href": "https://api.bitbucket.org/pullrequest_id"
    }
  }
  }
}
"""

BITBUCKET_PAYLOAD_SERVER_MERGED = r"""
{
    "date":"2020-10-20T14:07:35+0100",
    "pullRequest":{
        "closedDate":1603199255087,
        "title":"APP-26387: Adds strings",
        "updatedDate":1603199255087,
        "state":"MERGED",
        "version":2,
        "closed":true,
        "createdDate":1603196195463,
        "fromRef":{
            "displayId":"feature/APP-26387",
            "latestCommit":"4a257ccb3c27f468b4ff02b42d6eee7ce6149e5d",
            "id":"refs/heads/feature/APP-26387",
            "repository":{
                "scmId":"git",
                "slug":"locre",
                "forkable":true,
                "name":"locre",
                "links":{
                    "clone": [
                        {
                            "href": "https://example.com/scm/wlt/locre.git",
                            "name": "http"
                        },
                        {
                            "href": "ssh://git@example.com:7999/wlt/locre.git",
                            "name": "ssh"
                        }
                    ],
                    "self": [
                        {"href": "https://example.com/projects/WLT/repos/locre/browse"}
                    ]
                },
                "id":1796,
                "project":{
                    "name":"EXAMPLE",
                    "links":{"self": [{"href": "https://example.com/projects/WLT"}]},
                    "id":"790",
                    "key":"WLT",
                    "type":"NORMAL",
                    "public":"False",
                    "description":"Shared resources"
                },
                "state":"AVAILABLE",
                "public":false,
                "statusMessage":"Available"
            }
        },
        "open":false,
        "id":788
    },
    "eventKey":"pr:merged",
    "actor":{
        "displayName":"Bill",
        "name":"bill",
        "links":{
            "self":[
                {"href":"https://example.com/users/bill"}
            ]
        },
        "slug":"bill",
        "emailAddress":"bill@example.com",
        "active":true,
        "type":"NORMAL",
        "id":1350586
    }
}
"""


BITBUCKET_PAYLOAD_HOSTED = r"""
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
"""

BITBUCKET_PAYLOAD_SERVER = r"""
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
                "id": "refs/heads/main",
                "displayId": "main",
                "type": "BRANCH"
            },
            "refId": "refs/heads/main",
            "fromHash": "fdff3f418a8e3d25d6c8cb80776d6ac142bef800",
            "toHash": "7cb42185f7d8eab95f5fac3de2648a16361ecf34",
            "type": "UPDATE"
        }
    ]
}
"""

BITBUCKET_PAYLOAD_WEBHOOK_CLOSED = r"""
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
"""

PAGURE_PAYLOAD = r"""
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
        "branch": "main",
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
"""

AZURE_PAYLOAD_FALLBACK = """
{
  "subscriptionId": "e40cce28-7b73-4d33-ada2-2f5bd5e070ce",
  "notificationId": 18,
  "id": "108f81f3-fc7a-4aef-b990-14a8a31de20f",
  "eventType": "git.push",
  "publisherId": "tfs",
  "resource": {
    "refUpdates": [
      {
        "name": "refs/heads/feat/localization",
        "oldObjectId": "9e219f8adc6d2f42e9228d33aeacb227e74439de",
        "newObjectId": "7d85491a4f0289f2ffcf70939b7c7160e8ce2865"
      }
    ],
    "repository": {
      "id": "278d5cd2-584d-4b63-824a-2ba458937249",
      "name": "ATEST",
      "url": "https://dev.azure.com/f/_apis/git/repositories/278d5cd2-584d-4b63",
      "project": {
        "id": "be9b3917-87e6-42a4-a549-2bc06a7a878f",
        "name": "p",
        "url": "https://dev.azure.com/f/_apis/projects/be9b3917-87e6-42a4"
      },
      "defaultBranch": "refs/heads/main",
      "remoteUrl": "https://devops.azure.com/f/p/_git/ATEST"
    },
    "pushId": 1,
    "date": "2014-05-02T19:17:13.3309587Z",
    "url": "https://dev.azure.com/f/_apis/git/repositories/278d5cd2-584d-4b63/pushes/1"
  },
  "resourceVersion": "1.0",
  "resourceContainers": {
    "collection": {
      "id": "ce901e71-c714-4dcc-a641-7e73281fd0d5"
    },
    "account": {
      "id": "f60924c9-19b8-461e-9c85-fab350512c61"
    },
    "project": {
      "id": "be9b3917-87e6-42a4-a549-2bc06a7a878f"
    }
  },
  "createdDate": "2014-05-02T20:45:11.5664246Z"
}
"""

AZURE_PAYLOAD_NEW = """
{
  "subscriptionId": "e40cce28-7b73-4d33-ada2-2f5bd5e070ce",
  "notificationId": 18,
  "id": "108f81f3-fc7a-4aef-b990-14a8a31de20f",
  "eventType": "git.push",
  "publisherId": "tfs",
  "message": {
    "text": "Jamal Hartnett pushed updates to ATEST:main.",
    "html": "Jamal Hartnett pushed updates to ATEST:main.",
    "markdown": "Jamal Hartnett pushed updates to `ATEST`:`main`."
  },
  "detailedMessage": {
    "text": "Jamal Hartnett pushed a commit to ATEST:main.",
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
        "name": "refs/heads/feat/localization",
        "oldObjectId": "9e219f8adc6d2f42e9228d33aeacb227e74439de",
        "newObjectId": "7d85491a4f0289f2ffcf70939b7c7160e8ce2865"
      }
    ],
    "repository": {
      "id": "278d5cd2-584d-4b63-824a-2ba458937249",
      "name": "ATEST",
      "url": "https://dev.azure.com/f/_apis/git/repositories/278d5cd2-584d-4b63",
      "project": {
        "id": "be9b3917-87e6-42a4-a549-2bc06a7a878f",
        "name": "p",
        "url": "https://dev.azure.com/f/_apis/projects/be9b3917-87e6-42a4",
        "state": "wellFormed",
        "visibility": "unchanged",
        "lastUpdateTime": "0001-01-01T00:00:00"
      },
      "defaultBranch": "refs/heads/main",
      "remoteUrl": "https://dev.azure.com/f/p/_git/ATEST"
    },
    "pushedBy": {
      "displayName": "Jamal Hartnett",
      "id": "00067FFED5C7AF52@Live.com",
      "uniqueName": "fabrikamfiber4@hotmail.com"
    },
    "pushId": 1,
    "date": "2014-05-02T19:17:13.3309587Z",
    "url": "https://dev.azure.com/f/_apis/git/repositories/278d5cd2-584d-4b63/pushes/1"
  },
  "resourceVersion": "1.0",
  "resourceContainers": {
    "collection": {
      "id": "ce901e71-c714-4dcc-a641-7e73281fd0d5"
    },
    "account": {
      "id": "f60924c9-19b8-461e-9c85-fab350512c61"
    },
    "project": {
      "id": "be9b3917-87e6-42a4-a549-2bc06a7a878f"
    }
  },
  "createdDate": "2014-05-02T20:45:11.5664246Z"
}
"""

AZURE_PAYLOAD_OLD = """
{
  "subscriptionId": "00000000-0000-0000-0000-000000000000",
  "notificationId": 1,
  "id": "03c164c2-8912-4d5e-8009-3707d5f83734",
  "eventType": "git.push",
  "publisherId": "tfs",
  "message": {
    "text": "Jamal Hartnett pushed updates to ATEST:main.",
    "html": "Jamal Hartnett pushed updates to ATEST:main.",
    "markdown": "Jamal Hartnett pushed updates to `ATEST`:`main`."
  },
  "detailedMessage": {
    "text": "Jamal Hartnett pushed a commit to ATEST:main.",
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
        "name": "refs/heads/main",
        "oldObjectId": "aad331d8d3b131fa9ae03cf5e53965b51942618a",
        "newObjectId": "33b55f7cb7e7e245323987634f960cf4a6e6bc74"
      }
    ],
    "repository": {
      "id": "278d5cd2-584d-4b63-824a-2ba458937249",
      "name": "ATEST",
      "url": "https://f.visualstudio.com/c/_apis/git/repositories/278d5cd2-584d-4b63",
      "project": {
        "id": "be9b3917-87e6-42a4-a549-2bc06a7a878f",
        "name": "c",
        "url": "https://f.visualstudio.com/c/_apis/projects/6ce954b1-ce1f-45d1",
        "state": "wellFormed",
        "visibility": "unchanged",
        "lastUpdateTime": "0001-01-01T00:00:00"
      },
      "defaultBranch": "refs/heads/main",
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
"""
AZURE_PAYLOAD_SPACES = r"""
{
    "subscriptionId": "8efced88-c100-41a3-96ca-ee29eb1f877a",
    "notificationId": 2,
    "id": "8efced88-c100-41a3-96ca-ee29eb1f877a",
    "eventType": "git.push",
    "publisherId": "tfs",
    "message": {
        "text": "Dev User pushed updates to My-Fe-App:dev\r\n(https://dev.azure.com/MyOrg/My%20Special%20Shop/_git/My-Fe-App/#version=GBdev)",
        "html": "Dev User pushed updates to <a href=\"https://dev.azure.com/MyOrg/My%20Special%20Shop/_git/My-Fe-App/\">My-Fe-App</a>:<a href=\"https://dev.azure.com/MyOrg/My%20Special%20Shop/_git/My-Fe-App/#version=GBdev\">dev</a>",
        "markdown": "Dev User pushed updates to [My-Fe-App](https://dev.azure.com/MyOrg/My%20Special%20Shop/_git/My-Fe-App/):[dev](https://dev.azure.com/MyOrg/My%20Special%20Shop/_git/My-Fe-App/#version=GBdev)"
    },
    "detailedMessage": {
        "text": "Dev User pushed a commit to My-Fe-App:dev\r\n - Add translation from dev ed967ae1 (https://dev.azure.com/MyOrg/My%20Special%20Shop/_git/My-Fe-App/commit/ed967ae1dd2e97e3bdadf78281c5489c47f971e6)",
        "html": "Dev User pushed a commit to <a href=\"https://dev.azure.com/MyOrg/My%20Special%20Shop/_git/My-Fe-App/\">My-Fe-App</a>:<a href=\"https://dev.azure.com/MyOrg/My%20Special%20Shop/_git/My-Fe-App/#version=GBdev\">dev</a>\r\n<ul>\r\n<li>Add translation from dev <a href=\"https://dev.azure.com/MyOrg/My%20Special%20Shop/_git/My-Fe-App/commit/ed967ae1dd2e97e3bdadf78281c5489c47f971e6\">ed967ae1</a></li>\r\n</ul>",
        "markdown": "Dev User pushed a commit to [My-Fe-App](https://dev.azure.com/MyOrg/My%20Special%20Shop/_git/My-Fe-App/):[dev](https://dev.azure.com/MyOrg/My%20Special%20Shop/_git/My-Fe-App/#version=GBdev)\r\n* Add translation from dev [ed967ae1](https://dev.azure.com/MyOrg/My%20Special%20Shop/_git/My-Fe-App/commit/ed967ae1dd2e97e3bdadf78281c5489c47f971e6)"
    },
    "resource": {
        "refUpdates": [
            {
                "name": "refs/heads/dev",
                "oldObjectId": "8efced88-c100-41a3-96ca-ee29eb1f877a",
                "newObjectId": "8efced88-c100-41a3-96ca-ee29eb1f877a"
            }
        ],
        "repository": {
            "id": "8efced88-c100-41a3-96ca-ee29eb1f877a",
            "name": "My-Fe-App",
            "url": "https://dev.azure.com/MyOrg/_apis/git/repositories/8efced88-c100-41a3-96ca-ee29eb1f877a",
            "project": {
                "id": "8efced88-c100-41a3-96ca-ee29eb1f877a",
                "name": "NextGen B2B Shop",
                "url": "https://dev.azure.com/MyOrg/_apis/projects/8efced88-c100-41a3-96ca-ee29eb1f877a",
                "state": "wellFormed",
                "visibility": "unchanged",
                "lastUpdateTime": "0001-01-01T00:00:00"
            },
            "defaultBranch": "refs/heads/main",
            "remoteUrl": "https://dev.azure.com/MyOrg/My%20Special%20Shop/_git/My-Fe-App"
        },
        "pushedBy": {
            "displayName": "Dev User",
            "url": "https://spsprodweu5.vssps.visualstudio.com/8efced88-c100-41a3-96ca-ee29eb1f877a/_apis/Identities/8efced88-c100-41a3-96ca-ee29eb1f877a",
            "_links": {
                "avatar": {
                    "href": "https://dev.azure.com/MyOrg/_apis/GraphProfile/MemberAvatars/aad.NzZjOWE5ODgtN2E1OS03NDYwLWIwOGUtZjJhODE3NDVkMjdk"
                }
            },
            "id": "76c9a988-7a59-6460-b08e-f2a81745d27d",
            "uniqueName": "devuser@email.com",
            "imageUrl": "https://dev.azure.com/MyOrg/_api/_common/identityImage?id=8efced88-c100-41a3-96ca-ee29eb1f877a",
            "descriptor": "aad.NzZjOWE5ODgtN2E1OS03NDYwLWIwOGUtZjJhODE3NDVkMjdk"
        },
        "pushId": 2952,
        "date": "2024-03-07T12:27:01.2266022Z",
        "url": "https://dev.azure.com/MyOrg/_apis/git/repositories/8efced88-c100-41a3-96ca-ee29eb1f877a/pushes/2952",
        "_links": {
            "self": {
                "href": "https://dev.azure.com/MyOrg/_apis/git/repositories/8efced88-c100-41a3-96ca-ee29eb1f877a/pushes/2952"
            },
            "repository": {
                "href": "https://dev.azure.com/MyOrg/8efced88-c100-41a3-96ca-ee29eb1f877a/_apis/git/repositories/8efced88-c100-41a3-96ca-ee29eb1f877a"
            },
            "commits": {
                "href": "https://dev.azure.com/MyOrg/_apis/git/repositories/8efced88-c100-41a3-96ca-ee29eb1f877a/pushes/2952/commits"
            },
            "pusher": {
                "href": "https://spsprodweu5.vssps.visualstudio.com/8efced88-c100-41a3-96ca-ee29eb1f877a/_apis/Identities/76c9a988-7a59-6460-b08e-f2a81745d27d"
            },
            "refs": {
                "href": "https://dev.azure.com/MyOrg/8efced88-c100-41a3-96ca-ee29eb1f877a/_apis/git/repositories/8efced88-c100-41a3-96ca-ee29eb1f877a/refs/heads/dev"
            }
        }
    },
    "resourceVersion": "1.0",
    "resourceContainers": {
        "collection": {
            "id": "8efced88-c100-41a3-96ca-ee29eb1f877a",
            "baseUrl": "https://dev.azure.com/MyOrg/"
        },
        "account": {
            "id": "8efced88-c100-41a3-96ca-ee29eb1f877a",
            "baseUrl": "https://dev.azure.com/MyOrg/"
        },
        "project": {
            "id": "8efced88-c100-41a3-96ca-ee29eb1f877a",
            "baseUrl": "https://dev.azure.com/MyOrg/"
        }
    },
    "createdDate": "8efced88-c100-41a3-96ca-ee29eb1f877a"
}
"""

GITEA_PAYLOAD = """
{
  "secret": "3gEsCfjlV2ugRwgpU#w1*WaW*wa4NXgGmpCfkbG3",
  "ref": "refs/heads/main",
  "before": "28e1879d029cb852e4844d9c718537df08844e03",
  "after": "bffeb74224043ba2feb48d137756c8a9331c449a",
  "compare_url": "http://localhost:3000/gitea/webhooks/compare/28e187...bffeb7422",
  "commits": [
    {
      "id": "bffeb74224043ba2feb48d137756c8a9331c449a",
      "message": "Webhooks Yay!",
      "url": "http://localhost:3000/gitea/webhooks/commit/bffeb74224043ba2feb4",
      "author": {
        "name": "Gitea",
        "email": "someone@gitea.io",
        "username": "gitea"
      },
      "committer": {
        "name": "Gitea",
        "email": "someone@gitea.io",
        "username": "gitea"
      },
      "timestamp": "2017-03-13T13:52:11-04:00"
    }
  ],
  "repository": {
    "id": 140,
    "owner": {
      "id": 1,
      "login": "gitea",
      "full_name": "Gitea",
      "email": "someone@gitea.io",
      "avatar_url": "https://localhost:3000/avatars/1",
      "username": "gitea"
    },
    "name": "webhooks",
    "full_name": "gitea/webhooks",
    "description": "",
    "private": false,
    "fork": false,
    "html_url": "http://localhost:3000/gitea/webhooks",
    "ssh_url": "ssh://gitea@localhost:2222/gitea/webhooks.git",
    "clone_url": "http://localhost:3000/gitea/webhooks.git",
    "website": "",
    "stars_count": 0,
    "forks_count": 1,
    "watchers_count": 1,
    "open_issues_count": 7,
    "default_branch": "main",
    "created_at": "2017-02-26T04:29:06-05:00",
    "updated_at": "2017-03-13T13:51:58-04:00"
  },
  "pusher": {
    "id": 1,
    "login": "gitea",
    "full_name": "Gitea",
    "email": "someone@gitea.io",
    "avatar_url": "https://localhost:3000/avatars/1",
    "username": "gitea"
  },
  "sender": {
    "id": 1,
    "login": "gitea",
    "full_name": "Gitea",
    "email": "someone@gitea.io",
    "avatar_url": "https://localhost:3000/avatars/1",
    "username": "gitea"
  }
}
"""


GITEE_PAYLOAD = """
{
  "hook_name": "push_hooks",
  "password": "pwd",
  "ref": "refs/heads/main",
  "before": "0000000000000000000000000000000000000000",
  "after": "1cdcd819599cbb4099289dbbec762452f006cb40",
  "created": true,
  "deleted": false,
  "compare": "https://gitee.com/oschina/gitee/compare/000",
  "commits": [
    {
      "id": "1cdcd819599cbb4099289dbbec762452f006cb40",
      "tree_id": "db78f3594ec0683f5d857ef731df0d860f14f2b2",
      "distinct": true,
      "message": "Update README.md",
      "timestamp": "2018-02-05T23:46:46+08:00",
      "url": "https://gitee.com/oschina/gitee/commit/1cdcd819599cbb4099289dbbec7624",
      "author": {
        "time": "2018-02-05T23:46:46+08:00",
        "name": "robot",
        "email": "robot@gitee.com",
        "username": "robot",
        "user_name": "robot",
        "url": "https://gitee.com/robot"
      },
      "committer": {
        "name": "robot",
        "email": "robot@gitee.com",
        "username": "robot",
        "user_name": "robot",
        "url": "https://gitee.com/robot"
      },
      "added": null,
      "removed": null,
      "modified": [
        "README.md"
      ]
    }
  ],
  "head_commit": {
    "id": "1cdcd819599cbb4099289dbbec762452f006cb40",
    "tree_id": "db78f3594ec0683f5d857ef731df0d860f14f2b2",
    "distinct": true,
    "message": "Update README.md",
    "timestamp": "2018-02-05T23:46:46+08:00",
    "url": "https://gitee.com/oschina/gitee/commit/1cdcd819599cbb4099289dbbec76245",
    "author": {
      "time": "2018-02-05T23:46:46+08:00",
      "name": "robot",
      "email": "robot@gitee.com",
      "username": "robot",
      "user_name": "robot",
      "url": "https://gitee.com/robot"
    },
    "committer": {
      "name": "robot",
      "email": "robot@gitee.com",
      "username": "robot",
      "user_name": "robot",
      "url": "https://gitee.com/robot"
    },
    "added": null,
    "removed": null,
    "modified": [
      "README.md"
    ]
  },
  "total_commits_count": 0,
  "commits_more_than_ten": false,
  "repository": {
    "id": 120249025,
    "name": "Gitee",
    "path": "gitee",
    "full_name": "开源中国/Gitee",
    "owner": {
      "id": 1,
      "login": "robot",
      "avatar_url": "https://gitee.com/assets/favicon.ico",
      "html_url": "https://gitee.com/robot",
      "type": "User",
      "site_admin": false,
      "name": "robot",
      "email": "robot@gitee.com",
      "username": "robot",
      "user_name": "robot",
      "url": "https://gitee.com/robot"
    },
    "private": false,
    "html_url": "https://gitee.com/oschina/gitee",
    "url": "https://gitee.com/oschina/gitee",
    "description": "",
    "fork": false,
    "created_at": "2018-02-05T23:46:46+08:00",
    "updated_at": "2018-02-05T23:46:46+08:00",
    "pushed_at": "2018-02-05T23:46:46+08:00",
    "git_url": "git://gitee.com:oschina/gitee.git",
    "ssh_url": "git@gitee.com:oschina/gitee.git",
    "clone_url": "https://gitee.com/oschina/gitee.git",
    "svn_url": "svn://gitee.com/oschina/gitee",
    "git_http_url": "https://gitee.com/oschina/gitee.git",
    "git_ssh_url": "git@gitee.com:oschina/gitee.git",
    "git_svn_url": "svn://gitee.com/oschina/gitee",
    "homepage": null,
    "stargazers_count": 11,
    "watchers_count": 12,
    "forks_count": 0,
    "language": "ruby",
    "has_issues": true,
    "has_wiki": true,
    "has_pages": false,
    "license": null,
    "open_issues_count": 0,
    "default_branch": "main",
    "namespace": "oschina",
    "name_with_namespace": "开源中国/Gitee",
    "path_with_namespace": "oschina/gitee"
  },
  "sender": {
    "id": 1,
    "login": "robot",
    "avatar_url": "https://gitee.com/assets/favicon.ico",
    "html_url": "https://gitee.com/robot",
    "type": "User",
    "site_admin": false,
    "name": "robot",
    "email": "robot@gitee.com",
    "username": "robot",
    "user_name": "robot",
    "url": "https://gitee.com/robot"
  },
  "enterprise": {
    "name": "开源中国",
    "url": "https://gitee.com/oschina"
  }
}
"""


class HooksViewTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        # Avoid actual repository updates
        self.patcher = patch(
            "weblate.trans.models.component.Component.update_remote_branch"
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_project(self) -> None:
        response = self.client.get(
            reverse("update-hook", kwargs={"path": self.project.get_url_path()})
        )
        self.assertContains(response, "Update triggered")

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_component(self) -> None:
        response = self.client.get(reverse("update-hook", kwargs=self.kw_component))
        self.assertContains(response, "Update triggered")

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_github_exists(self) -> None:
        # Adjust matching repo
        self.component.repo = "git://github.com/defunkt/github.git"
        self.component.save()
        response = self.client.post(
            reverse("webhook", kwargs={"service": "github"}),
            {"payload": GITHUB_PAYLOAD},
            headers={"x-github-event": "push"},
        )
        self.assertContains(response, "Update triggered")

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_github_new(self) -> None:
        # Adjust matching repo
        self.component.repo = "git://github.com/defunkt/github.git"
        self.component.save()
        response = self.client.post(
            reverse("webhook", kwargs={"service": "github"}),
            {"payload": GITHUB_NEW_PAYLOAD},
            headers={"x-github-event": "push"},
        )
        self.assertContains(response, "Update triggered")

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_gitea(self) -> None:
        # Adjust matching repo
        self.component.repo = "http://localhost:3000/gitea/webhooks.git"
        self.component.save()
        response = self.client.post(
            reverse("webhook", kwargs={"service": "gitea"}), {"payload": GITEA_PAYLOAD}
        )
        self.assertContains(response, "Update triggered")

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_gitee(self) -> None:
        # Adjust matching repo
        self.component.repo = "https://gitee.com/oschina/gitee.git"
        self.component.save()
        response = self.client.post(
            reverse("webhook", kwargs={"service": "gitee"}), {"payload": GITEE_PAYLOAD}
        )
        self.assertContains(response, "Update triggered")

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_github_ping(self) -> None:
        response = self.client.post(
            reverse("webhook", kwargs={"service": "github"}),
            {"payload": '{"zen": "Approachable is better than simple."}'},
        )
        self.assertContains(response, "Hook working", status_code=201)

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_github_ping_no_slash(self) -> None:
        response = self.client.post(
            "/hooks/github",
            {"payload": '{"zen": "Approachable is better than simple."}'},
        )
        self.assertContains(response, "Hook working", status_code=201)

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_github_auth(self) -> None:
        # Adjust matching repo
        self.component.repo = "https://user:pwd@github.com/defunkt/github.git"
        self.component.save()
        response = self.client.post(
            reverse("webhook", kwargs={"service": "github"}),
            {"payload": GITHUB_PAYLOAD},
            headers={"x-github-event": "push"},
        )
        self.assertContains(response, "Update triggered")

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_github_disabled(self) -> None:
        # Adjust matching repo
        self.component.repo = "git://github.com/defunkt/github.git"
        self.component.save()
        self.project.enable_hooks = False
        self.project.save()
        response = self.client.post(
            reverse("webhook", kwargs={"service": "github"}),
            {"payload": GITHUB_PAYLOAD},
            headers={"x-github-event": "push"},
        )
        self.assertContains(
            response, "No matching repositories found!", status_code=202
        )

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_github(self) -> None:
        response = self.client.post(
            reverse("webhook", kwargs={"service": "github"}),
            {"payload": GITHUB_PAYLOAD},
            headers={"x-github-event": "push"},
        )
        self.assertContains(
            response, "No matching repositories found!", status_code=202
        )

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_gitlab(self) -> None:
        response = self.client.post(
            reverse("webhook", kwargs={"service": "gitlab"}),
            GITLAB_PAYLOAD,
            content_type="application/json",
        )
        self.assertContains(
            response, "No matching repositories found!", status_code=202
        )

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_bitbucket_ping(self) -> None:
        response = self.client.post(
            reverse("webhook", kwargs={"service": "bitbucket"}),
            {"payload": '{"foo": "bar"}'},
            headers={"x-event-key": "diagnostics:ping"},
        )
        self.assertContains(response, "Hook working", status_code=201)

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_bitbucket_git(self) -> None:
        response = self.client.post(
            reverse("webhook", kwargs={"service": "bitbucket"}),
            {"payload": BITBUCKET_PAYLOAD_GIT},
            headers={"x-event-key": "repo:push"},
        )
        self.assertContains(
            response, "No matching repositories found!", status_code=202
        )

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_bitbucket_hg(self) -> None:
        response = self.client.post(
            reverse("webhook", kwargs={"service": "bitbucket"}),
            {"payload": BITBUCKET_PAYLOAD_HG},
            headers={"x-event-key": "repo:push"},
        )
        self.assertContains(
            response, "No matching repositories found!", status_code=202
        )

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_bitbucket_hg_no_commit(self) -> None:
        response = self.client.post(
            reverse("webhook", kwargs={"service": "bitbucket"}),
            {"payload": BITBUCKET_PAYLOAD_HG_NO_COMMIT},
            headers={"x-event-key": "repo:push"},
        )
        self.assertContains(
            response, "No matching repositories found!", status_code=202
        )

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_bitbucket_webhook(self) -> None:
        response = self.client.post(
            reverse("webhook", kwargs={"service": "bitbucket"}),
            {"payload": BITBUCKET_PAYLOAD_WEBHOOK},
            headers={"x-event-key": "repo:push"},
        )
        self.assertContains(
            response, "No matching repositories found!", status_code=202
        )

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_bitbucket_hosted(self) -> None:
        response = self.client.post(
            reverse("webhook", kwargs={"service": "bitbucket"}),
            {"payload": BITBUCKET_PAYLOAD_HOSTED},
            headers={"x-event-key": "repo:push"},
        )
        self.assertContains(
            response, "No matching repositories found!", status_code=202
        )

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_bitbucket_webhook_closed(self) -> None:
        response = self.client.post(
            reverse("webhook", kwargs={"service": "bitbucket"}),
            {"payload": BITBUCKET_PAYLOAD_WEBHOOK_CLOSED},
            headers={"x-event-key": "repo:push"},
        )
        self.assertContains(
            response, "No matching repositories found!", status_code=202
        )

    @override_settings(ENABLE_HOOKS=False)
    def test_disabled(self) -> None:
        """Test for hooks disabling."""
        self.assert_disabled()

        response = self.client.post(
            reverse("webhook", kwargs={"service": "github"}),
            {"payload": GITHUB_PAYLOAD},
        )
        self.assertEqual(response.status_code, 405)
        response = self.client.post(
            reverse("webhook", kwargs={"service": "gitlab"}),
            GITLAB_PAYLOAD,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 405)
        response = self.client.post(
            reverse("webhook", kwargs={"service": "bitbucket"}),
            {"payload": BITBUCKET_PAYLOAD_GIT},
        )
        self.assertEqual(response.status_code, 405)

    def test_project_disabled(self) -> None:
        self.project.enable_hooks = False
        self.project.save()
        self.assert_disabled()

    def assert_disabled(self) -> None:
        response = self.client.get(
            reverse("update-hook", kwargs={"path": self.project.get_url_path()})
        )
        self.assertEqual(response.status_code, 405)
        response = self.client.get(reverse("update-hook", kwargs=self.kw_component))
        self.assertEqual(response.status_code, 405)

    @override_settings(ENABLE_HOOKS=True)
    def test_wrong_payload_github(self) -> None:
        """Test for invalid payloads with github."""
        # missing
        response = self.client.post(reverse("webhook", kwargs={"service": "github"}))
        self.assertContains(response, "Could not parse JSON payload!", status_code=400)
        # wrong
        response = self.client.post(
            reverse("webhook", kwargs={"service": "github"}), {"payload": "XX"}
        )
        self.assertContains(response, "Could not parse JSON payload!", status_code=400)
        # missing data
        response = self.client.post(
            reverse("webhook", kwargs={"service": "github"}), {"payload": "{}"}
        )
        self.assertContains(response, "Invalid data in json payload!", status_code=400)

    @override_settings(ENABLE_HOOKS=True)
    def test_wrong_payload_gitlab(self) -> None:
        """Test for invalid payloads with gitlab."""
        # missing
        response = self.client.post(reverse("webhook", kwargs={"service": "gitlab"}))
        self.assertContains(response, "Could not parse JSON payload!", status_code=400)
        # missing content-type header
        response = self.client.post(
            reverse("webhook", kwargs={"service": "gitlab"}), {"payload": "anything"}
        )
        self.assertContains(response, "Could not parse JSON payload!", status_code=400)
        # wrong
        response = self.client.post(
            reverse("webhook", kwargs={"service": "gitlab"}),
            "xx",
            content_type="application/json",
        )
        self.assertContains(response, "Could not parse JSON payload!", status_code=400)
        # missing params
        response = self.client.post(
            reverse("webhook", kwargs={"service": "gitlab"}),
            '{"other":42}',
            content_type="application/json",
        )
        self.assertContains(response, "Hook working", status_code=201)
        # missing data
        response = self.client.post(
            reverse("webhook", kwargs={"service": "gitlab"}),
            "{}",
            content_type="application/json",
        )
        self.assertContains(response, "Invalid data in json payload!", status_code=400)

    @override_settings(ENABLE_HOOKS=True)
    def test_hook_pagure(self) -> None:
        response = self.client.post(
            reverse("webhook", kwargs={"service": "pagure"}),
            {"payload": PAGURE_PAYLOAD},
        )
        self.assertContains(
            response, "No matching repositories found!", status_code=202
        )

        # missing data
        response = self.client.post(
            reverse("webhook", kwargs={"service": "gitlab"}),
            '{"msg": ""}',
            content_type="application/json",
        )
        self.assertContains(response, "Hook working", status_code=201)


class HookBackendTestCase(SimpleTestCase, ABC):
    hook: str = ""

    def assert_hook(self, payload, expected) -> None:
        handler = HOOK_HANDLERS[self.hook]
        result = handler(json.loads(payload), None)
        if result:
            result["repos"] = sorted(result["repos"])
        if expected:
            expected["repos"] = sorted(expected["repos"])
        self.maxDiff = None
        self.assertEqual(expected, result)

    @abstractmethod
    def test_git(self) -> Never:
        raise NotImplementedError


class GitHubBackendTest(HookBackendTestCase):
    hook = "github"

    def test_git(self) -> None:
        self.assert_hook(
            GITHUB_NEW_PAYLOAD.replace("defunkt/github", "defunkt/git.hub"),
            {
                "branch": "main",
                "full_name": "defunkt/github",
                "repo_url": "http://github.com/defunkt/git.hub",
                "repos": [
                    "git://github.com/defunkt/git.hub.git",
                    "git://github.com/defunkt/git.hub",
                    "git@github.com:defunkt/git.hub.git",
                    "git@github.com:defunkt/git.hub",
                    "http://github.com/defunkt/git.hub",
                    "https://github.com/defunkt/git.hub",
                    "https://github.com/defunkt/git.hub.git",
                ],
                "service_long_name": "GitHub",
            },
        )


class BitbucketBackendTest(HookBackendTestCase):
    hook = "bitbucket"

    def test_git(self) -> None:
        self.assert_hook(
            BITBUCKET_PAYLOAD_GIT,
            {
                "branch": "main",
                "full_name": "marcus/project-x",
                "repo_url": "https://bitbucket.org/marcus/project-x/",
                "repos": [
                    "ssh://git@bitbucket.org/marcus/project-x.git",
                    "ssh://git@bitbucket.org/marcus/project-x",
                    "git@bitbucket.org:marcus/project-x.git",
                    "git@bitbucket.org:marcus/project-x",
                    "https://bitbucket.org/marcus/project-x.git",
                    "https://bitbucket.org/marcus/project-x",
                ],
                "service_long_name": "Bitbucket",
            },
        )

    def test_hg(self) -> None:
        self.assert_hook(
            BITBUCKET_PAYLOAD_HG,
            {
                "branch": "featureA",
                "full_name": "marcus/project-x",
                "repo_url": "https://bitbucket.org/marcus/project-x/",
                "repos": [
                    "https://bitbucket.org/marcus/project-x",
                    "ssh://hg@bitbucket.org/marcus/project-x",
                    "hg::ssh://hg@bitbucket.org/marcus/project-x",
                    "hg::https://bitbucket.org/marcus/project-x",
                ],
                "service_long_name": "Bitbucket",
            },
        )

    def test_hg_no_commit(self) -> None:
        self.assert_hook(
            BITBUCKET_PAYLOAD_HG_NO_COMMIT,
            {
                "branch": None,
                "full_name": "marcus/project-x",
                "repo_url": "https://bitbucket.org/marcus/project-x/",
                "repos": [
                    "https://bitbucket.org/marcus/project-x",
                    "ssh://hg@bitbucket.org/marcus/project-x",
                    "hg::ssh://hg@bitbucket.org/marcus/project-x",
                    "hg::https://bitbucket.org/marcus/project-x",
                ],
                "service_long_name": "Bitbucket",
            },
        )

    def test_webhook(self) -> None:
        self.assert_hook(
            BITBUCKET_PAYLOAD_WEBHOOK,
            {
                "branch": "name-of-branch",
                "full_name": "team_name/repo_name",
                "repo_url": "https://api.bitbucket.org/bitbucket/bitbucket",
                "repos": [
                    "ssh://git@api.bitbucket.org/team_name/repo_name.git",
                    "ssh://git@bitbucket.org/team_name/repo_name.git",
                    "git@api.bitbucket.org:team_name/repo_name.git",
                    "git@bitbucket.org:team_name/repo_name.git",
                    "https://api.bitbucket.org/team_name/repo_name.git",
                    "https://bitbucket.org/team_name/repo_name.git",
                    "ssh://git@api.bitbucket.org/team_name/repo_name",
                    "ssh://git@bitbucket.org/team_name/repo_name",
                    "git@api.bitbucket.org:team_name/repo_name",
                    "git@bitbucket.org:team_name/repo_name",
                    "https://api.bitbucket.org/team_name/repo_name",
                    "https://bitbucket.org/team_name/repo_name",
                    "https://api.bitbucket.org/team_name/repo_name",
                    "https://bitbucket.org/team_name/repo_name",
                    "ssh://hg@api.bitbucket.org/team_name/repo_name",
                    "ssh://hg@bitbucket.org/team_name/repo_name",
                    "hg::ssh://hg@api.bitbucket.org/team_name/repo_name",
                    "hg::ssh://hg@bitbucket.org/team_name/repo_name",
                    "hg::https://api.bitbucket.org/team_name/repo_name",
                    "hg::https://bitbucket.org/team_name/repo_name",
                ],
                "service_long_name": "Bitbucket",
            },
        )

    def test_hosted(self) -> None:
        self.assert_hook(
            BITBUCKET_PAYLOAD_HOSTED,
            {
                "branch": "develop",
                "full_name": "~DSNOECK/weblate-training",
                "repo_url": "https://example.com/weblate-training/browse",
                "repos": [
                    "ssh://git@bitbucket.org/~DSNOECK/weblate-training.git",
                    "ssh://git@example.com/~DSNOECK/weblate-training.git",
                    "git@bitbucket.org:~DSNOECK/weblate-training.git",
                    "git@example.com:~DSNOECK/weblate-training.git",
                    "https://bitbucket.org/~DSNOECK/weblate-training.git",
                    "https://example.com/~DSNOECK/weblate-training.git",
                    "ssh://git@bitbucket.org/~DSNOECK/weblate-training",
                    "ssh://git@example.com/~DSNOECK/weblate-training",
                    "git@bitbucket.org:~DSNOECK/weblate-training",
                    "git@example.com:~DSNOECK/weblate-training",
                    "https://bitbucket.org/~DSNOECK/weblate-training",
                    "https://example.com/~DSNOECK/weblate-training",
                    "https://bitbucket.org/~DSNOECK/weblate-training",
                    "https://example.com/~DSNOECK/weblate-training",
                    "ssh://hg@bitbucket.org/~DSNOECK/weblate-training",
                    "ssh://hg@example.com/~DSNOECK/weblate-training",
                    "hg::ssh://hg@bitbucket.org/~DSNOECK/weblate-training",
                    "hg::ssh://hg@example.com/~DSNOECK/weblate-training",
                    "hg::https://bitbucket.org/~DSNOECK/weblate-training",
                    "hg::https://example.com/~DSNOECK/weblate-training",
                ],
                "service_long_name": "Bitbucket",
            },
        )

    def test_merge(self) -> None:
        self.assert_hook(
            BITBUCKET_PAYLOAD_MERGED,
            {
                "service_long_name": "Bitbucket",
                "repo_url": "https://api.bitbucket.org/bitbucket/bitbucket",
                "repos": [
                    "git@api.bitbucket.org:team_name/repo_name",
                    "git@api.bitbucket.org:team_name/repo_name.git",
                    "git@bitbucket.org:team_name/repo_name",
                    "git@bitbucket.org:team_name/repo_name.git",
                    "hg::https://api.bitbucket.org/team_name/repo_name",
                    "hg::https://bitbucket.org/team_name/repo_name",
                    "hg::ssh://hg@api.bitbucket.org/team_name/repo_name",
                    "hg::ssh://hg@bitbucket.org/team_name/repo_name",
                    "https://api.bitbucket.org/team_name/repo_name",
                    "https://api.bitbucket.org/team_name/repo_name",
                    "https://api.bitbucket.org/team_name/repo_name.git",
                    "https://bitbucket.org/team_name/repo_name",
                    "https://bitbucket.org/team_name/repo_name",
                    "https://bitbucket.org/team_name/repo_name.git",
                    "ssh://git@api.bitbucket.org/team_name/repo_name",
                    "ssh://git@api.bitbucket.org/team_name/repo_name.git",
                    "ssh://git@bitbucket.org/team_name/repo_name",
                    "ssh://git@bitbucket.org/team_name/repo_name.git",
                    "ssh://hg@api.bitbucket.org/team_name/repo_name",
                    "ssh://hg@bitbucket.org/team_name/repo_name",
                ],
                "branch": "target",
                "full_name": "team_name/repo_name",
            },
        )

    def test_merge_server(self) -> None:
        self.assert_hook(
            BITBUCKET_PAYLOAD_SERVER_MERGED,
            {
                "service_long_name": "Bitbucket",
                "repo_url": "https://example.com/projects/WLT/repos/locre/browse",
                "repos": [
                    "https://example.com/scm/wlt/locre.git",
                    "ssh://git@example.com:7999/wlt/locre.git",
                ],
                "branch": None,
                "full_name": "WLT/locre",
            },
        )

    def test_webhook_closed(self) -> None:
        self.assert_hook(
            BITBUCKET_PAYLOAD_WEBHOOK_CLOSED,
            {
                "branch": "name-of-branch",
                "full_name": "team_name/repo_name",
                "repo_url": "https://api.bitbucket.org/bitbucket/bitbucket",
                "repos": [
                    "ssh://git@api.bitbucket.org/team_name/repo_name.git",
                    "ssh://git@bitbucket.org/team_name/repo_name.git",
                    "git@api.bitbucket.org:team_name/repo_name.git",
                    "git@bitbucket.org:team_name/repo_name.git",
                    "https://api.bitbucket.org/team_name/repo_name.git",
                    "https://bitbucket.org/team_name/repo_name.git",
                    "ssh://git@api.bitbucket.org/team_name/repo_name",
                    "ssh://git@bitbucket.org/team_name/repo_name",
                    "git@api.bitbucket.org:team_name/repo_name",
                    "git@bitbucket.org:team_name/repo_name",
                    "https://api.bitbucket.org/team_name/repo_name",
                    "https://bitbucket.org/team_name/repo_name",
                    "https://api.bitbucket.org/team_name/repo_name",
                    "https://bitbucket.org/team_name/repo_name",
                    "ssh://hg@api.bitbucket.org/team_name/repo_name",
                    "ssh://hg@bitbucket.org/team_name/repo_name",
                    "hg::ssh://hg@api.bitbucket.org/team_name/repo_name",
                    "hg::ssh://hg@bitbucket.org/team_name/repo_name",
                    "hg::https://api.bitbucket.org/team_name/repo_name",
                    "hg::https://bitbucket.org/team_name/repo_name",
                ],
                "service_long_name": "Bitbucket",
            },
        )

    def test_server(self) -> None:
        self.assert_hook(
            BITBUCKET_PAYLOAD_SERVER,
            {
                "branch": "main",
                "full_name": "SANDPIT/my-repo",
                "repo_url": "https://example.com/projects/SANDPIT/repos/my-repo/browse",
                "repos": [
                    "https://example.com/scm/sandpit/my-repo.git",
                    "ssh://git@example.com:7999/sandpit/my-repo.git",
                ],
                "service_long_name": "Bitbucket",
            },
        )


class AzureBackendTest(HookBackendTestCase):
    hook = "azure"

    def test_ping(self) -> None:
        self.assert_hook('{"diagnostics": "ping"}', None)

    def test_git_old(self) -> None:
        url = "https://f.visualstudio.com/c/_git/ATEST"
        self.assert_hook(
            AZURE_PAYLOAD_OLD,
            {
                "branch": "main",
                "full_name": "ATEST",
                "repo_url": url,
                "repos": [
                    "https://dev.azure.com/f/c/_git/ATEST",
                    (
                        "https://dev.azure.com/f/be9b3917-87e6-42a4-a549-2bc06a7a878f/"
                        "_git/278d5cd2-584d-4b63-824a-2ba458937249"
                    ),
                    "git@ssh.dev.azure.com:v3/f/c/ATEST",
                    "https://f.visualstudio.com/c/_git/ATEST",
                    "f@vs-ssh.visualstudio.com:v3/f/c/ATEST",
                ],
                "service_long_name": "Azure",
            },
        )

    def test_git(self) -> None:
        self.assert_hook(
            AZURE_PAYLOAD_NEW,
            {
                "branch": "feat/localization",
                "full_name": "ATEST",
                "repo_url": "https://dev.azure.com/f/p/_git/ATEST",
                "repos": [
                    "https://dev.azure.com/f/p/_git/ATEST",
                    (
                        "https://dev.azure.com/f/be9b3917-87e6-42a4-a549-2bc06a7a878f/"
                        "_git/278d5cd2-584d-4b63-824a-2ba458937249"
                    ),
                    "git@ssh.dev.azure.com:v3/f/p/ATEST",
                    "https://f.visualstudio.com/p/_git/ATEST",
                    "f@vs-ssh.visualstudio.com:v3/f/p/ATEST",
                ],
                "service_long_name": "Azure",
            },
        )

    def test_git_spaces(self) -> None:
        self.assert_hook(
            AZURE_PAYLOAD_SPACES,
            {
                "branch": "dev",
                "full_name": "My-Fe-App",
                "repo_url": "https://dev.azure.com/MyOrg/My%20Special%20Shop/_git/My-Fe-App",
                "repos": [
                    "MyOrg@vs-ssh.visualstudio.com:v3/MyOrg/NextGen B2B Shop/My-Fe-App",
                    "MyOrg@vs-ssh.visualstudio.com:v3/MyOrg/NextGen%20B2B%20Shop/My-Fe-App",
                    "git@ssh.dev.azure.com:v3/MyOrg/NextGen B2B Shop/My-Fe-App",
                    "git@ssh.dev.azure.com:v3/MyOrg/NextGen%20B2B%20Shop/My-Fe-App",
                    "https://MyOrg.visualstudio.com/NextGen B2B Shop/_git/My-Fe-App",
                    "https://MyOrg.visualstudio.com/NextGen%20B2B%20Shop/_git/My-Fe-App",
                    "https://dev.azure.com/MyOrg/8efced88-c100-41a3-96ca-ee29eb1f877a/_git/8efced88-c100-41a3-96ca-ee29eb1f877a",
                    "https://dev.azure.com/MyOrg/8efced88-c100-41a3-96ca-ee29eb1f877a/_git/8efced88-c100-41a3-96ca-ee29eb1f877a",
                    "https://dev.azure.com/MyOrg/NextGen B2B Shop/_git/My-Fe-App",
                    "https://dev.azure.com/MyOrg/NextGen%20B2B%20Shop/_git/My-Fe-App",
                ],
                "service_long_name": "Azure",
            },
        )

    def test_git_fallback(self) -> None:
        http_url = "https://devops.azure.com/f/p/_git/ATEST"
        self.assert_hook(
            AZURE_PAYLOAD_FALLBACK,
            {
                "branch": "feat/localization",
                "full_name": "ATEST",
                "repo_url": http_url,
                "repos": [http_url],
                "service_long_name": "Azure",
            },
        )
