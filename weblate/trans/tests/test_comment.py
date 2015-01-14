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
Tests for comment views.
"""

from django.core.urlresolvers import reverse

from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.models import Comment


class CommentViewTest(ViewTestCase):
    def setUp(self):
        super(CommentViewTest, self).setUp()
        self.translation = self.subproject.translation_set.get(
            language_code='cs'
        )
        self.translation.invalidate_cache('comments')
        self.translation.invalidate_cache('sourcecomments')

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
        translation = self.subproject.translation_set.get(
            language_code='cs'
        )
        # Check number of comments
        self.assertTrue(unit.has_comment)
        self.assertEqual(
            translation.have_comment,
            1
        )
        self.assertEqual(
            translation.unit_set.count_type('sourcecomments', translation),
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
        translation = self.subproject.translation_set.get(
            language_code='cs'
        )
        # Check number of comments
        self.assertTrue(unit.has_comment)
        self.assertEqual(
            translation.have_comment,
            1
        )
        self.assertEqual(
            translation.unit_set.count_type('sourcecomments', translation),
            1
        )

    def test_delete_comment(self):
        unit = self.get_unit()

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
