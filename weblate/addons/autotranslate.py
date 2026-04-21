# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, ClassVar, Literal, TypedDict, cast

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy

from weblate.addons.base import BaseAddon
from weblate.addons.events import AddonEvent
from weblate.addons.forms import AutoAddonForm
from weblate.trans.actions import ACTIONS_CONTENT, ActionEvents
from weblate.trans.filter import FILTERS
from weblate.trans.models import Component
from weblate.trans.tasks import auto_translate, auto_translate_component

if TYPE_CHECKING:
    from collections.abc import Mapping

    from django.forms.boundfield import BoundField
    from django_stubs_ext import StrOrPromise

    from weblate.addons.base import AddonConfigurationValue
    from weblate.trans.models import Change

SKIP_ACTIONS = {ActionEvents.AUTO, ActionEvents.ENFORCED_CHECK}


DEFAULT_AUTO_SOURCE: Literal["mt", "others"] = "others"
DEFAULT_AUTO_TRANSLATE_MODE = "suggest"
DEFAULT_AUTO_TRANSLATE_QUERY = "state:<translated"
DEFAULT_AUTO_TRANSLATE_THRESHOLD = 80


class AutoTranslateAddonStoredConfiguration(TypedDict, total=False):
    auto_source: Literal["mt", "others"]
    component: int | Literal[""] | None
    engines: list[str]
    filter_type: str
    mode: str
    q: str
    threshold: int


class AutoTranslateAddonConfiguration(TypedDict):
    auto_source: Literal["mt", "others"]
    component: int | None
    engines: list[str]
    mode: str
    q: str
    threshold: int


class AutoTranslateAddon(
    BaseAddon[AutoTranslateAddonStoredConfiguration, AutoTranslateAddonConfiguration]
):
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

    def get_settings_form_data(
        self,
    ) -> Mapping[str, AddonConfigurationValue]:
        return cast("Mapping[str, AddonConfigurationValue]", self.get_configuration())

    def normalize_configuration(
        self, configuration: AutoTranslateAddonStoredConfiguration
    ) -> AutoTranslateAddonConfiguration:
        auto_source = configuration.get("auto_source", DEFAULT_AUTO_SOURCE)
        if auto_source == "others":
            raw_component = configuration.get("component")
            source_component_id = raw_component or None
        else:
            source_component_id = None

        raw_query = configuration.get("q")
        if raw_query is None:
            raw_filter_type = configuration.get("filter_type")
            if raw_filter_type is None:
                query = DEFAULT_AUTO_TRANSLATE_QUERY
            else:
                query = FILTERS.get_filter_query(raw_filter_type)
        else:
            query = raw_query

        threshold = (
            configuration.get("threshold", DEFAULT_AUTO_TRANSLATE_THRESHOLD)
            if auto_source == "mt"
            else DEFAULT_AUTO_TRANSLATE_THRESHOLD
        )

        return {
            "auto_source": auto_source,
            "component": source_component_id,
            "engines": configuration.get("engines", []),
            "mode": configuration.get("mode", DEFAULT_AUTO_TRANSLATE_MODE),
            "q": query,
            "threshold": threshold,
        }

    def trigger_autotranslate(
        self,
        *,
        component: Component | None = None,
        user_id: int | None = None,
        translation_id: int | None = None,
        unit_ids: list[int] | None = None,
    ) -> None:
        conf = self.get_configuration()
        source_component_id = conf["component"]
        if component is None:
            auto_translate.delay_on_commit(
                mode=conf["mode"],
                q=conf["q"],
                auto_source=conf["auto_source"],
                engines=conf["engines"],
                threshold=conf["threshold"],
                source_component_id=source_component_id,
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
                source_component_id=source_component_id,
            )

    def daily_component(
        self,
        component: Component,
        activity_log_id: int | None = None,
    ) -> None:
        # Translate every component less frequently to reduce load.
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

    def check_change_action(self, change: Change) -> bool:
        return (
            change.unit is not None
            or change.screenshot is not None
            or change.suggestion is not None
            or change.comment is not None
        )

    def change_event(self, change: Change, activity_log_id: int | None = None) -> None:
        units = []
        if change.action in ACTIONS_CONTENT and change.action not in SKIP_ACTIONS:
            if change.unit is not None:
                units.append(change.unit)
        elif change.action in {
            ActionEvents.SCREENSHOT_UPLOADED,
            ActionEvents.SCREENSHOT_ADDED,
            ActionEvents.SCREENSHOT_REMOVED,
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
        form = getattr(field, "form", None)
        form_data = getattr(form, "data", None)
        raw_auto_source = (
            form_data.get("auto_source", DEFAULT_AUTO_SOURCE)
            if form_data is not None
            else DEFAULT_AUTO_SOURCE
        )
        auto_source = (
            raw_auto_source
            if raw_auto_source in {"mt", "others"}
            else DEFAULT_AUTO_SOURCE
        )
        # Do not show UI hidden fields
        if (auto_source == "mt" and field.name == "component") or (
            auto_source == "others" and field.name in {"engines", "threshold"}
        ):
            return False
        return not field.is_hidden and field.value()

    def get_setting_value(self, field: BoundField) -> StrOrPromise:
        if field.name == "component" and not hasattr(field.field, "choices"):
            # Manually handle char field
            try:
                return str(Component.objects.get(pk=field.value()))
            except (Component.DoesNotExist, TypeError, ValueError):
                return str(field.value())
        return super().get_setting_value(field)
