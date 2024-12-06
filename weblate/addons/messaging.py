# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.utils.translation import gettext_lazy

from weblate.addons.base import BaseAddon
from weblate.addons.events import AddonEvent
from weblate.addons.forms import MessagingAddonForm
from weblate.trans.models import Component


class WeblateMessagingAddon(BaseAddon):
    name = 'weblate.messaging'
    verbose = gettext_lazy("Weblate Fedora Messaging")
    description = gettext_lazy("An add-on to integrate Fedora Messaging with weblate.")
    settings_form = MessagingAddonForm
    events = (AddonEvent.EVENT_COMPONENT_UPDATE, )
    icon = "email.svg"

    def component_update(self, component: Component) -> None:
        component.log_debug("running component_update add-on: %s", self.name)
