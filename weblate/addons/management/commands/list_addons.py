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

from textwrap import wrap

from weblate.addons.models import ADDONS, Addon
from weblate.trans.models import Component, Project
from weblate.utils.management.base import BaseCommand

PARAMS_TABLE = """.. list-table:: Parameters to use in :ref:`API <addons-api>`, :setting:`DEFAULT_ADDONS`, or :djadmin:`install_addon`

   * - Add-on ID
     - ``{}``
   * - Configuration
     - {}
"""


class Command(BaseCommand):
    help = "List installed add-ons"

    def handle(self, *args, **options):
        """List installed add-ons."""
        fake_addon = Addon(component=Component(project=Project()))
        for _unused, obj in sorted(ADDONS.items()):
            self.stdout.write(f".. _addon-{obj.name}:")
            self.stdout.write("\n")
            self.stdout.write(obj.verbose)
            self.stdout.write("-" * len(obj.verbose))
            self.stdout.write("\n")
            if obj.settings_form:
                form = obj(fake_addon).get_settings_form(None)
                params = ", ".join(f"``{key}``" for key in form.fields.keys())
            else:
                params = "`This add-on has no configuration.`"
            self.stdout.write(PARAMS_TABLE.format(obj.name, params))
            self.stdout.write("\n")
            self.stdout.write("\n".join(wrap(obj.description, 79)))
            self.stdout.write("\n")
