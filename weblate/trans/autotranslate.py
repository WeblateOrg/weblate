# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from celery import current_task
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Case, F, IntegerField, Q, QuerySet, Value, When
from django.db.models.functions import MD5, Lower
from django.utils.translation import gettext, ngettext

from weblate.logger import LOGGER
from weblate.machinery.base import MachineTranslationError
from weblate.machinery.models import MACHINERY
from weblate.trans.actions import ActionEvents
from weblate.trans.models import (
    Category,
    Component,
    Project,
    Suggestion,
    SuggestionAddResult,
    Translation,
    Unit,
    WorkflowSetting,
)
from weblate.trans.util import is_plural, split_plural
from weblate.utils.state import (
    STATE_APPROVED,
    STATE_FUZZY,
    STATE_READONLY,
    STATE_TRANSLATED,
)
from weblate.utils.stats import ProjectLanguage
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from weblate.auth.models import User
    from weblate.auth.results import PermissionResult
    from weblate.machinery.base import BatchMachineTranslation, UnitMemoryResultDict
    from weblate.utils.state import StringState


def fetch_machinery_matches(
    *,
    units: list[Unit],
    user: User | None,
    services: Sequence[BatchMachineTranslation],
    threshold: int,
    set_progress: Callable[[int], None] | None = None,
    log_translation: Translation | None = None,
) -> dict[int, UnitMemoryResultDict]:
    """Fetch machinery matches without applying them to units."""
    num_units = len(units)

    for pos, translation_service in enumerate(services):
        batch_size = translation_service.batch_size
        if log_translation is not None:
            log_translation.log_info(
                "fetching translations for %d units from %s, %d per request",
                num_units,
                translation_service.name,
                batch_size,
            )

        for batch_start in range(0, num_units, batch_size):
            if set_progress is not None:
                set_progress(pos * num_units + batch_start)
            try:
                translation_service.batch_translate(
                    units[batch_start : batch_start + batch_size],
                    user,
                    threshold=threshold,
                )
            except MachineTranslationError as error:
                if log_translation is not None:
                    log_translation.log_error("failed automatic translation: %s", error)
                else:
                    LOGGER.warning(
                        "failed machinery translation from %s: %s",
                        translation_service.name,
                        error,
                    )

    return {
        unit.id: unit.machinery
        for unit in units
        if unit.machinery and any(unit.machinery["quality"])
    }


