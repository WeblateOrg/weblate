# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from celery import current_task
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models.functions import MD5, Lower

from weblate.machinery.base import MachineTranslationError
from weblate.machinery.models import MACHINERY
from weblate.trans.models import Change, Component, Suggestion, Unit
from weblate.trans.util import split_plural
from weblate.utils.state import STATE_APPROVED, STATE_FUZZY, STATE_TRANSLATED


class AutoTranslate:
    def __init__(
        self,
        user,
        translation,
        filter_type: str,
        mode: str,
        component_wide: bool = False,
    ) -> None:
        self.user = user
        self.translation = translation
        translation.component.batch_checks = True
        self.filter_type = filter_type
        self.mode = mode
        self.updated = 0
        self.progress_steps = 0
        self.target_state = STATE_TRANSLATED
        if mode == "fuzzy":
            self.target_state = STATE_FUZZY
        elif mode == "approved":
            self.target_state = STATE_APPROVED
        self.component_wide = component_wide

    def get_units(self):
        units = self.translation.unit_set.all()
        if self.mode == "suggest":
            units = units.filter(suggestion__isnull=True)
        return units.filter_type(self.filter_type)

    def set_progress(self, current) -> None:
        if current_task and current_task.request.id and self.progress_steps:
            current_task.update_state(
                state="PROGRESS",
                meta={
                    "progress": 100 * current // self.progress_steps,
                    "translation": self.translation.pk,
                },
            )

    def update(self, unit, state: int, target: list[str], user=None) -> None:
        if isinstance(target, str):
            target = [target]
        if self.mode == "suggest" or any(
            len(item) > unit.get_max_length() for item in target
        ):
            suggestion = Suggestion.objects.add(
                unit, target, request=None, vote=False, user=user, raise_exception=False
            )
            if suggestion:
                self.updated += 1
        else:
            unit.is_batch_update = True
            unit.translate(
                user or self.user, target, state, Change.ACTION_AUTO, propagate=False
            )
            self.updated += 1

    def post_process(self) -> None:
        if self.updated > 0:
            if not self.component_wide:
                self.translation.component.update_source_checks()
                self.translation.component.run_batched_checks()
            self.translation.invalidate_cache()
            if self.user:
                self.user.profile.increase_count("translated", self.updated)

    @transaction.atomic
    def process_others(self, source: int | None) -> None:
        """Perform automatic translation based on other components."""
        kwargs = {
            "translation__plural": self.translation.plural,
            "state__gte": STATE_TRANSLATED,
        }
        source_language = self.translation.component.source_language
        exclude = {}
        if source:
            component = Component.objects.get(id=source)

            if (
                not component.project.contribute_shared_tm
                and component.project != self.translation.component.project
            ):
                raise PermissionDenied(
                    "Project has disabled contribution to shared translation memory."
                )
            if component.source_language != source_language:
                raise PermissionDenied("Component have different source languages.")
            kwargs["translation__component"] = component
        else:
            project = self.translation.component.project
            kwargs["translation__component__project"] = project
            kwargs["translation__component__source_language"] = source_language
            exclude["translation"] = self.translation
        sources = Unit.objects.filter(**kwargs)

        # Use memory_db for the query in case it exists. This is supposed
        # to be a read-only replica for offloading expensive translation
        # queries.
        if "memory_db" in settings.DATABASES:
            sources = sources.using("memory_db")

        if exclude:
            sources = sources.exclude(**exclude)

        # Fetch translations
        translations = {
            source: split_plural(target)
            for source, state, target in sources.filter(
                source__lower__md5__in=self.get_units()
                .annotate(source__lower__md5=MD5(Lower("source")))
                .values("source__lower__md5")
            ).values_list("source", "state", "target")
        }

        # Cannot use get_units() directly as SELECT FOR UPDATE cannot be used with JOIN
        unit_ids = list(
            self.get_units()
            .filter(source__in=translations.keys())
            .values_list("id", flat=True)
        )
        units = Unit.objects.filter(pk__in=unit_ids).prefetch_bulk().select_for_update()
        self.progress_steps = len(units)

        for pos, unit in enumerate(units):
            # Get update
            try:
                target = translations[unit.source]
            except KeyError:
                # Happens on MySQL due to case-insensitive lookup
                continue

            self.set_progress(pos)

            # No save if translation is same or unit does not exist
            if unit.state == self.target_state and unit.target == target:
                continue
            # Copy translation
            self.update(unit, self.target_state, target)

        self.post_process()

    def fetch_mt(self, engines, threshold):
        """Get the translations."""
        units = self.get_units()
        num_units = len(units)

        machinery_settings = self.translation.component.project.get_machinery_settings()

        engines = sorted(
            (
                MACHINERY[engine](setting)
                for engine, setting in machinery_settings.items()
                if engine in MACHINERY and engine in engines
            ),
            key=lambda engine: engine.get_rank(),
            reverse=True,
        )

        self.progress_steps = 2 * (len(engines) + num_units)

        for pos, translation_service in enumerate(engines):
            batch_size = translation_service.batch_size
            self.translation.log_info(
                "fetching translations from %s, %d per request",
                translation_service.name,
                batch_size,
            )

            for batch_start in range(0, num_units, batch_size):
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
                self.set_progress(pos * num_units + batch_start)

        return {
            unit.id: unit.machinery
            for unit in units
            if unit.machinery and any(unit.machinery["quality"])
        }

    def process_mt(self, engines: list[str], threshold: int) -> None:
        """Perform automatic translation based on machine translation."""
        translations = self.fetch_mt(engines, int(threshold))

        # Adjust total number to show correct progress
        offset = self.progress_steps // 2
        self.progress_steps = offset + len(translations)

        with transaction.atomic():
            # Perform the translation
            self.translation.log_info("updating %d strings", len(translations))
            for pos, unit in enumerate(
                self.translation.unit_set.filter(id__in=translations.keys())
                .prefetch_bulk()
                .select_for_update()
            ):
                translation = translations[unit.pk]
                # Use first existing origin for user
                # (there can be blanks for missing plurals)
                user = None
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
                self.set_progress(offset + pos)

            self.post_process()
