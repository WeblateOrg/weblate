# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
import subprocess  # ruff: ignore[suspicious-subprocess-import]
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from typing import TYPE_CHECKING, Any, TypedDict, Unpack
from unittest.mock import Mock, call, patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils.translation import override
from rest_framework.test import APIClient

from weblate.addons import automation_cel
from weblate.addons.automation import AutomationAddon
from weblate.addons.automation_definition import parse_workflow
from weblate.addons.automation_expressions import expressions
from weblate.addons.automation_forms import AutomationForm, validate_operations
from weblate.addons.automation_operations import (
    OPERATIONS,
    AutomaticTranslationOperation,
    AutomationOperation,
    register,
)
from weblate.addons.automation_runner import Runner, execution_context, run_automation
from weblate.addons.automation_schema import SCHEMA
from weblate.addons.events import AddonActivityLogStatus, AddonEvent
from weblate.addons.models import AddonActivityLog, handle_addon_event
from weblate.addons.tasks import run_addon_manually
from weblate.machinery.base import MachineTranslationError
from weblate.trans.actions import ActionEvents
from weblate.trans.autotranslate import BatchAutoTranslate
from weblate.trans.models import Change
from weblate.trans.tests.test_views import ComponentTestCase
from weblate.utils.automation import automation_origin
from weblate.utils.state import STATE_EMPTY, STATE_FUZZY, STATE_TRANSLATED

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
    def test_operation_registry_drives_action_schema(self) -> None:
        variants = SCHEMA["$defs"]["action"]["oneOf"]
        self.assertEqual(
            [variant["properties"]["action"]["const"] for variant in variants[:2]],
            list(OPERATIONS),
        )
        for variant in variants[:2]:
            operation = OPERATIONS[variant["properties"]["action"]["const"]]
            self.assertEqual(
                variant["properties"]["settings"], operation.settings_schema
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
        self.assertEqual(runner.trace[-1]["status"], "error")
        self.assertIn("Invalid result", runner.trace[-1]["error"])

    @override_settings(BACKGROUND_TASKS="monthly")
    @patch("weblate.addons.automation.timezone.now")
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

    @patch("weblate.addons.automation_runner.execute_operation")
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
                    "weblate.addons.automation_expressions.subprocess.run",
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

    @patch("weblate.addons.automation_runner.execute_operation")
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
        "weblate.addons.automation_runner.execute_operation",
        side_effect=RuntimeError("failed"),
    )
    def test_failure_stops_actions(self, operation: Mock) -> None:
        runner = Runner(WORKFLOW | {"actions": [AUTO, BULK]}, CONTEXT, Mock(), Mock())
        self.assertEqual(runner.run(), AddonActivityLogStatus.ERROR)
        operation.assert_called_once()
        self.assertEqual(runner.trace[-1]["status"], "skipped")

    @patch("weblate.addons.automation_runner.execute_operation")
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


class AutomationTest(ComponentTestCase):
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

    @patch("weblate.addons.tasks.automation_run.delay_on_commit")
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

    def test_invalid_configuration_and_preview_ui(self) -> None:
        addon = self.install()
        self.user.is_superuser = True
        self.user.save()
        self.client.force_login(self.user)
        page_response = self.client.post(
            addon.instance.get_absolute_url(),
            {"preview": "1", "workflow": json.dumps(WORKFLOW)},
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
        with patch("weblate.addons.tasks.automation_run.delay") as delay:
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

    @patch("weblate.addons.tasks.automation_run.delay_on_commit")
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
        with patch("weblate.addons.tasks.automation_run.delay_on_commit") as task:
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

    @patch("weblate.addons.tasks.automation_run.delay_on_commit")
    def test_manual_snapshot_and_duplicate_delivery(self, task: Mock) -> None:
        addon = self.install()
        run_addon_manually(addon.instance.pk, user_id=self.user.pk)
        activity = AddonActivityLog.objects.get(addon=addon.instance)
        self.assertEqual(
            activity.details["result"]["context"]["actor"]["id"], self.user.pk
        )
        task.assert_called_once_with(activity.pk)
        addon.configure({"workflow": WORKFLOW | {"actions": [AUTO]}})
        with patch("weblate.addons.automation_runner.execute_operation") as operation:
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

    @patch("weblate.addons.tasks.automation_run.delay_on_commit")
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
                run_addon_manually(addon.instance.pk)
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
