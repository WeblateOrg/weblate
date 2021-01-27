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


from django.utils.translation import gettext_lazy as _

from weblate.addons.base import StoreBaseAddon
from weblate.addons.forms import YAMLCustomizeForm

BREAKS = {"dos": "\r\n", "mac": "\r", "unix": "\n"}


class YAMLCustomizeAddon(StoreBaseAddon):
    name = "weblate.yaml.customize"
    verbose = _("Customize YAML output")
    description = _(
        "Allows adjusting YAML output behavior, for example line-length or newlines."
    )
    settings_form = YAMLCustomizeForm
    compat = {"file_format": {"yaml", "ruby-yaml"}}

    def store_post_load(self, translation, store):
        config = self.instance.configuration

        args = store.store.dump_args

        args["indent"] = int(config.get("indent", 2))
        args["width"] = int(config.get("width", 80))
        args["line_break"] = BREAKS[config.get("line_break", "unix")]
