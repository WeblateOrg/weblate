# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import requests
from django.conf import settings
from django.core.management.base import CommandError

import weblate.utils.version
from weblate.utils.management.base import BaseCommand

TAGS_API = "https://api.github.com/repos/WeblateOrg/weblate/git/ref/tags/{}"


class Command(BaseCommand):
    help = "records a release on Sentry"

    def handle(self, *args, **options) -> None:
        if weblate.utils.version.GIT_REVISION:
            # Get release from Git
            version = ref = weblate.utils.version.GIT_REVISION
        else:
            # Get commit hash from GitHub
            version = weblate.utils.version.TAG_NAME
            response = requests.get(TAGS_API.format(version), timeout=5)
            response.raise_for_status()
            data = response.json()
            object_url = data["object"]["url"]
            if not object_url.startswith("https://api.github.com/"):
                msg = f"Unexpected URL from GitHub: {object_url}"
                raise CommandError(msg)
            response = requests.get(object_url, timeout=5)
            response.raise_for_status()
            ref = response.json()["object"]["sha"]

        sentry_auth = {"Authorization": f"Bearer {settings.SENTRY_TOKEN}"}
        sentry_url = settings.SENTRY_RELEASES_API_URL
        release_url = sentry_url + version + "/"

        # Ensure the release is tracked on Sentry
        response = requests.get(release_url, headers=sentry_auth, timeout=30)
        if response.status_code == 404:
            data = {
                "version": version,
                "projects": settings.SENTRY_PROJECTS,
                "ref": ref,
                "refs": [{"repository": "WeblateOrg/weblate", "commit": ref}],
            }
            response = requests.post(
                sentry_url, json=data, headers=sentry_auth, timeout=30
            )
            self.stdout.write(f"Created new release {version}")
        response.raise_for_status()

        # Track the deploy
        response = requests.post(
            release_url + "deploys/",
            data={"environment": settings.SENTRY_ENVIRONMENT},
            headers=sentry_auth,
            timeout=30,
        )
        response.raise_for_status()
        self.stdout.write("Created new Sentry deploy {}".format(response.json()["id"]))
