# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy

from weblate.addons.base import BaseAddon
from weblate.addons.events import AddonEvent
from weblate.addons.forms import DiscoveryForm
from weblate.trans.discovery import ComponentDiscovery

if TYPE_CHECKING:
    from weblate.auth.models import User


class DiscoveryAddon(BaseAddon):
    events: set[AddonEvent] = {
        AddonEvent.EVENT_POST_UPDATE,
    }
    name = "weblate.discovery.discovery"
    verbose = gettext_lazy("Component discovery")
    description = gettext_lazy(
        "Automatically adds or removes project components based on file changes "
        "in the version control system."
    )
    settings_form = DiscoveryForm
    multiple = True
    icon = "magnify.svg"
    repo_scope = True
    needs_component = True
    trigger_update = True

    def post_update(self, component, previous_head: str, skip_push: bool) -> None:
        discovery = self.get_discovery(component)
        discovery.perform(
            remove=self.instance.configuration.get("remove"), background=True
        )

    def get_settings_form(self, user: User | None, **kwargs):
        """Return configuration form for this addon."""
        if "data" not in kwargs:
            kwargs["data"] = self.instance.configuration
            kwargs["data"]["confirm"] = False
        return super().get_settings_form(user, **kwargs)

    def get_discovery(self, component):
        # Handle old settings which did not have this set
        if "new_base_template" not in self.instance.configuration:
            self.instance.configuration["new_base_template"] = ""
        if "intermediate_template" not in self.instance.configuration:
            self.instance.configuration["intermediate_template"] = ""
        return ComponentDiscovery(
            component,
            **ComponentDiscovery.extract_kwargs(self.instance.configuration),
        )
