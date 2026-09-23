# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import re
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone
from django.utils.translation import override

from weblate.addons.automation_expressions import expressions
from weblate.addons.automation_operations import execute_operation
from weblate.addons.events import AddonActivityLogStatus
from weblate.trans.automation import UnitSelection
from weblate.trans.models import Unit
from weblate.utils.automation import automation_origin

if TYPE_CHECKING:
    from collections.abc import Callable

    from weblate.auth.models import User
    from weblate.trans.models import Change, Component


def execution_context(
    component: Component,
    trigger: str,
    change: Change | None = None,
    actor: User | None = None,
) -> dict[str, Any]:
    unit = change.unit if change and change.unit_id else None
    language = change.language if change and change.language_id else None
    if change:
        actor = change.user or change.author
    return {
        "component": {
            "id": component.pk,
            "slug": component.slug,
            "project": component.project.slug,
            "category": component.category.slug if component.category else None,
        },
        "language": {"id": language.pk, "code": language.code} if language else None,
        "unit": {
            "id": unit.pk,
            "state": unit.state,
            "source": unit.source[:4096],
            "target": unit.target[:4096],
        }
        if unit
        else None,
        "change": {
            "id": change.pk,
            "action": change.action,
            "timestamp": change.timestamp.isoformat(),
        }
        if change
        else None,
        "actor": {"id": actor.pk, "username": actor.username} if actor else None,
        "trigger": {
            "name": trigger,
            "timestamp": (change.timestamp if change else timezone.now()).isoformat(),
            "unit_ids": [unit.pk] if unit else None,
            "source_unit_ids": [unit.source_unit_id or unit.pk] if unit else None,
            "revision": component.local_revision or None,
        },
        "results": {},
    }


