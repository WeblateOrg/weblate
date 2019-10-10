# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2019 Michal Čihař <michal@cihar.com>
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
from weblate.utils.state import STATE_TRANSLATED


class AutoTranslate(object):
    def __init__(self, user, translation, filter_type, mode):
        self.user = user
        self.translation = translation
        self.filter_type = filter_type
        self.mode = mode
        self.updated = 0
        self.total = 0

    def get_units(self):
        units = self.translation.unit_set.filter_type(
            self.filter_type,
            self.translation.component.project,
            self.translation.language,
        )
        if self.mode == 'suggest':
            units = units.exclude(has_suggestion=True)
        return units

    def set_progress(self, current):
        if current_task and current_task.request.id:
            current_task.update_state(
                state="PROGRESS", meta={"progress": 100 * current // self.total}
            )

    def update(self, unit, state, target):
        if self.mode == 'suggest':
            Suggestion.objects.add(unit, target, None, False)
        else:
            unit.translate(self.user, target, state, Change.ACTION_AUTO, False)
        self.updated += 1

    def post_process(self):
        if self.updated > 0:
            self.translation.invalidate_cache()
            if self.user:
                self.user.profile.refresh_from_db()
                self.user.profile.translated += self.updated
                self.user.profile.save(update_fields=["translated"])

    @transaction.atomic
    def process_others(self, source):
        """Perform automatic translation based on other components."""
        sources = Unit.objects.filter(
            translation__language=self.translation.language, state__gte=STATE_TRANSLATED
        )
        if source:
            subprj = Component.objects.get(id=source)

            if (
                not subprj.project.contribute_shared_tm
                and not subprj.project != self.translation.component.project
            ):
                raise PermissionDenied()
            sources = sources.filter(translation__component=subprj)
        else:
            project = self.translation.component.project
            sources = sources.filter(translation__component__project=project).exclude(
                translation=self.translation
            )

        # Filter by strings
        units = self.get_units().filter(source__in=sources.values("source"))
        self.total = units.count()

        for pos, unit in enumerate(units.select_for_update().iterator()):
            # Get first matching entry
            update = sources.filter(source=unit.source)[0]
            # No save if translation is same
            if unit.state == update.state and unit.target == update.target:
                continue
            # Copy translation
            self.update(unit, update.state, update.target)
            self.set_progress(pos / 2)

        self.post_process()

    def fetch_mt(self, engines, threshold):
        """Get the translations"""
        translations = {}

        for pos, unit in enumerate(self.get_units().iterator()):
            # a list to store all found translations
            max_quality = threshold - 1
            translation = None

            # Run engines with higher maximal score first
            engines = sorted(
                engines,
                key=lambda x: MACHINE_TRANSLATION_SERVICES[x].get_rank(),
                reverse=True,
            )
            for engine in engines:
                translation_service = MACHINE_TRANSLATION_SERVICES[engine]

                # Skip service if it can not provide better results.
                # Typically we skip machine translation when we have
                # a terminology match.
                if max_quality >= translation_service.max_score:
                    continue

                result = translation_service.translate(
                    self.translation.language.code,
                    unit.get_source_plurals()[0],
                    unit,
                    self.user,
                )

                for item in result:
                    if item["quality"] > max_quality:
                        max_quality = item["quality"]
                        translation = item["text"]

                # Break if we can't get better match
                if max_quality == 100:
                    break

            if translation is None:
                continue

            translations[unit.pk] = translation
            self.set_progress(pos / 2)

        return translations

    def process_mt(self, engines, threshold):
        """Perform automatic translation based on machine translation."""
        self.total = self.get_units().count()
        translations = self.fetch_mt(engines, threshold)

        with transaction.atomic():
            # Perform the translation
            for pos, unit in enumerate(self.get_units().select_for_update().iterator()):
                # Copy translation
                try:
                    self.update(unit, STATE_TRANSLATED, translations[unit.pk])
                except KeyError:
                    # Probably new unit, ignore it for now
                    continue
                self.set_progress((self.total / 2) + (pos / 2))

            self.post_process()
