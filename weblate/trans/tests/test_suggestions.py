# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for suggestion views."""

from django.conf import settings
from django.urls import reverse

from weblate.trans.models import Suggestion, WorkflowSetting
from weblate.trans.tests.test_views import ViewTestCase


class SuggestionsTest(ViewTestCase):
    def add_suggestion_1(self):
        return self.edit_unit("Hello, world!\n", "Nazdar svete!\n", suggest="yes")

    def add_suggestion_2(self):
        return self.edit_unit("Hello, world!\n", "Ahoj svete!\n", suggest="yes")

    def test_add(self) -> None:
        translate_url = reverse("translate", kwargs=self.kw_translation)
        # Try empty suggestion (should not be added)
        response = self.edit_unit("Hello, world!\n", "", suggest="yes")
        # We should stay on same message
        self.assert_redirects_offset(response, translate_url, 1)

        # Add first suggestion
        response = self.add_suggestion_1()
        # We should get to second message
        self.assert_redirects_offset(response, translate_url, 2)

        # Add second suggestion
        response = self.add_suggestion_2()
        # We should get to second message
        self.assert_redirects_offset(response, translate_url, 2)

        # Reload from database
        unit = self.get_unit()
        translation = self.component.translation_set.get(language_code="cs")
        # Check number of suggestions
        self.assertEqual(translation.stats.suggestions, 1)
        self.assert_backend(0)

        # Unit should not be translated
        self.assertEqual(len(unit.all_checks), 0)
        self.assertFalse(unit.translated)
        self.assertFalse(unit.fuzzy)
        self.assertEqual(len(self.get_unit().suggestions), 2)

    def test_add_same(self) -> None:
        translate_url = reverse("translate", kwargs=self.kw_translation)
        # Add first suggestion
        response = self.add_suggestion_1()
        # We should get to second message
        self.assert_redirects_offset(response, translate_url, 2)
        # Add first suggestion
        response = self.add_suggestion_1()
        # We should stay on same message
        self.assert_redirects_offset(response, translate_url, 1)

        # Reload from database
        unit = self.get_unit()
        translation = self.component.translation_set.get(language_code="cs")

        # Check number of suggestions
        self.assertEqual(translation.stats.suggestions, 1)
        self.assert_backend(0)

        # Unit should not be translated
        self.assertEqual(len(unit.all_checks), 0)
        self.assertFalse(unit.translated)
        self.assertFalse(unit.fuzzy)
        self.assertEqual(len(self.get_unit().suggestions), 1)

    def test_delete(self, **kwargs) -> None:
        translate_url = reverse("translate", kwargs=self.kw_translation)
        # Create two suggestions
        self.add_suggestion_1()
        self.add_suggestion_2()

        # Get ids of created suggestions
        suggestions = self.get_unit().suggestions.values_list("pk", flat=True)
        self.assertEqual(len(suggestions), 2)

        # Delete one of suggestions
        response = self.edit_unit(
            "Hello, world!\n", "", delete=suggestions[0], **kwargs
        )
        self.assert_redirects_offset(response, translate_url, 1)

        # Ensure we have just one
        suggestions = self.get_unit().suggestions.values_list("pk", flat=True)
        self.assertEqual(len(suggestions), 1)

    def test_change_diff_for_deleted_suggestion(self, **kwargs) -> None:
        """
        Check that the diff for deleted suggestion is correctly displayed.

        When a suggestion is deleted, the diff for the deleted suggestion
        should be the same as the corresponding "Suggestion added"
        """
        translate_url = reverse("translate", kwargs=self.kw_translation)
        self.edit_unit("Hello, world!\n", "Nazdar!\n")
        self.add_suggestion_1()
        response = self.client.get(translate_url)
        self.assertNotContains(response, "Suggestion removed")
        # 1st diff occurrence is in the "Suggestions" tab, the 2nd in "History" tab
        self.assertContains(
            response,
            """Nazdar<ins><span class="hlspace"><span class="space-space"> </span></span>svete</ins>!""",
            count=2,
        )

        suggestions = self.get_unit().suggestions.values_list("pk", flat=True)
        self.assertEqual(len(suggestions), 1)
        response = self.edit_unit(
            "Hello, world!\n", "", delete=suggestions[0], **kwargs
        )

        response = self.client.get(translate_url)
        self.assertContains(response, "Suggestion removed", count=1)
        self.assertContains(response, "Suggestion added", count=1)
        # both diff occurrence are in "History" tab,
        # as suggestion is no longer visible in the "Suggestion" tab
        self.assertContains(
            response,
            """Nazdar<ins><span class="hlspace"><span class="space-space"> </span></span>svete</ins>!""",
            count=2,
        )

    def test_delete_spam(self) -> None:
        self.test_delete(spam="1")

    def test_accept_edit(self) -> None:
        translate_url = reverse("translate", kwargs=self.kw_translation)
        # Create suggestion
        self.add_suggestion_1()

        # Get ids of created suggestions
        suggestion = self.get_unit().suggestions[0].pk

        # Accept one of suggestions
        response = self.edit_unit("Hello, world!\n", "", accept_edit=suggestion)
        self.assert_redirects_offset(response, translate_url, 1)

    def test_accept(self) -> None:
        translate_url = reverse("translate", kwargs=self.kw_translation)
        # Create two suggestions
        self.add_suggestion_1()
        self.add_suggestion_2()

        # Get ids of created suggestions
        suggestions = self.get_unit().suggestions
        self.assertEqual(suggestions.count(), 2)

        # Accept one of suggestions
        response = self.edit_unit(
            "Hello, world!\n", "", accept=suggestions.get(target="Ahoj svete!\n").pk
        )
        self.assert_redirects_offset(response, translate_url, 2)

        # Reload from database
        unit = self.get_unit()
        translation = self.component.translation_set.get(language_code="cs")
        # Check number of suggestions
        self.assertEqual(translation.stats.suggestions, 1)

        # Unit should be translated
        self.assertEqual(len(unit.all_checks), 0)
        self.assertTrue(unit.translated)
        self.assertFalse(unit.fuzzy)
        self.assertEqual(unit.target, "Ahoj svete!\n")
        self.assert_backend(1)
        self.assertEqual(len(self.get_unit().suggestions), 1)

    def test_accept_anonymous(self) -> None:
        translate_url = reverse("translate", kwargs=self.kw_translation)
        self.client.logout()
        # Create suggestions
        self.add_suggestion_1()

        self.client.login(username="testuser", password="testpassword")

        # Get ids of created suggestion
        suggestions = list(self.get_unit().suggestions)
        self.assertEqual(len(suggestions), 1)

        self.assertEqual(suggestions[0].user.username, settings.ANONYMOUS_USER_NAME)

        # Accept one of suggestions
        response = self.edit_unit("Hello, world!\n", "", accept=suggestions[0].pk)
        self.assert_redirects_offset(response, translate_url, 2)

        # Reload from database
        unit = self.get_unit()
        translation = self.component.translation_set.get(language_code="cs")
        # Check number of suggestions
        self.assertEqual(translation.stats.suggestions, 0)

        # Unit should be translated
        self.assertEqual(unit.target, "Nazdar svete!\n")

    def test_vote_language(self) -> None:
        WorkflowSetting.objects.create(
            project=self.project,
            language=self.translation.language,
            enable_suggestions=True,
            suggestion_voting=True,
            suggestion_autoaccept=0,
        )

        self.assert_vote()

    def test_vote(self) -> None:
        self.component.suggestion_voting = True
        self.component.suggestion_autoaccept = 0
        self.component.save()

        self.assert_vote()

    def assert_vote(self) -> None:
        translate_url = reverse("translate", kwargs=self.kw_translation)
        self.add_suggestion_1()

        suggestion_id = self.get_unit().suggestions[0].pk

        response = self.edit_unit("Hello, world!\n", "", upvote=suggestion_id)
        self.assert_redirects_offset(response, translate_url, 2)

        suggestion = Suggestion.objects.get(pk=suggestion_id)
        self.assertEqual(suggestion.get_num_votes(), 1)

        response = self.edit_unit("Hello, world!\n", "", downvote=suggestion_id)
        self.assert_redirects_offset(response, translate_url, 1)

        suggestion = Suggestion.objects.get(pk=suggestion_id)
        self.assertEqual(suggestion.get_num_votes(), -1)

    def test_vote_autoaccept(self) -> None:
        self.add_suggestion_1()

        translate_url = reverse("translate", kwargs=self.kw_translation)
        self.component.suggestion_voting = True
        self.component.suggestion_autoaccept = 1
        self.component.save()

        suggestion_id = self.get_unit().suggestions[0].pk

        response = self.edit_unit("Hello, world!\n", "", upvote=suggestion_id)
        self.assert_redirects_offset(response, translate_url, 2)

        # Reload from database
        unit = self.get_unit()
        translation = self.component.translation_set.get(language_code="cs")
        # Check number of suggestions
        self.assertEqual(translation.stats.suggestions, 0)

        # Unit should be translated
        self.assertEqual(len(unit.all_checks), 0)
        self.assertTrue(unit.translated)
        self.assertFalse(unit.fuzzy)
        self.assertEqual(unit.target, "Nazdar svete!\n")
        self.assert_backend(1)

    def test_vote_when_same_suggestion(self) -> None:
        translate_url = reverse("translate", kwargs=self.kw_translation)
        self.component.suggestion_voting = True
        self.component.suggestion_autoaccept = 0
        self.component.save()

        # Add the first suggestion as default test-user
        response = self.add_suggestion_1()
        suggestion_id = self.get_unit().suggestions[0].pk
        suggestion = Suggestion.objects.get(pk=suggestion_id)

        # Suggestion get vote from the user that makes suggestion
        self.assertEqual(suggestion.get_num_votes(), 1)

        # Add suggestion as second user
        self.log_as_jane()
        response = self.add_suggestion_1()

        # When adding the same suggestion, we stay on the same page
        self.assert_redirects_offset(response, translate_url, 1)
        suggestion = Suggestion.objects.get(pk=suggestion_id)

        # and the suggestion gets an upvote
        self.assertEqual(suggestion.get_num_votes(), 2)
