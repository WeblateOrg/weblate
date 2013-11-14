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
from django.core import mail
from django.conf import settings
from trans.models.changes import Change
from trans.models.unitdata import Suggestion
from trans.tests.test_models import RepoTestCase
from accounts.models import Profile
from PIL import Image
import re
import time
from urlparse import urlsplit
from cStringIO import StringIO


class ViewTestCase(RepoTestCase):
    def setUp(self):
        super(ViewTestCase, self).setUp()
        # Many tests needs access to the request factory.
        self.factory = RequestFactory()
        # Create user
        self.user = User.objects.create_user(
            'testuser',
            'noreply@weblate.org',
            'testpassword'
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

    def get_unit(self, source='Hello, world!\n'):
        translation = self.get_translation()
        return translation.unit_set.get(source=source)

    def change_unit(self, target):
        unit = self.get_unit()
        unit.target = target
        unit.save_backend(self.get_request('/'))

    def edit_unit(self, source, target, **kwargs):
        unit = self.get_translation().unit_set.get(source=source)
        params = {
            'checksum': unit.checksum,
            'target': target,
        }
        params.update(kwargs)
        return self.client.post(
            self.get_translation().get_translate_url(),
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

    def assertPNG(self, response):
        '''
        Checks whether response contains valid PNG image.
        '''
        # Check response status code
        self.assertEqual(response.status_code, 200)
        # Try to load PNG with PIL
        image = Image.open(StringIO(response.content))
        self.assertEquals(image.format, 'PNG')

    def assertBackend(self, expected_translated):
        '''
        Checks that backend has correct data.
        '''
        translation = self.subproject.translation_set.get(
            language_code='cs'
        )
        store = translation.subproject.file_format_cls(
            translation.get_filename(),
            None
        )
        messages = set()
        translated = 0

        for unit in store.all_units():
            if not unit.is_translatable():
                continue
            checksum = unit.get_checksum()
            self.assertFalse(
                checksum in messages,
                'Duplicate string in in backend file!'
            )
            if unit.is_translated():
                translated += 1

        self.assertEqual(
            translated,
            expected_translated,
            'Did not found expected number of translations.'
        )


class NewLangTest(ViewTestCase):
    def create_subproject(self):
        return self.create_po_new_base()

    def test_none(self):
        self.project.new_lang = 'none'
        self.project.save()

        response = self.client.get(
            reverse('subproject', kwargs=self.kw_subproject)
        )
        self.assertNotContains(response, 'New translation')

    def test_url(self):
        self.project.new_lang = 'url'
        self.project.instructions = 'http://example.com/instructions'
        self.project.save()

        response = self.client.get(
            reverse('subproject', kwargs=self.kw_subproject)
        )
        self.assertContains(response, 'New translation')
        self.assertContains(response, 'http://example.com/instructions')

    def test_contact(self):
        # Hack to allow sending of mails
        settings.ADMINS = (('Weblate test', 'noreply@weblate.org'), )

        self.project.new_lang = 'contact'
        self.project.save()

        response = self.client.get(
            reverse('subproject', kwargs=self.kw_subproject)
        )
        self.assertContains(response, 'New translation')
        self.assertContains(response, '/new-lang/')

        response = self.client.post(
            reverse('new-language', kwargs=self.kw_subproject),
            {'lang': 'af'},
        )
        self.assertRedirects(
            response,
            self.subproject.get_absolute_url()
        )

        # Verify mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] New language request in Test/Test',
        )

    def test_add(self):
        self.project.new_lang = 'add'
        self.project.save()

        self.assertFalse(
            self.subproject.translation_set.filter(
                language__code='af'
            ).exists()
        )

        response = self.client.get(
            reverse('subproject', kwargs=self.kw_subproject)
        )
        self.assertContains(response, 'New translation')
        self.assertContains(response, '/new-lang/')

        response = self.client.post(
            reverse('new-language', kwargs=self.kw_subproject),
            {'lang': 'af'},
        )
        self.assertRedirects(
            response,
            self.subproject.get_absolute_url()
        )
        self.assertTrue(
            self.subproject.translation_set.filter(
                language__code='af'
            ).exists()
        )


class AndroidNewLangTest(NewLangTest):
    def create_subproject(self):
        return self.create_android()


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


class BasicJavaViewTest(BasicViewTest):
    def create_subproject(self):
        return self.create_java()


class BasicXliffViewTest(BasicViewTest):
    def create_subproject(self):
        return self.create_xliff()


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
        self.assertBackend(1)

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
        self.assertBackend(1)

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
        self.assertBackend(1)

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
        self.assertBackend(1)
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

    def test_revert(self):
        source = 'Hello, world!\n'
        target = 'Nazdar svete!\n'
        target_2 = 'Hei maailma!\n'
        self.edit_unit(
            source,
            target
        )
        # Ensure other edit gets different timestamp
        time.sleep(1)
        self.edit_unit(
            source,
            target_2
        )
        unit = self.get_unit()
        changes = Change.objects.content().filter(unit=unit)
        self.assertEqual(changes[1].target, target)
        self.assertEqual(changes[0].target, target_2)
        self.assertBackend(1)
        # revert it
        self.client.get(
            self.translate_url,
            {'checksum': unit.checksum, 'revert': changes[1].id}
        )
        unit = self.get_unit()
        self.assertEqual(unit.target, target)
        # check that we cannot revert to string from another translation
        self.edit_unit(
            'Thank you for using Weblate.',
            'Kiitoksia Weblaten kaytosta.'
        )
        unit2 = self.get_unit(
            source='Thank you for using Weblate.'
        )
        change = Change.objects.filter(unit=unit2)[0]
        response = self.client.get(
            self.translate_url,
            {'checksum': unit.checksum, 'revert': change.id}
        )
        self.assertContains(response, "Can not revert to different unit")
        self.assertBackend(2)

    def test_edit_message(self):
        # Save with failing check
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!',
            commit_message='Fixing issue #666',
        )
        # We should get to second message
        self.assertRedirectsOffset(response, self.translate_url, 1)

        # Did the commit message got stored?
        translation = self.get_translation()
        self.assertEquals(
            'Fixing issue #666',
            translation.commit_message
        )

        # Try commiting
        translation.commit_pending(self.get_request('/'))

    def test_edit_fixup(self):
        # Save with failing check
        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!'
        )
        # We should get to second message
        self.assertRedirectsOffset(response, self.translate_url, 1)
        unit = self.get_unit()
        self.assertEqual(unit.target, 'Nazdar svete!\n')
        self.assertFalse(unit.has_failing_check)
        self.assertEqual(len(unit.checks()), 0)
        self.assertEqual(len(unit.active_checks()), 0)
        self.assertEqual(unit.translation.failing_checks, 0)
        self.assertBackend(1)

    def test_edit_check(self):
        # Save with failing check
        response = self.edit_unit(
            'Hello, world!\n',
            'Hello, world!\n',
        )
        # We should stay on current message
        self.assertRedirectsOffset(response, self.translate_url, 0)
        unit = self.get_unit()
        self.assertEqual(unit.target, 'Hello, world!\n')
        self.assertTrue(unit.has_failing_check)
        self.assertEqual(len(unit.checks()), 1)
        self.assertEqual(len(unit.active_checks()), 1)
        self.assertEqual(unit.translation.failing_checks, 1)

        # Ignore check
        check_id = unit.checks()[0].id
        response = self.client.get(
            reverse('js-ignore-check', kwargs={'check_id': check_id})
        )
        self.assertContains(response, 'ok')
        # Should have one less check
        unit = self.get_unit()
        self.assertFalse(unit.has_failing_check)
        self.assertEqual(len(unit.checks()), 1)
        self.assertEqual(len(unit.active_checks()), 0)
        self.assertEqual(unit.translation.failing_checks, 0)

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
        self.assertEqual(unit.translation.failing_checks, 0)
        self.assertBackend(1)

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

    def test_fuzzy(self):
        '''
        Test for fuzzy flag handling.
        '''
        unit = self.get_unit()
        self.assertFalse(unit.fuzzy)
        self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n',
            fuzzy='yes'
        )
        unit = self.get_unit()
        self.assertTrue(unit.fuzzy)
        self.assertEqual(unit.target, 'Nazdar svete!\n')
        self.assertFalse(unit.has_failing_check)
        self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n',
        )
        unit = self.get_unit()
        self.assertFalse(unit.fuzzy)
        self.assertEqual(unit.target, 'Nazdar svete!\n')
        self.assertFalse(unit.has_failing_check)
        self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n',
            fuzzy='yes'
        )
        unit = self.get_unit()
        self.assertTrue(unit.fuzzy)
        self.assertEqual(unit.target, 'Nazdar svete!\n')
        self.assertFalse(unit.has_failing_check)


