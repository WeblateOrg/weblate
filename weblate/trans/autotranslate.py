# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
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

from django.core.exceptions import PermissionDenied
from django.db import transaction

from weblate.trans.models import Unit, Change, Component
from weblate.machinery import MACHINE_TRANSLATION_SERVICES
from weblate.utils.state import STATE_TRANSLATED


class AutoTranslate(object):
    def __init__(self, user, translation, filter_type, request=None):
        self.user = user
        self.request = request
        self.translation = translation
        self.filter_type = filter_type
        self.updated = 0

    def get_units(self):
        return self.translation.unit_set.filter_type(
            self.filter_type,
            self.translation.component.project,
            self.translation.language,
        )

    def update(self, unit, state, target):
        unit.translate(self.request, target, state, Change.ACTION_AUTO, False)
        self.updated += 1

    def post_process(self):
        if self.updated > 0:
            self.translation.invalidate_cache()
            self.user.profile.refresh_from_db()
            self.user.profile.translated += self.updated
            self.user.profile.save(update_fields=['translated'])

    @transaction.atomic
    def process_others(self, source, check_acl=True):
        """Perform automatic translation based on other components."""
        sources = Unit.objects.filter(
            translation__language=self.translation.language,
            state__gte=STATE_TRANSLATED,
        )
        if source:
            subprj = Component.objects.get(id=source)

            if check_acl and not self.user.can_access_project(subprj.project):
                raise PermissionDenied()
            sources = sources.filter(translation__component=subprj)
        else:
            project = self.translation.component.project
            sources = sources.filter(
                translation__component__project=project
            ).exclude(
                translation=self.translation
            )

        # Filter by strings
        units = self.get_units().filter(
            source__in=sources.values('source')
        )

        for unit in units.select_for_update().iterator():
            # Get first matching entry
            update = sources.filter(source=unit.source)[0]
            # No save if translation is same
            if unit.state == update.state and unit.target == update.target:
                continue
            # Copy translation
            self.update(unit, update.state, update.target)

        self.post_process()

    def fetch_mt(self, engines, threshold):
        """Get the translations"""
        translations = {}

        for unit in self.get_units().iterator():
            # a list to store all found translations
            max_quality = threshold - 1
            translation = None

            # Run engines with higher maximal score first
            engines = sorted(
                engines,
                key=lambda x: MACHINE_TRANSLATION_SERVICES[x].get_rank(),
                reverse=True
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
                    self.user
                )

                for item in result:
                    if item['quality'] > max_quality:
                        max_quality = item['quality']
                        translation = item['text']

                # Break if we can't get better match
                if max_quality == 100:
                    break

            if translation is None:
                continue

            translations[unit.pk] = translation

        return translations

    def process_mt(self, engines, threshold):
        """Perform automatic translation based on machine translation."""
        translations = self.fetch_mt(engines, threshold)

        with transaction.atomic():
            # Perform the translation
            for unit in self.get_units().select_for_update().iterator():
                # Copy translation
                try:
                    self.update(unit, STATE_TRANSLATED, translations[unit.pk])
                except KeyError:
                    # Probably new unit, ignore it for now
                    continue

            self.post_process()
