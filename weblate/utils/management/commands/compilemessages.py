# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.core.management.commands.compilemessages import Command as BaseCommand

from weblate.utils.files import should_skip


class Command(BaseCommand):
    # We just remove --format-check as it just complicates things
    # for some translations
    program_options = []

    def compile_messages(self, locations) -> None:
        # Avoid compiling po files in DATA_DIR
        locations = [location for location in locations if not should_skip(location[0])]
        if not locations:
            return
        super().compile_messages(locations)
