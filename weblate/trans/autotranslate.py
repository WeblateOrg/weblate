#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

from celery import current_task
from django.core.exceptions import PermissionDenied
from django.db import transaction

from weblate.machinery import MACHINE_TRANSLATION_SERVICES
from weblate.trans.models import Change, Component, Suggestion, Unit
from weblate.utils.db import get_nokey_args
from weblate.utils.state import STATE_FUZZY, STATE_TRANSLATED


class AutoTranslate:
    def __init__(self, user, translation, filter_type, mode):
        self.user = user
        self.translation = translation
        self.filter_type = filter_type
        self.mode = mode
        self.updated = 0
        self.progress_steps = 0
        self.target_state = STATE_FUZZY if mode == "fuzzy" else STATE_TRANSLATED

    def get_units(self, filter_mode=True):
        units = self.translation.unit_set.all()
        if self.mode == "suggest" and filter_mode:
            units = units.filter(suggestion__isnull=True)
        return units.filter_type(self.filter_type)

    def set_progress(self, current):
        if current_task and current_task.request.id and self.progress_steps:
            current_task.update_state(
                state="PROGRESS",
                meta={
                    "progress": 100 * current // self.progress_steps,
                    "translation": self.translation.pk,
                },
            )

    def update(self, unit, state, target):
        if self.mode == "suggest" or len(target) > unit.get_max_length():
            Suggestion.objects.add(unit, target, None, False)
        else:
            unit.translate(self.user, target, state, Change.ACTION_AUTO, False)
        self.updated += 1

    def post_process(self):
        if self.updated > 0:
            self.translation.invalidate_cache()
            if self.user:
                self.user.profile.increase_count("translated", self.updated)

    @transaction.atomic
    def process_others(self, source):
        """Perform automatic translation based on other components."""
        kwargs = {
            "translation__language": self.translation.language,
            "state__gte": STATE_TRANSLATED,
        }
        source_language = self.translation.component.source_language
        exclude = {}
        if source:
            component = Component.objects.get(id=source)

            if (
                not component.project.contribute_shared_tm
                and not component.project != self.translation.component.project
            ) or component.source_language != source_language:
                raise PermissionDenied()
            kwargs["translation__component"] = component
        else:
            project = self.translation.component.project
            kwargs["translation__component__project"] = project
            kwargs["translation__component__source_language"] = source_language
            exclude["translation"] = self.translation
        sources = Unit.objects.filter(**kwargs)
        if exclude:
            sources = sources.exclude(**exclude)

        # Fetch translations
        translations = {
            source: (state, target)
            for source, state, target in sources.filter(
                source__in=self.get_units().values("source")
            ).values_list("source", "state", "target")
        }

        # We need to skip mode (suggestions) filtering here as SELECT FOR UPDATE
        # cannot be used with JOIN
        units = (
            self.get_units(False)
            .filter(source__in=translations.keys())
            .select_for_update(**get_nokey_args())
        )
        self.progress_steps = len(units)

        for pos, unit in enumerate(units):
            # Get update
            state, target = translations[unit.source]

            self.set_progress(pos)

            # No save if translation is same or unit does not exist
            if unit.state == state and unit.target == target:
                continue
            # Copy translation
            self.update(unit, state, target)

        self.post_process()

    def fetch_mt(self, engines, threshold):
        """Get the translations."""
        units = self.get_units()
        num_units = len(units)

        engines = sorted(
            engines,
            key=lambda x: MACHINE_TRANSLATION_SERVICES[x].get_rank(),
            reverse=True,
        )

        self.progress_steps = 2 * (len(engines) + num_units)

        for pos, engine in enumerate(engines):
            translation_service = MACHINE_TRANSLATION_SERVICES[engine]
            batch_size = translation_service.batch_size

            for batch_start in range(0, num_units, batch_size):
                translation_service.batch_translate(
                    units[batch_start : batch_start + batch_size],
                    self.user,
                    threshold=threshold,
                )
                self.set_progress(pos * num_units + batch_start)

        return {
            unit.id: unit.machinery["translation"]
            for unit in units
            if unit.machinery["best"] >= threshold
        }

    def process_mt(self, engines, threshold):
        """Perform automatic translation based on machine translation."""
        translations = self.fetch_mt(engines, int(threshold))

        # Adjust total number to show correct progress
        offset = self.progress_steps / 2
        self.progress_steps = offset + len(translations)

        with transaction.atomic():
            # Perform the translation
            for pos, unit in enumerate(
                Unit.objects.filter(id__in=translations.keys())
                .prefetch()
                .select_for_update(**get_nokey_args())
            ):
                # Copy translation
                self.update(unit, self.target_state, translations[unit.pk])
                self.set_progress(offset + pos)

            self.post_process()
