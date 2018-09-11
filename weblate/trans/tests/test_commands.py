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

"""Test for management commands."""

from unittest import SkipTest
import sys

from six import StringIO

from django.test import SimpleTestCase
from django.core.management import call_command
from django.core.management.base import CommandError, SystemCheckError

from weblate.trans.tests.test_models import RepoTestCase
from weblate.trans.models import Translation, Component, Suggestion, Source
from weblate.trans.search import Fulltext
from weblate.runner import main
from weblate.trans.tests.utils import get_test_file, create_test_user
from weblate.vcs.mercurial import HgRepository
from weblate.accounts.models import Profile

TEST_PO = get_test_file('cs.po')
TEST_COMPONENTS = get_test_file('components.json')


class RunnerTest(SimpleTestCase):
    def test_help(self):
        restore = sys.stdout
        try:
            sys.stdout = StringIO()
            main(['help'])
            self.assertIn('list_versions', sys.stdout.getvalue())
        finally:
            sys.stdout = restore


class ImportProjectTest(RepoTestCase):
    def do_import(self, path=None, **kwargs):
        call_command(
            'import_project',
            'test',
            self.git_repo_path if path is None else path,
            'master',
            '**/*.po',
            **kwargs
        )

    def test_import(self):
        project = self.create_project()
        self.do_import()
        self.assertEqual(project.component_set.count(), 4)

    def test_import_deep(self):
        project = self.create_project()
        call_command(
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            'deep/*/locales/*/LC_MESSAGES/**.po',
        )
        self.assertEqual(project.component_set.count(), 1)

    def test_import_ignore(self):
        project = self.create_project()
        self.do_import()
        self.do_import()
        self.assertEqual(project.component_set.count(), 4)

    def test_import_duplicate(self):
        project = self.create_project()
        self.do_import()
        self.do_import(path='weblate://test/po')
        self.assertEqual(project.component_set.count(), 4)

    def test_import_main_1(self, name='po-mono'):
        project = self.create_project()
        call_command(
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/*.po',
            main_component=name
        )
        non_linked = project.component_set.exclude(
            repo__startswith='weblate:/'
        )
        self.assertEqual(
            non_linked.count(),
            1
        )
        self.assertEqual(
            non_linked[0].slug,
            name
        )

    def test_import_main_2(self):
        self.test_import_main_1('second-po')

    def test_import_main_invalid(self):
        self.assertRaises(
            CommandError,
            self.test_import_main_1,
            'x-po',
        )

    def test_import_filter(self):
        project = self.create_project()
        call_command(
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/*.po',
            language_regex='cs'
        )
        self.assertEqual(project.component_set.count(), 4)
        for component in project.component_set.all():
            self.assertEqual(component.translation_set.count(), 1)

    def test_import_re(self):
        project = self.create_project()
        call_command(
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            r'(?P<component>[^/-]*)/(?P<language>[^/]*)\.po'
        )
        self.assertEqual(project.component_set.count(), 1)

    def test_import_name(self):
        project = self.create_project()
        call_command(
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            r'(?P<component>[^/-]*)/(?P<language>[^/]*)\.po',
            name_template='Test name'
        )
        self.assertEqual(project.component_set.count(), 1)
        self.assertTrue(
            project.component_set.filter(name='Test name').exists()
        )

    def test_import_re_missing(self):
        self.assertRaises(
            CommandError,
            call_command,
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            r'(?P<name>[^/-]*)/.*\.po'
        )

    def test_import_re_wrong(self):
        self.assertRaises(
            CommandError,
            call_command,
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            r'(?P<name>[^/-]*'
        )

    def test_import_po(self):
        project = self.create_project()
        call_command(
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/*.po',
            file_format='po'
        )
        self.assertEqual(project.component_set.count(), 4)

    def test_import_invalid(self):
        project = self.create_project()
        self.assertRaises(
            CommandError,
            call_command,
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/*.po',
            file_format='INVALID'
        )
        self.assertEqual(project.component_set.count(), 0)

    def test_import_aresource(self):
        project = self.create_project()
        call_command(
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/values-*/strings.xml',
            file_format='aresource',
            base_file_template='android/values/strings.xml',
        )
        self.assertEqual(project.component_set.count(), 2)

    def test_import_aresource_format(self):
        project = self.create_project()
        call_command(
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/values-*/strings.xml',
            file_format='aresource',
            base_file_template='%s/values/strings.xml',
        )
        self.assertEqual(project.component_set.count(), 2)

    def test_re_import(self):
        project = self.create_project()
        call_command(
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/*.po',
        )
        self.assertEqual(project.component_set.count(), 4)

        call_command(
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/*.po',
        )
        self.assertEqual(project.component_set.count(), 4)

    def test_import_against_existing(self):
        """Test importing with a weblate:// URL"""
        android = self.create_android()
        project = android.project
        self.assertEqual(project.component_set.count(), 1)
        call_command(
            'import_project',
            project.slug,
            'weblate://{0!s}/{1!s}'.format(project.slug, android.slug),
            'master',
            '**/*.po',
        )
        self.assertEqual(project.component_set.count(), 5)

    def test_import_missing_project(self):
        """Test of correct handling of missing project."""
        self.assertRaises(
            CommandError,
            call_command,
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/*.po',
        )

    def test_import_missing_wildcard(self):
        """Test of correct handling of missing wildcard."""
        self.create_project()
        self.assertRaises(
            CommandError,
            call_command,
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '*/*.po',
        )

    def test_import_wrong_vcs(self):
        """Test of correct handling of wrong vcs."""
        self.create_project()
        self.assertRaises(
            CommandError,
            call_command,
            'import_project',
            'test',
            self.git_repo_path,
            'master',
            '**/*.po',
            vcs='nonexisting',
        )

    def test_import_mercurial(self):
        """Test importing Mercurial project"""
        if not HgRepository.is_supported():
            raise SkipTest('Mercurial not available!')
        project = self.create_project()
        call_command(
            'import_project',
            'test',
            self.mercurial_repo_path,
            'default',
            '**/*.po',
            vcs='mercurial'
        )
        self.assertEqual(project.component_set.count(), 3)

    def test_import_mercurial_mixed(self):
        """Test importing Mercurial project with mixed component/lang"""
        if not HgRepository.is_supported():
            raise SkipTest('Mercurial not available!')
        self.create_project()
        self.assertRaises(
            CommandError,
            call_command,
            'import_project',
            'test',
            self.mercurial_repo_path,
            'default',
            '*/**.po',
            vcs='mercurial'
        )


