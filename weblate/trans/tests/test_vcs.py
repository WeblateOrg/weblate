# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

from __future__ import unicode_literals

import tempfile
import shutil
import os.path
from unittest import SkipTest

from django.test import TestCase
from django.utils import timezone

from weblate.trans.tests.test_models import RepoTestCase
from weblate.trans.vcs import GitRepository, HgRepository, \
    RepositoryException, GitWithGerritRepository, GithubRepository
from weblate.trans.tests.utils import get_test_file


class GithubFakeRepository(GithubRepository):
    _is_supported = None
    _version = None
    _cmd = get_test_file('hub')


class GitTestRepository(GitRepository):
    _is_supported = None
    _version = None


class NonExistingRepository(GitRepository):
    _is_supported = None
    _version = None
    _cmd = 'nonexisting-command'


class GitVersionRepository(GitRepository):
    _is_supported = None
    _version = None
    req_version = '200000'


class GitNoVersionRepository(GitRepository):
    _is_supported = None
    _version = None
    req_version = None


class RepositoryTest(TestCase):
    def test_not_supported(self):
        self.assertFalse(NonExistingRepository.is_supported())

    def test_not_supported_version(self):
        self.assertFalse(GitVersionRepository.is_supported())

    def test_is_supported(self):
        self.assertTrue(GitTestRepository.is_supported())

    def test_is_supported_no_version(self):
        self.assertTrue(GitNoVersionRepository.is_supported())

    def test_is_supported_cache(self):
        GitTestRepository.is_supported()
        self.assertTrue(GitTestRepository.is_supported())


