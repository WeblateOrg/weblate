# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import subprocess  # ruff: ignore[suspicious-subprocess-import]
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from textwrap import dedent
from threading import Barrier
from typing import TYPE_CHECKING, Any, TypedDict, Unpack
from unittest.mock import Mock, call, patch

from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.template.loader import render_to_string
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils.translation import override
from lxml import html
from rest_framework.test import APIClient

from weblate.addons.ai import (
    AIEvaluationAddon,
    EvaluatedUnitSnapshot,
    EvaluationSnapshot,
)
from weblate.addons.events import AddonActivityLogStatus, AddonEvent
from weblate.addons.models import AddonActivityLog, handle_addon_event
from weblate.addons.tasks import run_addon_manually
from weblate.automation import cel as automation_cel
from weblate.automation.addon import AutomationAddon
from weblate.automation.context import automation_origin
from weblate.automation.definition import parse_workflow
from weblate.automation.expressions import expressions
from weblate.automation.forms import AutomationForm, WorkflowField, validate_operations
from weblate.automation.operations import (
    OPERATIONS,
    AIQualityOperation,
    AutomaticTranslationOperation,
    AutomationOperation,
    SelectOperation,
    register,
)
from weblate.automation.runner import Runner, execution_context, run_automation
from weblate.automation.schema import SCHEMA
from weblate.machinery.anthropic import AnthropicTranslation
from weblate.machinery.base import MachineTranslationError
from weblate.machinery.models import MachineryInstallation
from weblate.machinery.openai import OpenAITranslation
from weblate.trans.actions import ActionEvents, get_change_action_identifier
from weblate.trans.automation import UnitSelection
from weblate.trans.autotranslate import AutoTranslate, BatchAutoTranslate
from weblate.trans.models import Change, Unit
from weblate.trans.templatetags.translations import format_last_changes_content
from weblate.trans.tests.test_views import (
    ComponentTestCase,
    ReusableComponentTestCase,
)
from weblate.trans.tests.utils import create_another_user
from weblate.utils.change_origin import change_origin, change_origin_context
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_EMPTY,
    STATE_FUZZY,
    STATE_NEEDS_CHECKING,
    STATE_TRANSLATED,
)

if TYPE_CHECKING:
    from weblate.trans.models import Category, Component, Project


class AutomationScope(TypedDict, total=False):
    component: Component | None
    category: Category | None
    project: Project | None


WORKFLOW: dict[str, Any] = {"version": 1, "triggers": [], "actions": []}
AUTO: dict[str, Any] = {
    "action": "weblate.automatic_translation",
    "id": "first",
    "settings": {},
}
BULK: dict[str, Any] = {
    "action": "weblate.bulk_edit",
    "settings": {"q": "state:translated", "state": STATE_FUZZY},
}
CONTEXT = {
    "component": {"id": 1, "category": "frontend"},
    "language": None,
    "unit": None,
    "change": None,
    "actor": None,
    "trigger": {"name": "manual"},
    "results": {},
}


