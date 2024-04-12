# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import requests
from django.conf import settings

import weblate.utils.version
from weblate.utils.management.base import BaseCommand

TAGS_API = "https://api.github.com/repos/WeblateOrg/weblate/git/ref/tags/{}"
RELEASES_API = "https://sentry.weblate.org/api/0/organizations/weblate/releases/"


class Command(BaseCommand):
    help = "records a release on Sentry"

    def handle(self, *args, **options) -> None:
        if weblate.utils.version.GIT_REVISION:
            # Get release from Git
            version = ref = weblate.utils.version.GIT_REVISION
        else:
            # Get commit hash from GitHub
            version = weblate.utils.version.TAG_NAME
            response = requests.get(TAGS_API.format(version), timeout=1)
            response.raise_for_status()
            response = requests.get(response.json()["object"]["url"], timeout=1)
            response.raise_for_status()
            ref = response.json()["object"]["sha"]

        sentry_auth = {"Authorization": f"Bearer {settings.SENTRY_TOKEN}"}
        release_url = RELEASES_API + version + "/"

        # Ensure the release is tracked on Sentry
        response = requests.get(release_url, headers=sentry_auth, timeout=1)
        if response.status_code == 404:
            data = {
                "version": version,
                "projects": settings.SENTRY_PROJECTS,
                "ref": ref,
                "refs": [{"repository": "WeblateOrg/weblate", "commit": ref}],
            }
            response = requests.post(
                RELEASES_API, json=data, headers=sentry_auth, timeout=1
            )
            self.stdout.write(f"Created new release {version}")
        response.raise_for_status()

        # Track the deploy
        response = requests.post(
            release_url + "deploys/",
            data={"environment": settings.SENTRY_ENVIRONMENT},
            headers=sentry_auth,
            timeout=1,
        )
        response.raise_for_status()
        self.stdout.write("Created new Sentry deploy {}".format(response.json()["id"]))
