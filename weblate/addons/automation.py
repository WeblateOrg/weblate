# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any, ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext, gettext_lazy

from weblate.addons.automation_definition import parse_workflow
from weblate.addons.automation_forms import AutomationForm, validate_operations
from weblate.addons.automation_runner import (
    Runner,
    execution_context,
)
from weblate.addons.automation_schema import CHANGE_ACTIONS, TRIGGERS
from weblate.addons.base import BaseAddon
from weblate.addons.events import AddonActivityLogReason, AddonEvent, AddonEventOutcome
from weblate.auth.models import User
from weblate.trans.models import Change, Component
from weblate.utils.automation import automation_origin, manual_actor

if TYPE_CHECKING:
    from weblate.addons.models import AddonActivityLog


class AutomationAddon(BaseAddon):
    name = "weblate.automation.automation"
    verbose = gettext_lazy("Automation")
    description = gettext_lazy(
        "Runs ordered translation operations with conditions and branches."
    )
    version_added = "2026.10"
    multiple = True
    settings_form = AutomationForm
    user_name = "automation"
    user_verbose = "Automation add-on"
    has_preview = True
    show_skipped_result = True
    run_on_configuration = False
    events: ClassVar[set[AddonEvent]] = set(TRIGGERS.values())

    @property
    def configured_events(self) -> set[AddonEvent]:
        return {AddonEvent.EVENT_MANUAL} | {
            TRIGGERS[trigger["trigger"]]
            for trigger in self.instance.configuration.get("workflow", {}).get(
                "triggers", []
            )
            if trigger.get("trigger") in TRIGGERS
        }

    def post_configure_run(self) -> None:
        """Keep saving an automation free of workflow side effects."""

    def check_change_action(self, change: Change) -> bool:
        if change.component_id is None or change.details.get("automation_origin"):
            return False
        return any(
            trigger["trigger"] == "change"
            and change.action in {CHANGE_ACTIONS[event] for event in trigger["events"]}
            for trigger in self.instance.configuration["workflow"]["triggers"]
        )

    def queue(
        self,
        component: Component,
        activity_log_id: int | None,
        change: Change | None = None,
    ) -> AddonEventOutcome:
        from weblate.addons.models import AddonActivityLog  # ruff: ignore[import-outside-top-level]
        from weblate.addons.tasks import automation_run  # ruff: ignore[import-outside-top-level]

        if automation_origin.get() or activity_log_id is None:
            return AddonEventOutcome.skipped(AddonActivityLogReason.NOT_APPLICABLE)
        activity = AddonActivityLog.objects.get(pk=activity_log_id)
        trigger = next(
            name for name, event in TRIGGERS.items() if event == activity.event
        )
        actor = (
            User.objects.filter(pk=manual_actor.get()).first()
            if manual_actor.get()
            else None
        )
        context = execution_context(component, trigger, change, actor)
        activity.details = {
            "result": {
                "workflow": deepcopy(self.instance.configuration["workflow"]),
                "context": context,
                "trace": [],
            }
        }
        activity.save(update_fields=["details"])
        automation_run.delay_on_commit(activity.pk)
        return AddonEventOutcome.pending()

    def change_event(
        self, change: Change, activity_log_id: int | None = None
    ) -> AddonEventOutcome:
        if change.component is None:
            return AddonEventOutcome.skipped(AddonActivityLogReason.NOT_APPLICABLE)
        return self.queue(change.component, activity_log_id, change)

    def component_update(
        self, component: Component, activity_log_id: int | None = None
    ) -> AddonEventOutcome:
        return self.queue(component, activity_log_id)

    def post_update(
        self,
        component: Component,
        previous_head: str,
        skip_push: bool,
        changed_files: list[str],
        parse_after_update: bool = False,
        activity_log_id: int | None = None,
    ) -> AddonEventOutcome:
        return self.queue(component, activity_log_id)

    def post_commit(
        self, component: Component, store_hash: bool, activity_log_id: int | None = None
    ) -> AddonEventOutcome:
        return self.queue(component, activity_log_id)

    def post_push(
        self, component: Component, activity_log_id: int | None = None
    ) -> AddonEventOutcome:
        return self.queue(component, activity_log_id)

    def manual_component(
        self, component: Component, activity_log_id: int | None = None
    ) -> AddonEventOutcome:
        return self.queue(component, activity_log_id)

    def daily_component(
        self, component: Component, activity_log_id: int | None = None
    ) -> AddonEventOutcome:
        if settings.BACKGROUND_TASKS == "never":
            return AddonEventOutcome.skipped(
                AddonActivityLogReason.BACKGROUND_TASKS_DISABLED
            )
        today = timezone.now()
        if (
            settings.BACKGROUND_TASKS == "monthly"
            and component.pk % 30 + 1 != today.day
        ) or (
            settings.BACKGROUND_TASKS == "weekly"
            and component.pk % 7 != today.weekday()
        ):
            return AddonEventOutcome.skipped(AddonActivityLogReason.BACKGROUND_CADENCE)
        return self.queue(component, activity_log_id)

    def preview(
        self,
        workflow: object,
        component_id: int | None,
        change_id: int | None = None,
        actor: User | None = None,
    ) -> dict[str, Any]:
        component = self.instance.affected_components().filter(pk=component_id).first()
        if component is None:
            raise ValidationError(
                gettext("The component is outside this add-on's scope.")
            )
        change = None
        if change_id is not None:
            change = Change.objects.filter(pk=change_id, component=component).first()
            if change is None:
                raise ValidationError(
                    gettext("The change does not belong to this component.")
                )
        definition = validate_operations(parse_workflow(workflow), component)
        runner = Runner(
            definition,
            execution_context(
                component, "change" if change else "manual", change, actor
            ),
            component,
            None,
            preview=True,
        )
        runner.run()
        return runner.result()

    def render_activity_log(self, activity: AddonActivityLog) -> str:
        return format_html(
            "<pre>{}</pre>",
            json.dumps(
                activity.details.get("result", {}), indent=2, ensure_ascii=False
            ),
        )
