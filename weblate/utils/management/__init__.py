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

import sys

from django.core.management import ManagementUtility

RESTRICTED_COMMANDS = {"squashmigrations", "makemigrations"}


class WeblateManagementUtility(ManagementUtility):
    def __init__(self, argv=None, developer_mode: bool = False):
        super().__init__(argv)
        self.developer_mode = developer_mode

    def fetch_command(self, subcommand):
        # Block usage of some commands
        if not self.developer_mode and subcommand in RESTRICTED_COMMANDS:
            sys.stderr.write("Blocked command: %r\n" % subcommand)
            sys.stderr.write("This command is restricted for developers only.\n")
            sys.stderr.write(
                "In case you really want to do this, please execute "
                "using manage.py from the Weblate source code.\n"
            )
            sys.exit(1)

        # Fetch command class
        command = super().fetch_command(subcommand)

        # Monkey patch it's output
        original_notice = command.style.NOTICE

        def patched_notice(txt):
            return original_notice(
                txt.replace("python manage.py migrate", "weblate migrate")
            )

        command.style.NOTICE = patched_notice

        return command
