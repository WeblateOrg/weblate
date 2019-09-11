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

from datetime import timedelta

from django.test.utils import override_settings
from django.utils import timezone

from weblate.trans.models import Comment, Suggestion
from weblate.trans.tasks import (
    cleanup_old_comments,
    cleanup_old_suggestions,
    cleanup_suggestions,
)
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.state import STATE_TRANSLATED


class CleanupTest(ViewTestCase):
    def test_cleanup_suggestions_case_sensitive(self):
        unit = self.get_unit()
        request = self.get_request()

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
        unit.translate(self.user, 'zkouška', STATE_TRANSLATED)

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

    def test_cleanup_old_suggestions(self, expected=2):
        request = self.get_request()
        unit = self.get_unit()
        Suggestion.objects.add(unit, 'Zkouška', request)
        Suggestion.objects.all().update(
            timestamp=timezone.now() - timedelta(days=30)
        )
        Suggestion.objects.add(unit, 'Zkouška 2', request)
        cleanup_old_suggestions()
        self.assertEqual(Suggestion.objects.count(), expected)

    @override_settings(SUGGESTION_CLEANUP_DAYS=15)
    def test_cleanup_old_suggestions_enabled(self):
        self.test_cleanup_old_suggestions(1)

    def test_cleanup_old_comments(self, expected=2):
        unit = self.get_unit()
        Comment.objects.add(unit, self.user, None, 'Zkouška')
        Comment.objects.all().update(
            timestamp=timezone.now() - timedelta(days=30)
        )
        Comment.objects.add(unit, self.user, None, 'Zkouška 2')
        cleanup_old_comments()
        self.assertEqual(Comment.objects.count(), expected)

    @override_settings(COMMENT_CLEANUP_DAYS=15)
    def test_cleanup_old_comments_enabled(self):
        self.test_cleanup_old_comments(1)
