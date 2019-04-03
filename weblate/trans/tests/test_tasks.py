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

from weblate.trans.models import Suggestion
from weblate.trans.tasks import cleanup_suggestions
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.state import STATE_TRANSLATED


class CleanupTest(ViewTestCase):
    def test_cleanup_suggestions_case_sensitive(self):
        request = self.get_request()
        unit = self.get_unit()

        # Add two suggestions
        Suggestion.objects.add(unit, 'Zkouška', request)
        Suggestion.objects.add(unit, 'zkouška', request)
        # This should be ignored
        Suggestion.objects.add(unit, 'zkouška', request)
        self.assertEqual(len(unit.suggestions), 2)

        # Perform cleanup, no suggestions should be deleted
        cleanup_suggestions()
        unit = self.get_unit()
        self.assertEqual(len(unit.suggestions), 2)

        # Translate string to one of suggestions
        unit.translate(request, 'zkouška', STATE_TRANSLATED)

        # The cleanup should remove one
        cleanup_suggestions()
        unit = self.get_unit()
        self.assertEqual(len(unit.suggestions), 1)

    def test_cleanup_suggestions_duplicate(self):
        request = self.get_request()
        unit = self.get_unit()

        # Add two suggestions
        Suggestion.objects.add(unit, 'Zkouška', request)
        Suggestion.objects.add(unit, 'zkouška', request)
        self.assertEqual(len(unit.suggestions), 2)

        # Perform cleanup, no suggestions should be deleted
        cleanup_suggestions()
        unit = self.get_unit()
        self.assertEqual(len(unit.suggestions), 2)

        # Create two suggestions with same target
        for suggestion in unit.suggestions:
            suggestion.target = 'zkouška'
            suggestion.save()

        # The cleanup should remove one
        cleanup_suggestions()
        unit = self.get_unit()
        self.assertEqual(len(unit.suggestions), 1)
