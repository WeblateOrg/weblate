#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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


from datetime import timedelta

from django.test.utils import override_settings
from django.utils import timezone

from weblate.trans.models import Comment, Suggestion
from weblate.trans.tasks import (
    cleanup_old_comments,
    cleanup_old_suggestions,
    cleanup_suggestions,
    daily_update_checks,
)
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.state import STATE_TRANSLATED


class CleanupTest(ViewTestCase):
    def test_cleanup_suggestions_case_sensitive(self):
        request = self.get_request()
        unit = self.get_unit()

        # Add two suggestions
        Suggestion.objects.add(unit, "Zkouška\n", request)
        Suggestion.objects.add(unit, "zkouška\n", request)
        # This should be ignored
        Suggestion.objects.add(unit, "zkouška\n", request)
        self.assertEqual(len(self.get_unit().suggestions), 2)

        # Perform cleanup, no suggestions should be deleted
        cleanup_suggestions()
        self.assertEqual(len(self.get_unit().suggestions), 2)

        # Translate string to one of suggestions
        unit.translate(self.user, "zkouška\n", STATE_TRANSLATED)

        # The cleanup should remove one
        cleanup_suggestions()
        self.assertEqual(len(self.get_unit().suggestions), 1)

    def test_cleanup_suggestions_duplicate(self):
        request = self.get_request()
        unit = self.get_unit()

        # Add two suggestions
        Suggestion.objects.add(unit, "Zkouška", request)
        Suggestion.objects.add(unit, "zkouška", request)
        self.assertEqual(len(self.get_unit().suggestions), 2)

        # Perform cleanup, no suggestions should be deleted
        cleanup_suggestions()
        self.assertEqual(len(self.get_unit().suggestions), 2)

        # Create two suggestions with same target
        unit.suggestions.update(target="zkouška")

        # The cleanup should remove one
        cleanup_suggestions()
        self.assertEqual(len(self.get_unit().suggestions), 1)

    def test_cleanup_old_suggestions(self, expected=2):
        request = self.get_request()
        unit = self.get_unit()
        Suggestion.objects.add(unit, "Zkouška", request)
        Suggestion.objects.all().update(timestamp=timezone.now() - timedelta(days=30))
        Suggestion.objects.add(unit, "Zkouška 2", request)
        cleanup_old_suggestions()
        self.assertEqual(Suggestion.objects.count(), expected)

    @override_settings(SUGGESTION_CLEANUP_DAYS=15)
    def test_cleanup_old_suggestions_enabled(self):
        self.test_cleanup_old_suggestions(1)

    def test_cleanup_old_comments(self, expected=2):
        request = self.get_request()
        unit = self.get_unit()
        Comment.objects.add(unit.source_unit, request, "Zkouška")
        Comment.objects.all().update(timestamp=timezone.now() - timedelta(days=30))
        Comment.objects.add(unit.source_unit, request, "Zkouška 2")
        cleanup_old_comments()
        self.assertEqual(Comment.objects.count(), expected)

    @override_settings(COMMENT_CLEANUP_DAYS=15)
    def test_cleanup_old_comments_enabled(self):
        self.test_cleanup_old_comments(1)


class TasksTest(ViewTestCase):
    def test_daily_update_checks(self):
        daily_update_checks()
