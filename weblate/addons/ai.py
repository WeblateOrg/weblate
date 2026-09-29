# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from itertools import batched, groupby
from operator import attrgetter
from typing import TYPE_CHECKING, ClassVar, TypedDict, cast

import httpx2
from django import forms
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext_lazy

from weblate.addons.base import BaseAddon
from weblate.addons.events import AddonActivityLogReason, AddonEvent, AddonEventOutcome
from weblate.addons.forms import BaseAddonForm
from weblate.checks.ai import AI_CHECKS, evaluation_fingerprint
from weblate.checks.models import CHECKS
from weblate.configuration.models import Setting, SettingCategory
from weblate.machinery.base import MachineTranslationError
from weblate.machinery.llm import BaseLLMTranslation
from weblate.machinery.models import MACHINERY
from weblate.trans.actions import ACTIONS_CONTENT, ActionEvents
from weblate.trans.alerts.registry import update_alerts
from weblate.trans.models import Unit
from weblate.utils.forms import QueryField
from weblate.utils.lock import WeblateLock

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from weblate.addons.models import Addon
    from weblate.auth.models import User
    from weblate.machinery.evaluation import EvaluationIssue
    from weblate.trans.models import Category, Change, Component, Project
    from weblate.trans.models.unit import UnitQuerySet


def available_evaluation_services(configured: Iterable[str]) -> list[str]:
    """Return configured services that support quality evaluation."""
    return [
        key
        for key in configured
        if key in MACHINERY and issubclass(MACHINERY[key], BaseLLMTranslation)
    ]


class AIEvaluationConfiguration(TypedDict, total=False):
    service: str
    q: str
    interval: str
    on_change: bool
    on_update: bool


class AIEvaluationForm(BaseAddonForm[AIEvaluationConfiguration, "AIEvaluationAddon"]):
    public_configuration_fields = frozenset(
        {"service", "q", "interval", "on_change", "on_update"}
    )
    service = forms.ChoiceField(label=gettext_lazy("Evaluation service"))
    q = QueryField(initial="state:>=translated")
    interval = forms.ChoiceField(
        label=gettext_lazy("Evaluation frequency"),
        initial="weekly",
        choices=(
            ("disabled", gettext_lazy("Disabled")),
            ("daily", gettext_lazy("Daily")),
            ("weekly", gettext_lazy("Weekly")),
            ("monthly", gettext_lazy("Monthly")),
        ),
    )
    on_change = forms.BooleanField(
        label=gettext_lazy("Evaluate translation changes"), required=False
    )
    on_update = forms.BooleanField(
        label=gettext_lazy("Evaluate repository updates"), required=False
    )

    def __init__(
        self,
        user: User | None,
        addon: AIEvaluationAddon,
        instance: Addon | None = None,
        *args: object,
        **kwargs: object,
    ) -> None:
        super().__init__(user, addon, instance, *args, **kwargs)
        service_field = cast("forms.ChoiceField", self.fields["service"])
        if addon.documentation_build:
            service_field.choices = [
                (key, service.name)
                for key, service in MACHINERY.items()
                if issubclass(service, BaseLLMTranslation)
            ]
            return
        storage = addon.instance
        project = storage.project
        if storage.component is not None:
            project = storage.component.project
        elif storage.category is not None:
            project = storage.category.project
        configured = (
            project.get_machinery_settings()
            if project
            else Setting.objects.get_settings_dict(SettingCategory.MT)
        )
        service_field.choices = [
            (key, MACHINERY[key].name)
            for key in available_evaluation_services(configured)
        ]


def effective_evaluator(component: Component) -> Addon | None:
    """Prefer component, nearest category, project, then site configuration."""
    categories = []
    category = component.category
    while category is not None:
        categories.append(category.pk)
        category = category.category

    def priority(addon: Addon) -> tuple[int, int]:
        if addon.component_id:
            return (0, addon.pk)
        if addon.category_id:
            return (1 + categories.index(addon.category_id), addon.pk)
        return (5 if addon.project_id else 6, addon.pk)

    return min(
        (
            addon
            for addon in component.addons_cache.addons
            if addon.name == AIEvaluationAddon.name
        ),
        key=priority,
        default=None,
    )


def refresh_evaluation_checks(unit: Unit) -> None:
    unit.clear_checks_cache()
    unit.source_unit.clear_checks_cache()
    unit.source_unit.run_checks()
    unit.translation.invalidate_cache()


