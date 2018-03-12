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


@transaction.atomic
def auto_translate(user, translation, source, inconsistent, overwrite,
                   check_acl=True):
    """Perform automatic translation based on other components."""
    updated = 0

    if inconsistent:
        units = translation.unit_set.filter_type(
            'check:inconsistent',
            translation.subproject.project,
            translation.language,
        )
    elif overwrite:
        units = translation.unit_set.all()
    else:
        units = translation.unit_set.filter(
            state__lt=STATE_TRANSLATED,
        )

    sources = Unit.objects.filter(
        translation__language=translation.language,
        state__gte=STATE_TRANSLATED,
    )
    if source:
        subprj = SubProject.objects.get(id=source)

        if check_acl and not can_access_project(user, subprj.project):
            raise PermissionDenied()
        sources = sources.filter(translation__subproject=subprj)
    else:
        sources = sources.filter(
            translation__subproject__project=translation.subproject.project
        ).exclude(
            translation=translation
        )

    # Filter by strings
    units = units.filter(
        source__in=sources.values('source')
    )

    translation.commit_pending(None)

    for unit in units.select_for_update().iterator():
        # Get first matching entry
        update = sources.filter(source=unit.source)[0]
        # No save if translation is same
        if unit.state == update.state and unit.target == update.target:
            continue
        # Copy translation
        unit.state = update.state
        unit.target = update.target
        # Create signle change object for whole merge
        Change.objects.create(
            action=Change.ACTION_AUTO,
            unit=unit,
            user=user,
            author=user
        )
        # Save unit to backend
        unit.save_backend(None, False, False, user=user)
        updated += 1

    return updated


def auto_translate_mt(user, translation, engines, threshold, inconsistent,
                      overwrite):
    """Perform automatic translation based on machine translation."""
    updated = 0

    if inconsistent:
        units = translation.unit_set.filter_type(
            'check:inconsistent',
            translation.subproject.project,
            translation.language,
        )
    elif overwrite:
        units = translation.unit_set.all()
    else:
        units = translation.unit_set.filter(
            state__lt=STATE_TRANSLATED,
        )

    # get the translations (optimized: first WeblateMT, then others)
    for unit in units.iterator():
        # a list to store all found translations
        results = []

        # check if weblate is in the chosen engines
        if 'weblate' in engines:
            translation_service = MACHINE_TRANSLATION_SERVICES['weblate']
            result = translation_service.translate(
                unit.translation.language.code,
                unit.get_source_plurals()[0],
                unit,
                user
            )

            for item in result:
                results.append((item['quality'], item['text'], item['service']))

        # use the other machine translation services if weblate did not
        # find anything or has not been chosen
        if 'weblate' not in engines or not results:
            for engine in engines:
                # skip weblate
                if 'weblate' == engine:
                    continue

                translation_service = MACHINE_TRANSLATION_SERVICES[engine]
                result = translation_service.translate(
                    unit.translation.language.code,
                    unit.get_source_plurals()[0],
                    unit,
                    user
                )

                for item in result:
                    results.append((item['quality'], item['text'], item['service']))

        if not results:
            continue

        # sort the list descending - the best result will be on top
        results.sort(key=lambda tup: tup[0], reverse=True)

        # take the "best" result and check the quality score
        result = results[0]
        if result[0] < threshold:
            continue

        with transaction.atomic():
            # Copy translation
            unit.state = STATE_TRANSLATED
            unit.target = result[1]
            # Create single change object for whole merge
            Change.objects.create(
                action=Change.ACTION_AUTO,
                unit=unit,
                user=user,
                author=user
            )
            # Save unit to backend
            unit.save_backend(None, False, False, user=user)
            updated += 1

    return updated
