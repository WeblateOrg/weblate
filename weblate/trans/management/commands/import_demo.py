# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from time import sleep

from weblate.addons.discovery import DiscoveryAddon
from weblate.trans.models import Component, Project
from weblate.trans.tasks import actual_project_removal
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    """Command for creating demo project."""

    help = "imports demo project and components"

    def add_arguments(self, parser) -> None:
        super().add_arguments(parser)
        parser.add_argument(
            "--additional", type=int, default=0, help="number of additional components"
        )
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Update existing add-ons configuration",
        )

    def handle(self, *args, **options) -> None:
        if options["delete"]:
            try:
                project = Project.objects.get(slug="demo")
            except Project.DoesNotExist:
                pass
            else:
                # Remove without creating a backup
                actual_project_removal(project.pk, None)
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
        while component.in_progress():
            self.stdout.write(
                f"Importing base component: {component.get_progress()[0]}%"
            )
            sleep(1)
        component.clean()

        # Install discovery
        DiscoveryAddon.create(
            component=component,
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

        for i in range(options["additional"]):
            Component.objects.create(
                name=f"Additional {i}",
                slug=f"additional-{i}",
                project=project,
                vcs="git",
                repo=component.get_repo_link_url(),
                filemask="weblate/langdata/locale/*/LC_MESSAGES/django.po",
                new_base="weblate/langdata/locale/django.pot",
                file_format="po",
                license="GPL-3.0-or-later",
            )
