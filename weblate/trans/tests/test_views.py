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

"""Test for translation views."""

from xml.dom import minidom
from io import BytesIO

from six.moves.urllib.parse import urlsplit

from PIL import Image

from django.test.client import RequestFactory
from django.urls import reverse
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.management import call_command
from django.core import mail
from django.core.cache import cache

from weblate.auth.models import Group, Role, Permission, setup_project_groups
from weblate.lang.models import Language
from weblate.trans.management.commands.update_index import (
    Command as UpdateIndexCommand
)
from weblate.trans.models import ComponentList, WhiteboardMessage, Project
from weblate.trans.search import Fulltext
from weblate.trans.tests.test_models import RepoTestCase
from weblate.trans.tests.utils import create_test_user
from weblate.utils.hash import hash_to_checksum
from weblate.accounts.models import Profile


class RegistrationTestMixin(object):
    """Helper to share code for registration testing."""
    def assert_registration_mailbox(self, match=None):
        if match is None:
            match = '[Weblate] Your registration on Weblate'
        # Check mailbox
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            match
        )

        live_url = getattr(self, 'live_server_url', None)

        # Parse URL
        line = ''
        for line in mail.outbox[0].body.splitlines():
            if live_url and line.startswith(live_url):
                return line
            if line.startswith('http://example.com'):
                return line[18:]

        self.fail('Confirmation URL not found')

    def assert_notify_mailbox(self, sent_mail):
        self.assertEqual(
            sent_mail.subject,
            '[Weblate] Activity on your account at Weblate'
        )