class EditResourceTest(EditTest):
    def create_subproject(self):
        return self.create_android()


class EditPoMonoTest(EditTest):
    def create_subproject(self):
        return self.create_po_mono()


class EditIphoneTest(EditTest):
    def create_subproject(self):
        return self.create_iphone()


class EditJavaTest(EditTest):
    def create_subproject(self):
        return self.create_java()


class EditXliffTest(EditTest):
    def create_subproject(self):
        return self.create_xliff()


class EditLinkTest(EditTest):
    def create_subproject(self):
        return self.create_link()


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
        self.assertEquals(len(self.get_unit().suggestions()), 2)

    def test_delete(self):
        translate_url = self.get_translation().get_translate_url()
        # Create two suggestions
        self.add_suggestion_1()
        self.add_suggestion_2()

        # Get ids of created suggestions
        suggestions = [sug.pk for sug in self.get_unit().suggestions()]
        self.assertEquals(len(suggestions), 2)

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
        self.assertEquals(len(self.get_unit().suggestions()), 1)

    def test_accept(self):
        translate_url = self.get_translation().get_translate_url()
        # Create two suggestions
        self.add_suggestion_1()
        self.add_suggestion_2()

        # Get ids of created suggestions
        suggestions = [sug.pk for sug in self.get_unit().suggestions()]
        self.assertEquals(len(suggestions), 2)

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
        self.assertEquals(len(self.get_unit().suggestions()), 1)

    def test_accept_anonymous(self):
        translate_url = self.get_translation().get_translate_url()
        self.client.logout()
        # Create suggestions
        self.add_suggestion_1()

        self.client.login(username='testuser', password='testpassword')

        # Get ids of created suggestion
        suggestions = list(self.get_unit().suggestions())
        self.assertEquals(len(suggestions), 1)

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

    def test_all_search(self):
        '''
        Searching in all projects.
        '''
        response = self.client.get(
            reverse('search'),
            {'q': 'hello'}
        )
        self.assertContains(
            response,
            '<span class="hlmatch">Hello</span>, world'
        )

    def test_project_search(self):
        '''
        Searching within project.
        '''
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
        # Short string
        self.do_search(
            {'q': 'x'},
            'Ensure this value has at least 2 characters (it has 1).'
        )
        # Wrong type
        self.do_search(
            {'q': 'xxxxx', 'search': 'xxxx'},
            'Select a valid choice. xxxx is not one of the available choices.'
        )

    def test_review(self):
        # Review
        self.do_search(
            {'date': '2010-01-10', 'type': 'review'},
            None
        )
        # Review, invalid date
        self.do_search(
            {'date': '2010-01-', 'type': 'review'},
            'Enter a valid date.'
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

    def test_search_plural(self):
        response = self.do_search(
            {'q': 'banana'},
            'banana'
        )
        self.assertContains(response, 'One')
        self.assertContains(response, 'Few')
        self.assertContains(response, 'Other')
        self.assertNotContains(response, 'Plural form ')

    def test_checksum(self):
        response = self.do_search({'checksum': 'invalid'}, None)
        self.assertRedirects(
            response,
            self.get_translation().get_absolute_url()
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
