# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from datetime import timedelta
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

import httpx2
from django.core.cache import cache
from django.db import transaction
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from weblate.addons.ai import AIEvaluationAddon, AIEvaluationForm, effective_evaluator
from weblate.addons.events import AddonActivityLogStatus, AddonEvent
from weblate.addons.models import Addon, AddonActivityLog
from weblate.addons.tasks import evaluate_quality
from weblate.checks.ai import AI_CHECKS
from weblate.checks.models import Check
from weblate.machinery.base import MachineryRateLimitError, MachineTranslationError
from weblate.machinery.evaluation import parse_evaluation_response
from weblate.machinery.google import GoogleTranslation
from weblate.machinery.openai import OpenAITranslation
from weblate.trans.actions import ActionEvents
from weblate.trans.alerts.base import AlertSeverity
from weblate.trans.alerts.registry import update_alerts
from weblate.trans.models import Change, Unit
from weblate.trans.models.project import Project
from weblate.trans.tests.test_views import ComponentTestCase
from weblate.trans.util import join_plural
from weblate.utils.hash import calculate_hash
from weblate.utils.state import STATE_TRANSLATED

if TYPE_CHECKING:
    from collections.abc import Callable

    from weblate.addons.ai import AIEvaluationConfiguration
    from weblate.machinery.evaluation import EvaluationIssue
    from weblate.machinery.types import SettingsDict

ISSUE: EvaluationIssue = {
    "category": "accuracy",
    "severity": "major",
    "explanation": "The meaning is reversed.",
}


def evaluation_response(results: dict[int, list[EvaluationIssue]]) -> str:
    return json.dumps(
        {
            "results": [
                {"unit_id": unit_id, "issues": issues}
                for unit_id, issues in results.items()
            ]
        }
    )


class EvaluationResponseTest(SimpleTestCase):
    def test_valid(self) -> None:
        # Results can be reordered, and clean units must have explicit entries.
        self.assertEqual(
            parse_evaluation_response(evaluation_response({2: [], 1: [ISSUE]}), {1, 2}),
            {1: [ISSUE], 2: []},
        )
        self.assertEqual(
            parse_evaluation_response(evaluation_response({1: []}), {1}), {1: []}
        )

    def test_invalid(self) -> None:
        invalid = [
            None,
            "",
            "not JSON",
            "[]",
            '{"results": null}',
            '{"results": [{}]}',
            '{"results":[]}',
            '{"issues":[]}',
            json.dumps(
                {"results": [{"unit_id": 1, "issues": [ISSUE]}], "translation": "foo"}
            ),
            evaluation_response({1: [ISSUE] * 101}),
            " " * 500_001,
        ]
        invalid_fields: dict[str, list[object]] = {
            "category": ["custom", [], None],
            "severity": ["warning", [], None],
            "explanation": ["", " ", None, "x" * 4001, chr(0), chr(0xD800)],
        }
        for key, values in invalid_fields.items():
            invalid.extend(
                json.dumps(
                    {"results": [{"unit_id": 1, "issues": [{**ISSUE, key: value}]}]}
                )
                for value in values
            )
        invalid_ids: tuple[object, ...] = (True, 1.0, "1", None, [], 2)
        invalid_issues: tuple[object, ...] = (None, {}, "", [{}])
        invalid.extend(
            json.dumps({"results": [{"unit_id": unit_id, "issues": []}]})
            for unit_id in invalid_ids
        )
        invalid.extend(
            json.dumps({"results": [{"unit_id": 1, "issues": issues}]})
            for issues in invalid_issues
        )
        for response in invalid:
            with (
                self.subTest(response=response),
                self.assertRaises(MachineTranslationError),
            ):
                parse_evaluation_response(response, {1})

    def test_invalid_batch_membership(self) -> None:
        for ids in ([1], [1, 1], [1, 3], [1, 2, 3]):
            response = json.dumps(
                {"results": [{"unit_id": unit_id, "issues": []} for unit_id in ids]}
            )
            with self.subTest(ids=ids), self.assertRaises(MachineTranslationError):
                parse_evaluation_response(response, {1, 2})

    def test_limits_apply_per_unit(self) -> None:
        result = {1: [ISSUE] * 100, 2: [ISSUE] * 100}
        self.assertEqual(
            parse_evaluation_response(evaluation_response(result), {1, 2}), result
        )


