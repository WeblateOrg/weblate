# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from weblate.auth.models import User
from weblate.trans.backups import ProjectBackup
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    """Command for importing project backup into Weblate."""

    help = "imports project backup"

    def add_arguments(self, parser) -> None:
        super().add_arguments(parser)
        parser.add_argument("project_name", help="Project name")
        parser.add_argument("project_slug", help="Project slug")
        parser.add_argument("username", help="Username doing import")
        parser.add_argument("filename", help="Path to project backup")

    def handle(
        self,
        project_name: str,
        project_slug: str,
        username: str,
        filename: str,
        **options,
    ) -> None:
        user = User.objects.get(username=username)
        restore = ProjectBackup(filename)

        restore.validate()

        restore.restore(project_name=project_name, project_slug=project_slug, user=user)