class ViewTestCase(RepoTestCase):
    def setUp(self):
        super(ViewTestCase, self).setUp()
        # Many tests needs access to the request factory.
        self.factory = RequestFactory()
        # Create user
        self.user = create_test_user()
        group = Group.objects.get(name='Users')
        self.user.groups.add(group)
        # Create project to have some test base
        self.component = self.create_component()
        self.project = self.component.project
        # Invalidate caches
        self.project.stats.invalidate()
        cache.clear()
        # Login
        self.client.login(username='testuser', password='testpassword')
        # Prepopulate kwargs
        self.kw_project = {
            'project': self.project.slug
        }
        self.kw_component = {
            'project': self.project.slug,
            'component': self.component.slug,
        }
        self.kw_translation = {
            'project': self.project.slug,
            'component': self.component.slug,
            'lang': 'cs',
        }
        self.kw_lang_project = {
            'project': self.project.slug,
            'lang': 'cs',
        }

        # Store URL for testing
        self.translation_url = self.get_translation().get_absolute_url()
        self.project_url = self.project.get_absolute_url()
        self.component_url = self.component.get_absolute_url()

    def update_fulltext_index(self):
        command = UpdateIndexCommand()
        command.do_update(Fulltext(), 100000)

    def make_manager(self):
        """Make user a Manager."""
        # Sitewide privileges
        self.user.groups.add(
            Group.objects.get(name='Managers')
        )
        # Project privileges
        self.project.add_user(self.user, '@Administration')

    def get_request(self, *args, **kwargs):
        """Wrapper to get fake request object."""
        request = self.factory.get(*args, **kwargs)
        request.user = self.user
        setattr(request, 'session', 'session')
        messages = FallbackStorage(request)
        setattr(request, '_messages', messages)
        return request

    def get_translation(self):
        return self.component.translation_set.get(
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
        """Do edit single unit using web interface."""
        unit = self.get_unit(source)
        params = {
            'checksum': unit.checksum,
            'contentsum': hash_to_checksum(unit.content_hash),
            'translationsum': hash_to_checksum(unit.get_target_hash()),
            'target_0': target,
            'review': '20',
        }
        params.update(kwargs)
        return self.client.post(
            self.get_translation().get_translate_url(),
            params
        )

    def assert_redirects_offset(self, response, exp_path, exp_offset):
        """Assert that offset in response matches expected one."""
        self.assertEqual(response.status_code, 302)

        # We don't use all variables
        # pylint: disable=unused-variable
        scheme, netloc, path, query, fragment = urlsplit(response['Location'])

        self.assertEqual(path, exp_path)

        exp_offset = 'offset={0:d}'.format(exp_offset)
        self.assertTrue(
            exp_offset in query,
            'Offset {0} not in {1}'.format(exp_offset, query)
        )

    def assert_png(self, response):
        """Check whether response contains valid PNG image."""
        # Check response status code
        self.assertEqual(response.status_code, 200)
        self.assert_png_data(response.content)

    def assert_png_data(self, content):
        """Check whether data is PNG image"""
        # Try to load PNG with PIL
        image = Image.open(BytesIO(content))
        self.assertEqual(image.format, 'PNG')

    def assert_svg(self, response):
        """Check whether response is a SVG image."""
        # Check response status code
        self.assertEqual(response.status_code, 200)
        dom = minidom.parseString(response.content)
        self.assertEqual(dom.firstChild.nodeName, 'svg')

    def assert_backend(self, expected_translated):
        """Check that backend has correct data."""
        translation = self.get_translation()
        translation.commit_pending(None)
        store = translation.component.file_format_cls(
            translation.get_filename(),
            None
        )
        messages = set()
        translated = 0

        for unit in store.all_units():
            if not unit.is_translatable():
                continue
            id_hash = unit.get_id_hash()
            self.assertFalse(
                id_hash in messages,
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


class FixtureTestCase(ViewTestCase):
    @classmethod
    def setUpTestData(cls):
        """Manually load fixture."""
        # Ensure there are no Language objects, we add
        # them in defined order in fixture
        Language.objects.all().delete()

        # Stolen from setUpClass, we just need to do it
        # after transaction checkpoint and deleting languages
        for db_name in cls._databases_names(include_mirrors=False):
            call_command(
                'loaddata', 'simple-project.json',
                verbosity=0,
                database=db_name
            )
        # Apply group project/language automation
        for group in Group.objects.all():
            group.save()

        super(FixtureTestCase, cls).setUpTestData()

    def clone_test_repos(self):
        return

    def create_project(self):
        project = Project.objects.all()[0]
        setup_project_groups(self, project)
        return project

    def create_component(self):
        return self.create_project().component_set.all()[0]


class TranslationManipulationTest(ViewTestCase):
    def setUp(self):
        super(TranslationManipulationTest, self).setUp()
        self.component.new_lang = 'add'
        self.component.save()

    def create_component(self):
        return self.create_po_new_base()

    def test_model_add(self):
        self.assertTrue(
            self.component.add_new_language(
                Language.objects.get(code='af'),
                self.get_request('/')
            )
        )
        self.assertTrue(
            self.component.translation_set.filter(
                language_code='af'
            ).exists()
        )

    def test_model_add_duplicate(self):
        self.assertFalse(
            self.component.add_new_language(
                Language.objects.get(code='de'),
                self.get_request('/')
            )
        )

    def test_model_add_disabled(self):
        self.component.new_lang = 'contact'
        self.component.save()
        self.assertFalse(
            self.component.add_new_language(
                Language.objects.get(code='de'),
                self.get_request('/')
            )
        )

    def test_remove(self):
        translation = self.component.translation_set.get(language_code='de')
        translation.remove(self.user)
        # Force scanning of the repository
        self.component.create_translations()
        self.assertFalse(
            self.component.translation_set.filter(
                language_code='de'
            ).exists()
        )


class NewLangTest(ViewTestCase):
    def create_component(self):
        return self.create_po_new_base(new_lang='add')

    def test_no_permission(self):
        # Remove permission to add translations
        Role.objects.get(name='Power user').permissions.remove(
            Permission.objects.get(codename='translation.add')
        )

        # Test there is no add form
        response = self.client.get(
            reverse('component', kwargs=self.kw_component)
        )
        self.assertContains(response, 'Start new translation')
        self.assertContains(response, 'permission to start new translation')

        # Test adding fails
        response = self.client.post(
            reverse('new-language', kwargs=self.kw_component),
            {'lang': 'af'},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            self.component.translation_set.filter(
                language__code='af'
            ).exists()
        )

    def test_none(self):
        self.component.new_lang = 'none'
        self.component.save()

        response = self.client.get(
            reverse('component', kwargs=self.kw_component)
        )
        self.assertNotContains(response, 'Start new translation')

    def test_url(self):
        self.component.new_lang = 'url'
        self.component.save()
        self.project.instructions = 'http://example.com/instructions'
        self.project.save()

        response = self.client.get(
            reverse('component', kwargs=self.kw_component)
        )
        self.assertContains(response, 'Start new translation')
        self.assertContains(response, 'http://example.com/instructions')

    def test_contact(self):
        # Add manager to receive notifications
        self.make_manager()
        self.component.new_lang = 'contact'
        self.component.save()

        response = self.client.get(
            reverse('component', kwargs=self.kw_component)
        )
        self.assertContains(response, 'Start new translation')
        self.assertContains(response, '/new-lang/')

        response = self.client.post(
            reverse('new-language', kwargs=self.kw_component),
            {'lang': 'af'},
        )
        self.assertRedirects(
            response,
            self.component.get_absolute_url()
        )

        # Verify mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            '[Weblate] New language request in Test/Test',
        )

    def test_add(self):
        self.assertFalse(
            self.component.translation_set.filter(
                language__code='af'
            ).exists()
        )

        response = self.client.get(
            reverse('component', kwargs=self.kw_component)
        )
        self.assertContains(response, 'Start new translation')
        self.assertContains(response, '/new-lang/')

        response = self.client.post(
            reverse('new-language', kwargs=self.kw_component),
            {'lang': 'af'},
        )
        self.assertRedirects(
            response,
            self.component.get_absolute_url()
        )
        self.assertTrue(
            self.component.translation_set.filter(
                language__code='af'
            ).exists()
        )

        # Not selected language
        response = self.client.post(
            reverse('new-language', kwargs=self.kw_component),
            {'lang': ''},
            follow=True
        )
        self.assertContains(
            response,
            'Please fix errors in the form'
        )

        # Existing language
        response = self.client.post(
            reverse('new-language', kwargs=self.kw_component),
            {'lang': 'af'},
            follow=True
        )
        self.assertContains(
            response,
            'Please fix errors in the form'
        )

    def test_add_owner(self):
        self.component.project.add_user(self.user, '@Administration')
        # None chosen
        response = self.client.post(
            reverse('new-language', kwargs=self.kw_component),
            follow=True
        )
        self.assertContains(
            response,
            'Please fix errors in the form'
        )
        # One chosen
        response = self.client.post(
            reverse('new-language', kwargs=self.kw_component),
            {'lang': 'af'},
            follow=True
        )
        self.assertNotContains(
            response,
            'Please fix errors in the form'
        )
        # More chosen
        response = self.client.post(
            reverse('new-language', kwargs=self.kw_component),
            {'lang': ['nl', 'fr', 'uk']},
            follow=True
        )
        self.assertNotContains(
            response,
            'Please fix errors in the form'
        )
        self.assertEqual(
            self.component.translation_set.filter(
                language__code__in=('af', 'nl', 'fr', 'uk')
            ).count(),
            4
        )

    def test_add_rejected(self):
        self.component.project.add_user(self.user, '@Administration')
        self.component.language_regex = '^cs$'
        self.component.save()
        # One chosen
        response = self.client.post(
            reverse('new-language', kwargs=self.kw_component),
            {'lang': 'af'},
            follow=True
        )
        self.assertContains(
            response,
            'Given language is filtered by the language filter!',
        )

    def test_remove(self):
        self.test_add_owner()
        kwargs = {'lang': 'af'}
        kwargs.update(self.kw_component)
        response = self.client.post(
            reverse('remove_translation', kwargs=kwargs),
            follow=True
        )
        self.assertContains(response, 'Translation has been removed.')


class AndroidNewLangTest(NewLangTest):
    def create_component(self):
        return self.create_android(new_lang='add')


class BasicViewTest(ViewTestCase):
    def test_view_project(self):
        response = self.client.get(
            reverse('project', kwargs=self.kw_project)
        )
        self.assertContains(response, 'Test/Test')

    def test_view_component(self):
        response = self.client.get(
            reverse('component', kwargs=self.kw_component)
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

    def test_view_component_list(self):
        clist = ComponentList.objects.create(name="TestCL", slug="testcl")
        clist.components.add(self.component)
        response = self.client.get(
            reverse('component-list', kwargs={'name': 'testcl'})
        )
        self.assertContains(response, 'TestCL')
        self.assertContains(response, self.component.name)


class BasicResourceViewTest(BasicViewTest):
    def create_component(self):
        return self.create_android()


class BasicBranchViewTest(BasicViewTest):
    def create_component(self):
        return self.create_po_branch()


class BasicMercurialViewTest(BasicViewTest):
    def create_component(self):
        return self.create_po_mercurial()


class BasicPoMonoViewTest(BasicViewTest):
    def create_component(self):
        return self.create_po_mono()


class BasicIphoneViewTest(BasicViewTest):
    def create_component(self):
        return self.create_iphone()


class BasicJSONViewTest(BasicViewTest):
    def create_component(self):
        return self.create_json()


class BasicJavaViewTest(BasicViewTest):
    def create_component(self):
        return self.create_java()


class BasicXliffViewTest(BasicViewTest):
    def create_component(self):
        return self.create_xliff()


class BasicLinkViewTest(BasicViewTest):
    def create_component(self):
        return self.create_link()


class HomeViewTest(ViewTestCase):
    """Test for home/inidex view."""
    def test_view_home(self):
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Test/Test')

    def test_view_projects(self):
        response = self.client.get(reverse('projects'))
        self.assertContains(response, 'Test')

    def test_home_with_whiteboard(self):
        msg = WhiteboardMessage(message='test_message')
        msg.save()

        response = self.client.get(reverse('home'))
        self.assertContains(response, 'whiteboard')
        self.assertContains(response, 'test_message')

    def test_home_without_whiteboard(self):
        response = self.client.get(reverse('home'))
        self.assertNotContains(response, 'whiteboard')

    def test_component_list(self):
        clist = ComponentList.objects.create(name="TestCL", slug="testcl")
        clist.components.add(self.component)

        response = self.client.get(reverse('home'))
        self.assertContains(response, 'TestCL')
        self.assertContains(
            response, reverse('component-list', kwargs={'name': 'testcl'})
        )
        self.assertEqual(len(response.context['componentlists']), 1)

    def test_user_component_list(self):
        clist = ComponentList.objects.create(name="TestCL", slug="testcl")
        clist.components.add(self.component)

        self.user.profile.dashboard_view = Profile.DASHBOARD_COMPONENT_LIST
        self.user.profile.dashboard_component_list = clist
        self.user.profile.save()

        response = self.client.get(reverse('home'))
        self.assertContains(response, 'TestCL')
        self.assertEqual(response.context['active_tab_slug'], 'list-testcl')

    def test_subscriptions(self):
        # no subscribed projects at first
        response = self.client.get(reverse('home'))
        self.assertFalse(len(response.context['subscribed_projects']))

        # subscribe a project
        self.user.profile.subscriptions.add(self.project)
        response = self.client.get(reverse('home'))
        self.assertEqual(len(response.context['subscribed_projects']), 1)

    def test_language_filters(self):
        # check language filters
        response = self.client.get(reverse('home'))
        self.assertEqual(len(response.context['userlanguages']), 1)
        self.assertFalse(response.context['usersubscriptions'])

        # add a language
        lang = Language.objects.get(code='cs')
        self.user.profile.languages.add(lang)
        response = self.client.get(reverse('home'))
        self.assertEqual(len(response.context['userlanguages']), 1)
        self.assertFalse(response.context['usersubscriptions'])

        # add a subscription
        self.user.profile.subscriptions.add(self.project)
        response = self.client.get(reverse('home'))
        self.assertEqual(len(response.context['usersubscriptions']), 1)

    def test_user_hide_completed(self):
        self.user.profile.hide_completed = True
        self.user.profile.save()

        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Test/Test')


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
        self.assertEqual(unit.priority, 60)
        self.assertEqual(unit.source_info.priority, 60)

    def test_edit_context(self):
        # Need extra power
        self.user.is_superuser = True
        self.user.save()

        source = self.get_unit().source_info
        response = self.client.post(
            reverse('edit_context', kwargs={'pk': source.pk}),
            {'context': 'Extra context'}
        )
        self.assertRedirects(response, source.get_absolute_url())

        unit = self.get_unit()
        self.assertEqual(unit.context, '')
        self.assertEqual(unit.source_info.context, 'Extra context')

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
        self.assertEqual(unit.source_info.check_flags, 'ignore-same')

    def test_review_source(self):
        response = self.client.get(
            reverse('review_source', kwargs=self.kw_component)
        )
        self.assertContains(response, 'Test/Test')

    def test_review_source_expand(self):
        unit = self.get_unit()
        response = self.client.get(
            reverse('review_source', kwargs=self.kw_component),
            {'checksum': unit.checksum}
        )
        self.assertContains(response, unit.checksum)

    def test_view_source(self):
        response = self.client.get(
            reverse('show_source', kwargs=self.kw_component)
        )
        self.assertContains(response, 'Test/Test')

    def test_matrix(self):
        response = self.client.get(
            reverse('matrix', kwargs=self.kw_component)
        )
        self.assertContains(response, 'Czech')

    def test_matrix_load(self):
        response = self.client.get(
            reverse('matrix-load', kwargs=self.kw_component) +
            '?offset=0&lang=cs'
        )
        self.assertContains(response, 'lang="cs"')
