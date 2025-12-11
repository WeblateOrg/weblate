# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from typing import TYPE_CHECKING

from weblate.auth.models import create_groups, setup_project_groups
from weblate.trans.models import Project
from weblate.utils.management.base import BaseCommand

if TYPE_CHECKING:
    from django.core.management.base import CommandParser


class Command(BaseCommand):
    help = "setups default user groups"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--no-privs-update",
            action="store_false",
            dest="update",
            default=True,
            help="Prevents updates of privileges of existing groups",
        )
        parser.add_argument(
            "--no-projects-update",
            action="store_false",
            dest="projects",
            default=True,
            help="Prevents updates of groups for existing projects",
        )

    def handle(self, *args, **options) -> None:
        """
        Create or update default set of groups.

        It also optionally updates them and moves users around to default group.
        """
        create_groups(options["update"])
        if options["projects"]:
            for project in Project.objects.iterator():
                setup_project_groups(Project, project)
