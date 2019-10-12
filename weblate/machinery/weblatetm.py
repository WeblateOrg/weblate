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

from __future__ import unicode_literals

from django.utils.encoding import force_text

from weblate.machinery.base import MachineTranslation
from weblate.trans.models import Unit


class WeblateTranslation(MachineTranslation):
    """Translation service using strings already translated in Weblate."""

    name = 'Weblate'
    rank_boost = 1
    cache_translations = False

    def is_supported(self, source, language):
        """Any language is supported."""
        return True

    def format_unit_match(self, unit, quality):
        """Format unit to translation service result."""
        if quality < 50:
            return None
        return {
            'text': unit.get_target_plurals()[0],
            'quality': quality,
            'service': self.name,
            'origin': force_text(unit.translation.component),
            'origin_url': unit.get_absolute_url(),
            'source': unit.get_source_plurals()[0],
        }

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from a service."""
        if user:
            kwargs = {
                'translation__component__project__in': user.allowed_projects
            }
        else:
            kwargs = {
                'translation__component__project': unit.translation.component.project
            }
        matching_units = (
            Unit.objects.prefetch()
            .filter(**kwargs)
            .more_like_this(unit, 1000)
            .distinct()
        )

        result = [
            self.format_unit_match(
                munit, self.comparer.similarity(text, munit.get_source_plurals()[0])
            )
            for munit in matching_units
        ]
        while None in result:
            result.remove(None)
        return result
