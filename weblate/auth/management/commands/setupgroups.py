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

from weblate.auth.models import create_groups, setup_project_groups
from weblate.trans.models import Project
from weblate.utils.management.base import BaseCommand


class Command(BaseCommand):
    help = "setups default user groups"

    def add_arguments(self, parser):
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

    def handle(self, *args, **options):
        """Create or update default set of groups.

        It also optionally updates them and moves users around to default group.
        """
        create_groups(options["update"])
        if options["projects"]:
            for project in Project.objects.iterator():
                setup_project_groups(Project, project)
