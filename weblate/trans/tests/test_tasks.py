# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from datetime import timedelta
from unittest.mock import patch

from django.test.utils import override_settings
from django.utils import timezone

from weblate.trans.models import Comment, PendingUnitChange, Suggestion
from weblate.trans.models.project import CommitPolicyChoices
from weblate.trans.tasks import (
    cleanup_old_comments,
    cleanup_old_suggestions,
    cleanup_suggestions,
    commit_pending,
    daily_update_checks,
)
from weblate.trans.tests.test_views import ViewTestCase
from weblate.utils.state import STATE_FUZZY, STATE_TRANSLATED
from weblate.utils.version import GIT_VERSION


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
        Comment.objects.add(request, unit, "Zkouška", "global")
        Comment.objects.all().update(timestamp=timezone.now() - timedelta(days=30))
        Comment.objects.add(request, unit, "Zkouška 2", "global")
        cleanup_old_comments()
        self.assertEqual(Comment.objects.count(), expected)

    @override_settings(COMMENT_CLEANUP_DAYS=15)
    def test_cleanup_old_comments_enabled(self) -> None:
        self.test_cleanup_old_comments(1)


class TasksTest(ViewTestCase):
    def test_daily_update_checks(self) -> None:
        daily_update_checks()

    def test_commit_pending(self) -> None:
        self.component.commit_pending_age = 1
        self.component.save()

        component2 = self.create_ftl(name="Component 2", project=self.project)
        component2.commit_pending_age = 3
        component2.save()

        translation = self.component.translation_set.get(language_code="cs")
        unit = translation.unit_set.get(source="Hello, world!\n")
        unit.translate(self.user, "Nazdar svete!\n", STATE_TRANSLATED)

        translation2 = component2.translation_set.get(language_code="cs")
        unit2 = translation2.unit_set.get(source="Hello, ${ name }!")
        unit2.translate(self.user, "Ahoj ${ name }!\n", STATE_TRANSLATED)

        self.assertEqual(self.component.count_pending_units, 1)
        self.assertEqual(component2.count_pending_units, 1)

        PendingUnitChange.objects.update(timestamp=timezone.now() - timedelta(hours=2))

        commit_pending()
        self.assertEqual(self.component.count_pending_units, 0)
        self.assertEqual(component2.count_pending_units, 1)

        commit_pending(hours=1)
        self.assertEqual(component2.count_pending_units, 0)

    @patch("weblate.trans.tasks.perform_commit")
    def test_commit_pending_with_ineligible_changes(self, mock_perform_commit) -> None:
        """Test that perform_commit is not called when all changes are ineligible."""
        self.project.commit_policy = CommitPolicyChoices.WITHOUT_NEEDS_EDITING
        self.project.save()

        self.component.commit_pending_age = 1
        self.component.save()

        translation = self.component.translation_set.get(language_code="cs")
        unit = translation.unit_set.get(source="Hello, world!\n")
        unit.translate(self.user, "Nazdar svete!\n", STATE_FUZZY)

        component2 = self.create_ftl(name="Component 2", project=self.project)
        component2.commit_pending_age = 1
        component2.save()

        translation2 = component2.translation_set.get(language_code="cs")
        unit2 = translation2.unit_set.get(source="Hello, ${ name }!")
        unit2.translate(self.user, "Ahoj ${ name }!\n", STATE_TRANSLATED)

        pending_change = unit2.pending_changes.first()
        pending_change.metadata = {
            "last_failed": timezone.now().isoformat(),
            "failed_revision": translation2.revision,
            "weblate_version": GIT_VERSION,
            "blocking_unit": True,
        }
        pending_change.save()

        self.assertEqual(self.component.count_pending_units, 0)
        self.assertEqual(component2.count_pending_units, 0)
        self.assertEqual(
            PendingUnitChange.objects.for_component(
                self.component, apply_filters=False
            ).count(),
            1,
        )
        self.assertEqual(
            PendingUnitChange.objects.for_component(
                component2, apply_filters=False
            ).count(),
            1,
        )

        PendingUnitChange.objects.update(timestamp=timezone.now() - timedelta(hours=2))

        commit_pending()
        mock_perform_commit.delay.assert_not_called()

        self.assertEqual(self.component.count_pending_units, 0)
        self.assertEqual(component2.count_pending_units, 0)
        self.assertEqual(
            PendingUnitChange.objects.for_component(
                self.component, apply_filters=False
            ).count(),
            1,
        )
        self.assertEqual(
            PendingUnitChange.objects.for_component(
                component2, apply_filters=False
            ).count(),
            1,
        )

        unit.translate(self.user, "Nazdar svete!\n", STATE_TRANSLATED)
        PendingUnitChange.objects.update(timestamp=timezone.now() - timedelta(hours=2))

        self.assertEqual(self.component.count_pending_units, 1)
        self.assertEqual(component2.count_pending_units, 0)
        self.assertEqual(
            PendingUnitChange.objects.for_component(
                self.component, apply_filters=False
            ).count(),
            2,
        )
        self.assertEqual(
            PendingUnitChange.objects.for_component(
                component2, apply_filters=False
            ).count(),
            1,
        )

        commit_pending()
        mock_perform_commit.delay.assert_called_with(
            self.component.pk, "commit_pending"
        )

        # actually call commit_pending on the component to test count_pending_units is updated
        self.component.commit_pending("commit_pending", None)
        component2.commit_pending("commit_pending", None)

        self.assertEqual(self.component.count_pending_units, 0)
        self.assertEqual(component2.count_pending_units, 0)
        self.assertEqual(
            PendingUnitChange.objects.for_component(
                self.component, apply_filters=False
            ).count(),
            0,
        )
        self.assertEqual(
            PendingUnitChange.objects.for_component(
                component2, apply_filters=False
            ).count(),
            1,
        )
