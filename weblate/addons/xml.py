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
from translate.storage.lisa import LISAfile

from weblate.addons.base import StoreBaseAddon
from weblate.addons.forms import XMLCustomizeForm


class XMLCustomizeAddon(StoreBaseAddon):
    """Class providing XML formatting changes as a component AddOn."""

    name = "weblate.xml.customize"
    verbose = _("Customize XML output")
    description = _(
        "Allows adjusting XML output behavior, for example closing tags instead of "
        "self-closing tags for empty tags."
    )
    settings_form = XMLCustomizeForm

    @classmethod
    def can_install(cls, component, user):
        """Hook triggered to determine if add-on is compatible with component."""
        # component are attached to a file format which is defined by a loader
        # we want to provide this package only for component using LISAfile as loader
        if not hasattr(component.file_format_cls, "get_class"):
            # Non translate-toolkit based formats
            return False
        return issubclass(component.file_format_cls.get_class(), LISAfile)

    def store_post_load(self, translation, store):
        """Hook triggered once component formatter has been loaded."""
        config = self.instance.configuration
        store.store.XMLSelfClosingTags = not config.get("closing_tags", True)
