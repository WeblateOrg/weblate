# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import sys

from django.core.management import ManagementUtility

RESTRICTED_COMMANDS = {"squashmigrations", "makemigrations"}


class WeblateManagementUtility(ManagementUtility):
    def __init__(self, argv=None, developer_mode: bool = False) -> None:
        super().__init__(argv)
        self.developer_mode = developer_mode

    def fetch_command(self, subcommand):
        # Block usage of some commands
        if not self.developer_mode and subcommand in RESTRICTED_COMMANDS:
            sys.stderr.write(f"Blocked command: {subcommand!r}\n")
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

        command.style.NOTICE = patched_notice  # type: ignore[method-assign]

        return command
