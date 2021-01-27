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


from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_POST_UPDATE
from weblate.addons.forms import DiscoveryForm
from weblate.trans.discovery import ComponentDiscovery


class DiscoveryAddon(BaseAddon):
    events = (EVENT_POST_UPDATE,)
    name = "weblate.discovery.discovery"
    verbose = _("Component discovery")
    description = _(
        "Automatically adds or removes project components based on file changes "
        "in the version control system."
    )
    settings_form = DiscoveryForm
    multiple = True
    icon = "magnify.svg"
    repo_scope = True
    trigger_update = True

    def post_update(self, component, previous_head: str, skip_push: bool):
        self.discovery.perform(
            remove=self.instance.configuration["remove"], background=True
        )

    def get_settings_form(self, user, **kwargs):
        """Return configuration form for this addon."""
        if "data" not in kwargs:
            kwargs["data"] = self.instance.configuration
            kwargs["data"]["confirm"] = False
        return super().get_settings_form(user, **kwargs)

    @cached_property
    def discovery(self):
        # Handle old settings which did not have this set
        if "new_base_template" not in self.instance.configuration:
            self.instance.configuration["new_base_template"] = ""
        return ComponentDiscovery(
            self.instance.component,
            **ComponentDiscovery.extract_kwargs(self.instance.configuration)
        )
