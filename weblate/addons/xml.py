#
# Copyright © 2022–2023 Loïc LEUILLIOT <loic.leuilliot@gmail.com>
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
from weblate.addons.forms import XMLCustomizeForm


class XMLCustomizeAddon(StoreBaseAddon):
    name = "weblate.xml.customize"
    verbose = _("Customize XML output")
    description = _(
        "Allows adjusting XML output behavior, for example indentation or sorting."
    )
    settings_form = XMLCustomizeForm

    def store_post_load(self, translation, store):
        config = self.instance.configuration
        store.XMLSelfClosingTags = (
            config.get("tags_format", "closing_tags") == "self_closing_tags"
        )