class AIEvaluationAddon(
    BaseAddon[AIEvaluationConfiguration, AIEvaluationConfiguration]
):
    name = "weblate.ai.quality"
    verbose = gettext_lazy("AI quality evaluation")
    description = gettext_lazy(
        "Evaluates existing translations using an LLM and records quality checks."
    )
    alert = "AIEvaluationUnavailable"
    settings_form = AIEvaluationForm
    icon = "language.svg"
    events: ClassVar[set[AddonEvent]] = {
        AddonEvent.EVENT_CHANGE,
        AddonEvent.EVENT_COMPONENT_UPDATE,
        AddonEvent.EVENT_DAILY,
        AddonEvent.EVENT_MANUAL,
    }
    INTERVALS: ClassVar[dict[str, int]] = {"daily": 1, "weekly": 7, "monthly": 30}

    def __init__(self, storage: Addon) -> None:
        super().__init__(storage)
        self.storage_id = storage.pk

    def normalize_configuration(
        self, configuration: AIEvaluationConfiguration
    ) -> AIEvaluationConfiguration:
        return {
            "service": configuration.get("service", ""),
            "q": configuration.get("q", "state:>=translated"),
            "interval": configuration.get("interval", "weekly"),
            "on_change": configuration.get("on_change", False),
            "on_update": configuration.get("on_update", False),
        }

    def cleanup_checks(self) -> None:
        storage_id = self.instance.pk or self.storage_id
        units = Unit.objects.filter(
            check__name__in=AI_CHECKS, check__metadata__addon_id=storage_id
        ).distinct()
        for unit in units.iterator(chunk_size=200):
            unit.check_set.filter(
                name__in=AI_CHECKS, metadata__addon_id=storage_id
            ).delete()
            refresh_evaluation_checks(unit)

    def configure(self, configuration: AIEvaluationConfiguration) -> None:
        if configuration != self.instance.configuration:
            with transaction.atomic():
                type(self.instance).objects.select_for_update().get(pk=self.instance.pk)
                self.cleanup_checks()
                self.instance.state = {}
                super().configure(configuration)
        else:
            super().configure(configuration)

    def post_uninstall(self) -> None:
        self.cleanup_checks()
        self.refresh_diagnostics()

    def post_configure_run(self) -> None:
        self.refresh_diagnostics()

    def refresh_diagnostics(self) -> None:
        # Refresh diagnostics without initiating paid requests.
        for component in self.instance.affected_components():
            component.drop_addons_cache()
            update_alerts(component, {self.alert})

    def is_schedule_due(self, component: Component) -> bool:
        interval = self.INTERVALS.get(self.get_configuration()["interval"])
        if interval is None:
            return False
        last_run = self.get_component_state(component).get("last_run")
        if not isinstance(last_run, str):
            return True
        try:
            last_date = date.fromisoformat(last_run)
        except ValueError:
            return True
        return timezone.now().date() - last_date >= timedelta(days=interval)

    def queue(
        self,
        components: list[Component],
        *,
        activity_log_id: int | None = None,
        unit_ids: list[int] | None = None,
        scheduled: bool = False,
    ) -> AddonEventOutcome:
        from weblate.addons.tasks import evaluate_quality  # ruff: ignore[import-outside-top-level]

        component_ids = [
            component.pk
            for component in components
            if not component.is_glossary
            and (effective := effective_evaluator(component)) is not None
            and effective.pk == self.instance.pk
            and (not scheduled or self.is_schedule_due(component))
        ]
        if not component_ids:
            return AddonEventOutcome.skipped(AddonActivityLogReason.NOT_APPLICABLE)
        evaluate_quality.delay_on_commit(
            self.instance.pk,
            component_ids,
            self.get_configuration(),
            unit_ids=unit_ids,
            scheduled=scheduled,
            activity_log_id=activity_log_id,
        )
        return AddonEventOutcome.pending()

    def manual(
        self,
        component: Component | None = None,
        category: Category | None = None,
        project: Project | None = None,
        activity_log_id: int | None = None,
    ) -> AddonEventOutcome:
        return self.queue(
            list(
                self.resolve_components(
                    component=component, category=category, project=project
                )
            ),
            activity_log_id=activity_log_id,
        )

    def daily(
        self,
        component: Component | None = None,
        category: Category | None = None,
        project: Project | None = None,
        activity_log_id: int | None = None,
    ) -> AddonEventOutcome:
        if settings.BACKGROUND_TASKS == "never":
            return AddonEventOutcome.skipped(
                AddonActivityLogReason.BACKGROUND_TASKS_DISABLED
            )
        return self.queue(
            list(
                self.resolve_components(
                    component=component, category=category, project=project
                )
            ),
            scheduled=True,
            activity_log_id=activity_log_id,
        )

    def component_update(
        self, component: Component, activity_log_id: int | None = None
    ) -> AddonEventOutcome:
        if not self.get_configuration()["on_update"]:
            return AddonEventOutcome.skipped(AddonActivityLogReason.NOT_APPLICABLE)
        return self.queue([component], activity_log_id=activity_log_id)

    def check_change_action(self, change: Change) -> bool:
        return (
            self.get_configuration()["on_change"]
            and change.unit_id is not None
            and change.action in ACTIONS_CONTENT
            and change.action != ActionEvents.ENFORCED_CHECK
        )

    def change_event(
        self, change: Change, activity_log_id: int | None = None
    ) -> AddonEventOutcome:
        if not self.check_change_action(change):
            return AddonEventOutcome.skipped(AddonActivityLogReason.NO_RELEVANT_CHANGES)
        unit = change.unit
        if unit is None:
            return AddonEventOutcome.skipped(AddonActivityLogReason.TARGET_MISSING)
        unit_ids = (
            list(unit.unit_set.values_list("pk", flat=True))
            if unit.is_source
            else [unit.pk]
        )
        return self.queue(
            [unit.translation.component],
            unit_ids=unit_ids,
            activity_log_id=activity_log_id,
        )