class BasicCommandTest(SimpleTestCase):
    allow_database_queries = True

    def test_versions(self):
        output = StringIO()
        call_command(
            'list_versions',
            stdout=output
        )
        self.assertIn('Weblate', output.getvalue())

    def test_check(self):
        with self.assertRaises(SystemCheckError):
            call_command(
                'check',
                '--deploy',
            )


class CleanupCommandTest(RepoTestCase):
    def test_cleanup(self):
        orig_fake = Fulltext.FAKE
        Fulltext.FAKE = False
        fulltext = Fulltext()
        try:
            component = self.create_component()
            index = fulltext.get_source_index()
            self.assertEqual(len(list(index.reader().all_stored_fields())), 12)
            # Create dangling suggestion
            Suggestion.objects.create(
                project=component.project,
                content_hash=1,
                language=component.translation_set.all()[0].language,
            )
            # Remove all translations
            Translation.objects.all().delete()
            call_command('cleanuptrans')
            self.assertEqual(Suggestion.objects.count(), 0)
            self.assertEqual(Source.objects.count(), 0)
            self.assertEqual(len(list(index.reader().all_stored_fields())), 0)
        finally:
            Fulltext.FAKE = orig_fake


class CheckGitTest(RepoTestCase):
    """Base class for handling tests of WeblateComponentCommand
    based commands."""
    command_name = 'checkgit'
    expected_string = 'On branch master'

    def setUp(self):
        super(CheckGitTest, self).setUp()
        self.create_component()

    def do_test(self, *args, **kwargs):
        output = StringIO()
        call_command(
            self.command_name,
            *args,
            stdout=output,
            **kwargs
        )
        if self.expected_string:
            self.assertIn(self.expected_string, output.getvalue())
        else:
            self.assertEqual('', output.getvalue())

    def test_all(self):
        self.do_test(
            all=True,
        )

    def test_project(self):
        self.do_test(
            'test',
        )

    def test_component(self):
        self.do_test(
            'test/test',
        )

    def test_nonexisting_project(self):
        self.assertRaises(
            CommandError,
            self.do_test,
            'notest',
        )

    def test_nonexisting_component(self):
        self.assertRaises(
            CommandError,
            self.do_test,
            'test/notest',
        )


