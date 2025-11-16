# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, ClassVar

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy

from weblate.addons.base import BaseAddon
from weblate.addons.events import AddonEvent
from weblate.addons.forms import AutoAddonForm
from weblate.trans.actions import ACTIONS_CONTENT, ActionEvents
from weblate.trans.models import Component
from weblate.trans.tasks import auto_translate, auto_translate_component

if TYPE_CHECKING:
    from django.forms.boundfield import BoundField
    from django_stubs_ext import StrOrPromise

    from weblate.trans.models import Change

SKIP_ACTIONS = {ActionEvents.AUTO, ActionEvents.ENFORCED_CHECK}


class AutoTranslateAddon(BaseAddon):
    events: ClassVar[set[AddonEvent]] = {
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

    def component_update(
        self, component: Component, activity_log_id: int | None = None
    ) -> None:
        self.trigger_autotranslate(component=component)

    def trigger_autotranslate(
        self,
        *,
        component: Component | None = None,
        user_id: int | None = None,
        translation_id: int | None = None,
        unit_ids: list[int] | None = None,
    ) -> None:
        conf = self.instance.configuration
        if component is None:
            auto_translate.delay_on_commit(
                mode=conf["mode"],
                q=conf["q"],
                auto_source=conf["auto_source"],
                engines=conf["engines"],
                threshold=conf["threshold"],
                component=conf["component"],
                user_id=user_id,
                unit_ids=unit_ids,
                translation_id=translation_id,
            )
        else:
            auto_translate_component.delay_on_commit(
                component.pk,
                mode=conf["mode"],
                q=conf["q"],
                auto_source=conf["auto_source"],
                engines=conf["engines"],
                threshold=conf["threshold"],
                component=conf["component"],
            )

    def daily(self, component: Component, activity_log_id: int | None = None) -> None:
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

        self.trigger_autotranslate(component=component)

    def change_event(self, change: Change, activity_log_id: int | None = None) -> None:
        units = []
        if change.action in ACTIONS_CONTENT and change.action not in SKIP_ACTIONS:
            if change.unit is not None:
                units.append(change.unit)
        elif change.action in {
            ActionEvents.SCREENSHOT_UPLOADED,
            ActionEvents.SCREENSHOT_ADDED,
        }:
            if change.screenshot is not None:
                units.extend(change.screenshot.units.all())
        elif change.action in {
            ActionEvents.SUGGESTION,
            ActionEvents.SUGGESTION_CLEANUP,
            ActionEvents.SUGGESTION_DELETE,
        }:
            if change.suggestion is not None:
                units.append(change.suggestion.unit)
        elif (
            change.action
            in {
                ActionEvents.COMMENT,
                ActionEvents.COMMENT_RESOLVE,
                ActionEvents.COMMENT_DELETE,
            }
            and change.comment is not None
        ):
            units.append(change.comment.unit)

        all_units = set()
        for unit in units:
            all_units.add(unit)
            # for source units, trigger auto-translation on all target units
            if unit.is_source:
                all_units.update(unit.unit_set.exclude(pk=unit.pk))

        translation_with_unit_ids = defaultdict(list)
        for unit in all_units:
            if unit.automatically_translated:
                # Skip already automatically translated strings here to avoid repeated
                # translating, for example with enforced checks.
                continue
            translation_with_unit_ids[unit.translation.id].append(unit.pk)

        for translation_id, unit_ids in translation_with_unit_ids.items():
            self.trigger_autotranslate(
                user_id=change.user_id,
                translation_id=translation_id,
                unit_ids=unit_ids,
            )

    def show_setting_field(self, field: BoundField) -> bool:
        auto_source = self.instance.configuration["auto_source"]
        # Do not show UI hidden fields
        if (auto_source == "mt" and field.name == "component") or (
            auto_source == "others" and field.name in {"engines", "threshold"}
        ):
            return False
        return not field.is_hidden and field.value()

    def get_setting_value(self, field: BoundField) -> StrOrPromise:
        if field.name == "component" and not hasattr(field.field, "choices"):
            # Manually handle char field
            return str(Component.objects.get(pk=field.value()))
        return super().get_setting_value(field)
