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
'''
Tests for changes done in remote repository.
'''
from weblate.trans.models import SubProject
from weblate.trans.tests.test_models import REPOWEB_URL
from weblate.trans.tests.test_views import ViewTestCase
from django.utils import timezone

EXTRA_PO = '''
#: accounts/models.py:319 trans/views/basic.py:104 weblate/html/index.html:21
msgid "Languages"
msgstr "Jazyky"
'''

MINIMAL_PO = r'''
msgid ""
msgstr ""
"Project-Id-Version: Weblate Hello World 2012\n"
"Report-Msgid-Bugs-To: <noreply@example.net>\n"
"POT-Creation-Date: 2012-03-14 15:54+0100\n"
"PO-Revision-Date: 2013-08-25 15:23+0200\n"
"Last-Translator: testuser <>\n"
"Language-Team: Czech <http://example.com/projects/test/test/cs/>\n"
"Language: cs\n"
"MIME-Version: 1.0\n"
"Content-Type: text/plain; charset=UTF-8\n"
"Content-Transfer-Encoding: 8bit\n"
"Plural-Forms: nplurals=3; plural=(n==1) ? 0 : (n>=2 && n<=4) ? 1 : 2;\n"
"X-Generator: Weblate 1.7-dev\n"

#: main.c:11
#, c-format
msgid "Hello, world!\n"
msgstr "Nazdar svete!\n"
'''


class MultiRepoTest(ViewTestCase):
    '''
    Tests handling of remote changes, conflicts and so on.
    '''
    def setUp(self):
        super(MultiRepoTest, self).setUp()
        self.subproject2 = SubProject.objects.create(
            name='Test 2',
            slug='test-2',
            project=self.project,
            repo=self.git_repo_path,
            push=self.git_repo_path,
            filemask='po/*.po',
            template='',
            file_format='po',
            repoweb=REPOWEB_URL,
            new_base='',
        )
        self.request = self.get_request('/')

    def push_first(self, propagate=True, newtext='Nazdar svete!\n'):
        '''
        Changes and pushes first subproject.
        '''
        if not propagate:
            # Disable changes propagating
            self.subproject2.allow_translation_propagation = False
            self.subproject2.save()

        unit = self.get_unit()
        unit.translate(self.request, [newtext], False)
        self.assertEqual(self.get_translation().translated, 1)
        self.subproject.do_push(self.request)

    def push_replace(self, content, mode):
        '''
        Replaces content of a po file and pushes it to remote repository.
        '''
        # Manually edit po file, adding new unit
        translation = self.subproject.translation_set.get(
            language_code='cs'
        )
        with open(translation.get_filename(), mode) as handle:
            handle.write(content)

        # Do changes in first repo
        translation.git_commit(
            self.request, 'TEST <test@example.net>', timezone.now(),
            force_commit=True
        )
        translation.subproject.do_push(self.request)

    def test_propagate(self):
        '''
        Tests handling of propagating.
        '''
        # Do changes in first repo
        self.push_first()

        # Verify changes got to the second one
        translation = self.subproject2.translation_set.get(
            language_code='cs'
        )
        self.assertEqual(translation.translated, 1)

    def test_update(self):
        '''
        Tests handling update in case remote has changed.
        '''
        # Do changes in first repo
        self.push_first(False)

        # Test pull
        translation = self.subproject2.translation_set.get(
            language_code='cs'
        )
        self.assertEqual(translation.translated, 0)

        translation.do_update(self.request)
        translation = self.subproject2.translation_set.get(
            language_code='cs'
        )
        self.assertEqual(translation.translated, 1)

    def test_conflict(self):
        '''
        Tests conflict handling.
        '''
        # Do changes in first repo
        self.push_first(False)

        # Do changes in the second repo
        translation = self.subproject2.translation_set.get(
            language_code='cs'
        )
        unit = translation.unit_set.get(source='Hello, world!\n')
        unit.translate(self.request, 'Ahoj svete!\n', False)

        self.assertFalse(translation.do_update(self.request))

    def test_more_changes(self):
        '''
        Test more string changes in remote repo.
        '''
        translation = self.subproject2.translation_set.get(
            language_code='cs'
        )

        self.push_first(False, 'Hello, world!\n')
        translation.do_update(self.request)
        translation = self.subproject2.translation_set.get(
            language_code='cs'
        )
        self.assertEqual(translation.failing_checks, 1)

        self.push_first(False, 'Nazdar svete\n')
        translation.do_update(self.request)
        translation = self.subproject2.translation_set.get(
            language_code='cs'
        )
        self.assertEqual(translation.failing_checks, 0)

    def test_new_unit(self):
        '''
        Tests adding new unit with update.
        '''
        self.push_replace(EXTRA_PO, 'a')

        self.subproject2.do_update(self.request)

        translation = self.subproject2.translation_set.get(
            language_code='cs'
        )
        self.assertEqual(translation.total, 5)

    def test_deleted_unit(self):
        '''
        Test removing several units from remote repo.
        '''
        self.push_replace(MINIMAL_PO, 'w')

        self.subproject2.do_update(self.request)

        translation = self.subproject2.translation_set.get(
            language_code='cs'
        )
        self.assertEqual(translation.total, 1)

    def test_deleted_stale_unit(self):
        '''
        Test removing several units from remote repo with no
        other reference, so full cleanup has to happen.
        '''
        self.push_replace(MINIMAL_PO, 'w')
        self.subproject.delete()

        self.subproject2.do_update(self.request)

        translation = self.subproject2.translation_set.get(
            language_code='cs'
        )
        self.assertEqual(translation.total, 1)
