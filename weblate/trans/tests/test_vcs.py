# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2014 Michal Čihař <michal@cihar.com>
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

from weblate.trans.tests.test_models import RepoTestCase
from weblate.trans.vcs import GitRepository, RepositoryException

import tempfile
import shutil
import os.path
import datetime


class VCSGitTest(RepoTestCase):
    _tempdir = None

    def setUp(self):
        super(VCSGitTest, self).setUp()
        self._tempdir = tempfile.mkdtemp()
        self.repo = GitRepository.clone(self.repo_path, self._tempdir)

    def tearDown(self):
        if self._tempdir is not None:
            shutil.rmtree(self._tempdir)

    def test_clone(self):
        self.assertTrue(os.path.exists(os.path.join(self._tempdir, '.git')))

    def test_revision(self):
        self.assertEquals(
            self.repo.last_revision,
            self.repo.last_remote_revision
        )

    def test_update_remote(self):
        self.repo.update_remote()

    def test_push(self):
        self.repo.push('master')

    def test_reset(self):
        self.repo.reset('master')

    def test_merge(self):
        self.repo.merge('master')

    def test_rebase(self):
        self.repo.rebase('master')

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
        self.assertTrue('author' in info)
        self.assertTrue('authordate' in info)
        self.assertTrue('commit' in info)
        self.assertTrue('commitdate' in info)

    def test_revision_info(self):
        # Latest commit
        info = self.repo.get_revision_info(self.repo.last_revision)
        self.check_valid_info(info)

        # GPG signed commit
        info = self.repo.get_revision_info(
            'd6179e46c8255f1d5029f06c49468caf57b13b61'
        )
        self.check_valid_info(info)
        self.assertEquals(
            info['author'],
            'Michal Čihař <michal@cihar.com>'
        )

        # Normal commit
        info = self.repo.get_revision_info(
            '2ae1998450a693f0a7962d69a1eec4cb2213d595'
        )
        self.check_valid_info(info)

    def test_needs_merge(self):
        self.assertFalse(self.repo.needs_merge('master'))
        self.assertFalse(self.repo.needs_push('master'))

    def test_get_version(self):
        self.assertTrue(GitRepository.get_version() != '')

    def test_set_committer(self):
        self.repo.set_committer('Foo Bar', 'foo@example.net')
        self.assertEquals(
            self.repo.get_config('user.name'), 'Foo Bar'
        )
        self.assertEquals(
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
            datetime.datetime.now(),
            ['testfile']
        )
        # Check we have new revision
        self.assertNotEquals(
            oldrev,
            self.repo.last_revision
        )
        info = self.repo.get_revision_info(self.repo.last_revision)
        self.assertEquals(
            info['author'],
            'Foo Bar <foo@bar.com>',
        )

        # Check file hash
        self.assertEquals(
            self.repo.get_object_hash('testfile'),
            'fafd745150eb1f20fc3719778942a96e2106d25b'
        )

    def test_object_hash(self):
        obj_hash = self.repo.get_object_hash('README.md')
        self.assertEquals(
            len(obj_hash),
            40
        )

    def test_configure_remote(self):
        self.repo.configure_remote('pullurl', 'pushurl', 'branch')
        self.assertEquals(
            self.repo.get_config('remote.origin.url'),
            'pullurl',
        )
        self.assertEquals(
            self.repo.get_config('remote.origin.pushURL'),
            'pushurl',
        )
        # Test that we handle not set fetching
        self.repo.execute(['config', '--unset', 'remote.origin.fetch'])
        self.repo.configure_remote('pullurl', 'pushurl', 'branch')
        self.assertEquals(
            self.repo.get_config('remote.origin.fetch'),
            '+refs/heads/branch:refs/remotes/origin/branch',
        )

    def test_configure_branch(self):
        # Existing branch
        self.repo.configure_branch('master')

        self.assertRaises(
            RepositoryException,
            self.repo.configure_branch,
            ('branch')
        )
