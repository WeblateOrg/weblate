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

from __future__ import unicode_literals

from django.utils.encoding import force_text

from weblate.trans.machine.base import MachineTranslation
from weblate.trans.models import Unit, Project


class WeblateBase(MachineTranslation):
    """Base abstract class for Weblate based MT"""
    # pylint: disable=abstract-method

    def is_supported(self, source, language):
        """Any language is supported."""
        return True

    def format_unit_match(self, unit, quality):
        """Format unit to translation service result."""
        return (
            unit.get_target_plurals()[0],
            quality,
            '{0} ({1})'.format(
                self.name,
                force_text(unit.translation.subproject)
            ),
            unit.get_source_plurals()[0],
        )


class WeblateTranslation(WeblateBase):
    """Translation service using strings already translated in Weblate."""
    name = 'Weblate'

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from a service."""
        matching_units = Unit.objects.prefetch().filter(
            translation__subproject__project__in=Project.objects.all_acl(user)
        ).same_source(unit)

        return list(set((
            self.format_unit_match(munit, 100)
            for munit in matching_units
        )))


class WeblateSimilarTranslation(WeblateBase):
    """Translation service using strings already translated in Weblate."""
    name = 'Weblate similarity'

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from a service."""
        matching_units = Unit.objects.prefetch().filter(
            translation__subproject__project__in=Project.objects.all_acl(user)
        ).more_like_this(unit, 1000)

        return list(set((
            self.format_unit_match(munit, munit.score)
            for munit in matching_units
        )))
