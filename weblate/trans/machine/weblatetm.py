# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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

from weblate.permissions.helpers import can_access_project
from weblate.trans.machine.base import MachineTranslation
from weblate.trans.models.unit import Unit


class WeblateBase(MachineTranslation):
    """Base class for Weblate based MT"""
    # pylint: disable=W0223

    def is_supported(self, source, language):
        """Any language is supported."""
        return True

    def format_unit_match(self, unit, text):
        """Format unit to translation service result."""
        return (
            unit.get_target_plurals()[0],
            int(self.dice_coefficient(text, unit.get_source_plurals()[0]) * 100),
            '{0} ({1})'.format(
                self.name,
                force_text(unit.translation.subproject)
            ),
            unit.get_source_plurals()[0],
        )

    """ duplicate bigrams in a word should be counted distinctly
    (per discussion), otherwise 'AA' and 'AAAA' would have a
    dice coefficient of 1...

    source:
    https://en.wikibooks.org/wiki/Algorithm_Implementation/Strings/Dice%27s_coefficient#Python
    """
    def dice_coefficient(self, a, b):
        if not len(a) or not len(b): return 0.0
        """ quick case for true duplicates """
        if a == b: return 1.0
        """ if a != b, and a or b are single chars, then they can't possibly match """
        if len(a) == 1 or len(b) == 1: return 0.0
        
        """ use python list comprehension, preferred over list.append() """
        a_bigram_list = [a[i:i+2] for i in range(len(a)-1)]
        b_bigram_list = [b[i:i+2] for i in range(len(b)-1)]
        
        a_bigram_list.sort()
        b_bigram_list.sort()
        
        # assignments to save function calls
        lena = len(a_bigram_list)
        lenb = len(b_bigram_list)
        # initialize match counters
        matches = i = j = 0
        while (i < lena and j < lenb):
            if a_bigram_list[i] == b_bigram_list[j]:
                matches += 2
                i += 1
                j += 1
            elif a_bigram_list[i] < b_bigram_list[j]:
                i += 1
            else:
                j += 1
        
        score = float(matches) / float(lena + lenb)
        return score

class WeblateTranslation(WeblateBase):
    """Translation service using strings already translated in Weblate."""
    name = 'Weblate'

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from a service."""
        matching_units = Unit.objects.same_source(unit)

        return list(set([
            self.format_unit_match(munit, text)
            for munit in matching_units
            if can_access_project(user, munit.translation.subproject.project)
        ]))


class WeblateSimilarTranslation(WeblateBase):
    """Translation service using strings already translated in Weblate."""
    name = 'Weblate similarity'

    def download_translations(self, source, language, text, unit, user):
        """Download list of possible translations from a service."""
        matching_units = Unit.objects.more_like_this(unit)

        return list(set([
            self.format_unit_match(munit)
            for munit in matching_units
            if can_access_project(user, munit.translation.subproject.project)
        ]))
