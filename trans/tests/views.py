# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
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
Tests for translation views.
"""

from django.test.client import RequestFactory
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.contrib.messages.storage.fallback import FallbackStorage
from trans.tests.models import RepoTestCase
from accounts.models import Profile
import cairo
import re
from urlparse import urlsplit
from cStringIO import StringIO


class ViewTestCase(RepoTestCase):
    def setUp(self):
        super(ViewTestCase, self).setUp()
        # Many tests needs access to the request factory.
        self.factory = RequestFactory()
        # Create user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpassword'
        )
        # Create profile for him
        Profile.objects.create(user=self.user)
        # Create project to have some test base
        self.subproject = self.create_subproject()
        self.project = self.subproject.project
        # Login
        self.client.login(username='testuser', password='testpassword')
        # Prepopulate kwargs
        self.kw_project = {
            'project': self.project.slug
        }
        self.kw_subproject = {
            'project': self.project.slug,
            'subproject': self.subproject.slug,
        }
        self.kw_translation = {
            'project': self.project.slug,
            'subproject': self.subproject.slug,
            'lang': 'cs',
        }
        self.kw_lang_project = {
            'project': self.project.slug,
            'lang': 'cs',
        }

        # Store URL for testing
        self.translation_url = self.get_translation().get_absolute_url()
        self.project_url = self.project.get_absolute_url()
        self.subproject_url = self.subproject.get_absolute_url()

    def get_request(self, *args, **kwargs):
        '''
        Wrapper to get fake request object.
        '''
        request = self.factory.get(*args, **kwargs)
        request.user = self.user
        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        return request

    def get_translation(self):
        return self.subproject.translation_set.get(
            language_code='cs'
        )

    def get_unit(self):
        translation = self.get_translation()
        return translation.unit_set.get(source='Hello, world!\n')

    def change_unit(self, target):
        unit = self.get_unit()
        unit.target = target
        unit.save_backend(self.get_request('/'))

    def assertPNG(self, response):
        '''
        Checks whether response contains valid PNG image.
        '''
        # Check response status code
        self.assertEqual(response.status_code, 200)
        # Try to load PNG with Cairo
        cairo.ImageSurface.create_from_png(
            StringIO(response.content)
        )


class BasicViewTest(ViewTestCase):
    def test_view_home(self):
        response = self.client.get(
            reverse('home')
        )
        self.assertContains(response, 'Test/Test')

    def test_view_project(self):
        response = self.client.get(
            reverse('project', kwargs=self.kw_project)
        )
        self.assertContains(response, 'Test/Test')

    def test_view_subproject(self):
        response = self.client.get(
            reverse('subproject', kwargs=self.kw_subproject)
        )
        self.assertContains(response, 'Test/Test')

    def test_view_translation(self):
        response = self.client.get(
            reverse('translation', kwargs=self.kw_translation)
        )
        self.assertContains(response, 'Test/Test')

    def test_review_source(self):
        response = self.client.get(
            reverse('review_source', kwargs=self.kw_subproject)
        )
        self.assertContains(response, 'Test/Test')

    def test_view_source(self):
        response = self.client.get(
            reverse('show_source', kwargs=self.kw_subproject)
        )
        self.assertContains(response, 'Test/Test')

    def test_view_unit(self):
        unit = self.get_unit()
        response = self.client.get(
            unit.get_absolute_url()
        )
        self.assertContains(response, 'Hello, world!')


class BasicResourceViewTest(BasicViewTest):
    def create_subproject(self):
        return self.create_android()


class BasicPoMonoViewTest(BasicViewTest):
    def create_subproject(self):
        return self.create_po_mono()


class BasicIphoneViewTest(BasicViewTest):
    def create_subproject(self):
        return self.create_iphone()


class BasicLinkViewTest(BasicViewTest):
    def create_subproject(self):
        return self.create_link()


class EditTest(ViewTestCase):
    '''
    Tests for manipulating translation.
    '''
    def setUp(self):
        super(EditTest, self).setUp()
        self.translation = self.subproject.translation_set.get(
            language_code='cs'
        )
        self.translate_url = self.translation.get_translate_url()

    def edit_unit(self, source, target, **kwargs):
        unit = self.translation.unit_set.get(source=source)
        params = {
            'checksum': unit.checksum,
            'target': target,
        }
        params.update(kwargs)
        return self.client.post(
            self.translate_url,
            params
        )

    def assertRedirectsOffset(self, response, exp_path, exp_offset):
        '''
        Asserts that offset in response matches expected one.
        '''
        self.assertEqual(response.status_code, 302)

        # We don't use all variables
        # pylint: disable=W0612
        scheme, netloc, path, query, fragment = urlsplit(response['Location'])

        self.assertEqual(path, exp_path)

        exp_offset = 'offset=%d' % exp_offset
        self.assertTrue(
            exp_offset in query,
            'Offset %s not in %s' % (exp_offset, query)
        )

    def test_edit(self):
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        # We should get to second message
        self.assertRedirectsOffset(response, self.translate_url, 1)
        unit = self.get_unit()
        self.assertEqual(unit.target, 'Nazdar svete!\n')
        self.assertEqual(len(unit.checks()), 0)
        self.assertTrue(unit.translated)
        self.assertFalse(unit.fuzzy)

        # Test that second edit with no change does not break anything
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        # We should get to second message
        self.assertRedirectsOffset(response, self.translate_url, 1)
        unit = self.get_unit()
        self.assertEqual(unit.target, 'Nazdar svete!\n')
        self.assertEqual(len(unit.checks()), 0)
        self.assertTrue(unit.translated)
        self.assertFalse(unit.fuzzy)

        # Test that third edit still works
        response = self.edit_unit(
            'Hello, world!\n',
            'Ahoj svete!\n'
        )
        # We should get to second message
        self.assertRedirectsOffset(response, self.translate_url, 1)
        unit = self.get_unit()
        self.assertEqual(unit.target, 'Ahoj svete!\n')
        self.assertEqual(len(unit.checks()), 0)
        self.assertTrue(unit.translated)
        self.assertFalse(unit.fuzzy)

    def test_suggest(self):
        # Try empty suggestion (should not be added)
        response = self.edit_unit(
            'Hello, world!\n',
            '',
            suggest='yes'
        )
        # We should get to second message
        self.assertRedirectsOffset(response, self.translate_url, 0)

        # Add first suggestion
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n',
            suggest='yes'
        )
        # We should get to second message
        self.assertRedirectsOffset(response, self.translate_url, 1)

        # Add second suggestion
        response = self.edit_unit(
            'Hello, world!\n',
            'Ahoj svete!\n',
            suggest='yes'
        )
        # We should get to second message
        self.assertRedirectsOffset(response, self.translate_url, 1)

        # Reload from database
        unit = self.get_unit()
        translation = self.subproject.translation_set.get(
            language_code='cs'
        )
        # Check number of suggestions
        self.assertEqual(translation.have_suggestion, 1)

        # Unit should not be translated
        self.assertEqual(len(unit.checks()), 0)
        self.assertFalse(unit.translated)
        self.assertFalse(unit.fuzzy)

        # Delete one of suggestions
        self.client.get(
            self.translate_url,
            {'delete': 1},
        )

        # Reload from database
        unit = self.get_unit()
        translation = self.subproject.translation_set.get(
            language_code='cs'
        )
        # Check number of suggestions
        self.assertEqual(translation.have_suggestion, 1)

        # Unit should not be translated
        self.assertEqual(len(unit.checks()), 0)
        self.assertFalse(unit.translated)
        self.assertFalse(unit.fuzzy)

        # Accept one of suggestions
        self.client.get(
            self.translate_url,
            {'accept': 2},
        )

        # Reload from database
        unit = self.get_unit()
        translation = self.subproject.translation_set.get(
            language_code='cs'
        )
        # Check number of suggestions
        self.assertEqual(translation.have_suggestion, 0)

        # Unit should not be translated
        self.assertEqual(len(unit.checks()), 0)
        self.assertTrue(unit.translated)
        self.assertFalse(unit.fuzzy)
        self.assertEqual(unit.target, 'Ahoj svete!\n')

    def test_merge(self):
        # Translate unit to have something to start with
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        unit = self.get_unit()
        # Try the merge
        response = self.client.get(
            self.translate_url,
            {'checksum': unit.checksum, 'merge': unit.id}
        )
        # We should get to second message
        self.assertRedirectsOffset(response, self.translate_url, 1)

        # Test error handling
        unit2 = self.translation.unit_set.get(
            source='Thank you for using Weblate.'
        )
        response = self.client.get(
            self.translate_url,
            {'checksum': unit.checksum, 'merge': unit2.id}
        )
        self.assertContains(response, 'Can not merge different messages!')

    def test_edit_check(self):
        # Save with failing check
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!'
        )
        # We should stay on current message
        self.assertRedirectsOffset(response, self.translate_url, 0)
        unit = self.get_unit()
        self.assertEqual(unit.target, 'Nazdar svete!')
        self.assertTrue(unit.has_failing_check)
        self.assertEqual(len(unit.checks()), 2)
        self.assertEqual(len(unit.active_checks()), 2)

        # Ignore one of checks
        check_id = unit.checks()[0].id
        response = self.client.get(
            reverse('js-ignore-check', kwargs={'check_id': check_id})
        )
        self.assertContains(response, 'ok')
        # Should have one less check
        unit = self.get_unit()
        self.assertTrue(unit.has_failing_check)
        self.assertEqual(len(unit.checks()), 2)
        self.assertEqual(len(unit.active_checks()), 1)

        # Save with no failing checks
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        # We should stay on current message
        self.assertRedirectsOffset(response, self.translate_url, 1)
        unit = self.get_unit()
        self.assertEqual(unit.target, 'Nazdar svete!\n')
        self.assertFalse(unit.has_failing_check)
        self.assertEqual(len(unit.checks()), 0)

    def test_commit_push(self):
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        # We should get to second message
        self.assertRedirectsOffset(response, self.translate_url, 1)
        self.assertTrue(self.translation.git_needs_commit())
        self.assertTrue(self.subproject.git_needs_commit())
        self.assertTrue(self.subproject.project.git_needs_commit())

        self.translation.commit_pending(self.get_request('/'))

        self.assertFalse(self.translation.git_needs_commit())
        self.assertFalse(self.subproject.git_needs_commit())
        self.assertFalse(self.subproject.project.git_needs_commit())

        self.assertTrue(self.translation.git_needs_push())
        self.assertTrue(self.subproject.git_needs_push())
        self.assertTrue(self.subproject.project.git_needs_push())

        self.translation.do_push(self.get_request('/'))

        self.assertFalse(self.translation.git_needs_push())
        self.assertFalse(self.subproject.git_needs_push())
        self.assertFalse(self.subproject.project.git_needs_push())

    def test_auto(self):
        '''
        Tests for automatic translation.
        '''
        # Need extra power
        self.user.is_superuser = True
        self.user.save()

        # Default params
        url = reverse('auto_translation', kwargs=self.kw_translation)
        response = self.client.post(
            url
        )
        self.assertRedirects(response, self.translation_url)


class EditResourceTest(EditTest):
    def create_subproject(self):
        return self.create_android()


class EditPoMonoTest(EditTest):
    def create_subproject(self):
        return self.create_po_mono()


class EditIphoneTest(EditTest):
    def create_subproject(self):
        return self.create_iphone()


class EditLinkTest(EditTest):
    def create_subproject(self):
        return self.create_link()


class SearchViewTest(ViewTestCase):
    def setUp(self):
        super(SearchViewTest, self).setUp()
        self.translation = self.subproject.translation_set.get(
            language_code='cs'
        )
        self.translate_url = self.translation.get_translate_url()

    def do_search(self, params, expected):
        '''
        Helper method for performing search test.
        '''
        response = self.client.get(
            self.translate_url,
            params,
        )
        if expected is None:
            self.assertRedirects(
                response,
                self.translation.get_absolute_url()
            )
        else:
            self.assertContains(
                response,
                expected
            )
        return response

    def test_search(self):
        # Default
        self.do_search(
            {'q': 'hello'},
            'Current filter: Fulltext search for'
        )
        # Fulltext
        self.do_search(
            {'q': 'hello', 'search': 'ftx'},
            'Current filter: Fulltext search for'
        )
        # Substring
        self.do_search(
            {'q': 'hello', 'search': 'substring'},
            'Current filter: Substring search for'
        )
        # Exact string
        self.do_search(
            {'q': 'Thank you for using Weblate.', 'search': 'exact'},
            'Current filter: Search for exact string'
        )
        # Review
        self.do_search(
            {'date': '2010-01-10', 'type': 'review'},
            None
        )

    def test_search_links(self):
        response = self.do_search(
            {'q': 'weblate'},
            'Current filter: Fulltext search for'
        )
        # Extract search ID
        search_id = re.findall(r'sid=([0-9a-f-]*)&amp', response.content)[0]
        # Try access to pages
        response = self.client.get(
            self.translate_url,
            {'sid': search_id, 'offset': 0}
        )
        self.assertContains(
            response,
            'http://demo.weblate.org/',
        )
        response = self.client.get(
            self.translate_url,
            {'sid': search_id, 'offset': 1}
        )
        self.assertContains(
            response,
            'Thank you for using Weblate.',
        )
        # Go to end
        response = self.client.get(
            self.translate_url,
            {'sid': search_id, 'offset': 2}
        )
        self.assertRedirects(
            response,
            self.translation.get_absolute_url()
        )
        # Try invalid SID (should be deleted above)
        response = self.client.get(
            self.translate_url,
            {'sid': search_id, 'offset': 1}
        )
        self.assertRedirects(
            response,
            self.translation.get_absolute_url()
        )

    def test_seach_checksum(self):
        unit = self.translation.unit_set.get(
            source='Try Weblate at <http://demo.weblate.org/>!\n'
        )
        response = self.do_search(
            {'checksum': unit.checksum},
            '3 / 4'
        )
        # Extract search ID
        search_id = re.findall(r'sid=([0-9a-f-]*)&amp', response.content)[0]
        # Navigation
        response = self.do_search(
            {'sid': search_id, 'offset': 0},
            '1 / 4'
        )
        response = self.do_search(
            {'sid': search_id, 'offset': 3},
            '4 / 4'
        )
        response = self.do_search(
            {'sid': search_id, 'offset': 4},
            None
        )

    def test_search_type(self):
        self.do_search(
            {'type': 'untranslated'},
            'Current filter: Untranslated strings'
        )
        self.do_search(
            {'type': 'fuzzy'},
            None
        )
        self.do_search(
            {'type': 'suggestions'},
            None
        )
        self.do_search(
            {'type': 'allchecks'},
            None
        )
        self.do_search(
            {'type': 'plurals'},
            None
        )
        self.do_search(
            {'type': 'all'},
            '1 / 4'
        )


class CommentViewTest(ViewTestCase):
    def setUp(self):
        super(CommentViewTest, self).setUp()
        self.translation = self.subproject.translation_set.get(
            language_code='cs'
        )
        self.translation.invalidate_cache('targetcomments')
        self.translation.invalidate_cache('sourcecomments')

    def test_add_target_comment(self):
        unit = self.get_unit()

        # Add comment
        response = self.client.post(
            reverse('comment', kwargs={'pk': unit.id}),
            {'comment': 'New target testing comment'}
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
            translation.unit_set.count_type('targetcomments', translation),
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
                'type': 'source'
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
        self.assertFalse(unit.has_comment)
        self.assertEqual(
            translation.unit_set.count_type('targetcomments', translation),
            0
        )
        self.assertEqual(
            translation.unit_set.count_type('sourcecomments', translation),
            1
        )


class LanguagesViewTest(ViewTestCase):
    def test_languages(self):
        response = self.client.get(reverse('languages'))
        self.assertContains(response, 'Czech')

        response = self.client.get(reverse(
            'show_language',
            kwargs={'lang': 'cs'}
        ))
        self.assertContains(response, 'Czech')
        self.assertContains(response, 'Test/Test')
