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
Tests for translation views.
"""

import time
from urlparse import urlsplit
from cStringIO import StringIO
from xml.dom import minidom

from django.test.client import RequestFactory
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core import mail
from PIL import Image

from weblate import appsettings
from weblate.trans.models.whiteboard import WhiteboardMessage
from weblate.trans.models.changes import Change
from weblate.trans.tests.test_models import RepoTestCase
from weblate.accounts.models import Profile


class RegistrationTestMixin(object):
    """
    Helper to share code for registration testing.
    """
    def assert_registration_mailbox(self, match=None):
        if match is None:
            match = '[Weblate] Your registration on Weblate'
        # Check mailbox
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            match
        )

        # Parse URL
        line = ''
        for line in mail.outbox[0].body.splitlines():
            if line.startswith('http://example.com'):
                break

        # Return confirmation URL
        return line[18:]


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
        return translation.unit_set.get(source__startswith=source)

    def change_unit(self, target):
        unit = self.get_unit()
        unit.target = target
        unit.save_backend(self.get_request('/'))

    def edit_unit(self, source, target, **kwargs):
        '''
        Does edit single unit using web interface.
        '''
        unit = self.get_unit(source)
        params = {
            'checksum': unit.checksum,
            'target_0': target,
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
        self.assertEqual(image.format, 'PNG')

    def assertSVG(self, response):
        """
        Checks whether response is a SVG image.
        """
        # Check response status code
        self.assertEqual(response.status_code, 200)
        dom = minidom.parseString(response.content)
        self.assertEquals(dom.firstChild.nodeName, 'svg')

    def assertBackend(self, expected_translated):
        '''
        Checks that backend has correct data.
        '''
        translation = self.get_translation()
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
            'Did not found expected number of ' +
            'translations ({0} != {1}).'.format(
                translated, expected_translated
            )
        )


class NewLangTest(ViewTestCase):
    def create_subproject(self):
        return self.create_po_new_base()

    def test_none(self):
        self.subproject.new_lang = 'none'
        self.subproject.save()

        response = self.client.get(
            reverse('subproject', kwargs=self.kw_subproject)
        )
        self.assertNotContains(response, 'New translation')

    def test_url(self):
        self.subproject.new_lang = 'url'
        self.subproject.save()
        self.project.instructions = 'http://example.com/instructions'
        self.project.save()

        response = self.client.get(
            reverse('subproject', kwargs=self.kw_subproject)
        )
        self.assertContains(response, 'New translation')
        self.assertContains(response, 'http://example.com/instructions')

    def test_contact(self):
        self.subproject.new_lang = 'contact'
        self.subproject.save()

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
        self.subproject.new_lang = 'add'
        self.subproject.save()

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

    def test_view_unit(self):
        unit = self.get_unit()
        response = self.client.get(
            unit.get_absolute_url()
        )
        self.assertContains(response, 'Hello, world!')


class BasicResourceViewTest(BasicViewTest):
    def create_subproject(self):
        return self.create_android()


class BasicMercurialViewTest(BasicViewTest):
    def create_subproject(self):
        return self.create_po_mercurial()


class BasicPoMonoViewTest(BasicViewTest):
    def create_subproject(self):
        return self.create_po_mono()


class BasicIphoneViewTest(BasicViewTest):
    def create_subproject(self):
        return self.create_iphone()


class BasicJSONViewTest(BasicViewTest):
    def create_subproject(self):
        return self.create_json()


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
    has_plurals = True

    def setUp(self):
        super(EditTest, self).setUp()
        self.translation = self.get_translation()
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

    def test_plurals(self):
        '''
        Test plural editing.
        '''
        if not self.has_plurals:
            return

        response = self.edit_unit(
            'Orangutan',
            u'Opice má %d banán.\n',
            target_1=u'Opice má %d banány.\n',
            target_2=u'Opice má %d banánů.\n',
        )
        # We should get to second message
        self.assertRedirectsOffset(response, self.translate_url, 1)
        # Check translations
        unit = self.get_unit('Orangutan')
        plurals = unit.get_target_plurals()
        self.assertEqual(len(plurals), 3)
        self.assertEqual(
            plurals[0],
            u'Opice má %d banán.\n',
        )
        self.assertEqual(
            plurals[1],
            u'Opice má %d banány.\n',
        )
        self.assertEqual(
            plurals[2],
            u'Opice má %d banánů.\n',
        )

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
        # We should stay on same message
        self.assertRedirectsOffset(response, self.translate_url, unit.position)

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
        self.assertEqual(
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
    has_plurals = False

    def create_subproject(self):
        return self.create_android()


class EditResourceSourceTest(ViewTestCase):
    """Source strings (template) editing."""
    has_plurals = False

    def test_edit(self):
        translation = self.get_translation()
        translate_url = translation.get_translate_url()

        response = self.edit_unit(
            'Hello, world!\n',
            'Nazdar svete!\n'
        )
        # We should get to second message
        self.assertRedirectsOffset(response, translate_url, 1)
        unit = self.get_unit('Nazdar svete!\n')
        self.assertEqual(unit.target, 'Nazdar svete!\n')
        self.assertEqual(len(unit.checks()), 0)
        self.assertTrue(unit.translated)
        self.assertFalse(unit.fuzzy)
        self.assertBackend(4)

    def get_translation(self):
        return self.subproject.translation_set.get(
            language_code='en'
        )

    def create_subproject(self):
        return self.create_android()


class EditMercurialTest(EditTest):
    def create_subproject(self):
        return self.create_po_mercurial()


class EditPoMonoTest(EditTest):
    def create_subproject(self):
        return self.create_po_mono()


class EditIphoneTest(EditTest):
    has_plurals = False

    def create_subproject(self):
        return self.create_iphone()


class EditJSONTest(EditTest):
    has_plurals = False

    def create_subproject(self):
        return self.create_json()


class EditJSONMonoTest(EditTest):
    has_plurals = False

    def create_subproject(self):
        return self.create_json_mono()


class EditJavaTest(EditTest):
    has_plurals = False

    def create_subproject(self):
        return self.create_java()


class EditXliffTest(EditTest):
    has_plurals = False

    def create_subproject(self):
        return self.create_xliff()


class EditLinkTest(EditTest):
    def create_subproject(self):
        return self.create_link()


class EditTSTest(EditTest):
    def create_subproject(self):
        return self.create_ts()


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


class ZenViewTest(ViewTestCase):
    def test_zen(self):
        response = self.client.get(
            reverse('zen', kwargs=self.kw_translation)
        )
        self.assertContains(
            response,
            'Thank you for using Weblate.'
        )
        self.assertContains(
            response,
            'Orangutan has %d bananas'
        )
        self.assertContains(
            response,
            'You have reached end of translating.'
        )

    def test_load_zen(self):
        response = self.client.get(
            reverse('load_zen', kwargs=self.kw_translation)
        )
        self.assertContains(
            response,
            'Thank you for using Weblate.'
        )
        self.assertContains(
            response,
            'Orangutan has %d bananas'
        )
        self.assertContains(
            response,
            'You have reached end of translating.'
        )


class HomeViewTest(ViewTestCase):
    """Tests for home/inidex view."""
    def test_view_home(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Test/Test')

    def test_home_with_whiteboard(self):
        # @override_settings decorator does not work becase
        # appsettings.ENABLE_WHITEBOARD is just a constant that is being
        # assigned during first import
        appsettings.ENABLE_WHITEBOARD = True
        msg = WhiteboardMessage(message='test_message')
        msg.save()

        response = self.client.get(reverse('home'))
        self.assertContains(response, 'whiteboard')
        self.assertContains(response, 'test_message')

    def test_home_without_whiteboard(self):
        appsettings.ENABLE_WHITEBOARD = False
        response = self.client.get(reverse('home'))
        self.assertNotContains(response, 'whiteboard')


class SourceStringsTest(ViewTestCase):
    def test_edit_priority(self):
        # Need extra power
        self.user.is_superuser = True
        self.user.save()

        source = self.get_unit().source_info
        response = self.client.post(
            reverse('edit_priority', kwargs={'pk': source.pk}),
            {'priority': 60}
        )
        self.assertRedirects(response, source.get_absolute_url())

        unit = self.get_unit()
        self.assertEquals(unit.priority, 60)
        self.assertEquals(unit.source_info.priority, 60)

    def test_edit_check_flags(self):
        # Need extra power
        self.user.is_superuser = True
        self.user.save()

        source = self.get_unit().source_info
        response = self.client.post(
            reverse('edit_check_flags', kwargs={'pk': source.pk}),
            {'flags': 'ignore-same'}
        )
        self.assertRedirects(response, source.get_absolute_url())

        unit = self.get_unit()
        self.assertEquals(unit.source_info.check_flags, 'ignore-same')

    def test_review_source(self):
        response = self.client.get(
            reverse('review_source', kwargs=self.kw_subproject)
        )
        self.assertContains(response, 'Test/Test')

    def test_review_source_expand(self):
        unit = self.get_unit()
        response = self.client.get(
            reverse('review_source', kwargs=self.kw_subproject),
            {'checksum': unit.checksum}
        )
        self.assertContains(response, unit.checksum)

    def test_view_source(self):
        response = self.client.get(
            reverse('show_source', kwargs=self.kw_subproject)
        )
        self.assertContains(response, 'Test/Test')
