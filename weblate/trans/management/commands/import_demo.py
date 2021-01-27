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

from time import sleep

from weblate.addons.discovery import DiscoveryAddon
from weblate.trans.models import Component, Project
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    """Command for creating demo project."""

    help = "imports demo project and components"

    def handle(self, *args, **options):
        # Create project
        project = Project.objects.create(
            name="Demo", slug="demo", web="https://demo.weblate.org/"
        )

        # Create main component
        component = Component.objects.create(
            name="Gettext",
            slug="gettext",
            project=project,
            vcs="git",
            repo="https://github.com/WeblateOrg/demo.git",
            repoweb=(
                "https://github.com/WeblateOrg/weblate/"
                "blob/{{branch}}/{{filename}}#L{{line}}"
            ),
            filemask="weblate/langdata/locale/*/LC_MESSAGES/django.po",
            new_base="weblate/langdata/locale/django.pot",
            file_format="po",
            license="GPL-3.0-or-later",
        )
        component.clean()
        while component.in_progress():
            self.stdout.write(
                "Importing base component: {}%".format(component.get_progress()[0])
            )
            sleep(1)

        # Install discovery
        DiscoveryAddon.create(
            component,
            configuration={
                "file_format": "po",
                "match": (
                    r"weblate/locale/(?P<language>[^/]*)/"
                    r"LC_MESSAGES/(?P<component>[^/]*)\.po"
                ),
                "name_template": "Discovered: {{ component|title }}",
                "language_regex": "^[^.]+$",
                "base_file_template": "",
                "remove": True,
            },
        )

        # Manually add Android
        Component.objects.create(
            name="Android",
            slug="android",
            project=project,
            vcs="git",
            repo=component.get_repo_link_url(),
            filemask="app/src/main/res/values-*/strings.xml",
            template="app/src/main/res/values/strings.xml",
            file_format="aresource",
            license="GPL-3.0-or-later",
        )