class DefinitionTest(SimpleTestCase):
    def test_ai_quality_cookbook_workflow_parses(self) -> None:
        documentation = (
            Path(__file__).resolve().parents[2] / "docs/admin/automation.rst"
        ).read_text(encoding="utf-8")
        section = documentation.split(".. _automation-ai-quality-gateway:", 1)[1]
        example = section.split(".. code-block:: yaml\n\n", 1)[1].split("\n\n", 1)[0]
        workflow = parse_workflow(dedent(example))
        self.assertEqual(
            [action["action"] for action in workflow["actions"]],
            [
                "weblate.automatic_translation",
                "weblate.automatic_translation",
                "weblate.ai_quality",
                "weblate.bulk_edit",
                "weblate.bulk_edit",
            ],
        )

    def test_operation_registry_drives_action_schema(self) -> None:
        variants = SCHEMA["$defs"]["action"]["oneOf"]
        operations = variants[: len(OPERATIONS)]
        self.assertEqual(
            [variant["properties"]["action"]["const"] for variant in operations],
            list(OPERATIONS),
        )
        for variant in operations:
            operation = OPERATIONS[variant["properties"]["action"]["const"]]
            self.assertEqual(
                variant["properties"]["settings"], operation.settings_schema
            )
            scopes = variant["properties"]["scope"]["oneOf"]
            self.assertEqual(len(scopes), len(operation.supported_scopes))
            self.assertEqual(
                {option["const"] for option in scopes if "const" in option},
                operation.supported_scopes - {"result"},
            )

    def test_duplicate_operation_registration_is_rejected(self) -> None:
        class DuplicateOperation(AutomationOperation):
            name = AutomaticTranslationOperation.name

        with self.assertRaisesMessage(ValueError, "Duplicate automation operation"):
            register(DuplicateOperation)

    def test_invalid_operation_result_fails_without_storing_output(self) -> None:
        runner = Runner(WORKFLOW | {"actions": [AUTO]}, CONTEXT, Mock(), None)
        with patch.object(
            AutomaticTranslationOperation, "execute", return_value={"updated": "bad"}
        ):
            self.assertEqual(runner.run(), AddonActivityLogStatus.ERROR)
        self.assertEqual(runner.context["results"], {})
        self.assertEqual(runner.selections, {})
        self.assertEqual(runner.trace[-1]["status"], "error")
        self.assertIn("Invalid result", runner.trace[-1]["error"])

    @override_settings(BACKGROUND_TASKS="monthly")
    @patch("weblate.automation.addon.timezone.now")
    def test_monthly_schedule_covers_every_remainder(self, now: Mock) -> None:
        addon = Mock()
        for component_id in range(30, 60):
            scheduled_days = []
            for day in range(1, 32):
                now.return_value.day = day
                addon.queue.reset_mock()
                AutomationAddon.daily_component(addon, Mock(pk=component_id))
                if addon.queue.called:
                    scheduled_days.append(day)
            with self.subTest(component_id=component_id):
                self.assertEqual(scheduled_days, [component_id % 30 + 1])

    def test_normalized_size_limit(self) -> None:
        workflow = WORKFLOW | {"actions": [BULK | {"settings": {"q": "ž" * 3900}}] * 3}
        yaml = (
            "version: 1\ntriggers: []\nactions:\n"
            + (
                "  - action: weblate.bulk_edit\n    settings:\n      q: "
                + "ž" * 3900
                + "\n"
            )
            * 3
        )
        self.assertLess(len(yaml.encode()), 65536)
        for value in (yaml, json.dumps(workflow, ensure_ascii=False), workflow):
            with (
                self.subTest(value_type=type(value)),
                self.assertRaisesMessage(
                    ValidationError, "Automation definitions cannot exceed 64 KiB."
                ),
            ):
                parse_workflow(value)

    @patch("weblate.automation.runner.execute_operation")
    def test_runs_can_overlap_without_sharing_results(self, operation: Mock) -> None:
        barrier = Barrier(2, timeout=5)

        def execute(*args: object) -> dict[str, int]:
            barrier.wait()
            return {"updated": 1}

        operation.side_effect = execute
        runners = [
            Runner(WORKFLOW | {"actions": [AUTO]}, CONTEXT, Mock(), Mock())
            for _ in range(2)
        ]
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda runner: runner.run(), runners))
        self.assertEqual(outcomes, [AddonActivityLogStatus.SUCCESS] * 2)
        self.assertIsNot(runners[0].context["results"], runners[1].context["results"])

    @patch.object(UnitSelection, "count", return_value=10000)
    @patch("weblate.automation.runner.execute_operation")
    def test_large_selection_stays_out_of_result(
        self, operation: Mock, count: Mock
    ) -> None:
        def execute(
            action: dict[str, Any],
            component: object,
            user: object,
            selection: UnitSelection,
            affected: UnitSelection,
        ) -> dict[str, int]:
            if action["id"] == "first":
                affected.unit_ids = set(range(10000))
            return {"updated": len(affected.unit_ids or ())}

        operation.side_effect = execute
        workflow = WORKFLOW | {
            "actions": [AUTO, AUTO | {"id": "second", "scope": "result:first"}]
        }
        runner = Runner(workflow, CONTEXT, Mock(), Mock())
        self.assertEqual(runner.run(), AddonActivityLogStatus.SUCCESS)
        self.assertEqual(count.call_count, 1)
        self.assertEqual(runner.trace[1]["affected"], 10000)
        self.assertLess(len(json.dumps(runner.result())), 2000)

    def test_deferred_origin_and_worker_cleanup(self) -> None:
        from weblate.utils.celery import (  # ruff: ignore[import-outside-top-level]
            reset_automation_origin,
            restore_automation_origin,
            store_published_task_metadata,
        )

        headers: dict[str, object] = {}
        token = automation_origin.set(42)
        try:
            store_published_task_metadata(headers=headers, body=([], {}, {}))
        finally:
            automation_origin.reset(token)
        task = Mock()
        task.request.headers = headers
        restore_automation_origin(task=task)
        self.assertEqual(automation_origin.get(), 42)
        reset_automation_origin(task=task)
        self.assertIsNone(automation_origin.get())

    def test_yaml_and_json(self) -> None:
        self.assertEqual(
            parse_workflow("version: 1\ntriggers: []\nactions: []"), WORKFLOW
        )
        self.assertEqual(parse_workflow(WORKFLOW), WORKFLOW)

    def test_documented_event_names_and_legacy_aliases(self) -> None:
        for event in ActionEvents:
            with self.subTest(event=event), override("en"):
                canonical = get_change_action_identifier(event.label)
                for name in (canonical, event.name.lower()):
                    workflow = parse_workflow(
                        WORKFLOW
                        | {
                            "triggers": [{"trigger": "change", "events": [name]}],
                            "conditions": [
                                {"condition": "change_action", "value": name}
                            ],
                        }
                    )
                    self.assertEqual(workflow["triggers"][0]["events"], [canonical])
                    self.assertEqual(workflow["conditions"][0]["value"], canonical)
        with override("cs"):
            workflow = parse_workflow(
                WORKFLOW
                | {
                    "triggers": [{"trigger": "change", "events": ["change"]}],
                }
            )
        self.assertEqual(workflow["triggers"][0]["events"], ["translation_changed"])

    def test_event_errors_and_normalized_duplicates(self) -> None:
        with self.assertRaisesMessage(
            ValidationError, "workflow.triggers[0].events[0]"
        ):
            parse_workflow(
                WORKFLOW
                | {
                    "triggers": [{"trigger": "change", "events": ["unknown_event"]}],
                }
            )
        with self.assertRaises(ValidationError):
            parse_workflow(
                WORKFLOW
                | {
                    "triggers": [
                        {
                            "trigger": "change",
                            "events": ["change", "translation_changed"],
                        }
                    ],
                }
            )

    def test_yaml_editor_order_and_round_trip(self) -> None:
        # PostgreSQL JSON objects do not preserve the submitted key order.
        workflow = {
            "actions": [
                {
                    "action": "weblate.bulk_edit",
                    "settings": {
                        "q": 'source:"Žlutý: yes"',
                        "add_flags": "yes",
                    },
                }
            ],
            "conditions": [],
            "triggers": [{"trigger": "change", "events": ["change"]}],
            "version": 1,
        }
        field = WorkflowField()
        text = str(field.prepare_value(workflow))
        self.assertEqual(
            [
                line.split(":")[0]
                for line in text.splitlines()
                if line and not line[0].isspace()
            ],
            ["version", "triggers", "conditions", "actions"],
        )
        self.assertIn("Žlutý", text)
        self.assertEqual(parse_workflow(text), parse_workflow(workflow))
        self.assertIn("font-monospace", field.widget.attrs["class"])
        invalid = "version: [unfinished"
        self.assertEqual(field.prepare_value(invalid), invalid)

    def test_invalid(self) -> None:
        for value in (
            "version: 1\nversion: 1\ntriggers: []\nactions: []",
            "!!python/object:foo {}",
            "x: &x [*x]",
            WORKFLOW | {"mode": "queued"},
            WORKFLOW | {"version": 2},
            WORKFLOW | {"actions": [{"action": "python", "settings": {}}]},
            WORKFLOW | {"actions": [AUTO, AUTO]},
            WORKFLOW | {"actions": [BULK] * 101},
            WORKFLOW | {"triggers": [{"trigger": "change", "events": ["invalid"]}]},
        ):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                parse_workflow(value)

    def test_scope_validation(self) -> None:
        trigger = AUTO | {"scope": "trigger"}
        result = BULK | {"scope": "result:first"}
        self.assertEqual(
            parse_workflow(
                WORKFLOW
                | {
                    "triggers": [{"trigger": "change", "events": ["source_change"]}],
                    "actions": [trigger, result],
                }
            )["actions"],
            [trigger, result],
        )
        for workflow in (
            WORKFLOW | {"actions": [trigger]},
            WORKFLOW
            | {
                "triggers": [{"trigger": "daily"}],
                "actions": [trigger],
            },
            WORKFLOW | {"actions": [result, AUTO]},
            WORKFLOW | {"actions": [BULK | {"settings": {"state": STATE_FUZZY}}]},
        ):
            with self.subTest(workflow=workflow), self.assertRaises(ValidationError):
                parse_workflow(workflow)

    def test_cel(self) -> None:
        self.assertEqual(
            expressions(
                ['component.category == "frontend" && [1,2].all(x, x > 0)'], CONTEXT
            ),
            [True],
        )
        for source in (
            "1 + true",
            "1 + 2",
            "unknown.variable",
            '__import__("os")',
            "component.missing > 0",
        ):
            with self.subTest(source=source), self.assertRaises(ValidationError):
                expressions([source], CONTEXT)

    def test_cel_resource_limit(self) -> None:
        self.assertEqual(expressions(["true"], CONTEXT), [True])
        source = "0"
        items = str(list(range(32)))
        for index in range(6):
            source = f"{items}.map(x{index}, {source})"
        with self.assertRaises(ValidationError):
            expressions([f"size({source}) > 0"], CONTEXT)

    def test_cel_platform_limits(self) -> None:
        for platform in ("darwin", "linux"):
            with (
                self.subTest(platform=platform),
                patch.object(automation_cel.sys, "platform", platform),
                patch.object(automation_cel.resource, "setrlimit") as setrlimit,
                patch.object(
                    automation_cel, "evaluate_request", return_value={}
                ) as evaluate,
                patch.object(automation_cel.sys.stdout, "write"),
            ):
                automation_cel.main()
                expected = [
                    call(automation_cel.resource.RLIMIT_CPU, (2, 2)),
                    call(automation_cel.resource.RLIMIT_CORE, (0, 0)),
                ]
                if platform != "darwin":
                    expected.insert(
                        0,
                        call(
                            automation_cel.resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2
                        ),
                    )
                self.assertEqual(setrlimit.call_args_list, expected)
                evaluate.assert_called_once_with()

    def test_cel_limit_setup_failure(self) -> None:
        for platform, limit_count in (("darwin", 2), ("linux", 3)):
            for index in range(limit_count):
                with (
                    self.subTest(platform=platform, limit=index),
                    patch.object(automation_cel.sys, "platform", platform),
                    patch.object(
                        automation_cel.resource,
                        "setrlimit",
                        side_effect=[None] * index + [ValueError("Cannot set limit")],
                    ),
                    patch.object(automation_cel, "evaluate_request") as evaluate,
                    self.assertRaisesRegex(ValueError, "Cannot set limit"),
                ):
                    automation_cel.main()
                evaluate.assert_not_called()

    @override("en")
    def test_cel_subprocess_stderr(self) -> None:
        message = "CEL validation or evaluation failed or exceeded its resource limit."
        for stderr, detail in (
            (b"  Cannot set limit\n", "Cannot set limit"),
            (b"", ""),
            (None, ""),
            (b" \n", ""),
            (b"Invalid: \xff", "Invalid: \ufffd"),
            (b"x" * 5000, "x" * 4096),
            (b"<script>failure</script>", "<script>failure</script>"),
        ):
            error = subprocess.CalledProcessError(1, ["python"], stderr=stderr)
            with (
                self.subTest(stderr=stderr),
                patch(
                    "weblate.automation.expressions.subprocess.run",
                    side_effect=error,
                ),
                self.assertRaises(ValidationError) as caught,
            ):
                expressions(["true"], CONTEXT)
            self.assertEqual(
                caught.exception.messages,
                [f"{message}\n{detail}" if detail else message],
            )
            self.assertIs(caught.exception.__cause__, error)

    @patch("weblate.automation.runner.execute_operation")
    def test_sequence_and_choose(self, operation: Mock) -> None:
        operation.return_value = {"updated": 2}
        workflow = WORKFLOW | {
            "actions": [
                AUTO,
                {
                    "choose": [
                        {
                            "conditions": [
                                {
                                    "condition": "expression",
                                    "value": "results.first.updated == 2",
                                }
                            ],
                            "sequence": [BULK],
                        }
                    ],
                    "default": [AUTO | {"id": "fallback"}],
                },
            ]
        }
        runner = Runner(workflow, CONTEXT, Mock(), Mock())
        self.assertEqual(runner.run(), AddonActivityLogStatus.SUCCESS)
        self.assertEqual(
            [call.args[0]["action"] for call in operation.call_args_list],
            [AUTO["action"], BULK["action"]],
        )
        self.assertEqual(runner.trace[-1]["status"], "skipped")

    @patch(
        "weblate.automation.runner.execute_operation",
        side_effect=RuntimeError("failed"),
    )
    def test_failure_stops_actions(self, operation: Mock) -> None:
        runner = Runner(WORKFLOW | {"actions": [AUTO, BULK]}, CONTEXT, Mock(), Mock())
        self.assertEqual(runner.run(), AddonActivityLogStatus.ERROR)
        operation.assert_called_once()
        self.assertEqual(runner.trace[-1]["status"], "skipped")

    @patch("weblate.automation.runner.execute_operation")
    def test_preview_unknown_results(self, operation: Mock) -> None:
        workflow = WORKFLOW | {
            "actions": [
                AUTO,
                {
                    "choose": [
                        {
                            "conditions": [
                                {
                                    "condition": "expression",
                                    "value": "results.first.updated > 0",
                                }
                            ],
                            "sequence": [BULK],
                        }
                    ],
                    "default": [BULK],
                },
            ]
        }
        runner = Runner(workflow, CONTEXT, Mock(), None, preview=True)
        runner.run()
        operation.assert_not_called()
        self.assertIn("unknown", [step["status"] for step in runner.trace])
        self.assertEqual(
            sum(step["status"] == "conditional" for step in runner.trace), 2
        )

    @patch("weblate.automation.runner.execute_operation")
    def test_preview_scopes(self, operation: Mock) -> None:
        runner = Runner(
            WORKFLOW
            | {
                "actions": [
                    AUTO,
                    BULK | {"scope": "result:first"},
                ]
            },
            CONTEXT,
            Mock(),
            None,
            preview=True,
        )
        self.assertEqual(runner.run(), AddonActivityLogStatus.SUCCESS)
        self.assertEqual(runner.trace[-1]["status"], "conditional")
        operation.assert_not_called()
        runner = Runner(
            WORKFLOW | {"actions": [BULK | {"scope": "trigger"}]},
            CONTEXT,
            Mock(),
            None,
            preview=True,
        )
        self.assertEqual(runner.run(), AddonActivityLogStatus.ERROR)
        self.assertEqual(runner.trace[-1]["status"], "error")


