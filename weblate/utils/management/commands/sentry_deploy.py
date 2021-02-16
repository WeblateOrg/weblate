#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

import requests
from django.conf import settings

import weblate.utils.version
from weblate.utils.management.base import BaseCommand

TAGS_API = "https://api.github.com/repos/WeblateOrg/weblate/git/ref/tags/{}"
RELEASES_API = "https://sentry.io/api/0/organizations/{}/releases/"


class Command(BaseCommand):
    help = "records a release on Sentry"

    def handle(self, *args, **options):
        if weblate.utils.version.GIT_REVISION:
            # Get release from Git
            version = ref = weblate.utils.version.GIT_REVISION
        else:
            # Get commit hash from GitHub
            version = weblate.utils.version.TAG_NAME
            response = requests.get(TAGS_API.format(version))
            response.raise_for_status()
            response = requests.get(response.json()["object"]["url"])
            response.raise_for_status()
            ref = response.json()["object"]["sha"]

        sentry_auth = {"Authorization": f"Bearer {settings.SENTRY_TOKEN}"}
        sentry_base = RELEASES_API.format(settings.SENTRY_ORGANIZATION)
        release_url = sentry_base + version + "/"

        # Ensure the release is tracked on Sentry
        response = requests.get(release_url, headers=sentry_auth)
        if response.status_code == 404:
            data = {
                "version": version,
                "projects": settings.SENTRY_PROJECTS,
                "ref": ref,
                "refs": [{"repository": "WeblateOrg/weblate", "commit": ref}],
            }
            response = requests.post(sentry_base, json=data, headers=sentry_auth)
            self.stdout.write(f"Created new release {version}")
        response.raise_for_status()

        # Track the deploy
        response = requests.post(
            release_url + "deploys/",
            data={"environment": settings.SENTRY_ENVIRONMENT},
            headers=sentry_auth,
        )
        response.raise_for_status()
        self.stdout.write("Created new Sentry deploy {}".format(response.json()["id"]))
