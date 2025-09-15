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
from weblate.trans.actions import ACTIONS_CONTENT, ActionEvents
from weblate.trans.tasks import auto_translate, auto_translate_component

if TYPE_CHECKING:
    from weblate.trans.models import Change, Component


class AutoTranslateAddon(BaseAddon):
    events: set[AddonEvent] = {
        AddonEvent.EVENT_COMPONENT_UPDATE,
        AddonEvent.EVENT_DAILY,
        AddonEvent.EVENT_CHANGE,
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
        conf = self.instance.configuration
        auto_translate_component.delay_on_commit(
            component.pk,
            mode=conf["mode"],
            q=conf["q"],
            auto_source=conf["auto_source"],
            engines=conf["engines"],
            threshold=conf["threshold"],
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

    def change_event(self, change: Change) -> None:
        translation_ids = set()
        if change.action in ACTIONS_CONTENT:
            if change.unit is not None:
                translation_ids.add(change.unit.translation.id)
        elif change.action in {
            ActionEvents.SCREENSHOT_UPLOADED,
            ActionEvents.SCREENSHOT_ADDED,
        }:
            if change.screenshot is not None:
                translation_ids.update(
                    change.screenshot.units.values_list("translation_id", flat=True)
                )
        elif change.action in {
            ActionEvents.SUGGESTION,
            ActionEvents.SUGGESTION_CLEANUP,
            ActionEvents.SUGGESTION_DELETE,
        }:
            if change.suggestion is not None:
                translation_ids.add(change.suggestion.unit.translation.id)
        elif (
            change.action
            in {
                ActionEvents.COMMENT,
                ActionEvents.COMMENT_RESOLVE,
                ActionEvents.COMMENT_DELETE,
            }
            and change.comment is not None
        ):
            translation_ids.add(change.comment.unit.translation.id)

        for translation_id in translation_ids:
            auto_translate.delay(
                user_id=change.user_id,
                translation_id=translation_id,
                **self.instance.configuration,
            )