class AutomationTest(ReusableComponentTestCase):
    @patch("weblate.automation.tasks.automation_run.delay_on_commit")
    def test_changes_identify_automation_and_execution(self, task: Mock) -> None:
        units = self.component.translation_set.get(language_code="cs").unit_set
        addons = [self.install(WORKFLOW | {"actions": [BULK]}) for _ in range(2)]
        client = APIClient()
        client.force_authenticate(self.user)
        self.user.is_superuser = True
        for addon in addons:
            with self.subTest(addon=addon.instance.pk):
                units.update(state=STATE_TRANSLATED)
                run_addon_manually(addon.instance.pk, user_id=self.user.pk)
                activity = AddonActivityLog.objects.get(addon=addon.instance)
                with change_origin_context({"scope": "api"}):
                    run_automation(activity.pk)
                    self.assertEqual(change_origin.get(), {"scope": "api"})
                activity.refresh_from_db()
                self.assertEqual(activity.status, AddonActivityLogStatus.SUCCESS)
                changes = list(
                    Change.objects.filter(details__automation_origin=activity.pk)
                )
                self.assertTrue(changes)
                expected = {
                    "scope": "automation",
                    "automation": {
                        "addon_id": addon.instance.pk,
                        "activity_id": activity.pk,
                    },
                }
                description = (
                    f"Created by automation #{addon.instance.pk} (run #{activity.pk})."
                )
                for change in changes:
                    self.assertEqual(change.details["change_origin"], expected)
                    self.assertEqual(change.get_origin_display(), "Automation")
                    self.assertEqual(change.get_origin_description(), description)
                change = changes[0]
                rendered = render_to_string(
                    "snippets/last-changes-content.html",
                    format_last_changes_content([change], self.user),
                )
                self.assertIn(description, rendered)
                response = client.get(
                    reverse("api:change-detail", kwargs={"pk": change.pk})
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["details"]["change_origin"], expected)
                activity.delete()
                addon.instance.delete()
                change.refresh_from_db()
                self.assertEqual(change.details["change_origin"], expected)
                self.assertEqual(change.get_origin_display(), "Automation")
                self.assertEqual(change.get_origin_description(), description)
        self.assertEqual(task.call_count, 2)
        self.assertIsNone(change_origin.get())
        self.assertIsNone(automation_origin.get())

    def test_select_component_and_chained_result_scopes(self) -> None:
        selected = self.component.translation_set.get(language_code="cs").unit_set.get(
            source="Hello, world!\n"
        )
        actions = [
            {
                "action": "weblate.select",
                "id": "first",
                "settings": {"q": f"id:{selected.pk}"},
            },
            {
                "action": "weblate.select",
                "id": "second",
                "scope": "result:first",
                "settings": {},
            },
            {
                "action": "weblate.select",
                "id": "third",
                "scope": "result:second",
                "settings": {"q": "language:de"},
            },
        ]
        workflow = validate_operations(
            parse_workflow(WORKFLOW | {"actions": actions}), self.component
        )
        before = list(
            Unit.objects.filter(translation__component=self.component)
            .order_by("pk")
            .values_list("pk", "state", "target")
        )
        changes = Change.objects.filter(component=self.component).count()
        runner = Runner(
            workflow,
            execution_context(self.component, "manual"),
            self.component,
            self.user,
        )
        self.assertEqual(runner.run(), AddonActivityLogStatus.SUCCESS, runner.trace)
        successes = [step for step in runner.trace if step["status"] == "success"]
        self.assertEqual(runner.selections["first"].unit_ids, {selected.pk})
        self.assertEqual(runner.selections["second"].unit_ids, {selected.pk})
        self.assertEqual(runner.selections["third"].unit_ids, set())
        self.assertEqual(
            [result["selected"] for result in runner.context["results"].values()],
            [1, 1, 0],
        )
        self.assertEqual(successes[1]["scope_units"], 1)
        self.assertEqual(successes[1]["affected"], 1)
        self.assertEqual(successes[2]["scope"], "result:second")
        self.assertEqual(successes[2]["affected"], 0)
        self.assertEqual(
            list(
                Unit.objects.filter(translation__component=self.component)
                .order_by("pk")
                .values_list("pk", "state", "target")
            ),
            before,
        )
        self.assertEqual(
            Change.objects.filter(component=self.component).count(), changes
        )
        self.assertNotIn("unit_ids", json.dumps(runner.context["results"]))
        self.assertNotIn("unit_ids", json.dumps(runner.trace))

    def test_select_trigger_preserves_source_expansion(self) -> None:
        source = self.component.source_translation.unit_set.get(
            source="Hello, world!\n"
        )
        change = Change.objects.create(
            unit=source, action=ActionEvents.SOURCE_CHANGE, user=self.user
        )
        actions = [
            {
                "action": "weblate.select",
                "id": "expanded",
                "scope": "trigger",
                "settings": {},
            },
            {
                "action": "weblate.select",
                "id": "german",
                "scope": "result:expanded",
                "settings": {"q": "language:de"},
            },
        ]
        workflow = validate_operations(
            parse_workflow(
                WORKFLOW
                | {
                    "triggers": [{"trigger": "change", "events": ["source_change"]}],
                    "actions": actions,
                }
            ),
            self.component,
        )
        runner = Runner(
            workflow,
            execution_context(self.component, "change", change),
            self.component,
            self.user,
        )
        self.assertEqual(runner.run(), AddonActivityLogStatus.SUCCESS, runner.trace)
        successes = [step for step in runner.trace if step["status"] == "success"]
        expanded = set(
            source.unit_set.exclude(pk=source.pk).values_list("pk", flat=True)
        )
        german = set(
            source.unit_set.filter(translation__language__code="de").values_list(
                "pk", flat=True
            )
        )
        self.assertEqual(
            set(
                runner.selections["expanded"]
                .queryset(self.component)
                .values_list("pk", flat=True)
            ),
            expanded,
        )
        self.assertEqual(runner.selections["german"].unit_ids, german)
        self.assertEqual(successes[0]["scope_units"], len(expanded))
        self.assertEqual(successes[0]["affected"], len(expanded))
        self.assertEqual(runner.context["results"]["german"]["selected"], len(german))

    def test_select_validation_and_empty_result(self) -> None:
        action = {"action": "weblate.select", "settings": {}}
        with self.assertRaises(ValidationError):
            parse_workflow(WORKFLOW | {"actions": [action]})
        for query in ("", "   ", "("):
            with self.subTest(query=query), self.assertRaises(ValidationError):
                SelectOperation.normalize({"q": query}, self.component)
        with self.assertRaises(ValidationError):
            SelectOperation.normalize({"q": "("}, self.component, scope="trigger")
        self.assertEqual(
            SelectOperation.normalize({}, self.component, scope="trigger"),
            {"q": ""},
        )
        self.assertEqual(
            SelectOperation.normalize({}, self.component, scope="result:first"),
            {"q": ""},
        )
        action |= {"id": "empty", "settings": {"q": "id:0"}}
        workflow = validate_operations(
            parse_workflow(WORKFLOW | {"actions": [action]}), self.component
        )
        runner = Runner(
            workflow,
            execution_context(self.component, "manual"),
            self.component,
            self.user,
        )
        self.assertEqual(runner.run(), AddonActivityLogStatus.SUCCESS, runner.trace)
        self.assertEqual(runner.context["results"]["empty"]["selected"], 0)
        self.assertEqual(runner.selections["empty"].unit_ids, set())

    def test_select_retains_matching_unit_snapshots(self) -> None:
        units = list(
            self.component.translation_set.get(language_code="cs").unit_set.order_by(
                "pk"
            )[:2]
        )
        selected, excluded = units
        snapshots = {
            unit.pk: EvaluatedUnitSnapshot(
                unit=EvaluationSnapshot("test", unit.last_updated),
                source_unit_id=unit.source_unit_id or unit.pk,
                source_unit=EvaluationSnapshot("source", unit.last_updated),
            )
            for unit in units
        }
        selection = UnitSelection({selected.pk, excluded.pk}, unit_snapshots=snapshots)
        affected = UnitSelection(set())
        result = SelectOperation.execute(
            self.component,
            {"q": f"id:{selected.pk}"},
            self.user,
            selection=selection,
            affected=affected,
        )
        self.assertEqual(result["selected"], 1)
        self.assertEqual(affected.unit_ids, {selected.pk})
        self.assertEqual(affected.unit_snapshots, {selected.pk: snapshots[selected.pk]})

    def test_select_preview_counts_and_chains(self) -> None:
        selected = self.component.translation_set.get(language_code="cs").unit_set.get(
            source="Hello, world!\n"
        )
        actions = [
            {
                "action": "weblate.select",
                "id": "first",
                "settings": {"q": f"id:{selected.pk}"},
            },
            {
                "action": "weblate.select",
                "id": "second",
                "scope": "result:first",
                "settings": {},
            },
        ]
        workflow = validate_operations(
            parse_workflow(WORKFLOW | {"actions": actions}), self.component
        )
        runner = Runner(
            workflow,
            execution_context(self.component, "manual"),
            self.component,
            self.user,
            preview=True,
        )
        self.assertEqual(runner.run(), AddonActivityLogStatus.SUCCESS, runner.trace)
        self.assertEqual([step["status"] for step in runner.trace], ["success"] * 2)
        self.assertEqual(runner.context["results"]["second"]["selected"], 1)
        self.assertEqual(runner.trace[1]["affected"], 1)
        self.assertFalse(runner.planned)

    def test_unnamed_select_counts_without_materializing(self) -> None:
        workflow = validate_operations(
            parse_workflow(
                WORKFLOW
                | {
                    "actions": [
                        {
                            "action": "weblate.select",
                            "settings": {"q": "language:cs"},
                        }
                    ]
                }
            ),
            self.component,
        )
        expected = Unit.objects.filter(
            translation__component=self.component, translation__language_code="cs"
        ).count()
        for preview in (False, True):
            with (
                self.subTest(preview=preview),
                patch(
                    "weblate.trans.models.unit.UnitQuerySet.iterator",
                    side_effect=AssertionError("Unit IDs were materialized"),
                ),
            ):
                runner = Runner(
                    workflow,
                    execution_context(self.component, "manual"),
                    self.component,
                    self.user,
                    preview=preview,
                )
                self.assertEqual(
                    runner.run(), AddonActivityLogStatus.SUCCESS, runner.trace
                )
                self.assertEqual(runner.selections, {})
                self.assertEqual(runner.context["results"], {})
                success = [step for step in runner.trace if step["status"] == "success"]
                self.assertEqual(success[0]["output"]["selected"], expected)
                self.assertEqual(success[0]["affected"], expected)

    def test_select_preview_known_result_scope_is_planned(self) -> None:
        selected = self.component.translation_set.get(language_code="cs").unit_set.get(
            source="Hello, world!\n"
        )
        actions = [
            {
                "action": "weblate.select",
                "id": "picked",
                "settings": {"q": f"id:{selected.pk}"},
            },
            BULK | {"scope": "result:picked", "settings": {"state": STATE_FUZZY}},
        ]
        workflow = validate_operations(
            parse_workflow(WORKFLOW | {"actions": actions}), self.component
        )
        runner = Runner(
            workflow,
            execution_context(self.component, "manual"),
            self.component,
            self.user,
            preview=True,
        )
        self.assertEqual(runner.run(), AddonActivityLogStatus.SUCCESS, runner.trace)
        self.assertEqual(
            [step["status"] for step in runner.trace], ["success", "planned"]
        )

    def test_select_result_limits_following_bulk_edit(self) -> None:
        units = self.component.translation_set.get(language_code="cs").unit_set
        selected = units.get(source="Hello, world!\n")
        units.update(state=STATE_TRANSLATED)
        actions = [
            {
                "action": "weblate.select",
                "id": "selected",
                "settings": {"q": f"id:{selected.pk}"},
            },
            {
                "action": "weblate.bulk_edit",
                "scope": "result:selected",
                "settings": {"state": STATE_FUZZY},
            },
        ]
        workflow = validate_operations(
            parse_workflow(WORKFLOW | {"actions": actions}), self.component
        )
        runner = Runner(
            workflow,
            execution_context(self.component, "manual"),
            self.component,
            self.user,
        )
        self.assertEqual(runner.run(), AddonActivityLogStatus.SUCCESS, runner.trace)
        self.assertEqual(units.get(pk=selected.pk).state, STATE_FUZZY)
        self.assertFalse(
            units.exclude(pk=selected.pk).exclude(state=STATE_TRANSLATED).exists()
        )
        self.assertEqual(runner.context["results"]["selected"]["selected"], 1)
        self.assertEqual(runner.trace[-1]["scope_units"], 1)

    def test_select_preview_after_planned_write_is_conditional(self) -> None:
        selected = self.component.translation_set.get(language_code="cs").unit_set.get(
            source="Hello, world!\n"
        )
        actions = [
            BULK,
            {
                "action": "weblate.select",
                "id": "selected",
                "settings": {"q": f"id:{selected.pk} AND state:translated"},
            },
        ]
        workflow = validate_operations(
            parse_workflow(WORKFLOW | {"actions": actions}), self.component
        )
        runner = Runner(
            workflow,
            execution_context(self.component, "manual"),
            self.component,
            self.user,
            preview=True,
        )
        self.assertEqual(runner.run(), AddonActivityLogStatus.SUCCESS, runner.trace)
        self.assertEqual(runner.trace[-1]["status"], "conditional")
        self.assertNotIn("selected", runner.context["results"])

    def test_select_preview_condition_uses_known_result_after_planned_write(
        self,
    ) -> None:
        selected = self.component.translation_set.get(language_code="cs").unit_set.get(
            source="Hello, world!\n"
        )
        for result_id in ("second", "results"):
            with self.subTest(result_id=result_id):
                actions = [
                    {
                        "action": "weblate.select",
                        "id": "first",
                        "settings": {"q": f"id:{selected.pk}"},
                    },
                    BULK,
                    {
                        "action": "weblate.select",
                        "id": result_id,
                        "scope": "result:first",
                        "settings": {},
                    },
                    {
                        "choose": [
                            {
                                "conditions": [
                                    {
                                        "condition": "expression",
                                        "value": f"results.{result_id}.selected > 0",
                                    }
                                ],
                                "sequence": [BULK | {"scope": f"result:{result_id}"}],
                            }
                        ]
                    },
                ]
                workflow = validate_operations(
                    parse_workflow(WORKFLOW | {"actions": actions}), self.component
                )
                runner = Runner(
                    workflow,
                    execution_context(self.component, "manual"),
                    self.component,
                    self.user,
                    preview=True,
                )
                self.assertEqual(
                    runner.run(), AddonActivityLogStatus.SUCCESS, runner.trace
                )
                self.assertEqual(runner.context["results"][result_id]["selected"], 1)
                self.assertIn(
                    {
                        "path": "actions[3].choose[0].conditions[0]",
                        "status": "evaluated",
                        "value": True,
                    },
                    runner.trace,
                )
                self.assertEqual(runner.trace[-1]["status"], "planned")

    @patch("weblate.automation.tasks.automation_run.delay_on_commit")
    def test_select_activity_log_stores_counts_only(self, task: Mock) -> None:
        selected = self.component.translation_set.get(language_code="cs").unit_set.get(
            source="Hello, world!\n"
        )
        addon = self.install(
            WORKFLOW
            | {
                "actions": [
                    {
                        "action": "weblate.select",
                        "id": "picked",
                        "settings": {"q": f"id:{selected.pk}"},
                    }
                ]
            }
        )
        run_addon_manually(addon.instance.pk)
        activity = AddonActivityLog.objects.get(addon=addon.instance)
        task.assert_called_once_with(activity.pk)
        run_automation(activity.pk)
        activity.refresh_from_db()
        self.assertEqual(activity.status, AddonActivityLogStatus.SUCCESS)
        result = activity.details["result"]
        self.assertEqual(
            result["context"]["results"]["picked"],
            {"component": self.component.pk, "selected": 1},
        )
        trace = [step for step in result["trace"] if step["status"] == "success"]
        self.assertEqual(trace[0]["scope"], "component")
        self.assertEqual(trace[0]["affected"], 1)
        self.assertNotIn("unit_ids", json.dumps(trace))

    def test_suggestion_result_tracks_created_unit(self) -> None:
        translation = self.component.translation_set.get(language_code="cs")
        unit = translation.unit_set.all()[0]
        auto = AutoTranslate(
            translation=translation,
            user=None,
            q="",
            mode="suggest",
            component_wide=True,
            enforce_permissions=False,
        )
        auto.update(unit, STATE_TRANSLATED, ["Proposed translation"])
        auto.update(unit, STATE_TRANSLATED, ["Proposed translation"])
        self.assertEqual(auto.updated, 1)
        self.assertEqual(auto.affected_unit_ids, {unit.pk})
        self.assertEqual(auto.affected_source_unit_ids, {unit.source_unit_id})

    def test_trigger_scope_expands_source_change(self) -> None:
        source = self.component.source_translation.unit_set.all()[0]
        change = Change.objects.create(
            unit=source, action=ActionEvents.SOURCE_CHANGE, user=self.user
        )
        runner = Runner(
            WORKFLOW,
            execution_context(self.component, "change", change),
            self.component,
            self.user,
        )
        selected = runner.selection("trigger").queryset(self.component)
        self.assertEqual(
            set(selected.values_list("pk", flat=True)),
            set(source.unit_set.exclude(pk=source.pk).values_list("pk", flat=True)),
        )
        source.unit_set.exclude(pk=source.pk).update(state=STATE_TRANSLATED)
        scoped_workflow = validate_operations(
            parse_workflow(
                WORKFLOW
                | {
                    "triggers": [{"trigger": "change", "events": ["source_change"]}],
                    "actions": [
                        BULK
                        | {
                            "scope": "trigger",
                            "settings": {"q": "language:cs", "state": STATE_FUZZY},
                        }
                    ],
                }
            ),
            self.component,
        )
        runner = Runner(
            scoped_workflow,
            execution_context(self.component, "change", change),
            self.component,
            self.user,
        )
        self.assertEqual(runner.run(), AddonActivityLogStatus.SUCCESS, runner.trace)
        self.assertEqual(
            source.unit_set.filter(translation__language__code="cs").get().state,
            STATE_FUZZY,
        )
        self.assertTrue(
            source.unit_set.exclude(pk=source.pk)
            .exclude(translation__language__code="cs")
            .filter(state=STATE_TRANSLATED)
            .exists()
        )
        target = source.unit_set.exclude(pk=source.pk)[0]
        target_change = Change.objects.create(
            unit=target, action=ActionEvents.CHANGE, user=self.user
        )
        runner = Runner(
            WORKFLOW,
            execution_context(self.component, "change", target_change),
            self.component,
            self.user,
        )
        self.assertEqual(
            list(runner.selection("trigger").queryset(self.component)), [target]
        )

    def test_result_scope_tracks_only_changed_units(self) -> None:
        units = self.component.translation_set.get(language_code="cs").unit_set
        units.update(state=STATE_TRANSLATED)
        first = units.all()[0]
        actions = [
            {
                "action": "weblate.bulk_edit",
                "id": "first",
                "settings": {"q": f"id:{first.pk}", "state": STATE_FUZZY},
            },
            {
                "action": "weblate.bulk_edit",
                "scope": "result:first",
                "settings": {"state": STATE_TRANSLATED},
            },
        ]
        workflow = validate_operations(
            parse_workflow(WORKFLOW | {"actions": actions}), self.component
        )
        runner = Runner(
            workflow,
            execution_context(self.component, "manual"),
            self.component,
            self.user,
        )
        self.assertEqual(runner.run(), AddonActivityLogStatus.SUCCESS, runner.trace)
        self.assertEqual(runner.selections["first"].unit_ids, {first.pk})
        self.assertEqual(runner.context["results"]["first"]["updated"], 1)
        self.assertEqual(runner.trace[-1]["scope_units"], 1)
        self.assertNotIn("unit_ids", json.dumps(runner.result()["context"]["results"]))

    def test_missing_runtime_scopes_fail(self) -> None:
        for scope in ("trigger", "result:first"):
            runner = Runner(
                WORKFLOW | {"actions": [BULK | {"scope": scope}]},
                CONTEXT,
                self.component,
                self.user,
            )
            with self.subTest(scope=scope):
                self.assertEqual(runner.run(), AddonActivityLogStatus.ERROR)
                self.assertEqual(runner.trace[-1]["status"], "error")

    def test_batch_preserves_failure_after_successful_translation(self) -> None:
        auto = BatchAutoTranslate(
            self.component,
            user=None,
            q="state:<translated",
            mode="translate",
            enforce_permissions=False,
        )
        auto.translations = [self.get_translation()] * 2
        with patch(
            "weblate.trans.autotranslate.AutoTranslate.process_mt",
            side_effect=[MachineTranslationError("Service unavailable"), None],
        ) as process:
            message = auto.perform(
                auto_source="mt", engines=[], threshold=80, source_component_ids=None
            )
        self.assertEqual(process.call_count, 2)
        self.assertEqual(message, "Automatic translation failed: Service unavailable")
        self.assertEqual(auto.failure_message, message)
        with patch("weblate.trans.autotranslate.AutoTranslate.process_mt"):
            message = auto.perform(
                auto_source="mt", engines=[], threshold=80, source_component_ids=None
            )
        self.assertIsNone(auto.failure_message)
        self.assertIn("completed", message)

    @patch("weblate.automation.tasks.automation_run.delay_on_commit")
    @patch("weblate.trans.automation.bulk_edit")
    @patch(
        "weblate.trans.autotranslate.AutoTranslate.process_others",
        side_effect=MachineTranslationError("Service unavailable"),
    )
    def test_translation_failure_stops_workflow(
        self, translate: Mock, bulk: Mock, task: Mock
    ) -> None:
        addon = self.install(WORKFLOW | {"actions": [AUTO, BULK]})
        run_addon_manually(addon.instance.pk)
        activity = AddonActivityLog.objects.get(addon=addon.instance)
        task.assert_called_once_with(activity.pk)
        run_automation(activity.pk)
        activity.refresh_from_db()
        self.assertTrue(translate.called)
        bulk.assert_not_called()
        self.assertEqual(activity.status, AddonActivityLogStatus.ERROR)
        result = activity.details["result"]
        self.assertEqual(result["context"]["results"], {})
        self.assertEqual(result["trace"][-1]["status"], "skipped")
        self.assertIn("Service unavailable", result["trace"][-2]["error"])

    def test_real_translation_passes_only_process_remaining_strings(self) -> None:
        fallback = self.create_po(
            name="Fallback",
            slug="fallback",
            project=self.project,
            allow_translation_propagation=False,
        )
        target = self.create_po(
            name="Target",
            slug="target",
            project=self.project,
            allow_translation_propagation=False,
        )
        first_translation = self.component.translation_set.get(language_code="cs")
        fallback_translation = fallback.translation_set.get(language_code="cs")
        target_translation = target.translation_set.get(language_code="cs")
        first_translation.unit_set.update(state=STATE_EMPTY, target="")
        target_translation.unit_set.update(state=STATE_EMPTY, target="")
        first = first_translation.unit_set.get(source="Hello, world!\n")
        first_translation.unit_set.filter(pk=first.pk).update(
            target="First pass\n", state=STATE_TRANSLATED
        )
        fallback_translation.unit_set.update(
            target="Fallback\n", state=STATE_TRANSLATED
        )
        actions = [
            {
                "action": AUTO["action"],
                "id": "first",
                "settings": {
                    "component": self.component.pk,
                    "mode": "translate",
                    "q": "state:empty AND language:cs",
                },
            },
            {
                "action": AUTO["action"],
                "id": "second",
                "settings": {
                    "component": fallback.pk,
                    "mode": "translate",
                    "q": "state:empty AND language:cs",
                },
            },
            {
                "action": "weblate.bulk_edit",
                "scope": "result:first",
                "settings": {"state": STATE_FUZZY},
            },
        ]
        addon = self.install(WORKFLOW | {"actions": actions}, component=target)
        workflow = validate_operations(
            parse_workflow(addon.instance.configuration["workflow"]), target
        )
        runner = Runner(
            workflow, execution_context(target, "manual"), target, addon.user
        )
        self.assertEqual(runner.run(), AddonActivityLogStatus.SUCCESS, runner.trace)
        self.assertEqual(
            target_translation.unit_set.get(source=first.source).target, "First pass\n"
        )
        self.assertEqual(runner.context["results"]["first"]["updated"], 1)
        self.assertGreater(runner.context["results"]["second"]["updated"], 0)
        self.assertEqual(
            runner.selections["first"].unit_ids,
            {target_translation.unit_set.get(source=first.source).pk},
        )
        self.assertEqual(
            target_translation.unit_set.get(source=first.source).state, STATE_FUZZY
        )

    def test_invalid_configuration_and_preview_ui(self) -> None:
        addon = self.install()
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        page_response = self.client.post(
            addon.instance.get_absolute_url(),
            {
                "run": "1",
                "execution-preview": "on",
                "workflow": "invalid unsaved edits",
            },
        )
        self.assertContains(page_response, "Automation preview")
        self.assertFalse(AddonActivityLog.objects.filter(addon=addon.instance).exists())
        client = APIClient()
        client.force_authenticate(self.user)
        url = reverse("api:addon-detail", kwargs={"pk": addon.instance.pk})
        response = client.patch(
            url,
            {"configuration": {"workflow": WORKFLOW | {"actions": [AUTO]}}},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            response.data["configuration"]["workflow"]["actions"][0]["settings"][
                "threshold"
            ],
            80,
        )
        response = client.patch(
            url,
            {"configuration": {"workflow": WORKFLOW | {"mode": "parallel"}}},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_repository_dispatch_is_deferred(self) -> None:
        addon = self.install(WORKFLOW | {"triggers": [{"trigger": "post_push"}]})
        with patch("weblate.automation.tasks.automation_run.delay") as delay:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                handle_addon_event(
                    AddonEvent.EVENT_POST_PUSH,
                    "post_push",
                    (self.component,),
                    component=self.component,
                )
                delay.assert_not_called()
            self.assertTrue(callbacks)
            for callback in callbacks:
                callback()
            activity = AddonActivityLog.objects.get(addon=addon.instance)
            delay.assert_called_once_with(activity.pk)

        self.assertEqual(
            activity.details["result"]["context"]["trigger"]["name"], "post_push"
        )

    @patch("weblate.automation.tasks.automation_run.delay_on_commit")
    def test_skipped_conditions_are_visible_in_log(self, task: Mock) -> None:
        addon = self.install(
            WORKFLOW
            | {
                "conditions": [{"condition": "language", "value": "cs"}],
                "actions": [AUTO],
            }
        )
        run_addon_manually(addon.instance.pk)
        activity = AddonActivityLog.objects.get(addon=addon.instance)
        run_automation(activity.pk)
        activity.refresh_from_db()
        self.assertEqual(activity.status, AddonActivityLogStatus.SKIPPED)
        self.assertIn("evaluated", activity.get_details_display())
        self.assertEqual(activity.details["result"]["trace"][-1]["status"], "skipped")

    def install(
        self, workflow: dict | None = None, **scope: Unpack[AutomationScope]
    ) -> AutomationAddon:
        return AutomationAddon.create(
            configuration={"workflow": deepcopy(workflow or WORKFLOW)},
            run=False,
            **(scope or {"component": self.component}),
        )

    def test_change_history_redacts_workflow_and_links_current_addon(self) -> None:
        addon = self.install(WORKFLOW | {"actions": [AUTO]})
        addon_id = addon.instance.pk
        created = self.component.change_set.get(
            action=ActionEvents.ADDON_CREATE, target=AutomationAddon.name
        )
        self.assertEqual(created.addon_id, addon_id)
        self.assertEqual(created.details["configuration"], {"workflow": None})
        self.assertEqual(created.details["redacted_fields"], ["workflow"])

        addon.configure({"workflow": WORKFLOW | {"actions": [BULK]}})
        changed = self.component.change_set.get(
            action=ActionEvents.ADDON_CHANGE, target=AutomationAddon.name
        )
        self.assertEqual(changed.addon_id, addon_id)
        self.assertEqual(changed.details["configuration"], {"workflow": None})
        self.assertEqual(changed.details["changed_fields"], ["workflow"])
        self.assertEqual(changed.details["redacted_fields"], ["workflow"])

        addon.instance.delete()

        changes = self.component.change_set.filter(target=AutomationAddon.name)
        self.assertEqual(changes.count(), 3)
        self.assertFalse(changes.exclude(addon=None).exists())
        removed = changes.get(action=ActionEvents.ADDON_REMOVE)
        self.assertEqual(removed.details["configuration"], {"workflow": None})
        self.assertEqual(removed.details["redacted_fields"], ["workflow"])

    def test_subscription_update_and_no_install_run(self) -> None:
        addon = self.install(
            WORKFLOW | {"triggers": [{"trigger": "post_update"}, {"trigger": "daily"}]}
        )
        self.assertEqual(
            addon.configured_events,
            {
                AddonEvent.EVENT_MANUAL,
                AddonEvent.EVENT_POST_UPDATE,
                AddonEvent.EVENT_DAILY,
            },
        )
        with patch("weblate.automation.tasks.automation_run.delay_on_commit") as task:
            addon.configure(
                {"workflow": WORKFLOW | {"triggers": [{"trigger": "post_commit"}]}}
            )
            task.assert_not_called()
        self.assertEqual(
            set(addon.instance.event_set.values_list("event", flat=True)),
            {AddonEvent.EVENT_MANUAL, AddonEvent.EVENT_POST_COMMIT},
        )

    def test_operation_validation(self) -> None:
        workflow = validate_operations(
            parse_workflow(WORKFLOW | {"actions": [AUTO]}), self.component
        )
        self.assertEqual(workflow["actions"][0]["settings"]["threshold"], 80)
        invalid = deepcopy(BULK)
        invalid["settings"]["state"] = 987654
        with self.assertRaises(ValidationError):
            validate_operations(WORKFLOW | {"actions": [invalid]}, self.component)

    def test_automatic_translation_accepts_restricted_source(self) -> None:
        source = self.create_link_existing(
            name="Restricted automation source",
            slug="restricted-automation-source",
            allow_translation_propagation=False,
        )
        source.restricted = True
        source.save(update_fields=["restricted"])

        workflow = validate_operations(
            parse_workflow(
                WORKFLOW | {"actions": [AUTO | {"settings": {"component": source.pk}}]}
            ),
            self.component,
        )

        self.assertEqual(workflow["actions"][0]["settings"]["component"], source.pk)

    def test_restricted_source_is_redacted_from_changes_api(self) -> None:
        source = self.create_link_existing(
            name="Restricted audit source",
            slug="restricted-audit-source",
            allow_translation_propagation=False,
        )
        source.restricted = True
        source.save(update_fields=["restricted"])
        self.assertFalse(self.user.can_access_component(source))
        workflow = validate_operations(
            parse_workflow(
                WORKFLOW | {"actions": [AUTO | {"settings": {"component": source.pk}}]}
            ),
            self.component,
        )
        self.install(workflow)
        change = self.component.change_set.get(
            action=ActionEvents.ADDON_CREATE, target=AutomationAddon.name
        )

        client = APIClient()
        client.force_authenticate(self.user)
        urls = (
            reverse("api:change-list"),
            reverse("api:project-changes", kwargs={"slug": self.project.slug}),
        )
        for url in urls:
            with self.subTest(url=url):
                response = client.get(url)
                self.assertEqual(response.status_code, 200, response.data)
                serialized = next(
                    item for item in response.data["results"] if item["id"] == change.pk
                )
                self.assertIsNone(serialized["addon"])
                self.assertEqual(
                    serialized["details"]["configuration"], {"workflow": None}
                )
                self.assertEqual(serialized["details"]["redacted_fields"], ["workflow"])

        restricted_url = reverse(
            "api:component-detail",
            kwargs={"project__slug": self.project.slug, "slug": source.slug},
        )
        self.assertEqual(client.get(restricted_url).status_code, 404)

    def test_default_expanded_size_limit_in_form(self) -> None:
        addon = self.install()
        workflow = WORKFLOW | {"actions": [BULK | {"settings": {"q": "a" * 3900}}] * 16}
        parse_workflow(workflow)
        form = AutomationForm(self.user, addon, data={"workflow": json.dumps(workflow)})
        self.assertFalse(form.is_valid())
        self.assertIn(
            "Automation definitions cannot exceed 64 KiB.", form.errors["workflow"]
        )

    def test_normalized_workflow_round_trip(self) -> None:
        addon = self.install()
        workflow = WORKFLOW | {"actions": [BULK | {"settings": {"q": "ž" * 3900}}] * 2}
        form = AutomationForm(
            self.user,
            addon,
            data={"workflow": json.dumps(workflow, ensure_ascii=False)},
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.serialize_form()["workflow"]
        self.assertEqual(parse_workflow(saved), saved)

    @patch("weblate.automation.tasks.automation_run.delay_on_commit")
    def test_manual_snapshot_and_duplicate_delivery(self, task: Mock) -> None:
        addon = self.install()
        run_addon_manually(addon.instance.pk, user_id=self.user.pk)
        activity = AddonActivityLog.objects.get(addon=addon.instance)
        self.assertEqual(
            activity.details["result"]["context"]["actor"]["id"], self.user.pk
        )
        task.assert_called_once_with(activity.pk)
        addon.configure({"workflow": WORKFLOW | {"actions": [AUTO]}})
        with patch("weblate.automation.runner.execute_operation") as operation:
            run_automation(activity.pk)
            run_automation(activity.pk)
            operation.assert_not_called()
        activity.refresh_from_db()
        self.assertEqual(activity.status, AddonActivityLogStatus.SUCCESS)

    def test_change_context_and_recursion(self) -> None:
        addon = self.install(
            WORKFLOW
            | {"triggers": [{"trigger": "change", "events": ["source_change"]}]}
        )
        unit = self.component.source_translation.unit_set.first()
        change = Change.objects.create(
            unit=unit, action=ActionEvents.SOURCE_CHANGE, user=self.user
        )
        self.assertTrue(addon.check_change_action(change))
        context = execution_context(self.component, "change", change)
        self.assertEqual(context["trigger"]["unit_ids"], [unit.pk])
        token = automation_origin.set(123)
        try:
            changes = Change.objects.bulk_create(
                [Change(unit=unit, action=ActionEvents.SOURCE_CHANGE)]
            )
        finally:
            automation_origin.reset(token)
        changes[0].refresh_from_db()
        self.assertFalse(addon.check_change_action(changes[0]))

    @patch("weblate.automation.tasks.automation_run.delay_on_commit")
    def test_inherited_manual_runs(self, task: Mock) -> None:
        category = self.create_category(self.project)
        self.component.category = category
        self.component.save()
        scopes: list[AutomationScope] = [
            {"project": self.project},
            {"category": category},
            {"component": None},
        ]
        for scope in scopes:
            with self.subTest(scope=scope):
                addon = self.install(**scope)
                with self.assertRaises(ValidationError):
                    addon.instance.schedule_manual_run()
                run_addon_manually(addon.instance.pk)
                self.assertFalse(
                    AddonActivityLog.objects.filter(addon=addon.instance).exists()
                )
                addon.schedule_run(self.component.pk)
                self.assertTrue(
                    AddonActivityLog.objects.filter(
                        addon=addon.instance, component=self.component
                    ).exists()
                )

    def test_bulk_operation_is_real_and_preview_does_not_write(self) -> None:
        addon = self.install(WORKFLOW | {"actions": [BULK]})
        units = self.component.translation_set.get(language_code="cs").unit_set
        units.update(state=STATE_TRANSLATED)
        before = list(units.values_list("state", flat=True))
        addon.preview(addon.instance.configuration["workflow"], self.component.pk)
        self.assertEqual(list(units.values_list("state", flat=True)), before)
        runner = Runner(
            validate_operations(
                deepcopy(addon.instance.configuration["workflow"]), self.component
            ),
            execution_context(self.component, "manual"),
            self.component,
            addon.user,
        )
        self.assertEqual(runner.run(), AddonActivityLogStatus.SUCCESS)
        self.assertFalse(units.filter(state=STATE_TRANSLATED).exists())

    @patch("weblate.automation.tasks.automation_run.delay_on_commit")
    def test_execution_form_preview_default_and_real_run(self, task: Mock) -> None:
        addon = self.install()
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        url = addon.instance.get_absolute_url()
        page = self.client.get(url)
        self.assertTrue(page.context["execution_form"]["preview"].value())
        self.assertNotIn("preview_change", page.context["form"].fields)
        page = self.client.post(url, {"run": "1", "execution-preview": "on"})
        self.assertContains(page, "Automation preview")
        task.assert_not_called()
        self.assertFalse(AddonActivityLog.objects.filter(addon=addon.instance).exists())
        response = self.client.post(url, {"run": "1"})
        self.assertRedirects(response, url)
        activity = AddonActivityLog.objects.get(addon=addon.instance)
        task.assert_called_once_with(activity.pk)
        self.assertEqual(activity.details["requested_by"]["id"], self.user.pk)
        page = self.client.get(url)
        self.assertTrue(page.context["execution_form"]["preview"].value())

    @patch("weblate.automation.tasks.automation_run.delay_on_commit")
    def test_change_context_activity_log_displays_requester(self, task: Mock) -> None:
        addon = self.install(
            WORKFLOW
            | {"triggers": [{"trigger": "change", "events": ["translation_changed"]}]}
        )
        author = create_another_user()
        unit = self.component.translation_set.get(language_code="cs").unit_set.get(
            source="Hello, world!\n"
        )
        change = Change.objects.create(
            unit=unit, action=ActionEvents.CHANGE, user=author
        )
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        addon.instance.schedule_manual_run(
            user_id=self.user.pk, component_id=self.component.pk, change_id=change.pk
        )
        activity = AddonActivityLog.objects.get(addon=addon.instance)
        task.assert_called_once_with(activity.pk)
        for status in (AddonActivityLogStatus.PENDING, AddonActivityLogStatus.SUCCESS):
            with self.subTest(status=status):
                if status == AddonActivityLogStatus.SUCCESS:
                    run_automation(activity.pk)
                activity.refresh_from_db()
                self.assertEqual(activity.status, status)
                details = deepcopy(activity.details)
                response = self.client.get(
                    reverse("addon-logs", kwargs={"pk": addon.instance.pk})
                )
                self.assertEqual(response.status_code, 200)
                rendered = html.fromstring(response.content).xpath("//td/pre")
                self.assertEqual(len(rendered), 1)
                result = json.loads(rendered[0].text_content())
                self.assertEqual(
                    result.pop("requested_by"),
                    {"id": self.user.pk, "username": self.user.username},
                )
                self.assertEqual(
                    result["context"]["actor"],
                    {"id": author.pk, "username": author.username},
                )
                self.assertEqual(result, details["result"])
                self.assertEqual(activity.details, details)

    @patch("weblate.automation.tasks.automation_run.delay_on_commit")
    def test_change_execution_context_and_validation(self, task: Mock) -> None:
        addon = self.install(
            WORKFLOW
            | {
                "triggers": [{"trigger": "change", "events": ["translation_changed"]}],
                "actions": [BULK | {"scope": "trigger"}],
            }
        )
        unit = self.component.translation_set.get(language_code="cs").unit_set.get(
            source="Hello, world!\n"
        )
        change = Change.objects.create(
            unit=unit, action=ActionEvents.CHANGE, user=self.user
        )
        other = Change.objects.create(
            unit=unit, action=ActionEvents.COMMENT, user=self.user
        )
        unitless = Change.objects.create(
            component=self.component, action=ActionEvents.CHANGE
        )
        for change_id in (None, other.pk, unitless.pk, 999999):
            with self.subTest(change_id=change_id):
                with self.assertRaises(ValidationError):
                    addon.preview(
                        addon.instance.configuration["workflow"],
                        self.component.pk,
                        change_id,
                    )
                with self.assertRaises(ValidationError):
                    addon.schedule_run(self.component.pk, change_id, self.user)
        task.assert_not_called()
        preview = addon.preview(
            addon.instance.configuration["workflow"],
            self.component.pk,
            change.pk,
            self.user,
        )
        addon.schedule_run(self.component.pk, change.pk, self.user)
        activity = AddonActivityLog.objects.get(addon=addon.instance)
        self.assertEqual(preview["context"], activity.details["result"]["context"])
        self.assertEqual(activity.event, AddonEvent.EVENT_MANUAL)
        self.assertEqual(
            activity.details["result"]["context"]["trigger"]["unit_ids"], [unit.pk]
        )
        # Saving new settings after submission must not change the queued workflow.
        addon.configure({"workflow": WORKFLOW})
        activity.refresh_from_db()
        self.assertEqual(
            activity.details["result"]["workflow"]["actions"][0]["scope"], "trigger"
        )

    def test_execution_form_validation_preserves_checkbox(self) -> None:
        addon = self.install(
            WORKFLOW | {"triggers": [{"trigger": "change", "events": ["change"]}]}
        )
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        for checked in (False, True):
            data = {"run": "1"}
            if checked:
                data["execution-preview"] = "on"
            response = self.client.post(addon.instance.get_absolute_url(), data)
            self.assertContains(response, "Select a change for this automation.")
            self.assertEqual(
                bool(response.context["execution_form"]["preview"].value()), checked
            )
        self.assertFalse(AddonActivityLog.objects.filter(addon=addon.instance).exists())

    @patch("weblate.automation.tasks.automation_run.delay_on_commit")
    def test_inherited_execution_requires_target_and_validates_change_scope(
        self, task: Mock
    ) -> None:
        addon = self.install(project=self.project)
        with self.assertRaises(ValidationError):
            addon.preview(WORKFLOW, None)
        with self.assertRaises(ValidationError):
            addon.schedule_run()
        # A different existing component is outside a component installation.
        other = self.create_po_new_base(
            name="Other", slug="other", project=self.project
        )
        component_addon = self.install(
            WORKFLOW
            | {
                "triggers": [{"trigger": "change", "events": ["change"]}],
            }
        )
        foreign = Change.objects.create(component=other, action=ActionEvents.CHANGE)
        for component_id, change_id in (
            (other.pk, foreign.pk),
            (self.component.pk, foreign.pk),
        ):
            with self.subTest(component=component_id):
                with self.assertRaises(ValidationError):
                    component_addon.preview(
                        component_addon.instance.configuration["workflow"],
                        component_id,
                        change_id,
                    )
                with self.assertRaises(ValidationError):
                    component_addon.schedule_run(component_id, change_id)
        with self.assertRaises(ValidationError):
            component_addon.instance.schedule_manual_run()
        run_addon_manually(component_addon.instance.pk)
        task.assert_not_called()
        self.assertFalse(
            AddonActivityLog.objects.filter(addon=component_addon.instance).exists()
        )

    def test_editor_renders_yaml_after_database_reload_and_preserves_invalid_input(
        self,
    ) -> None:
        addon = self.install(
            WORKFLOW
            | {
                "triggers": [{"trigger": "change", "events": ["change"]}],
            }
        )
        # Simulate a workflow saved before public identifiers were supported.
        addon.instance.configuration["workflow"]["triggers"][0]["events"] = ["change"]
        addon.instance.save(update_fields=["configuration"])
        addon.instance.refresh_from_db()
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        url = addon.instance.get_absolute_url()
        response = self.client.get(url)
        rendered = response.context["form"]["workflow"].as_widget()
        self.assertIn("version: 1", rendered)
        self.assertIn("translation_changed", rendered)
        self.assertLess(rendered.index("version:"), rendered.index("triggers:"))
        self.assertLess(rendered.index("triggers:"), rendered.index("actions:"))
        invalid = "version: [unfinished"
        response = self.client.post(url, {"workflow": invalid})
        self.assertEqual(response.context["form"]["workflow"].value(), invalid)
        addon.instance.refresh_from_db()
        self.assertEqual(addon.instance.configuration["workflow"]["version"], 1)

    @patch("weblate.automation.tasks.automation_run.delay_on_commit")
    def test_saved_preview_and_context_trigger_api(self, task: Mock) -> None:
        addon = self.install(
            WORKFLOW | {"triggers": [{"trigger": "change", "events": ["change"]}]}
        )
        self.user.is_superuser = True
        self.user.save()
        client = APIClient()
        client.force_authenticate(self.user)
        unit = self.component.translation_set.get(language_code="cs").unit_set.get(
            source="Hello, world!\n"
        )
        change = Change.objects.create(unit=unit, action=ActionEvents.CHANGE)
        for action, success in (("preview", 200), ("trigger", 202)):
            url = reverse(f"api:addon-{action}", kwargs={"pk": addon.instance.pk})
            response = client.post(url, {}, format="json")
            self.assertEqual(response.status_code, 400, response.data)
            self.assertEqual(response.data["errors"][0]["attr"], "change")
            response = client.post(url, {"change": change.pk}, format="json")
            self.assertEqual(response.status_code, success, response.data)
        activity = AddonActivityLog.objects.get(addon=addon.instance)
        task.assert_called_once_with(activity.pk)

    def test_preview_api(self) -> None:
        addon = self.install()
        client = APIClient()
        client.force_authenticate(self.user)
        url = reverse("api:addon-preview", kwargs={"pk": addon.instance.pk})
        denied = client.post(
            url, {"workflow": WORKFLOW, "component": self.component.pk}, format="json"
        )
        self.assertEqual(denied.status_code, 404)
        self.user.is_superuser = True
        self.user.save()
        response = client.post(
            reverse("api:addon-preview", kwargs={"pk": addon.instance.pk}),
            {"workflow": WORKFLOW, "component": self.component.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["preview"])
        response = client.post(
            reverse("api:addon-preview", kwargs={"pk": addon.instance.pk}),
            {"workflow": WORKFLOW, "component": 999999},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(BACKGROUND_TASKS="never")
    def test_daily_disabled(self) -> None:
        self.assertEqual(
            self.install().daily_component(self.component).status,
            AddonActivityLogStatus.SKIPPED,
        )


class AIQualityAutomationTest(ComponentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.service = OpenAITranslation.get_identifier()
        MachineryInstallation.objects.create(
            project=self.project,
            engine=self.service,
            configuration={
                "key": "test",
                "model": "custom",
                "custom_model": "test-model",
            },
        )
        self.units = list(
            self.component.translation_set.get(language_code="cs").unit_set.order_by(
                "pk"
            )[:2]
        )
        for unit in self.units:
            Unit.objects.filter(pk=unit.pk).update(
                target=f"Translation {unit.pk}", state=STATE_TRANSLATED
            )
        self.addon = AIEvaluationAddon.create(
            component=self.component,
            configuration={"service": self.service, "q": "state:>=translated"},
            run=False,
        )
        self.component.drop_addons_cache()

    def quality_action(self, *, query: str = "") -> dict[str, Any]:
        return {
            "action": "weblate.ai_quality",
            "id": "quality",
            "settings": {"q": query} if query else {},
        }

    def test_omitted_service_uses_effective_evaluator(self) -> None:
        settings = AIQualityOperation.normalize({}, self.component)
        self.assertEqual(settings, {"q": ""})
        with patch(
            "weblate.automation.operations.evaluate_component",
            return_value={"evaluated": 0, "failed": 0, "skipped": 0},
        ) as evaluate:
            AIQualityOperation.execute(self.component, settings, self.user)
        self.assertEqual(evaluate.call_args.args[2]["service"], self.service)

    def test_explicit_matching_service(self) -> None:
        settings = AIQualityOperation.normalize(
            {"service": self.service}, self.component
        )
        self.assertEqual(settings, {"q": "", "service": self.service})
        with patch(
            "weblate.automation.operations.evaluate_component",
            return_value={"evaluated": 0, "failed": 0, "skipped": 0},
        ) as evaluate:
            AIQualityOperation.execute(self.component, settings, self.user)
        evaluate.assert_called_once()

    def test_slug_selector_matches_current_installation(self) -> None:
        installation = MachineryInstallation.objects.get(
            project=self.project, engine=self.service
        )
        installation.slug = "quality"
        installation.save(update_fields=["slug"])
        alias = f"{self.service}:quality"
        settings = AIQualityOperation.normalize({"service": alias}, self.component)
        self.assertEqual(settings["service"], alias)
        with patch(
            "weblate.automation.operations.evaluate_component",
            return_value={"evaluated": 0, "failed": 0, "skipped": 0},
        ) as evaluate:
            AIQualityOperation.execute(self.component, settings, self.user)
        evaluate.assert_called_once()

        installation.slug = ""
        installation.save(update_fields=["slug"])
        MachineryInstallation.objects.create(
            project=self.project,
            engine=self.service,
            slug="quality",
            configuration=installation.configuration,
        )
        with self.assertRaisesMessage(ValidationError, "does not match"):
            AIQualityOperation.normalize({"service": alias}, self.component)

    def test_explicit_mismatching_service(self) -> None:
        other_service = AnthropicTranslation.get_identifier()
        with self.assertRaisesMessage(ValidationError, "does not match"):
            AIQualityOperation.normalize({"service": other_service}, self.component)
        with self.assertRaisesMessage(ValueError, "does not match"):
            AIQualityOperation.execute(
                self.component, {"service": other_service, "q": ""}, self.user
            )

    def test_component_scope_passes_lazy_selection(self) -> None:
        settings = AIQualityOperation.normalize(
            {"service": self.service}, self.component
        )
        with patch(
            "weblate.automation.operations.evaluate_component",
            return_value={"evaluated": 0, "failed": 0, "skipped": 0},
        ) as evaluate:
            AIQualityOperation.execute(self.component, settings, self.user)
        selected_ids = evaluate.call_args.args[3]
        self.assertIsInstance(selected_ids, QuerySet)

    def test_quality_routes_only_evaluated_units(self) -> None:
        clean, problematic = self.units
        checks = " OR ".join(
            f"check:ai_{category}"
            for category in (
                "accuracy",
                "fluency",
                "terminology",
                "style",
                "formatting",
            )
        )
        actions = [
            self.quality_action(query=f"id:{clean.pk} OR id:{problematic.pk}"),
            {
                "action": "weblate.bulk_edit",
                "scope": "result:quality",
                "settings": {"q": f"NOT ({checks})", "state": STATE_APPROVED},
            },
            {
                "action": "weblate.bulk_edit",
                "scope": "result:quality",
                "settings": {"q": checks, "state": STATE_NEEDS_CHECKING},
            },
        ]
        workflow = validate_operations(
            parse_workflow(WORKFLOW | {"actions": actions}), self.component
        )
        with patch.object(
            OpenAITranslation,
            "evaluate_batch",
            return_value={
                clean.pk: [],
                problematic.pk: [
                    {
                        "category": "accuracy",
                        "severity": "major",
                        "explanation": "The meaning is reversed.",
                    }
                ],
            },
        ):
            runner = Runner(
                workflow,
                execution_context(self.component, "manual"),
                self.component,
                self.user,
            )
            self.assertEqual(runner.run(), AddonActivityLogStatus.SUCCESS, runner.trace)
        self.assertEqual(
            runner.selections["quality"].unit_ids, {clean.pk, problematic.pk}
        )
        self.assertEqual(
            runner.context["results"]["quality"],
            {
                "component": self.component.pk,
                "evaluated": 2,
            },
        )
        self.assertNotIn("unit_ids", json.dumps(runner.context["results"]))
        clean.refresh_from_db()
        problematic.refresh_from_db()
        self.assertEqual(clean.state, STATE_APPROVED)
        self.assertEqual(problematic.state, STATE_NEEDS_CHECKING)

    def test_quality_skips_unit_changed_during_later_batch(self) -> None:
        changed, unchanged = self.units
        actions = [
            self.quality_action(query=f"id:{changed.pk} OR id:{unchanged.pk}"),
            {
                "action": "weblate.bulk_edit",
                "scope": "result:quality",
                "settings": {"state": STATE_APPROVED},
            },
        ]
        workflow = validate_operations(
            parse_workflow(WORKFLOW | {"actions": actions}), self.component
        )
        calls = 0

        def evaluate(batch: list[Unit]) -> dict[int, list[object]]:
            nonlocal calls
            calls += 1
            if calls == 2:
                changed.target = "Changed after evaluation"
                changed.save(update_fields=["target"])
            return {batch[0].pk: []}

        with (
            patch.object(OpenAITranslation, "batch_size", 1),
            patch.object(OpenAITranslation, "evaluate_batch", side_effect=evaluate),
        ):
            runner = Runner(
                workflow,
                execution_context(self.component, "manual"),
                self.component,
                self.user,
            )
            self.assertEqual(runner.run(), AddonActivityLogStatus.SUCCESS, runner.trace)
        changed.refresh_from_db()
        unchanged.refresh_from_db()
        self.assertEqual(changed.state, STATE_TRANSLATED)
        self.assertEqual(unchanged.state, STATE_APPROVED)

    def test_quality_snapshots_survive_chained_result_scope(self) -> None:
        unit = self.units[0]
        actions = [
            self.quality_action(query=f"id:{unit.pk}"),
            {
                "action": "weblate.bulk_edit",
                "id": "routed",
                "scope": "result:quality",
                "settings": {"state": STATE_NEEDS_CHECKING},
            },
            {
                "action": "weblate.bulk_edit",
                "scope": "result:routed",
                "settings": {"state": STATE_APPROVED},
            },
        ]
        workflow = validate_operations(
            parse_workflow(WORKFLOW | {"actions": actions}), self.component
        )
        with patch.object(
            OpenAITranslation, "evaluate_batch", return_value={unit.pk: []}
        ):
            runner = Runner(
                workflow,
                execution_context(self.component, "manual"),
                self.component,
                self.user,
            )
            self.assertEqual(runner.run(), AddonActivityLogStatus.SUCCESS, runner.trace)
        unit.refresh_from_db()
        self.assertEqual(unit.state, STATE_APPROVED)
        self.assertEqual(
            set(runner.selections["routed"].unit_snapshots or {}), {unit.pk}
        )

    def test_quality_unchanged_result_approves(self) -> None:
        unit = self.units[0]
        actions = [
            self.quality_action(query=f"id:{unit.pk}"),
            {
                "action": "weblate.bulk_edit",
                "scope": "result:quality",
                "settings": {"state": STATE_APPROVED},
            },
        ]
        workflow = validate_operations(
            parse_workflow(WORKFLOW | {"actions": actions}), self.component
        )
        with patch.object(
            OpenAITranslation, "evaluate_batch", return_value={unit.pk: []}
        ):
            runner = Runner(
                workflow,
                execution_context(self.component, "manual"),
                self.component,
                self.user,
            )
            self.assertEqual(runner.run(), AddonActivityLogStatus.SUCCESS, runner.trace)
        unit.refresh_from_db()
        self.assertEqual(unit.state, STATE_APPROVED)

    def test_scope_query_and_empty_selection(self) -> None:
        selected, excluded = self.units
        action = self.quality_action()
        settings = AIQualityOperation.normalize(action["settings"], self.component)
        affected = UnitSelection(set())
        with patch.object(
            OpenAITranslation, "evaluate_batch", return_value={selected.pk: []}
        ) as evaluate:
            result = AIQualityOperation.execute(
                self.component,
                settings,
                self.user,
                selection=UnitSelection({selected.pk}),
                affected=affected,
            )
        self.assertEqual(result["evaluated"], 1)
        self.assertEqual(affected.unit_ids, {selected.pk})
        evaluate.assert_called_once()
        self.assertNotIn(excluded.pk, [unit.pk for unit in evaluate.call_args.args[0]])
        affected = UnitSelection(set())
        with patch.object(OpenAITranslation, "evaluate_batch") as evaluate:
            result = AIQualityOperation.execute(
                self.component,
                settings,
                self.user,
                selection=UnitSelection(set()),
                affected=affected,
            )
        self.assertEqual(result["evaluated"], 0)
        self.assertEqual(affected.unit_ids, set())
        evaluate.assert_not_called()

    def test_trigger_scope_expands_source_unit(self) -> None:
        selected = self.units[0]
        source = selected.source_unit
        change = Change.objects.create(
            unit=source, action=ActionEvents.SOURCE_CHANGE, user=self.user
        )
        action = self.quality_action(query=f"id:{selected.pk}") | {"scope": "trigger"}
        workflow = validate_operations(
            parse_workflow(
                WORKFLOW
                | {
                    "triggers": [{"trigger": "change", "events": ["source_change"]}],
                    "actions": [action],
                }
            ),
            self.component,
        )
        with patch.object(
            OpenAITranslation, "evaluate_batch", return_value={selected.pk: []}
        ):
            runner = Runner(
                workflow,
                execution_context(self.component, "change", change),
                self.component,
                self.user,
            )
            self.assertEqual(runner.run(), AddonActivityLogStatus.SUCCESS, runner.trace)
        self.assertEqual(runner.selections["quality"].unit_ids, {selected.pk})

    def test_result_scope_uses_machine_selection(self) -> None:
        selected, excluded = self.units
        workflow = validate_operations(
            parse_workflow(
                WORKFLOW
                | {
                    "actions": [
                        AUTO | {"id": "machine"},
                        self.quality_action(query=f"id:{selected.pk}")
                        | {"scope": "result:machine"},
                    ]
                }
            ),
            self.component,
        )

        def translated(
            _component: Component,
            _settings: dict[str, Any],
            _user: object,
            *,
            selection: UnitSelection | None,
            affected: UnitSelection | None,
        ) -> dict[str, Any]:
            if affected is not None:
                affected.unit_ids = {selected.pk, excluded.pk}
            return {
                "component": self.component.pk,
                "updated": 2,
                "message": "Done",
                "warnings": [],
                "warnings_omitted": 0,
            }

        with (
            patch.object(AutomaticTranslationOperation, "execute", translated),
            patch.object(
                OpenAITranslation, "evaluate_batch", return_value={selected.pk: []}
            ) as evaluate,
        ):
            runner = Runner(
                workflow,
                execution_context(self.component, "manual"),
                self.component,
                self.user,
            )
            self.assertEqual(runner.run(), AddonActivityLogStatus.SUCCESS, runner.trace)
        self.assertEqual(runner.selections["quality"].unit_ids, {selected.pk})
        self.assertEqual(
            [unit.pk for unit in evaluate.call_args.args[0]], [selected.pk]
        )

    def test_missing_or_mismatched_evaluator(self) -> None:
        with self.assertRaises(ValidationError):
            AIQualityOperation.normalize(
                {"service": self.service, "q": "("}, self.component
            )
        self.addon.instance.delete()
        self.component.drop_addons_cache()
        with self.assertRaisesMessage(ValidationError, "requires an effective add-on"):
            AIQualityOperation.normalize({}, self.component)
        with self.assertRaisesMessage(ValueError, "requires an effective add-on"):
            AIQualityOperation.execute(self.component, {"q": ""}, self.user)

    def test_inherited_workflow_uses_component_evaluators(self) -> None:
        other_service = AnthropicTranslation.get_identifier()
        MachineryInstallation.objects.create(
            project=self.project,
            engine=other_service,
            configuration={
                "key": "test",
                "model": "custom",
                "custom_model": "test-model",
            },
        )
        other_component = self.create_po_new_base(name="other", project=self.project)
        AIEvaluationAddon.create(
            component=other_component,
            configuration={"service": other_service, "q": "state:>=translated"},
            run=False,
        )
        other_component.drop_addons_cache()
        workflow = validate_operations(
            parse_workflow(WORKFLOW | {"actions": [self.quality_action()]}),
            self.project,
        )
        self.assertEqual(workflow["actions"][0]["settings"], {"q": ""})
        with patch(
            "weblate.automation.operations.evaluate_component",
            return_value={"evaluated": 0, "failed": 0, "skipped": 0},
        ) as evaluate:
            for component, expected_service in (
                (self.component, self.service),
                (other_component, other_service),
            ):
                with self.subTest(component=component.pk):
                    action = validate_operations(deepcopy(workflow), component)[
                        "actions"
                    ][0]
                    AIQualityOperation.execute(component, action["settings"], self.user)
                    self.assertEqual(
                        evaluate.call_args.args[2]["service"], expected_service
                    )

    def test_inherited_evaluator_and_query_intersection(self) -> None:
        selected, excluded = self.units
        self.addon.instance.delete()
        AIEvaluationAddon.create(
            project=self.project,
            configuration={"service": self.service, "q": f"id:{selected.pk}"},
            run=False,
        )
        self.component.drop_addons_cache()
        settings = AIQualityOperation.normalize(
            {"service": self.service, "q": f"id:{selected.pk} OR id:{excluded.pk}"},
            self.component,
        )
        affected = UnitSelection(set())
        with patch.object(
            OpenAITranslation, "evaluate_batch", return_value={selected.pk: []}
        ) as evaluate:
            result = AIQualityOperation.execute(
                self.component, settings, self.user, affected=affected
            )
        self.assertEqual(result["evaluated"], 1)
        self.assertEqual(affected.unit_ids, {selected.pk})
        evaluate.assert_called_once()

    def test_rate_limited_evaluation_stops_approval(self) -> None:
        unit = self.units[0]
        workflow = validate_operations(
            parse_workflow(
                WORKFLOW
                | {
                    "actions": [
                        self.quality_action(query=f"id:{unit.pk}"),
                        {
                            "action": "weblate.bulk_edit",
                            "scope": "result:quality",
                            "settings": {"state": STATE_APPROVED},
                        },
                    ]
                }
            ),
            self.component,
        )
        with (
            patch.object(OpenAITranslation, "is_rate_limited", return_value=True),
            patch.object(OpenAITranslation, "evaluate_batch") as evaluate,
        ):
            runner = Runner(
                workflow,
                execution_context(self.component, "manual"),
                self.component,
                self.user,
            )
            self.assertEqual(runner.run(), AddonActivityLogStatus.ERROR)
        evaluate.assert_not_called()
        unit.refresh_from_db()
        self.assertEqual(unit.state, STATE_TRANSLATED)
        self.assertEqual(runner.context["results"], {})

    def test_failed_evaluation_stops_approval(self) -> None:
        unit = self.units[0]
        workflow = validate_operations(
            parse_workflow(
                WORKFLOW
                | {
                    "actions": [
                        self.quality_action(query=f"id:{unit.pk}"),
                        {
                            "action": "weblate.bulk_edit",
                            "scope": "result:quality",
                            "settings": {"state": STATE_APPROVED},
                        },
                    ]
                }
            ),
            self.component,
        )
        with patch.object(
            OpenAITranslation,
            "evaluate_batch",
            side_effect=MachineTranslationError("provider secret response"),
        ):
            runner = Runner(
                workflow,
                execution_context(self.component, "manual"),
                self.component,
                self.user,
            )
            self.assertEqual(runner.run(), AddonActivityLogStatus.ERROR)
        unit.refresh_from_db()
        self.assertEqual(unit.state, STATE_TRANSLATED)
        self.assertEqual(runner.trace[-1]["status"], "skipped")
        self.assertNotIn("provider secret response", json.dumps(runner.result()))
