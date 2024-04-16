# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

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
    def test_cleanup_suggestions_case_sensitive(self) -> None:
        request = self.get_request()
        unit = self.get_unit()

        # Add two suggestions
        Suggestion.objects.add(unit, ["Zkouška\n"], request)
        Suggestion.objects.add(unit, ["zkouška\n"], request)
        # This should be ignored
        Suggestion.objects.add(unit, ["zkouška\n"], request)
        self.assertEqual(len(self.get_unit().suggestions), 2)

        # Perform cleanup, no suggestions should be deleted
        cleanup_suggestions()
        self.assertEqual(len(self.get_unit().suggestions), 2)

        # Translate string to one of suggestions
        unit.translate(self.user, "zkouška\n", STATE_TRANSLATED)

        # The cleanup should remove one
        cleanup_suggestions()
        self.assertEqual(len(self.get_unit().suggestions), 1)

    def test_cleanup_suggestions_duplicate(self) -> None:
        request = self.get_request()
        unit = self.get_unit()

        # Add two suggestions
        Suggestion.objects.add(unit, ["Zkouška"], request)
        Suggestion.objects.add(unit, ["zkouška"], request)
        self.assertEqual(len(self.get_unit().suggestions), 2)

        # Perform cleanup, no suggestions should be deleted
        cleanup_suggestions()
        self.assertEqual(len(self.get_unit().suggestions), 2)

        # Create two suggestions with same target
        unit.suggestions.update(target="zkouška")

        # The cleanup should remove one
        cleanup_suggestions()
        self.assertEqual(len(self.get_unit().suggestions), 1)

    def test_cleanup_old_suggestions(self, expected=2) -> None:
        request = self.get_request()
        unit = self.get_unit()
        Suggestion.objects.add(unit, ["Zkouška"], request)
        Suggestion.objects.all().update(timestamp=timezone.now() - timedelta(days=30))
        Suggestion.objects.add(unit, ["Zkouška 2"], request)
        cleanup_old_suggestions()
        self.assertEqual(Suggestion.objects.count(), expected)

    @override_settings(SUGGESTION_CLEANUP_DAYS=15)
    def test_cleanup_old_suggestions_enabled(self) -> None:
        self.test_cleanup_old_suggestions(1)

    def test_cleanup_old_comments(self, expected=2) -> None:
        request = self.get_request()
        unit = self.get_unit()
        Comment.objects.add(unit.source_unit, request, "Zkouška")
        Comment.objects.all().update(timestamp=timezone.now() - timedelta(days=30))
        Comment.objects.add(unit.source_unit, request, "Zkouška 2")
        cleanup_old_comments()
        self.assertEqual(Comment.objects.count(), expected)

    @override_settings(COMMENT_CLEANUP_DAYS=15)
    def test_cleanup_old_comments_enabled(self) -> None:
        self.test_cleanup_old_comments(1)


class TasksTest(ViewTestCase):
    def test_daily_update_checks(self) -> None:
        daily_update_checks()