def check_auto_translate_permission(
    user: User | None, translation: Translation, mode: str
) -> bool | PermissionResult:
    # Add-on users identify generated changes rather than authorize the operation.
    if user is None or (user.is_bot and user.username.startswith("addon:")):
        return True
    if not (permission := user.has_perm("translation.auto", translation)):
        return permission
    if mode == "suggest":
        if not translation.restrict_direct_editing:
            return True
        return user.has_perm("suggestion.add", translation)
    return user.has_perm("meta:unit.direct_edit", translation)


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
        self.affected_unit_ids: set[int] = set()
        self.affected_source_unit_ids: set[int] = set()

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
        enforce_permissions: bool = True,
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
        self.enforce_permissions = enforce_permissions
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
        return units.search(
            self.q, parser="unit", project=self.translation.component.project
        )

    def get_task_meta(self) -> dict[str, Any]:
        return {"translation": self.translation.pk}

    def update(
        self, unit: Unit, state: StringState, target: list[str], user=None
    ) -> None:
        if isinstance(target, str):
            target = [target]
        max_length = unit.get_max_length()
        if self.mode == "suggest" or any(len(item) > max_length for item in target):
            _, result = Suggestion.objects.add(
                unit,
                target,
                request=None,
                vote=False,
                user=user or self.user,
                raise_exception=False,
            )
            if result == SuggestionAddResult.CREATED:
                self.updated += 1
                self.affected_unit_ids.add(unit.pk)
                self.affected_source_unit_ids.add(unit.source_unit_id or unit.pk)
        else:
            if (
                state == STATE_APPROVED
                and self.enforce_permissions
                and self.user is not None
                and not self.user.has_perm("unit.review", unit)
            ):
                return
            # Ensure deferred changes accumulate on the right Translation instance
            unit.translation = self.translation
            unit.is_batch_update = True
            saved = unit.translate(
                user or self.user,
                target,
                state,
                change_action=ActionEvents.AUTO,
                propagate=False,
                select_for_update=False,
            )
            self.updated += 1
            if saved:
                self.affected_unit_ids.add(unit.pk)
                self.affected_source_unit_ids.add(unit.source_unit_id or unit.pk)

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
        self,
        filtered_sources,
        component_ids: list[int],
        *,
        source_field: str = "source",
    ) -> tuple[dict[tuple[str, str], list[str]], dict[str, list[str]]]:
        """Collect context matches and source fallbacks preserving source priority."""
        translations: dict[str, list[str]] = {}
        context_translations: dict[tuple[str, str], list[str]] = {}
        translation_priority: dict[str, int] = {}
        context_priority: dict[tuple[str, str], int] = {}
        component_priority = {
            component_id: index for index, component_id in enumerate(component_ids)
        }
        mismatched_translation_ids: set[int] = set()
        target_plural_id = self.translation.plural_id

        if component_ids:
            filtered_sources = filtered_sources.annotate(
                component_priority=Case(
                    *[
                        When(translation__component_id=component_id, then=priority)
                        for component_id, priority in component_priority.items()
                    ],
                    output_field=IntegerField(),
                )
            ).order_by("component_priority", "translation_id", "pk")
        else:
            filtered_sources = filtered_sources.order_by("translation_id", "pk")

        source_units = filtered_sources.values_list(
            "translation__component_id",
            source_field,
            "context",
            "target",
            "translation_id",
            "translation__plural_id",
        )
        for (
            component_id,
            source,
            context,
            target,
            translation_id,
            plural_id,
        ) in source_units:
            if plural_id != target_plural_id and (
                is_plural(source) or is_plural(target)
            ):
                mismatched_translation_ids.add(translation_id)
                continue
            priority = component_priority.get(component_id, 0)
            context_key = (source, context)
            target_plurals = split_plural(target)
            if priority < translation_priority.get(source, len(component_ids) + 1):
                translations[source] = target_plurals
                translation_priority[source] = priority
            if priority < context_priority.get(context_key, len(component_ids) + 1):
                context_translations[context_key] = target_plurals
                context_priority[context_key] = priority

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

        return context_translations, translations

    @transaction.atomic
    def process_others(self, source_component_ids: list[int] | None) -> None:
        """Perform automatic translation based on other components."""
        sources = Unit.objects.filter(
            translation__language=self.translation.language,
            state__gte=STATE_TRANSLATED,
        )
        components = Component.objects.all()
        if self.enforce_permissions and self.user is not None:
            sources = sources.filter_access(self.user)
            components = components.filter_access(self.user)
        # Read-only units can have STATE_READONLY even when their target is
        # empty, so state__gte=STATE_TRANSLATED is not enough to find usable
        # translations. The lower-MD5 lookup matches the trans_unit_target_md5
        # index and keeps this exclusion cheap on large components.
        sources = sources.exclude(target__lower__md5=MD5(Value("")))
        project = self.translation.component.project
        custom_sources = bool(project.translation_parent_language_ids)
        if custom_sources:
            target_units = self.get_units().annotate(
                reuse_source=Unit.objects.effective_source_expression(),
                reuse_language=Unit.objects.effective_source_language_expression(),
            )
            source_language_ids = set(
                target_units.values_list("reuse_language", flat=True)
            )
            if not source_language_ids:
                source_language_ids.add(self.translation.effective_source_language.pk)
        else:
            language_id = self.translation.component.source_language_id
            target_units = self.get_units().annotate(
                reuse_source=F("source"), reuse_language=Value(language_id)
            )
            source_language_ids = {language_id}
        donor_custom_sources = custom_sources
        component_ids = list(dict.fromkeys(source_component_ids or []))
        if component_ids:
            source_components = list(components.filter(id__in=component_ids))
            component_map = {component.id: component for component in source_components}
            if len(component_map) != len(component_ids):
                msg = "Component not found."
                raise Component.DoesNotExist(msg)

            other_project_ids = {
                component.project_id
                for component in source_components
                if component.project_id != project.pk
            }
            if not donor_custom_sources and other_project_ids:
                donor_custom_sources = WorkflowSetting.objects.filter(
                    project_id__in=other_project_ids,
                    source_language__isnull=False,
                ).exists()

            for component_id in component_ids:
                component = component_map[component_id]
                if not self.allow_non_shared_tm_source_components and (
                    not component.project.contribute_shared_tm
                    and component.project != self.translation.component.project
                ):
                    msg = "Project has disabled contribution to shared translation memory."
                    raise PermissionDenied(msg)
                if component.source_language_id not in source_language_ids and not (
                    donor_custom_sources
                    and Unit.objects.filter(
                        translation__component=component,
                        translation__language=self.translation.language,
                        translation_parent__translation__language_id__in=source_language_ids,
                    ).exists()
                ):
                    msg = "Component have different source languages."
                    raise PermissionDenied(msg)
            sources = sources.filter(translation__component_id__in=component_ids)
        else:
            sources = sources.filter(
                translation__component__project=project,
            ).exclude(translation=self.translation)

        sources = sources.exclude_blocked(custom_sources=donor_custom_sources)

        # Use memory_db for the query in case it exists. This is supposed
        # to be a read-only replica for offloading expensive translation
        # queries.
        if "memory_db" in settings.DATABASES:
            sources = sources.using("memory_db")

        for language_id in source_language_ids:
            self.process_others_language(
                sources,
                target_units.filter(reuse_language=language_id),
                component_ids,
                language_id,
                custom_sources=donor_custom_sources,
            )
        self.post_process()

    def process_others_language(
        self,
        sources,
        target_units,
        component_ids: list[int],
        language_id: int,
        *,
        custom_sources: bool,
    ) -> None:
        """Reuse translations whose effective source text and language match."""
        source_md5s = list(
            target_units.annotate(reuse_md5=MD5(Lower("reuse_source"))).values_list(
                "reuse_md5", flat=True
            )
        )
        if custom_sources:
            # Keep the indexed canonical-source and parent-target lookups separate.
            filtered_sources = sources.filter(
                Q(
                    translation_parent__isnull=True,
                    translation__component__source_language_id=language_id,
                    source__lower__md5__in=source_md5s,
                )
                | Q(
                    translation_parent__translation__language_id=language_id,
                    translation_parent__target__lower__md5__in=source_md5s,
                )
            ).annotate(reuse_source=Unit.objects.effective_source_expression())
        else:
            filtered_sources = sources.filter(
                translation__component__source_language_id=language_id,
                source__lower__md5__in=source_md5s,
            ).annotate(reuse_source=F("source"))
        context_translations, translations = self.collect_other_translations(
            filtered_sources, component_ids, source_field="reuse_source"
        )

        # Resolve IDs before locking: the effective-source lookup uses nullable joins.
        unit_ids = list(
            target_units.annotate(reuse_md5=MD5(Lower("reuse_source")))
            .filter(
                reuse_md5__in=[MD5(Lower(Value(source))) for source in translations]
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
            source = unit.effective_source
            try:
                target = context_translations.get(
                    (source, unit.context), translations[source]
                )
            except KeyError:
                # The indexed lookup is case-insensitive; require an exact match.
                continue
            self.set_progress(pos)
            if unit.state == self.target_state and unit.target == target:
                continue
            self.update(unit, self.target_state, target)

    def fetch_mt(
        self, engines_list: list[str], threshold: int
    ) -> dict[int, UnitMemoryResultDict]:
        """Get the translations."""
        queryset = self.get_units()
        if self.translation.component.project.translation_parent_language_ids:
            queryset = queryset.prefetch_source()
        else:
            queryset = queryset.select_related("source_unit")
        units: list[Unit] = list(queryset)
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

        translations = fetch_machinery_matches(
            units=units,
            user=self.user,
            services=engines,
            threshold=threshold,
            set_progress=self.set_progress,
            log_translation=self.translation,
        )
        self.set_progress(self.progress_base)
        return translations

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
    translations: QuerySet[Translation] | Sequence[Translation]

    def __init__(
        self,
        obj: Translation | Component | Category | ProjectLanguage | Workspace,
        *,
        user: User | None,
        q: str,
        mode: str,
        component_wide: bool = False,
        unit_ids: list[int] | None = None,
        allow_non_shared_tm_source_components: bool = False,
        enforce_permissions: bool = True,
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
        self.workspace_source_component_ids: dict[int, list[int]] | None = None
        self.enforce_permissions = enforce_permissions

        match obj:
            case Translation():
                self.translations = [obj]
                self._task_meta = {"translation": obj.pk}
            case Component():
                self.translations = obj.translation_set.select_related(
                    "language"
                ).exclude_source()
                self._task_meta = {"component": obj.pk}
            case Category():
                self.translations = (
                    Translation.objects.filter(component__category=obj)
                    .select_related("language", "component", "component__project")
                    .exclude_source()
                )
                self._task_meta = {"category": obj.pk}
            case ProjectLanguage():
                self.translations = list(
                    obj.action_translation_set.select_related("language")
                    .exclude_source()
                    .prefetch()
                )
                self._task_meta = {
                    "project": obj.project.pk,
                    "language": obj.language.pk,
                }
            case Workspace():
                components = Component.objects.filter(project__workspace=obj)
                if user is not None:
                    components = components.filter_access(user)
                self.translations = (
                    Translation.objects.filter(component__in=components)
                    .select_related("language", "component", "component__project")
                    .exclude_source()
                )
                source_component_ids: dict[int, list[int]] = {}
                for source_language_id, component_id in components.filter(
                    source_language_id__isnull=False
                ).values_list("source_language_id", "pk"):
                    source_component_ids.setdefault(source_language_id, []).append(
                        component_id
                    )
                self.workspace_source_component_ids = source_component_ids
                self.allow_non_shared_tm_source_components = True
                self._task_meta = {"workspace": str(obj.pk)}
            case _:  # pragma: no cover
                msg = "Unsupported object type for BatchAutoTranslate"
                raise ValueError(msg)
        self._preload_workflow_settings()
        self.progress_steps = len(self.translations)

    def _preload_workflow_settings(self) -> None:
        self.translations = list(self.translations)
        projects: dict[int, Project] = {}
        project_languages: dict[int, dict[int, ProjectLanguage]] = {}

        for translation in self.translations:
            project = translation.component.project
            project = projects.setdefault(project.pk, project)
            languages = project_languages.setdefault(project.pk, {})
            if translation.language_id not in languages:
                languages[translation.language_id] = ProjectLanguage(
                    project, translation.language
                )

        for project_id, languages in project_languages.items():
            projects[project_id].project_languages.preload_workflow_settings(
                languages.values()
            )

        for translation in self.translations:
            translation.__dict__["workflow_settings"] = project_languages[
                translation.component.project_id
            ][translation.language_id].workflow_settings

    def get_task_meta(self) -> dict[str, Any]:
        return self._task_meta

    def _can_process_translation(self, translation: Translation) -> bool:
        return not self.enforce_permissions or bool(
            check_auto_translate_permission(self.user, translation, self.mode)
        )

    def _get_workspace_effective_sources(
        self, selected_ids: list[int] | None
    ) -> dict[tuple[int, int], list[int]] | None:
        """Match workspace donors by target language and actual effective sources."""
        if self.workspace_source_component_ids is None:
            return None
        workspace_ids = {
            component_id
            for ids in self.workspace_source_component_ids.values()
            for component_id in ids
        }
        donor_ids = sorted(workspace_ids) if selected_ids is None else selected_ids
        component_ids = workspace_ids | set(donor_ids)
        if not WorkflowSetting.objects.filter(
            project__component__pk__in=component_ids,
            source_language__isnull=False,
        ).exists():
            return None

        donors: dict[tuple[int, int], list[int]] = {}
        for target_language, source_language, component_id in (
            Unit.objects.filter(translation__component_id__in=donor_ids)
            .with_effective_source()
            .values_list(
                "translation__language_id",
                "check_source_language",
                "translation__component_id",
            )
            .distinct()
        ):
            donors.setdefault((target_language, source_language), []).append(
                component_id
            )
        return donors

    def perform(
        self,
        *,
        auto_source: Literal["mt", "others"],
        engines: list[str],
        threshold: int,
        source_component_ids: list[int] | None,
    ) -> str:
        selected_workspace_source_component_ids: dict[int, list[int]] | None = None
        self.failure_message = None
        workspace_effective_sources = (
            self._get_workspace_effective_sources(source_component_ids)
            if auto_source == "others"
            else None
        )
        if (
            auto_source == "others"
            and workspace_effective_sources is None
            and source_component_ids is not None
            and self.workspace_source_component_ids is not None
        ):
            selected_workspace_source_component_ids = {}
            for selected_source_language_id, component_id in Component.objects.filter(
                pk__in=source_component_ids, source_language_id__isnull=False
            ).values_list("source_language_id", "pk"):
                if selected_source_language_id is not None:
                    selected_workspace_source_component_ids.setdefault(
                        selected_source_language_id, []
                    ).append(component_id)

        for pos, translation in enumerate(self.translations, start=1):
            if not self._can_process_translation(translation):
                self.set_progress(pos)
                continue

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
                enforce_permissions=self.enforce_permissions,
            )

            effective_source_component_ids = source_component_ids
            if (
                auto_source == "others"
                and self.workspace_source_component_ids is not None
            ):
                source_language_id = translation.component.source_language_id
                if workspace_effective_sources is not None:
                    source_languages = set(
                        auto_translate.get_units()
                        .with_effective_source()
                        .values_list("check_source_language", flat=True)
                        .distinct()
                    ) or {translation.effective_source_language.pk}
                    effective_source_component_ids = list(
                        dict.fromkeys(
                            component_id
                            for language_id in source_languages
                            for component_id in workspace_effective_sources.get(
                                (translation.language_id, language_id), []
                            )
                        )
                    )
                    if (
                        not effective_source_component_ids
                        and source_component_ids is not None
                    ):
                        self.add_warning(
                            gettext(
                                "Automatic translation skipped some translations because "
                                "selected source components use a different source language."
                            )
                        )
                elif selected_workspace_source_component_ids is None:
                    effective_source_component_ids = (
                        []
                        if source_language_id is None
                        else self.workspace_source_component_ids.get(
                            source_language_id, []
                        )
                    )
                elif source_language_id is None:
                    self.add_warning(
                        gettext(
                            "Automatic translation skipped some translations because "
                            "selected source components use a different source language."
                        )
                    )
                    self.set_progress(pos)
                    continue
                else:
                    effective_source_component_ids = (
                        selected_workspace_source_component_ids.get(
                            source_language_id, []
                        )
                    )
                    if not effective_source_component_ids:
                        self.add_warning(
                            gettext(
                                "Automatic translation skipped some translations because "
                                "selected source components use a different source language."
                            )
                        )
                        self.set_progress(pos)
                        continue

                effective_source_component_ids = [
                    component_id
                    for component_id in effective_source_component_ids
                    if component_id != translation.component_id
                ]
                if not effective_source_component_ids:
                    if source_component_ids is not None:
                        self.set_progress(pos)
                        continue
                    self.add_warning(
                        gettext(
                            "Automatic translation skipped some translations because "
                            "no other source components were available."
                        )
                    )
                    self.set_progress(pos)
                    continue

            auto_translate.perform(
                auto_source=auto_source,
                engines=engines,
                threshold=threshold,
                source_component_ids=effective_source_component_ids,
            )
            self.updated += auto_translate.updated
            self.affected_unit_ids.update(auto_translate.affected_unit_ids)
            self.affected_source_unit_ids.update(
                auto_translate.affected_source_unit_ids
            )
            if auto_translate.failure_message and self.failure_message is None:
                self.failure_message = auto_translate.failure_message
            for warning in auto_translate.get_warnings():
                self.add_warning(warning)
            self.set_progress(pos)

        return self.failure_message or self.get_message()