class CommitPendingTest(CheckGitTest):
    command_name = 'commit_pending'
    expected_string = ''


class CommitGitTest(CheckGitTest):
    command_name = 'commitgit'
    expected_string = ''


class PushGitTest(CheckGitTest):
    command_name = 'pushgit'
    expected_string = ''


class LoadTest(CheckGitTest):
    command_name = 'loadpo'
    expected_string = ''


class UpdateChecksTest(CheckGitTest):
    command_name = 'updatechecks'
    expected_string = 'Processing'


class UpdateGitTest(CheckGitTest):
    command_name = 'updategit'
    expected_string = ''


class RebuildIndexTest(CheckGitTest):
    command_name = 'rebuild_index'
    expected_string = 'Processing'

    def test_all_clean(self):
        self.do_test(
            all=True,
            clean=True,
        )

    def test_optimize(self):
        self.expected_string = ''
        try:
            self.do_test(
                optimize=True,
            )
        finally:
            self.expected_string = 'Processing'


class LockTranslationTest(CheckGitTest):
    command_name = 'lock_translation'
    expected_string = ''


class UnLockTranslationTest(CheckGitTest):
    command_name = 'unlock_translation'
    expected_string = ''


class FixupFlagsTest(CheckGitTest):
    command_name = 'fixup_flags'
    expected_string = 'Processing'


class ListTranslatorsTest(RepoTestCase):
    """Test translators list"""
    def setUp(self):
        super(ListTranslatorsTest, self).setUp()
        self.create_component()

    def test_output(self):
        component = Component.objects.all()[0]
        output = StringIO()
        call_command(
            'list_translators',
            '{0}/{1}'.format(
                component.project.slug,
                component.slug,
            ),
            stdout=output
        )
        self.assertEqual(output.getvalue(), '')


class LockingCommandTest(RepoTestCase):
    """Test locking and unlocking."""
    def setUp(self):
        super(LockingCommandTest, self).setUp()
        self.create_component()

    def test_locking(self):
        component = Component.objects.all()[0]
        self.assertFalse(
            Component.objects.filter(locked=True).exists()
        )
        call_command(
            'lock_translation',
            '{0}/{1}'.format(
                component.project.slug,
                component.slug,
            )
        )
        self.assertTrue(
            Component.objects.filter(locked=True).exists()
        )
        call_command(
            'unlock_translation',
            '{0}/{1}'.format(
                component.project.slug,
                component.slug,
            )
        )
        self.assertFalse(
            Component.objects.filter(locked=True).exists()
        )


class BenchmarkCommandTest(RepoTestCase):
    """Benchmarking test."""
    def setUp(self):
        super(BenchmarkCommandTest, self).setUp()
        self.create_component()

    def test_benchmark(self):
        output = StringIO()
        call_command(
            'benchmark', 'test', 'weblate://test/test', 'po/*.po',
            stdout=output
        )
        self.assertIn('function calls', output.getvalue())


