# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from celery import current_task
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from django.db.models.functions import MD5, Lower
from django.utils.translation import gettext, ngettext

from weblate.machinery.base import MachineTranslationError
from weblate.machinery.models import MACHINERY
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Category, Component, Suggestion, Translation, Unit
from weblate.trans.util import is_plural, split_plural
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_FUZZY,
    STATE_READONLY,
    STATE_TRANSLATED,
)
from weblate.utils.stats import ProjectLanguage

if TYPE_CHECKING:
    from collections.abc import Sequence

    from weblate.auth.models import User
    from weblate.machinery.base import BatchMachineTranslation, UnitMemoryResultDict
    from weblate.utils.state import StringState


class BaseAutoTranslate:
    updated: int = 0
    progress_steps: int = 0

    def __init__(
        self,
        *,
        user: User | None,
        q: str,
        mode: str,
        component_wide: bool = False,
        unit_ids: list[int] | None = None,
        allow_non_shared_tm_source_components: bool = False,
    ) -> None:
        self.user: User | None = user
        self.q: str = q
        self.mode: str = mode
        self.component_wide: bool = component_wide
        self.unit_ids: list[int] | None = unit_ids
        self.allow_non_shared_tm_source_components = (
            allow_non_shared_tm_source_components
        )
        self.failure_message: str | None = None
        self.warnings: list[str] = []

    def get_message(self) -> str:
        if self.updated == 0:
            return gettext("Automatic translation completed, no strings were updated.")
        message = ngettext(
            "Automatic translation completed, %d string was updated.",
            "Automatic translation completed, %d strings were updated.",
            self.updated,
        )
        try:
            return message % self.updated
        except TypeError:
            return message

    def get_task_meta(self) -> dict[str, Any]:
        """Return a metadata dictionary for Celery task progress tracking."""
        raise NotImplementedError

    def add_warning(self, warning: str) -> None:
        if warning not in self.warnings:
            self.warnings.append(warning)

    def get_warnings(self) -> list[str]:
        return self.warnings

    def set_progress(self, current: int) -> None:
        if current_task and current_task.request.id and self.progress_steps:
            current_task.update_state(
                state="PROGRESS",
                meta=self.get_task_meta()
                | {"progress": 100 * current // self.progress_steps},
            )


class AutoTranslate(BaseAutoTranslate):
    def __init__(
        self,
        *,
        translation: Translation,
        user: User | None,
        q: str,
        mode: str,
        component_wide: bool = False,
        unit_ids: list[int] | None = None,
        allow_non_shared_tm_source_components: bool = False,
    ) -> None:
        super().__init__(
            user=user,
            q=q,
            mode=mode,
            component_wide=component_wide,
            unit_ids=unit_ids,
            allow_non_shared_tm_source_components=(
                allow_non_shared_tm_source_components
            ),
        )
        self.translation: Translation = translation
        translation.component.start_batched_checks()
        self.progress_base = 0
        self.target_state = STATE_TRANSLATED
        if self.mode == "fuzzy":
            self.target_state = STATE_FUZZY
        elif self.mode == "approved" and translation.enable_review:
            self.target_state = STATE_APPROVED

    def get_units(self):
        units = self.translation.unit_set.exclude(state=STATE_READONLY)
        if self.unit_ids is not None:
            units = units.filter(pk__in=self.unit_ids)
        if self.mode == "suggest":
            units = units.filter(suggestion__isnull=True)
        return units.search(self.q, parser="unit")

    def get_task_meta(self) -> dict[str, Any]:
        return {"translation": self.translation.pk}

    def update(
        self, unit: Unit, state: StringState, target: list[str], user=None
    ) -> None:
        if isinstance(target, str):
            target = [target]
        max_length = unit.get_max_length()
        if self.mode == "suggest" or any(len(item) > max_length for item in target):
            suggestion = Suggestion.objects.add(
                unit,
                target,
                request=None,
                vote=False,
                user=user or self.user,
                raise_exception=False,
            )
            if suggestion:
                self.updated += 1
        else:
            # Ensure deferred changes accumulate on the right Translation instance
            unit.translation = self.translation
            unit.is_batch_update = True
            unit.translate(
                user or self.user,
                target,
                state,
                change_action=ActionEvents.AUTO,
                propagate=False,
                select_for_update=False,
            )
            self.updated += 1

    def post_process(self) -> None:
        if self.updated > 0:
            self.translation.log_info("finalizing automatic translation")
            self.translation.store_update_changes()
            if not self.component_wide:
                self.translation.component.run_batched_checks()
            self.translation.invalidate_cache()
            if self.user:
                self.user.profile.increase_count("translated", self.updated)

    def collect_other_translations(
        self, filtered_sources, component_ids: list[int]
    ) -> dict[str, list[str]]:
        """Collect candidate translations while preserving source priority."""
        translations: dict[str, list[str]] = {}
        mismatched_translation_ids: set[int] = set()
        target_plural_id = self.translation.plural_id

        if component_ids:
            component_priority = {
                component_id: index for index, component_id in enumerate(component_ids)
            }
            translation_priority: dict[str, int] = {}
            source_units = (
                filtered_sources.annotate(
                    component_priority=Case(
                        *[
                            When(
                                translation__component_id=component_id,
                                then=priority,
                            )
                            for component_id, priority in component_priority.items()
                        ],
                        output_field=IntegerField(),
                    )
                )
                .order_by("component_priority", "translation_id")
                .values_list(
                    "translation__component_id",
                    "source",
                    "target",
                    "translation_id",
                    "translation__plural_id",
                )
            )
            for (
                component_id,
                source,
                target,
                translation_id,
                plural_id,
            ) in source_units:
                if plural_id != target_plural_id and (
                    is_plural(source) or is_plural(target)
                ):
                    mismatched_translation_ids.add(translation_id)
                    continue
                priority = component_priority[component_id]
                if priority >= translation_priority.get(source, len(component_ids)):
                    continue
                translations[source] = split_plural(target)
                translation_priority[source] = priority
        else:
            source_units = filtered_sources.values_list(
                "source", "target", "translation_id", "translation__plural_id"
            ).order_by("translation_id")
            for source, target, translation_id, plural_id in source_units:
                if plural_id != target_plural_id and (
                    is_plural(source) or is_plural(target)
                ):
                    mismatched_translation_ids.add(translation_id)
                    continue
                translations.setdefault(source, split_plural(target))

        mismatched_components = (
            Component.objects.filter(translation__in=mismatched_translation_ids)
            .defer_huge()
            .prefetch()
            .distinct()
            .order_project()
        )
        for component in mismatched_components:
            self.add_warning(
                gettext(
                    "Plural forms in %(component)s do not match the target translation. "
                    "Automatic translation skipped pluralized strings and processed only single-form strings."
                )
                % {"component": component}
            )

        return translations

    @transaction.atomic
    def process_others(self, source_component_ids: list[int] | None) -> None:
        """Perform automatic translation based on other components."""
        sources = Unit.objects.filter(
            translation__language=self.translation.language,
            state__gte=STATE_TRANSLATED,
        )
        source_language = self.translation.component.source_language
        component_ids = list(dict.fromkeys(source_component_ids or []))
        if component_ids:
            components = list(Component.objects.filter(id__in=component_ids))
            component_map = {component.id: component for component in components}
            if len(component_map) != len(component_ids):
                raise Component.DoesNotExist

            for component_id in component_ids:
                component = component_map[component_id]
                if not self.allow_non_shared_tm_source_components and (
                    not component.project.contribute_shared_tm
                    and component.project != self.translation.component.project
                ):
                    msg = "Project has disabled contribution to shared translation memory."
                    raise PermissionDenied(msg)
                if component.source_language != source_language:
                    msg = "Component have different source languages."
                    raise PermissionDenied(msg)
            sources = sources.filter(translation__component_id__in=component_ids)
        else:
            project = self.translation.component.project
            sources = sources.filter(
                translation__component__project=project,
                translation__component__source_language=source_language,
            ).exclude(translation=self.translation)

        # Use memory_db for the query in case it exists. This is supposed
        # to be a read-only replica for offloading expensive translation
        # queries.
        if "memory_db" in settings.DATABASES:
            sources = sources.using("memory_db")

        # Get source MD5s
        source_md5s = list(
            self.get_units()
            .annotate(source__lower__md5=MD5(Lower("source")))
            .values_list("source__lower__md5", flat=True)
        )

        # Fetch available translations
        filtered_sources = sources.filter(source__lower__md5__in=source_md5s)
        translations = self.collect_other_translations(filtered_sources, component_ids)

        # Fetch translated unit IDs
        # Cannot use get_units() directly as SELECT FOR UPDATE cannot be used with JOIN
        unit_ids = list(
            self.get_units()
            .filter(
                source__lower__md5__in=[
                    MD5(Lower(Value(translation))) for translation in translations
                ]
            )
            .values_list("id", flat=True)
        )
        units = (
            Unit.objects.filter(pk__in=unit_ids)
            .prefetch()
            .prefetch_bulk()
            .select_for_update()
        )
        self.progress_steps = len(units)

        for pos, unit in enumerate(units):
            # Get update
            try:
                target = translations[unit.source]
            except KeyError:
                # Happens due to case-insensitive lookup
                continue

            self.set_progress(pos)

            # No save if translation is same or unit does not exist
            if unit.state == self.target_state and unit.target == target:
                continue
            # Copy translation
            self.update(unit, self.target_state, target)

        self.post_process()

    def fetch_mt(
        self, engines_list: list[str], threshold: int
    ) -> dict[int, UnitMemoryResultDict]:
        """Get the translations."""
        units: list[Unit] = list(self.get_units().select_related("source_unit"))
        num_units = len(units)

        machinery_settings = self.translation.component.project.get_machinery_settings()

        engines: list[BatchMachineTranslation] = sorted(
            (
                MACHINERY[engine](setting)
                for engine, setting in machinery_settings.items()
                if engine in MACHINERY and engine in engines_list
            ),
            key=lambda engine: engine.get_rank(),
            reverse=True,
        )

        self.progress_base = len(engines) * num_units
        # Estimate number of strings to translate, this is adjusted in process_mt
        self.progress_steps = self.progress_base + num_units

        for pos, translation_service in enumerate(engines):
            batch_size = translation_service.batch_size
            self.translation.log_info(
                "fetching translations for %d units from %s, %d per request",
                num_units,
                translation_service.name,
                batch_size,
            )

            for batch_start in range(0, num_units, batch_size):
                self.set_progress(pos * num_units + batch_start)
                try:
                    translation_service.batch_translate(
                        units[batch_start : batch_start + batch_size],
                        self.user,
                        threshold=threshold,
                    )
                except MachineTranslationError as error:
                    # Ignore errors here to complete fetching
                    self.translation.log_error(
                        "failed automatic translation: %s", error
                    )

        self.set_progress(self.progress_base)
        return {
            unit.id: unit.machinery
            for unit in units
            if unit.machinery and any(unit.machinery["quality"])
        }

    def process_mt(self, engines: list[str], threshold: int) -> None:
        """Perform automatic translation based on machine translation."""
        translations = self.fetch_mt(engines, int(threshold))

        # Adjust total number to show correct progress
        self.progress_steps = self.progress_base + len(translations)

        with transaction.atomic():
            # Perform the translation
            self.translation.log_info("updating %d strings", len(translations))
            for pos, unit in enumerate(
                self.translation.unit_set.filter(id__in=translations.keys())
                .prefetch_bulk()
                .select_for_update()
            ):
                translation: UnitMemoryResultDict = translations[unit.pk]
                # Use first existing origin for user
                # (there can be blanks for missing plurals)
                user: User | None = None
                for origin in translation["origin"]:
                    if origin is not None:
                        user = origin.user
                        break
                # Copy translation
                self.update(
                    unit,
                    self.target_state,
                    translation["translation"],
                    user=user,
                )
                self.set_progress(self.progress_base + pos + 1)

            self.post_process()

    def perform(
        self,
        *,
        auto_source: Literal["mt", "others"],
        engines: list[str],
        threshold: int,
        source_component_ids: list[int] | None,
    ) -> str:
        translation = self.translation
        self.failure_message = None
        translation.log_info(
            "starting automatic translation (%s) %s: %s: %s",
            self.mode,
            current_task.request.id if current_task and current_task.request.id else "",
            auto_source,
            ", ".join(engines)
            if engines
            else ", ".join(str(item) for item in source_component_ids or []),
        )
        try:
            if auto_source == "mt":
                self.process_mt(engines, threshold)
            else:
                self.process_others(source_component_ids)
        except (MachineTranslationError, Component.DoesNotExist) as error:
            translation.log_error("failed automatic translation: %s", error)
            self.failure_message = gettext("Automatic translation failed: %s") % error
            return self.failure_message

        translation.log_info("completed automatic translation")

        return self.get_message()


class BatchAutoTranslate(BaseAutoTranslate):
    translations: Sequence[Translation]

    def __init__(
        self,
        obj: Translation | Component | Category | ProjectLanguage,
        *,
        user: User | None,
        q: str,
        mode: str,
        component_wide: bool = False,
        unit_ids: list[int] | None = None,
        allow_non_shared_tm_source_components: bool = False,
    ) -> None:
        super().__init__(
            user=user,
            q=q,
            mode=mode,
            component_wide=component_wide,
            unit_ids=unit_ids,
            allow_non_shared_tm_source_components=(
                allow_non_shared_tm_source_components
            ),
        )
        self._task_meta: dict[str, Any] = {}

        match obj:
            case Translation():
                self.translations = [obj]
                self._task_meta = {"translation": obj.pk}
            case Component():
                self.translations = obj.translation_set.exclude_source()
                self._task_meta = {"component": obj.pk}
            case Category():
                self.translations = Translation.objects.filter(
                    component__category=obj
                ).exclude_source()
                self._task_meta = {"category": obj.pk}
            case ProjectLanguage():
                self.translations = [t for t in obj.translation_set if not t.is_source]
                self._task_meta = {
                    "project": obj.project.pk,
                    "language": obj.language.pk,
                }
            case _:  # pragma: no cover
                msg = "Unsupported object type for BatchAutoTranslate"
                raise ValueError(msg)
        self.progress_steps = len(self.translations)

    def get_task_meta(self) -> dict[str, Any]:
        return self._task_meta

    def perform(
        self,
        *,
        auto_source: Literal["mt", "others"],
        engines: list[str],
        threshold: int,
        source_component_ids: list[int] | None,
    ) -> str:
        for pos, translation in enumerate(self.translations, start=1):
            auto_translate = AutoTranslate(
                user=self.user,
                translation=translation,
                q=self.q,
                mode=self.mode,
                component_wide=self.component_wide,
                unit_ids=self.unit_ids,
                allow_non_shared_tm_source_components=(
                    self.allow_non_shared_tm_source_components
                ),
            )

            auto_translate.perform(
                auto_source=auto_source,
                engines=engines,
                threshold=threshold,
                source_component_ids=source_component_ids,
            )
            self.updated += auto_translate.updated
            for warning in auto_translate.get_warnings():
                self.add_warning(warning)
            self.set_progress(pos)

        return self.get_message()