def evaluation_units(
    component: Component, configuration: AIEvaluationConfiguration
) -> UnitQuerySet:
    return (
        Unit.objects.filter(translation__component=component)
        .exclude(source_unit_id=F("pk"))
        .exclude(source_unit_id__isnull=True)
        .search(configuration["q"])
    )


def evaluation_eligible(unit: Unit) -> bool:
    return (
        unit.translated
        and not unit.readonly
        and not unit.is_source
        and not unit.translation.component.is_glossary
        and any(
            not CHECKS[name].should_skip(unit) for name in AI_CHECKS if name in CHECKS
        )
    )


@dataclass(frozen=True)
class EvaluationSnapshot:
    fingerprint: str
    last_updated: datetime


def evaluation_snapshot(unit: Unit) -> EvaluationSnapshot:
    return EvaluationSnapshot(evaluation_fingerprint(unit), unit.last_updated)


def evaluation_batches(units: UnitQuerySet, batch_size: int) -> Iterator[list[Unit]]:
    ordered = units.select_related(
        "translation__component__project",
        "translation__language",
        "translation__plural",
        "source_unit",
    ).order_by("translation_id", "position", "pk")
    for _translation_id, translation_units in groupby(
        ordered.iterator(chunk_size=200), key=attrgetter("translation_id")
    ):
        eligible = (unit for unit in translation_units if evaluation_eligible(unit))
        for batch in batched(eligible, batch_size):
            yield list(batch)


def apply_evaluation(
    unit: Unit, issues: list[EvaluationIssue], *, addon_id: int, fingerprint: str
) -> None:
    """Replace one unit's findings inside the validated batch transaction."""
    names = []
    for name in AI_CHECKS:
        if name not in CHECKS or CHECKS[name].should_skip(unit):
            continue
        findings = [issue for issue in issues if f"ai_{issue['category']}" == name]
        if not findings:
            continue
        names.append(name)
        check, _created = unit.check_set.get_or_create(name=name)
        if check.metadata.get("fingerprint") != fingerprint:
            check.dismissed = False
        check.metadata = {
            "issues": findings,
            "fingerprint": fingerprint,
            "addon_id": addon_id,
        }
        check.save(update_fields=["metadata", "dismissed"])
    unit.check_set.filter(name__in=AI_CHECKS).exclude(name__in=names).delete()
    refresh_evaluation_checks(unit)


