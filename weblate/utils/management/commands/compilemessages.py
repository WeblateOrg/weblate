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


from django.core.management.commands.compilemessages import Command as BaseCommand

from weblate.utils.files import should_skip


class Command(BaseCommand):
    # We just remove --format-check as it just complicates things
    # for some translations
    program_options = []

    def compile_messages(self, locations):
        # Avoid compiling po files in DATA_DIR
        locations = [location for location in locations if not should_skip(location[0])]
        if not locations:
            return
        super().compile_messages(locations)
