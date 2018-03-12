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

from weblate.permissions.helpers import can_access_project
from weblate.trans.models import Unit, Change, SubProject
from weblate.trans.machine import MACHINE_TRANSLATION_SERVICES
from weblate.utils.state import STATE_TRANSLATED


class AutoTranslate(object):
    def __init__(self, user, translation, inconsistent, overwrite, request=None):
        self.user = user
        self.request = request
        self.translation = translation
        self.inconsistent = inconsistent
        self.overwrite = overwrite
        self.updated = 0

    def get_units(self):
        if self.inconsistent:
            return self.translation.unit_set.filter_type(
                'check:inconsistent',
                self.translation.subproject.project,
                self.translation.language,
            )
        elif self.overwrite:
            return self.translation.unit_set.all()
        return self.translation.unit_set.filter(
            state__lt=STATE_TRANSLATED,
        )

    def update(self, unit, state, target):
        unit.state = state
        unit.target = target
        # Create signle change object for whole merge
        Change.objects.create(
            action=Change.ACTION_AUTO,
            unit=unit,
            user=self.user,
            author=self.user
        )
        # Save unit to backend
        unit.save_backend(self.request, False, False, user=self.user)
        self.updated += 1

    @transaction.atomic
    def process_others(self, source, check_acl=True):
        """Perform automatic translation based on other components."""
        sources = Unit.objects.filter(
            translation__language=self.translation.language,
            state__gte=STATE_TRANSLATED,
        )
        if source:
            subprj = SubProject.objects.get(id=source)

            if check_acl and not can_access_project(self.user, subprj.project):
                raise PermissionDenied()
            sources = sources.filter(translation__subproject=subprj)
        else:
            project = self.translation.subproject.project
            sources = sources.filter(
                translation__subproject__project=project
            ).exclude(
                translation=self.translation
            )

        # Filter by strings
        units = self.get_units().filter(
            source__in=sources.values('source')
        )

        self.translation.commit_pending(None)

        for unit in units.select_for_update().iterator():
            # Get first matching entry
            update = sources.filter(source=unit.source)[0]
            # No save if translation is same
            if unit.state == update.state and unit.target == update.target:
                continue
            # Copy translation
            self.update(unit, update.state, update.target)

    @transaction.atomic
    def process_mt(self, engines, threshold):
        """Perform automatic translation based on machine translation."""
        self.translation.commit_pending(None)

        # get the translations (optimized: first WeblateMT, then others)
        for unit in self.get_units().iterator():
            # a list to store all found translations
            results = []

            # check if weblate is in the chosen engines
            if 'weblate' in engines:
                translation_service = MACHINE_TRANSLATION_SERVICES['weblate']
                result = translation_service.translate(
                    self.translation.language.code,
                    unit.get_source_plurals()[0],
                    unit,
                    self.user
                )

                for item in result:
                    results.append(
                        (item['quality'], item['text'], item['service'])
                    )

            # use the other machine translation services if weblate did not
            # find anything or has not been chosen
            if 'weblate' not in engines or not results:
                for engine in engines:
                    # skip weblate
                    if 'weblate' == engine:
                        continue

                    translation_service = MACHINE_TRANSLATION_SERVICES[engine]
                    result = translation_service.translate(
                        self.translation.language.code,
                        unit.get_source_plurals()[0],
                        unit,
                        self.user
                    )

                    for item in result:
                        results.append(
                            (item['quality'], item['text'], item['service'])
                        )

            if not results:
                continue

            # sort the list descending - the best result will be on top
            results.sort(key=lambda tup: tup[0], reverse=True)

            # take the "best" result and check the quality score
            result = results[0]
            if result[0] < threshold:
                continue

            # Copy translation
            self.update(unit, STATE_TRANSLATED, result[1])
