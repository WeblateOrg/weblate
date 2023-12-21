# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_COMPONENT_UPDATE, EVENT_DAILY
from weblate.addons.forms import AutoAddonForm
from weblate.trans.tasks import auto_translate_component


class AutoTranslateAddon(BaseAddon):
    events = (EVENT_COMPONENT_UPDATE, EVENT_DAILY)
    name = "weblate.autotranslate.autotranslate"
    verbose = gettext_lazy("Automatic translation")
    description = gettext_lazy(
        "Automatically translates strings using machine translation or "
        "other components."
    )
    settings_form = AutoAddonForm
    multiple = True
    icon = "language.svg"

    def component_update(self, component):
        transaction.on_commit(
            lambda: auto_translate_component.delay(
                component.pk, **self.instance.configuration
            )
        )

    def daily(self, component):
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