class VCSGitTest(RepoTestCase):
    _tempdir = None
    _class = GitRepository
    _vcs = 'git'
    _can_push = True

    def setUp(self):
        super(VCSGitTest, self).setUp()
        if not self._class.is_supported():
            raise SkipTest('Not supported')

        self._tempdir = tempfile.mkdtemp()
        self.repo = self.clone_repo(self._tempdir)

    def clone_repo(self, path):
        return self._class.clone(
            getattr(self, '{0}_repo_path'.format(self._vcs)),
            path,
        )

    def tearDown(self):
        if self._tempdir is not None:
            shutil.rmtree(self._tempdir)

    def add_remote_commit(self, conflict=False):
        tempdir = tempfile.mkdtemp()
        try:
            repo = self.clone_repo(tempdir)
            repo.set_committer('Second Bar', 'second@example.net')
            if conflict:
                filename = 'testfile'
            else:
                filename = 'test2'
            # Create test file
            with open(os.path.join(tempdir, filename), 'w') as handle:
                handle.write('SECOND TEST FILE\n')

            # Commit it
            repo.commit(
                'Test commit',
                'Foo Bar <foo@bar.com>',
                timezone.now(),
                [filename]
            )

            # Push it
            repo.push()
        finally:
            shutil.rmtree(tempdir)

    def test_clone(self):
        self.assertTrue(os.path.exists(
            os.path.join(self._tempdir, '.{0}'.format(self._vcs))
        ))

    def test_revision(self):
        self.assertEqual(
            self.repo.last_revision,
            self.repo.last_remote_revision
        )

    def test_update_remote(self):
        self.repo.update_remote()

    def test_push(self):
        self.repo.push()

    def test_push_commit(self):
        self.test_commit()
        self.test_push()

    def test_reset(self):
        original = self.repo.last_revision
        self.repo.reset()
        self.assertEqual(original, self.repo.last_revision)
        self.test_commit()
        self.assertNotEqual(original, self.repo.last_revision)
        self.repo.reset()
        self.assertEqual(original, self.repo.last_revision)

    def test_merge_commit(self):
        self.test_commit()
        self.test_merge()

    def test_rebase_commit(self):
        self.test_commit()
        self.test_rebase()

    def test_merge_remote(self):
        self.add_remote_commit()
        self.test_merge()

    def test_rebase_remote(self):
        self.add_remote_commit()
        self.test_rebase()

    def test_merge_both(self):
        self.add_remote_commit()
        self.test_commit()
        self.test_merge()

    def test_rebase_both(self):
        self.add_remote_commit()
        self.test_commit()
        self.test_rebase()

    def test_merge_conflict(self):
        self.add_remote_commit(conflict=True)
        self.test_commit()
        if self._can_push:
            self.assertRaises(RepositoryException, self.test_merge)
        else:
            self.test_merge()

    def test_rebase_conflict(self):
        self.add_remote_commit(conflict=True)
        self.test_commit()
        if self._can_push:
            self.assertRaises(RepositoryException, self.test_rebase)
        else:
            self.test_rebase()

    def test_merge(self):
        self.test_update_remote()
        self.repo.merge()

    def test_rebase(self):
        self.test_update_remote()
        self.repo.rebase()

    def test_status(self):
        status = self.repo.status()
        self.assertTrue(
            "Your branch is up-to-date with 'origin/master'." in status
        )

    def test_needs_commit(self):
        self.assertFalse(self.repo.needs_commit())
        with open(os.path.join(self._tempdir, 'README.md'), 'a') as handle:
            handle.write('CHANGE')
        self.assertTrue(self.repo.needs_commit())
        self.assertTrue(self.repo.needs_commit('README.md'))
        self.assertFalse(self.repo.needs_commit('dummy'))

    def check_valid_info(self, info):
        self.assertTrue('summary' in info)
        self.assertTrue(info['summary'] != '')
        self.assertTrue('author' in info)
        self.assertTrue(info['author'] != '')
        self.assertTrue('authordate' in info)
        self.assertTrue(info['authordate'] != '')
        self.assertTrue('commit' in info)
        self.assertTrue(info['commit'] != '')
        self.assertTrue('commitdate' in info)
        self.assertTrue(info['commitdate'] != '')
        self.assertTrue('revision' in info)
        self.assertTrue(info['revision'] != '')
        self.assertTrue('shortrevision' in info)
        self.assertTrue(info['shortrevision'] != '')

    def test_revision_info(self):
        # Latest commit
        info = self.repo.get_revision_info(self.repo.last_revision)
        self.check_valid_info(info)

        # GPG signed commit
        info = self.repo.get_revision_info(
            'd6179e46c8255f1d5029f06c49468caf57b13b61'
        )
        self.check_valid_info(info)
        self.assertEqual(
            info['author'],
            'Michal Čihař <michal@cihar.com>'
        )

        # Normal commit
        info = self.repo.get_revision_info(
            '2ae1998450a693f0a7962d69a1eec4cb2213d595'
        )
        self.check_valid_info(info)

    def test_needs_merge(self):
        self.assertFalse(self.repo.needs_merge())
        self.assertFalse(self.repo.needs_push())

    def test_needs_push(self):
        self.test_commit()
        self.assertTrue(self.repo.needs_push())

    def test_is_supported(self):
        self.assertTrue(self._class.is_supported())

    def test_get_version(self):
        self.assertTrue(self._class.get_version() != '')

    def test_set_committer(self):
        self.repo.set_committer('Foo Bar Žač', 'foo@example.net')
        self.assertEqual(
            self.repo.get_config('user.name'), 'Foo Bar Žač'
        )
        self.assertEqual(
            self.repo.get_config('user.email'), 'foo@example.net'
        )

    def test_commit(self):
        self.repo.set_committer('Foo Bar', 'foo@example.net')
        # Create test file
        with open(os.path.join(self._tempdir, 'testfile'), 'w') as handle:
            handle.write('TEST FILE\n')

        oldrev = self.repo.last_revision
        # Commit it
        self.repo.commit(
            'Test commit',
            'Foo Bar <foo@bar.com>',
            timezone.now(),
            ['testfile']
        )
        # Check we have new revision
        self.assertNotEqual(
            oldrev,
            self.repo.last_revision
        )
        info = self.repo.get_revision_info(self.repo.last_revision)
        self.assertEqual(
            info['author'],
            'Foo Bar <foo@bar.com>',
        )

        # Check file hash
        self.assertEqual(
            self.repo.get_object_hash('testfile'),
            'fafd745150eb1f20fc3719778942a96e2106d25b'
        )

        # Check invalid commit
        self.assertRaises(
            RepositoryException,
            self.repo.commit,
            'test commit',
            'Foo <bar@example.com>',
        )

    def test_object_hash(self):
        obj_hash = self.repo.get_object_hash('README.md')
        self.assertEqual(
            len(obj_hash),
            40
        )

    def test_configure_remote(self):
        self.repo.configure_remote('pullurl', 'pushurl', 'branch')
        self.assertEqual(
            self.repo.get_config('remote.origin.url'),
            'pullurl',
        )
        self.assertEqual(
            self.repo.get_config('remote.origin.pushURL'),
            'pushurl',
        )
        # Test that we handle not set fetching
        self.repo.execute(['config', '--unset', 'remote.origin.fetch'])
        self.repo.configure_remote('pullurl', 'pushurl', 'branch')
        self.assertEqual(
            self.repo.get_config('remote.origin.fetch'),
            '+refs/heads/branch:refs/remotes/origin/branch',
        )

    def test_configure_remote_no_push(self):
        self.repo.configure_remote('pullurl', '', 'branch')
        self.assertEqual(
            self.repo.get_config('remote.origin.pushURL'),
            '',
        )
        self.repo.configure_remote('pullurl', 'push', 'branch')
        self.assertEqual(
            self.repo.get_config('remote.origin.pushURL'),
            'push',
        )

    def test_configure_branch(self):
        # Existing branch
        self.repo.configure_branch(self._class.default_branch)

        self.assertRaises(
            RepositoryException,
            self.repo.configure_branch,
            'branch'
        )


class VCSGerritTest(VCSGitTest):
    _class = GitWithGerritRepository
    _vcs = 'git'
    _can_push = False


class VCSGithubTest(VCSGitTest):
    _class = GithubFakeRepository
    _vcs = 'git'


class VCSHgTest(VCSGitTest):
    """
    Mercurial repository testing.
    """
    _class = HgRepository
    _vcs = 'hg'

    def test_configure_remote(self):
        self.repo.configure_remote('/pullurl', '/pushurl', 'branch')
        self.assertEqual(
            self.repo.get_config('paths.default'),
            '/pullurl',
        )
        self.assertEqual(
            self.repo.get_config('paths.default-push'),
            '/pushurl',
        )

    def test_configure_remote_no_push(self):
        self.repo.configure_remote('/pullurl', '', 'branch')
        self.assertEqual(
            self.repo.get_config('paths.default-push'),
            '',
        )
        self.repo.configure_remote('/pullurl', '/push', 'branch')
        self.assertEqual(
            self.repo.get_config('paths.default-push'),
            '/push',
        )

    def test_revision_info(self):
        # Latest commit
        info = self.repo.get_revision_info(self.repo.last_revision)
        self.check_valid_info(info)

    def test_set_committer(self):
        self.repo.set_committer('Foo Bar Žač', 'foo@example.net')
        self.assertEqual(
            self.repo.get_config('ui.username'),
            'Foo Bar Žač <foo@example.net>'
        )

    def test_status(self):
        status = self.repo.status()
        self.assertEqual(status, '')
