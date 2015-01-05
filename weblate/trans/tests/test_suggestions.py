# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
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

"""
Tests for sugestion views.
"""

from weblate.trans.models.unitdata import Suggestion
from weblate.trans.tests.test_views import ViewTestCase


class SuggestionsTest(ViewTestCase):
    def add_suggestion_1(self):
        return self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n',
            suggest='yes'
        )

    def add_suggestion_2(self):
        return self.edit_unit(
            'Hello, world!\n',
            'Ahoj svete!\n',
            suggest='yes'
        )

    def test_add(self):
        translate_url = self.get_translation().get_translate_url()
        # Try empty suggestion (should not be added)
        response = self.edit_unit(
            'Hello, world!\n',
            '',
            suggest='yes'
        )
        # We should stay on same message
        self.assertRedirectsOffset(response, translate_url, 0)

        # Add first suggestion
        response = self.add_suggestion_1()
        # We should get to second message
        self.assertRedirectsOffset(response, translate_url, 1)

        # Add second suggestion
        response = self.add_suggestion_2()
        # We should get to second message
        self.assertRedirectsOffset(response, translate_url, 1)

        # Reload from database
        unit = self.get_unit()
        translation = self.subproject.translation_set.get(
            language_code='cs'
        )
        # Check number of suggestions
        self.assertEqual(translation.have_suggestion, 1)
        self.assertBackend(0)

        # Unit should not be translated
        self.assertEqual(len(unit.checks()), 0)
        self.assertFalse(unit.translated)
        self.assertFalse(unit.fuzzy)
        self.assertEqual(len(self.get_unit().suggestions()), 2)

    def test_delete(self):
        translate_url = self.get_translation().get_translate_url()
        # Create two suggestions
        self.add_suggestion_1()
        self.add_suggestion_2()

        # Get ids of created suggestions
        suggestions = [sug.pk for sug in self.get_unit().suggestions()]
        self.assertEqual(len(suggestions), 2)

        # Delete one of suggestions
        response = self.edit_unit(
            'Hello, world!\n',
            '',
            delete=suggestions[0],
        )
        self.assertRedirectsOffset(response, translate_url, 0)

        # Reload from database
        unit = self.get_unit()
        translation = self.subproject.translation_set.get(
            language_code='cs'
        )
        # Check number of suggestions
        self.assertEqual(translation.have_suggestion, 1)
        self.assertBackend(0)

        # Unit should not be translated
        self.assertEqual(len(unit.checks()), 0)
        self.assertFalse(unit.translated)
        self.assertFalse(unit.fuzzy)
        self.assertEqual(len(self.get_unit().suggestions()), 1)

    def test_accept(self):
        translate_url = self.get_translation().get_translate_url()
        # Create two suggestions
        self.add_suggestion_1()
        self.add_suggestion_2()

        # Get ids of created suggestions
        suggestions = [sug.pk for sug in self.get_unit().suggestions()]
        self.assertEqual(len(suggestions), 2)

        # Accept one of suggestions
        response = self.edit_unit(
            'Hello, world!\n',
            '',
            accept=suggestions[1],
        )
        self.assertRedirectsOffset(response, translate_url, 0)

        # Reload from database
        unit = self.get_unit()
        translation = self.subproject.translation_set.get(
            language_code='cs'
        )
        # Check number of suggestions
        self.assertEqual(translation.have_suggestion, 1)

        # Unit should be translated
        self.assertEqual(len(unit.checks()), 0)
        self.assertTrue(unit.translated)
        self.assertFalse(unit.fuzzy)
        self.assertEqual(unit.target, 'Ahoj svete!\n')
        self.assertBackend(1)
        self.assertEqual(len(self.get_unit().suggestions()), 1)

    def test_accept_anonymous(self):
        translate_url = self.get_translation().get_translate_url()
        self.client.logout()
        # Create suggestions
        self.add_suggestion_1()

        self.client.login(username='testuser', password='testpassword')

        # Get ids of created suggestion
        suggestions = list(self.get_unit().suggestions())
        self.assertEqual(len(suggestions), 1)

        self.assertIsNone(suggestions[0].user)

        # Accept one of suggestions
        response = self.edit_unit(
            'Hello, world!\n',
            '',
            accept=suggestions[0].pk,
        )
        self.assertRedirectsOffset(response, translate_url, 0)

        # Reload from database
        unit = self.get_unit()
        translation = self.subproject.translation_set.get(
            language_code='cs'
        )
        # Check number of suggestions
        self.assertEqual(translation.have_suggestion, 0)

        # Unit should be translated
        self.assertEqual(unit.target, 'Nazdar svete!\n')

    def test_vote(self):
        translate_url = self.get_translation().get_translate_url()
        self.subproject.suggestion_voting = True
        self.subproject.suggestion_autoaccept = 0
        self.subproject.save()

        self.add_suggestion_1()

        suggestion_id = self.get_unit().suggestions()[0].pk

        response = self.edit_unit(
            'Hello, world!\n',
            '',
            upvote=suggestion_id,
        )
        self.assertRedirectsOffset(response, translate_url, 0)

        suggestion = Suggestion.objects.get(pk=suggestion_id)
        self.assertEqual(
            suggestion.get_num_votes(),
            1
        )

        response = self.edit_unit(
            'Hello, world!\n',
            '',
            downvote=suggestion_id,
        )
        self.assertRedirectsOffset(response, translate_url, 0)

        suggestion = Suggestion.objects.get(pk=suggestion_id)
        self.assertEqual(
            suggestion.get_num_votes(),
            -1
        )

    def test_vote_autoaccept(self):
        self.add_suggestion_1()

        translate_url = self.get_translation().get_translate_url()
        self.subproject.suggestion_voting = True
        self.subproject.suggestion_autoaccept = 1
        self.subproject.save()

        suggestion_id = self.get_unit().suggestions()[0].pk

        response = self.edit_unit(
            'Hello, world!\n',
            '',
            upvote=suggestion_id,
        )
        self.assertRedirectsOffset(response, translate_url, 0)

        # Reload from database
        unit = self.get_unit()
        translation = self.subproject.translation_set.get(
            language_code='cs'
        )
        # Check number of suggestions
        self.assertEqual(translation.have_suggestion, 0)

        # Unit should be translated
        self.assertEqual(len(unit.checks()), 0)
        self.assertTrue(unit.translated)
        self.assertFalse(unit.fuzzy)
        self.assertEqual(unit.target, 'Nazdar svete!\n')
        self.assertBackend(1)