class Runner:
    def __init__(
        self,
        workflow: dict[str, Any],
        context: dict[str, Any],
        component: Component,
        user: User | None,
        *,
        preview: bool = False,
        persist: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.workflow = workflow
        self.context = deepcopy(context)
        self.component = component
        self.user = user
        self.preview = preview
        self.persist = persist
        self.trace: list[dict[str, Any]] = []
        self.failed = False
        self.planned = False
        self.selections: dict[str, UnitSelection] = {}

    def selection(self, scope: str) -> UnitSelection:
        if scope == "component":
            return UnitSelection()
        if scope == "trigger":
            trigger = self.context["trigger"]
            ids = trigger.get("unit_ids")
            if not ids:
                msg = "Trigger scope requires a change with a unit."
                raise ValueError(msg)
            source_ids = trigger.get("source_unit_ids")
            if source_ids is None:
                source_ids = list(
                    Unit.objects.filter(
                        pk__in=ids, translation__component=self.component
                    ).values_list("source_unit_id", flat=True)
                )
            sources = set(source_ids)
            source_changes = set(ids) & sources
            return UnitSelection(set(ids) - source_changes, sources, source_changes)
        action_id = scope.removeprefix("result:")
        if action_id not in self.selections:
            msg = f"Result scope requires completed action {action_id}."
            raise ValueError(msg)
        return self.selections[action_id]

    def record(self, path: str, status: str, **details: object) -> None:
        self.trace.append({"path": path, "status": status, **details})
        if self.persist:
            self.persist(self.result())

    def result(self) -> dict[str, Any]:
        return {
            "workflow": self.workflow,
            "context": self.context,
            "trace": self.trace,
            "preview": self.preview,
        }

    def conditions(
        self, nodes: list[dict[str, Any]], path: str, operator: str = "and"
    ) -> bool | None:
        values: list[bool | None] = []
        for index, node in enumerate(nodes):
            node_path = f"{path}[{index}]"
            if (operator == "and" and False in values) or (
                operator == "or" and True in values
            ):
                self.record(node_path, "skipped", reason="short-circuit")
                continue
            value = self.condition(node, node_path)
            values.append(value)
            self.record(
                node_path, "evaluated" if value is not None else "unknown", value=value
            )
        if operator == "or":
            return True if True in values else None if None in values else False
        return False if False in values else None if None in values else True

    def condition(self, node: dict[str, Any], path: str) -> bool | None:
        kind = node["condition"]
        if kind in {"and", "or", "not"}:
            value = self.conditions(
                node["conditions"],
                f"{path}.conditions",
                "or" if kind == "or" else "and",
            )
            return not value if kind == "not" and value is not None else value
        value = node["value"]
        if (
            self.preview
            and self.planned
            and (
                kind == "matching_strings"
                or (kind == "expression" and re.search(r"\bresults\b", value))
            )
        ):
            return None
        if kind == "expression":
            return expressions([value], self.context)[0]
        if kind == "matching_strings":
            return (
                Unit.objects.filter(translation__component=self.component)
                .search(value, project=self.component.project)
                .exists()
            )
        if kind == "component_category":
            return self.context["component"]["category"] == value
        if kind == "language":
            return (
                self.context["language"] is not None
                and self.context["language"]["code"] == value
            )
        if kind == "unit_state":
            return (
                self.context["unit"] is not None
                and self.context["unit"]["state"] == value
            )
        if kind == "change_action":
            from weblate.addons.automation_schema import CHANGE_ACTIONS  # ruff: ignore[import-outside-top-level]

            return (
                self.context["change"] is not None
                and self.context["change"]["action"] == CHANGE_ACTIONS[value]
            )
        msg = "Unsupported condition"
        raise ValueError(msg)

    def sequence(
        self,
        nodes: list[dict[str, Any]],
        path: str,
        *,
        skip: bool = False,
        conditional: bool = False,
    ) -> None:
        for index, node in enumerate(nodes):
            node_path = f"{path}[{index}]"
            skipped = skip or self.failed
            if "action" in node:
                if skipped:
                    self.record(node_path, "skipped")
                elif self.preview:
                    try:
                        scope = node.get("scope", "component")
                        if scope == "trigger":
                            self.selection(scope)
                        self.record(
                            node_path,
                            "conditional"
                            if conditional or scope.startswith("result:")
                            else "planned",
                            action=node["action"],
                        )
                        self.planned = True
                    except Exception as error:
                        self.failed = True
                        self.record(node_path, "error", error=str(error)[:4096])
                else:
                    self.record(node_path, "running", action=node["action"])
                    try:  # ruff: ignore[too-many-statements-in-try-clause]
                        scope = node.get("scope", "component")
                        selection = self.selection(scope)
                        scope_units = (
                            selection.count(self.component)
                            if scope != "component"
                            else None
                        )
                        affected = UnitSelection(set())
                        output = execute_operation(
                            node, self.component, self.user, selection, affected
                        )
                        if "id" in node:
                            self.context["results"][node["id"]] = output
                            self.selections[node["id"]] = affected
                        self.record(
                            node_path,
                            "success",
                            output=output,
                            scope=scope,
                            affected=len(affected.unit_ids or ()),
                            **(
                                {"scope_units": scope_units}
                                if scope_units is not None
                                else {}
                            ),
                        )
                    except Exception as error:
                        self.failed = True
                        self.record(node_path, "error", error=str(error)[:4096])
            elif "sequence" in node:
                self.sequence(
                    node["sequence"],
                    f"{node_path}.sequence",
                    skip=skipped,
                    conditional=conditional,
                )
            else:
                self.choose(node, node_path, skip=skipped, conditional=conditional)

    def choose(
        self, node: dict[str, Any], path: str, *, skip: bool, conditional: bool
    ) -> None:
        selected = False
        uncertain = conditional
        value: bool | None
        for index, branch in enumerate(node["choose"]):
            branch_path = f"{path}.choose[{index}]"
            if skip or selected or self.failed:
                value = False
                self.record(branch_path, "skipped")
            else:
                try:
                    value = self.conditions(
                        branch["conditions"], f"{branch_path}.conditions"
                    )
                except Exception as error:
                    self.failed = True
                    self.record(branch_path, "error", error=str(error)[:4096])
                    value = False
            uncertain |= value is None
            self.sequence(
                branch["sequence"],
                f"{branch_path}.sequence",
                skip=skip or value is False,
                conditional=uncertain,
            )
            selected |= value is True
        self.sequence(
            node.get("default", []),
            f"{path}.default",
            skip=skip or selected,
            conditional=uncertain,
        )

    def run(self) -> AddonActivityLogStatus:
        with override("en"):
            try:
                applicable = self.conditions(
                    self.workflow.get("conditions", []), "conditions"
                )
            except Exception as error:
                self.failed = True
                self.record("conditions", "error", error=str(error)[:4096])
                applicable = False
            self.sequence(self.workflow["actions"], "actions", skip=applicable is False)
        if self.failed:
            return AddonActivityLogStatus.ERROR
        return (
            AddonActivityLogStatus.SUCCESS
            if applicable
            else AddonActivityLogStatus.SKIPPED
        )


@override("en")
def run_automation(activity_id: int) -> None:
    from weblate.addons.automation_definition import parse_workflow  # ruff: ignore[import-outside-top-level]
    from weblate.addons.automation_forms import validate_operations  # ruff: ignore[import-outside-top-level]
    from weblate.addons.models import AddonActivityLog  # ruff: ignore[import-outside-top-level]

    with transaction.atomic():
        activity = (
            AddonActivityLog.objects.select_for_update().filter(pk=activity_id).first()
        )
        if (
            activity is None
            or activity.status != AddonActivityLogStatus.PENDING
            or activity.details.get("claimed")
        ):
            return
        activity.details["claimed"] = True
        activity.save(update_fields=["details"])
    details = activity.details
    result = details["result"]

    def persist(value: dict[str, Any]) -> None:
        details["result"] = value
        AddonActivityLog.objects.filter(pk=activity_id).update(details=details)

    origin = automation_origin.set(activity_id)
    try:  # ruff: ignore[too-many-statements-in-try-clause]
        addon = activity.addon
        if (
            not addon.is_valid
            or activity.component is None
            or not addon.affected_components().filter(pk=activity.component_id).exists()
        ):
            status = AddonActivityLogStatus.SKIPPED
            result["trace"] = [
                {"path": "workflow", "status": "skipped", "reason": "target-missing"}
            ]
        else:
            workflow = validate_operations(
                parse_workflow(result["workflow"]), activity.component
            )
            runner = Runner(
                workflow,
                result["context"],
                activity.component,
                addon.addon.user,
                persist=persist,
            )
            status = runner.run()
            result = runner.result()
    except Exception as error:
        status = AddonActivityLogStatus.ERROR
        result.setdefault("trace", []).append(
            {"path": "workflow", "status": "error", "error": str(error)[:4096]}
        )
    finally:
        automation_origin.reset(origin)
    persist(result)
    AddonActivityLog.objects.filter(pk=activity_id).update(status=status)