def store_evaluation_batch(
    addon: AIEvaluationAddon,
    units: list[Unit],
    results: dict[int, list[EvaluationIssue]],
    configuration: AIEvaluationConfiguration,
    snapshots: dict[int, EvaluationSnapshot],
) -> bool:
    """Apply the whole batch only while every participating unit is current."""
    from weblate.addons.models import Addon  # ruff: ignore[import-outside-top-level]

    with transaction.atomic():
        storage = Addon.objects.select_for_update().filter(pk=addon.instance.pk).first()
        if storage is None or storage.addon.get_configuration() != configuration:
            return False
        locked = {
            item.pk: item
            for item in Unit.objects.filter(pk__in=snapshots)
            .order_by("pk")
            .select_for_update()
        }
        if locked.keys() != snapshots.keys() or any(
            evaluation_snapshot(current) != snapshots[pk]
            for pk, current in locked.items()
        ):
            return False
        component = locked[units[0].pk].translation.component
        effective = effective_evaluator(component)
        if effective is None or effective.pk != storage.pk:
            return False
        unit_ids = {unit.pk for unit in units}
        selected_ids = set(
            evaluation_units(component, configuration)
            .filter(pk__in=unit_ids)
            .values_list("pk", flat=True)
        )
        if selected_ids != unit_ids:
            return False
        for unit in units:
            current = locked[unit.pk]
            if (
                current.source_unit_id != unit.source_unit_id
                or current.translation_id != unit.translation_id
                or not evaluation_eligible(current)
            ):
                return False
        # No writes before every member of the shared context has been validated.
        for unit in units:
            apply_evaluation(
                locked[unit.pk],
                results[unit.pk],
                addon_id=storage.pk,
                fingerprint=snapshots[unit.pk].fingerprint,
            )
    return True


def evaluate_component(
    addon: AIEvaluationAddon,
    component: Component,
    configuration: AIEvaluationConfiguration,
    unit_ids: Iterable[int] | None,
    *,
    scheduled: bool,
    evaluated_unit_ids: set[int] | None = None,
) -> dict[str, int]:
    from weblate.addons.models import Addon  # ruff: ignore[import-outside-top-level]

    result = {"evaluated": 0, "failed": 0, "skipped": 0}
    lock = WeblateLock(
        scope="ai-evaluation", key=component.pk, slug=component.full_slug
    )
    with lock:
        component.drop_addons_cache()
        effective = effective_evaluator(component)
        if (
            effective is None
            or effective.pk != addon.instance.pk
            or effective.addon.get_configuration() != configuration
            or component.is_glossary
        ):
            return result
        addon = AIEvaluationAddon(effective)
        if scheduled and not addon.is_schedule_due(component):
            return result
        service_key = configuration["service"]
        configured = component.project.get_machinery_settings()
        update_alerts(component, {addon.alert})
        if service_key not in available_evaluation_services(configured):
            msg = "The configured evaluation service is unavailable."
            raise MachineTranslationError(msg)
        service_class = cast("type[BaseLLMTranslation]", MACHINERY[service_key])
        service = service_class(configured[service_key])
        units = evaluation_units(component, configuration)
        if unit_ids is not None:
            units = units.filter(pk__in=unit_ids)
        for batch in evaluation_batches(units, service.batch_size):
            lock.reacquire()
            # Stop a queued sweep when its installation changes or disappears.
            if not Addon.objects.filter(
                pk=effective.pk, configuration=effective.configuration
            ).exists():
                result["skipped"] += len(batch)
                break
            if service.is_rate_limited():
                result["skipped"] += len(batch)
                continue
            snapshots = {
                item.pk: evaluation_snapshot(item)
                for unit in batch
                for item in (unit, unit.source_unit)
            }
            try:
                issues = service.evaluate_batch(batch)
            except (MachineTranslationError, httpx2.HTTPError) as error:
                # Do not persist provider response bodies or credentials in activity logs.
                if service.is_rate_limit_error(error):
                    service.set_rate_limit()
                result["failed"] += len(batch)
                continue
            if store_evaluation_batch(addon, batch, issues, configuration, snapshots):
                result["evaluated"] += len(batch)
                if evaluated_unit_ids is not None:
                    evaluated_unit_ids.update(unit.pk for unit in batch)
            else:
                result["skipped"] += len(batch)
        if unit_ids is None and not result["failed"] and not result["skipped"]:
            with transaction.atomic():
                storage = (
                    Addon.objects.select_for_update()
                    .filter(
                        pk=effective.pk,
                        configuration=effective.configuration,
                    )
                    .first()
                )
                if storage is not None:
                    addon.update_component_state(
                        component,
                        lambda state: state.update(
                            {"last_run": timezone.now().date().isoformat()}
                        ),
                    )
    return result