class AIEvaluationTest(ComponentTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.service_key = OpenAITranslation.get_identifier()
        self.service_settings: SettingsDict = {
            "key": "test",
            "model": "custom",
            "custom_model": "test-model",
            "persona": "Check carefully",
            "style": "Use formal language",
            "language_instructions": {"cs": "Use Czech terminology"},
        }
        self.project.machinery_settings = {self.service_key: self.service_settings}
        self.project.save(update_fields=["machinery_settings"])
        self.unit = self.change_unit("Ahoj světe!\n")
        self.configuration: AIEvaluationConfiguration = {
            "service": self.service_key,
            "q": f"id:{self.unit.pk}",
            "interval": "weekly",
            "on_change": False,
            "on_update": False,
        }
        self.addon = AIEvaluationAddon.create(
            component=self.component, configuration=self.configuration, run=False
        )

    def evaluate(self, issues: list[EvaluationIssue] | None = None) -> None:
        if issues is None:
            issues = [ISSUE]
        with patch.object(
            OpenAITranslation,
            "fetch_llm_translations",
            return_value=evaluation_response({self.unit.pk: issues}),
        ):
            evaluate_quality(
                self.addon.instance.pk, [self.component.pk], self.configuration
            )

    def test_create_group_remove(self) -> None:
        self.evaluate([ISSUE, {**ISSUE, "explanation": "Another issue."}])
        check = self.unit.check_set.get(name="ai_accuracy")
        self.assertEqual(len(check.metadata["issues"]), 2)
        self.assertIn("Another issue.", check.get_plain_description())
        self.assertTrue(
            Unit.objects.search("check:ai_accuracy").filter(pk=self.unit.pk).exists()
        )
        self.unit.refresh_from_db()
        self.assertTrue(self.unit.has_failing_check)
        self.unit.run_checks()
        self.assertTrue(self.unit.check_set.filter(pk=check.pk).exists())
        self.evaluate([])
        self.assertFalse(self.unit.check_set.filter(name__in=AI_CHECKS).exists())

    def test_service_configuration_scope(self) -> None:
        for project_override in (False, True):
            with self.subTest(project_override=project_override):
                self.project.machinery_settings = (
                    {self.service_key: self.service_settings}
                    if project_override
                    else {}
                )
                self.project.save(update_fields=["machinery_settings"])
                with (
                    patch(
                        "weblate.trans.models.project.Setting.objects.get_settings_dict",
                        return_value={self.service_key: dict(self.service_settings)},
                    ),
                    patch.object(
                        OpenAITranslation,
                        "fetch_llm_translations",
                        autospec=True,
                        return_value=evaluation_response({self.unit.pk: []}),
                    ) as fetch,
                ):
                    self.run_batch_evaluation()
                service = fetch.call_args.args[0]
                self.assertEqual(service.allow_private_targets, not project_override)
                if project_override:
                    self.assertEqual(service.settings["_project"], self.project)

    def test_existing_provider_cooldown(self) -> None:
        self.create_batch_units(3)
        service = OpenAITranslation(self.service_settings)
        self.addCleanup(cache.delete, service.rate_limit_cache)
        service.set_rate_limit()
        with patch.object(OpenAITranslation, "fetch_llm_translations") as fetch:
            self.assertEqual(
                self.run_batch_evaluation(scheduled=True),
                {"evaluated": 0, "failed": 0, "skipped": 3},
            )
        fetch.assert_not_called()
        self.addon.instance.refresh_from_db()
        self.assertTrue(self.addon.is_schedule_due(self.component))

    def test_provider_rate_limit_stops_requests(self) -> None:
        self.create_batch_units(5)
        service = OpenAITranslation(self.service_settings)
        self.addCleanup(cache.delete, service.rate_limit_cache)
        request = httpx2.Request("POST", "https://example.com/evaluate")
        errors = (
            httpx2.HTTPStatusError(
                "Too many requests",
                request=request,
                response=httpx2.Response(429, request=request),
            ),
            MachineryRateLimitError("Provider quota exceeded"),
        )
        for error in errors:
            with self.subTest(error=type(error).__name__):
                cache.delete(service.rate_limit_cache)
                with (
                    patch.object(OpenAITranslation, "batch_size", 2),
                    patch.object(
                        OpenAITranslation, "fetch_llm_translations", side_effect=error
                    ) as fetch,
                ):
                    self.assertEqual(
                        self.run_batch_evaluation(scheduled=True),
                        {"evaluated": 0, "failed": 2, "skipped": 3},
                    )
                fetch.assert_called_once()
                self.assertTrue(service.is_rate_limited())
                self.addon.instance.refresh_from_db()
                self.assertTrue(self.addon.is_schedule_due(self.component))

    def test_dismissal_survives_reevaluation(self) -> None:
        self.evaluate()
        check = self.unit.check_set.get(name="ai_accuracy")
        check.set_dismiss(recurse=False)
        self.evaluate()
        check.refresh_from_db()
        self.assertTrue(check.dismissed)

    def test_translation_change_removes_checks(self) -> None:
        self.evaluate()
        self.change_unit("Different translation")
        self.assertFalse(self.unit.check_set.filter(name__in=AI_CHECKS).exists())

    def test_source_change_removes_checks(self) -> None:
        self.evaluate()
        self.unit = Unit.objects.get(pk=self.unit.pk)
        self.unit.source = "Changed source"
        self.unit.invalidate_checks_cache()
        self.unit.run_checks()
        self.assertFalse(self.unit.check_set.filter(name__in=AI_CHECKS).exists())

    def test_ignore_flag(self) -> None:
        self.unit.extra_flags = "ignore-ai-accuracy"
        self.unit.save(update_fields=["extra_flags"])
        self.evaluate([ISSUE, {**ISSUE, "category": "style"}])
        self.assertFalse(self.unit.check_set.filter(name="ai_accuracy").exists())
        self.assertTrue(self.unit.check_set.filter(name="ai_style").exists())

    def test_output_is_escaped(self) -> None:
        self.evaluate([{**ISSUE, "explanation": "<script>alert(1)</script>"}])
        check = self.unit.check_set.get(name="ai_accuracy")
        self.assertIn("&lt;script&gt;", check.get_description())
        self.assertNotIn("<script>", check.get_description())

    def test_failure_preserves_existing_checks(self) -> None:
        self.evaluate()
        with patch.object(
            OpenAITranslation,
            "fetch_llm_translations",
            side_effect=MachineTranslationError("provider failure"),
        ):
            evaluate_quality(
                self.addon.instance.pk, [self.component.pk], self.configuration
            )
        self.assertTrue(self.unit.check_set.filter(name="ai_accuracy").exists())

    def test_inflight_edit_discards_response(self) -> None:
        def response(*args: object) -> str:
            Unit.objects.filter(pk=self.unit.pk).update(
                target="Changed while evaluating"
            )
            return evaluation_response({self.unit.pk: [ISSUE]})

        with patch.object(
            OpenAITranslation, "fetch_llm_translations", side_effect=response
        ):
            evaluate_quality(
                self.addon.instance.pk, [self.component.pk], self.configuration
            )
        self.assertFalse(self.unit.check_set.filter(name__in=AI_CHECKS).exists())

    def test_inflight_configuration_change_discards_response(self) -> None:
        def response(*args: object) -> str:
            Addon.objects.filter(pk=self.addon.instance.pk).update(
                configuration={**self.configuration, "q": "state:empty"}
            )
            return evaluation_response({self.unit.pk: [ISSUE]})

        with patch.object(
            OpenAITranslation, "fetch_llm_translations", side_effect=response
        ):
            evaluate_quality(
                self.addon.instance.pk, [self.component.pk], self.configuration
            )
        self.assertFalse(self.unit.check_set.filter(name__in=AI_CHECKS).exists())

    def test_cleanup(self) -> None:
        self.evaluate()
        self.addon.instance.delete()
        self.assertFalse(
            Check.objects.filter(unit=self.unit, name__in=AI_CHECKS).exists()
        )

    def test_configure_cleanup(self) -> None:
        self.evaluate()
        self.addon.configure({**self.configuration, "interval": "daily"})
        self.assertFalse(self.unit.check_set.filter(name__in=AI_CHECKS).exists())

    def test_defaults_and_manual_dispatch(self) -> None:
        defaults = self.addon.normalize_configuration({"service": self.service_key})
        self.assertEqual(defaults["interval"], "weekly")
        self.assertFalse(defaults["on_change"])
        with patch("weblate.addons.tasks.evaluate_quality.delay_on_commit") as task:
            outcome = self.addon.manual(component=self.component)
        self.assertEqual(outcome.status, AddonActivityLogStatus.PENDING)
        task.assert_called_once()
        self.assertEqual(
            task.call_args.args[:2], (self.addon.instance.pk, [self.component.pk])
        )

    def test_schedule(self) -> None:
        self.assertTrue(self.addon.is_schedule_due(self.component))
        self.evaluate()
        self.addon.instance.refresh_from_db()
        self.assertFalse(self.addon.is_schedule_due(self.component))
        self.addon.update_component_state(
            self.component,
            lambda state: state.update(
                last_run=(timezone.now().date() - timedelta(days=7)).isoformat()
            ),
        )
        self.assertTrue(self.addon.is_schedule_due(self.component))

    def test_no_trigger_loops(self) -> None:
        self.addon.instance.configuration["on_change"] = True
        for action in (
            ActionEvents.CHANGE,
            ActionEvents.AUTO,
            ActionEvents.SOURCE_CHANGE,
        ):
            with self.subTest(action=action):
                self.assertTrue(
                    self.addon.check_change_action(
                        Change(unit=self.unit, action=action)
                    )
                )
        for action in (
            ActionEvents.ENFORCED_CHECK,
            ActionEvents.COMMENT,
            ActionEvents.SUGGESTION,
        ):
            with self.subTest(action=action):
                self.assertFalse(
                    self.addon.check_change_action(
                        Change(unit=self.unit, action=action)
                    )
                )
        with patch("weblate.addons.tasks.evaluate_quality.delay_on_commit") as task:
            self.evaluate()
        task.assert_not_called()

    def test_optional_update_trigger(self) -> None:
        with patch("weblate.addons.tasks.evaluate_quality.delay_on_commit") as task:
            self.addon.component_update(self.component)
            task.assert_not_called()
            self.addon.instance.configuration["on_update"] = True
            self.addon.component_update(self.component)
            task.assert_called_once()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_dispatch_after_commit(self) -> None:
        with patch.object(evaluate_quality, "apply_async") as task:
            with self.captureOnCommitCallbacks(execute=True):
                self.addon.manual(component=self.component)
                task.assert_not_called()
            task.assert_called_once()

    def test_scheduled_run_respects_interval_and_manual_bypasses_it(self) -> None:
        self.evaluate()
        with patch.object(
            OpenAITranslation,
            "fetch_llm_translations",
            return_value=evaluation_response({self.unit.pk: []}),
        ) as fetch:
            evaluate_quality(
                self.addon.instance.pk,
                [self.component.pk],
                self.configuration,
                scheduled=True,
            )
            fetch.assert_not_called()
            evaluate_quality(
                self.addon.instance.pk, [self.component.pk], self.configuration
            )
            fetch.assert_called_once()

    def test_failure_log_and_schedule(self) -> None:
        activity = AddonActivityLog.objects.create(
            addon=self.addon.instance,
            component=self.component,
            event=AddonEvent.EVENT_MANUAL,
        )
        with patch.object(
            OpenAITranslation, "fetch_llm_translations", return_value="invalid JSON"
        ):
            evaluate_quality(
                self.addon.instance.pk,
                [self.component.pk],
                self.configuration,
                activity_log_id=activity.pk,
            )
        activity.refresh_from_db()
        self.assertEqual(activity.status, AddonActivityLogStatus.ERROR)
        self.assertFalse(
            self.component.alert_set.filter(name="AIEvaluationUnavailable").exists()
        )
        self.addon.instance.refresh_from_db()
        self.assertTrue(self.addon.is_schedule_due(self.component))
        self.assertFalse(self.unit.check_set.filter(name__in=AI_CHECKS).exists())

    def test_unavailable_service_diagnostic(self) -> None:
        for service in (
            "missing",
            GoogleTranslation.get_identifier(),
            self.service_key,
        ):
            with self.subTest(service=service):
                configuration = {**self.configuration, "service": service}
                self.addon.instance.configuration = configuration
                self.addon.instance.save()
                activity = AddonActivityLog.objects.create(
                    addon=self.addon.instance,
                    component=self.component,
                    event=AddonEvent.EVENT_MANUAL,
                )
                # Missing configuration, an unregistered backend, and a non-LLM backend.
                configured: dict[str, SettingsDict] = (
                    {} if service == self.service_key else {service: {}}
                )
                with (
                    patch.object(
                        Project, "get_machinery_settings", return_value=configured
                    ),
                    patch.object(OpenAITranslation, "fetch_llm_translations") as fetch,
                ):
                    evaluate_quality(
                        self.addon.instance.pk,
                        [self.component.pk],
                        configuration,
                        activity_log_id=activity.pk,
                    )
                fetch.assert_not_called()
                activity.refresh_from_db()
                self.assertEqual(activity.status, AddonActivityLogStatus.ERROR)
                alert = self.component.alert_set.get(name="AIEvaluationUnavailable")
                self.assertEqual(alert.severity, AlertSeverity.ERROR)
                self.assertEqual(
                    alert.details["occurrences"][0]["addon_id"],
                    str(self.addon.instance.pk),
                )
        self.addon.instance.configuration = self.configuration
        self.addon.instance.save()
        self.evaluate()
        self.assertFalse(
            self.component.alert_set.filter(name="AIEvaluationUnavailable").exists()
        )

    def test_unavailable_service_refresh_and_uninstall(self) -> None:
        with patch.object(Project, "get_machinery_settings", return_value={}):
            update_alerts(self.component, {"AIEvaluationUnavailable"})
        self.assertTrue(
            self.component.alert_set.filter(name="AIEvaluationUnavailable").exists()
        )
        self.addon.instance.delete()
        self.assertFalse(
            self.component.alert_set.filter(name="AIEvaluationUnavailable").exists()
        )

    def test_unavailable_inherited_evaluator_and_stale_task(self) -> None:
        inherited = AIEvaluationAddon.create(
            project=self.project,
            configuration={**self.configuration, "service": "missing"},
            run=False,
        )
        update_alerts(self.component, {"AIEvaluationUnavailable"})
        self.assertFalse(
            self.component.alert_set.filter(name="AIEvaluationUnavailable").exists()
        )
        with patch.object(OpenAITranslation, "fetch_llm_translations") as fetch:
            evaluate_quality(
                inherited.instance.pk,
                [self.component.pk],
                inherited.get_configuration(),
            )
        fetch.assert_not_called()
        self.assertFalse(
            self.component.alert_set.filter(name="AIEvaluationUnavailable").exists()
        )
        self.addon.instance.delete()
        alert = self.component.alert_set.get(name="AIEvaluationUnavailable")
        self.assertEqual(
            alert.details["occurrences"][0]["addon_id"], str(inherited.instance.pk)
        )
        inherited.configure(self.configuration)
        inherited.post_configure_run()
        self.assertFalse(
            self.component.alert_set.filter(name="AIEvaluationUnavailable").exists()
        )

    def test_evaluation_recommendation(self) -> None:
        name = "RecommendedAIEvaluationAddon"
        update_alerts(self.component, {name})
        self.assertFalse(self.component.alert_set.filter(name=name).exists())
        self.addon.instance.delete()
        self.component.drop_addons_cache()
        update_alerts(self.component, {name})
        alert = self.component.alert_set.get(name=name)
        self.assertEqual(alert.severity, AlertSeverity.INFO)
        self.assertTrue(alert.dismiss(self.user))
        update_alerts(self.component, {name})
        alert.refresh_from_db()
        self.assertTrue(alert.is_dismissed)
        unavailable: tuple[dict[str, SettingsDict], ...] = (
            {},
            {GoogleTranslation.get_identifier(): {}},
            {"missing": {}},
        )
        for configured in unavailable:
            with patch.object(
                Project, "get_machinery_settings", return_value=configured
            ):
                update_alerts(self.component, {name})
            self.assertFalse(self.component.alert_set.filter(name=name).exists())
        with override_settings(WEBLATE_ADDONS=[]):
            update_alerts(self.component, {name})
        self.assertFalse(self.component.alert_set.filter(name=name).exists())
        update_alerts(self.component, {name})
        inherited = AIEvaluationAddon.create(
            project=self.project, configuration=self.configuration, run=False
        )
        self.component.drop_addons_cache()
        update_alerts(self.component, {name})
        self.assertFalse(self.component.alert_set.filter(name=name).exists())
        inherited.instance.delete()
        self.component.is_glossary = True
        update_alerts(self.component, {name})
        self.assertFalse(self.component.alert_set.filter(name=name).exists())

    def test_deleted_addon_does_not_contact_service(self) -> None:
        addon_id = self.addon.instance.pk
        self.addon.instance.delete()
        with patch.object(OpenAITranslation, "fetch_llm_translations") as fetch:
            evaluate_quality(addon_id, [self.component.pk], self.configuration)
        fetch.assert_not_called()

    def test_missing_components_are_logged_as_skipped(self) -> None:
        for component_ids in ([], [-1]):
            with self.subTest(component_ids=component_ids):
                activity = AddonActivityLog.objects.create(
                    addon=self.addon.instance,
                    component=self.component,
                    event=AddonEvent.EVENT_MANUAL,
                )
                with patch.object(OpenAITranslation, "fetch_llm_translations") as fetch:
                    evaluate_quality(
                        self.addon.instance.pk,
                        component_ids,
                        self.configuration,
                        activity_log_id=activity.pk,
                    )
                fetch.assert_not_called()
                activity.refresh_from_db()
                self.assertEqual(activity.status, AddonActivityLogStatus.SKIPPED)
                self.assertEqual(activity.details["result"], {})

    def test_evaluation_omits_check_context(self) -> None:
        self.evaluate()
        unit = Unit.objects.get(pk=self.unit.pk)
        service = OpenAITranslation(self.service_settings)
        with patch.object(
            service,
            "_get_failing_checks_context",
            side_effect=AssertionError("Evaluation must not load check context"),
        ):
            _prompt, content = service.build_evaluation_request([unit])
        for string in json.loads(content)["units"][0]["strings"]:
            self.assertNotIn("failing_checks", string)

    def test_ineligible_units_do_not_contact_service(self) -> None:
        for flag in (
            "ignore-all-checks",
            ",".join(f"ignore-{name.replace('_', '-')}" for name in AI_CHECKS),
        ):
            Unit.objects.filter(pk=self.unit.pk).update(extra_flags=flag)
            with patch.object(OpenAITranslation, "fetch_llm_translations") as fetch:
                evaluate_quality(
                    self.addon.instance.pk, [self.component.pk], self.configuration
                )
            fetch.assert_not_called()

    def test_plural_context_and_placeholders(self) -> None:
        unit = Unit.objects.get(pk=self.unit.pk)
        unit.source = join_plural(["One file", "%d files"])
        unit.target = join_plural(["Jeden soubor", "%d soubory", "%d souborů"])
        unit.extra_flags = "python-format"
        unit.context = "file-count"
        unit.source_unit.explanation = "Number of files to copy"
        service = OpenAITranslation({**self.service_settings, "_project": self.project})
        _prompt, content = service.build_evaluation_request([unit])
        payload = json.loads(content)
        self.assertEqual(payload["units"][0]["translations"], unit.get_target_plurals())
        self.assertEqual(len(payload["units"][0]["translations"]), 3)
        self.assertEqual(
            payload["units"][0]["strings"][1]["placeholders"], {"@@PH0@@": "%d"}
        )
        self.assertEqual(payload["units"][0]["strings"][0]["context"], "file-count")
        self.assertEqual(
            payload["units"][0]["strings"][0]["explanation"], "Number of files to copy"
        )
        self.assertIn("plural=", payload["target_plural_formula"])

    def test_scope_precedence(self) -> None:
        project_addon = AIEvaluationAddon.create(
            project=self.project, configuration=self.configuration, run=False
        )
        self.component.drop_addons_cache()
        self.assertEqual(effective_evaluator(self.component), self.addon.instance)
        with patch("weblate.addons.tasks.evaluate_quality.delay_on_commit") as task:
            project_addon.manual(project=self.project)
        task.assert_not_called()

    def test_form_and_public_configuration(self) -> None:
        form = AIEvaluationForm(self.user, self.addon, data=self.configuration)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(self.addon.get_public_configuration(), self.configuration)
        form = AIEvaluationForm(
            self.user, self.addon, data={**self.configuration, "service": "invalid"}
        )
        self.assertFalse(form.is_valid())

    def test_payload_and_separate_operation(self) -> None:
        self.unit.target = "Broken %placeholder <b>"
        service = OpenAITranslation({**self.service_settings, "_project": self.project})
        with patch.object(
            service,
            "fetch_llm_translations",
            return_value=evaluation_response({self.unit.pk: []}),
        ) as fetch:
            self.assertEqual(service.evaluate(self.unit), [])
        prompt, content, _example, example_response = fetch.call_args.args
        payload = json.loads(content)
        self.assertEqual(payload["units"][0]["translations"], [self.unit.target])
        self.assertEqual(payload["units"][0]["strings"][0]["source"], self.unit.source)
        self.assertEqual(payload["target_language"], "cs")
        self.assertIn("glossary", payload)
        self.assertIn("Use Czech terminology", prompt)
        self.assertNotIn("failing_checks", payload["units"][0]["strings"][0])
        self.assertEqual(
            json.loads(example_response), {"results": [{"unit_id": 1, "issues": []}]}
        )

    def create_batch_units(self, count: int, language: str = "cs") -> list[Unit]:
        sources = Unit.objects.bulk_create(
            [
                Unit(
                    translation=self.component.source_translation,
                    id_hash=calculate_hash(f"batch:{language}:{index}"),
                    source="Bank",
                    target="Bank",
                    context=f"batch:{language}:{index}",
                    position=(count - index) // 2,
                    state=STATE_TRANSLATED,
                )
                for index in range(count)
            ]
        )
        translation = self.get_translation(language)
        units = Unit.objects.bulk_create(
            [
                Unit(
                    translation=translation,
                    source_unit=source,
                    id_hash=source.id_hash,
                    source=source.source,
                    context=source.context,
                    target=f"Translation {index}",
                    position=source.position,
                    state=STATE_TRANSLATED,
                )
                for index, source in enumerate(sources)
            ]
        )
        self.configuration["q"] = "context:batch"
        self.addon.instance.configuration = self.configuration
        self.addon.instance.save(update_fields=["configuration"])
        return sorted(units, key=lambda unit: (unit.position, unit.pk))

    @staticmethod
    def respond_to_batch(
        _prompt: str, content: str, _example: str, _response: str
    ) -> str:
        # Deliberately reverse results; source text is identical for all units.
        return evaluation_response(
            {
                item["unit_id"]: [
                    {**ISSUE, "explanation": f"Issue for {item['unit_id']}"}
                ]
                for item in reversed(json.loads(content)["units"])
            }
        )

    def run_batch_evaluation(self, *, scheduled: bool = False) -> dict[str, int]:
        activity = AddonActivityLog.objects.create(
            addon=self.addon.instance,
            component=self.component,
            event=AddonEvent.EVENT_MANUAL,
        )
        evaluate_quality(
            self.addon.instance.pk,
            [self.component.pk],
            self.configuration,
            scheduled=scheduled,
            activity_log_id=activity.pk,
        )
        activity.refresh_from_db()
        return cast(
            "dict[str, int]", activity.details["result"][self.component.full_slug]
        )

    def test_default_batch_size_and_reordered_results(self) -> None:
        units = self.create_batch_units(21)
        with patch.object(
            OpenAITranslation,
            "fetch_llm_translations",
            side_effect=self.respond_to_batch,
        ) as fetch:
            result = self.run_batch_evaluation(scheduled=True)
        self.assertEqual(result, {"evaluated": 21, "failed": 0, "skipped": 0})
        self.assertEqual(fetch.call_count, 2)
        batches = [json.loads(call.args[1])["units"] for call in fetch.call_args_list]
        self.assertEqual([len(batch) for batch in batches], [20, 1])
        self.assertEqual(
            [item["unit_id"] for batch in batches for item in batch],
            [unit.pk for unit in units],
        )
        for unit in units:
            self.assertIn(
                f"Issue for {unit.pk}",
                unit.check_set.get(name="ai_accuracy").get_plain_description(),
            )

    def test_provider_batch_size_and_translation_boundaries(self) -> None:
        units = [*self.create_batch_units(3), *self.create_batch_units(3, "de")]
        with (
            patch.object(OpenAITranslation, "batch_size", 2),
            patch.object(
                OpenAITranslation,
                "fetch_llm_translations",
                side_effect=self.respond_to_batch,
            ) as fetch,
        ):
            self.assertEqual(self.run_batch_evaluation()["evaluated"], 6)
        payloads = [json.loads(call.args[1]) for call in fetch.call_args_list]
        self.assertEqual([len(payload["units"]) for payload in payloads], [2, 1, 2, 1])
        by_id = {unit.pk: unit for unit in units}
        for payload in payloads:
            batch_units = [by_id[item["unit_id"]] for item in payload["units"]]
            self.assertEqual(len({unit.translation_id for unit in batch_units}), 1)
            self.assertEqual(
                payload["target_language"], batch_units[0].translation.language.code
            )

    def test_failed_batch_preserves_findings_and_continues(self) -> None:
        units = self.create_batch_units(5)
        with patch.object(
            OpenAITranslation,
            "fetch_llm_translations",
            side_effect=self.respond_to_batch,
        ):
            self.run_batch_evaluation()

        def response(prompt: str, content: str, example: str, reply: str) -> str:
            inputs = json.loads(content)["units"]
            if inputs[0]["unit_id"] == units[0].pk:
                # One clean entry is missing: none of this batch may be cleared.
                return evaluation_response({inputs[0]["unit_id"]: []})
            return evaluation_response({item["unit_id"]: [] for item in inputs})

        with (
            patch.object(OpenAITranslation, "batch_size", 2),
            patch.object(
                OpenAITranslation, "fetch_llm_translations", side_effect=response
            ) as fetch,
        ):
            result = self.run_batch_evaluation()
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(result, {"evaluated": 3, "failed": 2, "skipped": 0})
        self.assertEqual(
            set(
                Check.objects.filter(unit__in=units, name="ai_accuracy").values_list(
                    "unit_id", flat=True
                )
            ),
            {unit.pk for unit in units[:2]},
        )

    def test_stale_batch_is_discarded_before_any_writes(self) -> None:
        units = self.create_batch_units(2)
        changed = units[-1]
        mutations: dict[str, Callable[[], object]] = {
            "target": lambda: Unit.objects.filter(pk=changed.pk).update(
                target="Changed"
            ),
            "source": lambda: Unit.objects.filter(pk=changed.source_unit.pk).update(
                source="Changed"
            ),
            "deleted": lambda: Unit.objects.filter(pk=changed.pk).delete(),
            "ineligible": lambda: Unit.objects.filter(pk=changed.pk).update(
                extra_flags="ignore-all-checks"
            ),
            "configuration": lambda: Addon.objects.filter(
                pk=self.addon.instance.pk
            ).update(configuration={**self.configuration, "q": "state:empty"}),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name), transaction.atomic():

                def response(
                    prompt: str,
                    content: str,
                    example: str,
                    reply: str,
                    mutate: Callable[[], object] = mutate,
                ) -> str:
                    mutate()
                    return self.respond_to_batch(prompt, content, example, reply)

                with patch.object(
                    OpenAITranslation, "fetch_llm_translations", side_effect=response
                ):
                    self.assertEqual(
                        self.run_batch_evaluation(),
                        {"evaluated": 0, "failed": 0, "skipped": 2},
                    )
                self.assertFalse(
                    Check.objects.filter(unit__in=units, name__in=AI_CHECKS).exists()
                )
                self.addon.instance.refresh_from_db()
                self.assertTrue(self.addon.is_schedule_due(self.component))
                transaction.set_rollback(True)
            self.addon.instance.refresh_from_db()

    def test_batch_database_failure_rolls_back_all_findings(self) -> None:
        units = self.create_batch_units(2)
        with (
            patch.object(
                OpenAITranslation,
                "fetch_llm_translations",
                side_effect=self.respond_to_batch,
            ),
            patch(
                "weblate.addons.ai.refresh_evaluation_checks",
                side_effect=[None, RuntimeError("storage failure")],
            ),
            self.assertRaisesMessage(RuntimeError, "storage failure"),
        ):
            self.run_batch_evaluation()
        self.assertFalse(
            Check.objects.filter(unit__in=units, name__in=AI_CHECKS).exists()
        )

    def test_evaluate_batch_input_validation(self) -> None:
        units = [self.unit, self.get_unit(language="de")]
        service = OpenAITranslation(self.service_settings)
        with patch.object(service, "fetch_llm_translations") as fetch:
            self.assertEqual(service.evaluate_batch([]), {})
            for batch in (units, [self.unit, self.unit]):
                with (
                    self.subTest(ids=[unit.pk for unit in batch]),
                    self.assertRaises(ValueError),
                ):
                    service.evaluate_batch(batch)
        fetch.assert_not_called()