class SuggestionCommandTest(RepoTestCase):
    """Test suggestion addding."""
    def setUp(self):
        super(SuggestionCommandTest, self).setUp()
        self.component = self.create_component()

    def test_add_suggestions(self):
        user = create_test_user()
        call_command(
            'add_suggestions', 'test', 'test', 'cs', TEST_PO,
            author=user.email
        )
        translation = self.component.translation_set.get(language_code='cs')
        self.assertEqual(translation.stats.suggestions, 1)
        profile = Profile.objects.get(user__email=user.email)
        self.assertEqual(profile.suggested, 1)

    def test_default_user(self):
        call_command(
            'add_suggestions', 'test', 'test', 'cs', TEST_PO,
        )
        profile = Profile.objects.get(user__email='noreply@weblate.org')
        self.assertEqual(profile.suggested, 1)

    def test_missing_user(self):
        self.assertRaises(
            CommandError,
            call_command,
            'add_suggestions', 'test', 'test', 'cs', TEST_PO,
            author='foo@example.org',
        )

    def test_missing_project(self):
        self.assertRaises(
            CommandError,
            call_command,
            'add_suggestions', 'test', 'xxx', 'cs', TEST_PO,
        )


class ImportCommandTest(RepoTestCase):
    """Import test."""
    def setUp(self):
        super(ImportCommandTest, self).setUp()
        self.component = self.create_component()

    def test_import(self):
        output = StringIO()
        call_command(
            'import_json',
            '--main-component', 'test',
            '--project', 'test',
            TEST_COMPONENTS,
            stdout=output
        )
        self.assertEqual(
            self.component.project.component_set.count(),
            3
        )
        self.assertEqual(
            Translation.objects.count(),
            8
        )
        self.assertIn(
            'Imported Test/Gettext PO with 3 translations',
            output.getvalue()
        )

    def test_import_twice(self):
        call_command(
            'import_json',
            '--main-component', 'test',
            '--project', 'test',
            TEST_COMPONENTS,
        )
        self.assertRaises(
            CommandError,
            call_command,
            'import_json',
            '--main-component', 'test',
            '--project', 'test',
            TEST_COMPONENTS,
        )

    def test_import_ignore(self):
        output = StringIO()
        call_command(
            'import_json',
            '--main-component', 'test',
            '--project', 'test',
            TEST_COMPONENTS,
            stdout=output
        )
        self.assertIn(
            'Imported Test/Gettext PO with 3 translations',
            output.getvalue()
        )
        output.truncate()
        call_command(
            'import_json',
            '--main-component', 'test',
            '--project', 'test',
            '--ignore',
            TEST_COMPONENTS,
            stderr=output
        )
        self.assertIn(
            'Component Test/Gettext PO already exists',
            output.getvalue()
        )

    def test_import_update(self):
        call_command(
            'import_json',
            '--main-component', 'test',
            '--project', 'test',
            TEST_COMPONENTS,
        )
        call_command(
            'import_json',
            '--main-component', 'test',
            '--project', 'test',
            '--update',
            TEST_COMPONENTS,
        )

    def test_invalid_file(self):
        self.assertRaises(
            CommandError,
            call_command,
            'import_json',
            '--main-component', 'test',
            '--project', 'test',
            TEST_PO,
        )

    def test_nonexisting_project(self):
        self.assertRaises(
            CommandError,
            call_command,
            'import_json',
            '--main-component', 'test',
            '--project', 'test2',
            '/nonexisting/dfile',
        )

    def test_nonexisting_component(self):
        self.assertRaises(
            CommandError,
            call_command,
            'import_json',
            '--main-component', 'test2',
            '--project', 'test',
            '/nonexisting/dfile',
        )

    def test_missing_component(self):
        self.assertRaises(
            CommandError,
            call_command,
            'import_json',
            '--project', 'test',
            '/nonexisting/dfile',
        )
