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

"""
Tests for comment views.
"""

from django.urls import reverse

from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.models import Comment


class CommentViewTest(FixtureTestCase):
    def setUp(self):
        super(CommentViewTest, self).setUp()
        self.translation = self.component.translation_set.get(
            language_code='cs'
        )

    def test_add_target_comment(self):
        unit = self.get_unit()

        # Add comment
        response = self.client.post(
            reverse('comment', kwargs={'pk': unit.id}),
            {
                'comment': 'New target testing comment',
                'scope': 'translation',
            }
        )
        self.assertRedirects(response, unit.get_absolute_url())

        # Check it is shown on page
        response = self.client.get(unit.get_absolute_url())
        self.assertContains(response, 'New target testing comment')

        # Reload from database
        unit = self.get_unit()
        translation = self.component.translation_set.get(
            language_code='cs'
        )
        # Check number of comments
        self.assertTrue(unit.has_comment)
        self.assertEqual(
            translation.stats.comments,
            1
        )
        self.assertEqual(
            translation.stats.sourcecomments,
            0
        )

    def test_add_source_comment(self):
        unit = self.get_unit()

        # Add comment
        response = self.client.post(
            reverse('comment', kwargs={'pk': unit.id}),
            {
                'comment': 'New source testing comment',
                'scope': 'global',
            }
        )
        self.assertRedirects(response, unit.get_absolute_url())

        # Check it is shown on page
        response = self.client.get(unit.get_absolute_url())
        self.assertContains(response, 'New source testing comment')

        # Reload from database
        unit = self.get_unit()
        translation = self.component.translation_set.get(
            language_code='cs'
        )
        # Check number of comments
        self.assertTrue(unit.has_comment)
        self.assertEqual(
            translation.stats.comments,
            1
        )
        self.assertEqual(
            translation.stats.sourcecomments,
            1
        )

    def test_delete_comment(self):
        unit = self.get_unit()
        self.make_manager()

        # Add comment
        response = self.client.post(
            reverse('comment', kwargs={'pk': unit.id}),
            {
                'comment': 'New target testing comment',
                'scope': 'translation',
            }
        )

        comment = Comment.objects.all()[0]
        response = self.client.post(
            reverse('delete-comment', kwargs={'pk': comment.pk})
        )
        self.assertRedirects(response, unit.get_absolute_url())
