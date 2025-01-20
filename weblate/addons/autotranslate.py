# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy

from weblate.addons.base import BaseAddon
from weblate.addons.events import AddonEvent
from weblate.addons.forms import AutoAddonForm
from weblate.trans.tasks import auto_translate_component

if TYPE_CHECKING:
    from weblate.trans.models import Component


class AutoTranslateAddon(BaseAddon):
    events: set[AddonEvent] = {
        AddonEvent.EVENT_COMPONENT_UPDATE,
        AddonEvent.EVENT_DAILY,
    }
    name = "weblate.autotranslate.autotranslate"
    verbose = gettext_lazy("Automatic translation")
    description = gettext_lazy(
        "Automatically translates strings using machine translation or "
        "other components."
    )
    settings_form = AutoAddonForm
    multiple = True
    icon = "language.svg"

    def component_update(self, component: Component) -> None:
        auto_translate_component.delay_on_commit(
            component.pk, **self.instance.configuration
        )

    def daily(self, component: Component) -> None:
        # Translate every component less frequenctly to reduce load.
        # The translation is anyway triggered on update, so it should
        # not matter that much that we run this less often.
        if settings.BACKGROUND_TASKS == "never":
            return
        today = timezone.now()
        if settings.BACKGROUND_TASKS == "monthly" and component.id % 30 != today.day:
            return
        if (
            settings.BACKGROUND_TASKS == "weekly"
            and component.id % 7 != today.weekday()
        ):
            return

        self.component_update(component)
