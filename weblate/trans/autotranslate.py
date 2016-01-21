# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from django.core.exceptions import PermissionDenied

from weblate.trans.models import Unit, Change, SubProject


def auto_translate(user, translation, source, inconsistent, overwrite):
    updated = 0

    if inconsistent:
        units = translation.unit_set.filter_type(
            'inconsistent', translation
        )
    elif overwrite:
        units = translation.unit_set.all()
    else:
        units = translation.unit_set.filter(translated=False)

    sources = Unit.objects.filter(
        translation__language=translation.language,
        translated=True
    )
    if source:
        subprj = SubProject.objects.get(id=source)
        if not subprj.has_acl(user):
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

    for unit in units.iterator():
        # Get first matching entry
        update = sources.filter(source=unit.source)[0]
        # No save if translation is same
        if unit.fuzzy == update.fuzzy and unit.target == update.target:
            continue
        # Copy translation
        unit.fuzzy = update.fuzzy
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
