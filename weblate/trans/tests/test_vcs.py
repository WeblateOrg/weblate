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
from weblate.trans.vcs import GitRepository

import tempfile
import shutil


class VCSGitTest(RepoTestCase):
    _tempdir = None

    def setUp(self):
        super(VCSGitTest, self).setUp()
        self._tempdir = tempfile.mkdtemp()

    def tearDown(self):
        if self._tempdir is not None:
            shutil.rmtree(self._tempdir)

    def test_clone(self):
        GitRepository.clone(self.repo_path, self._tempdir)

    def test_revision(self):
        repo = GitRepository.clone(self.repo_path, self._tempdir)
        self.assertEquals(
            repo.last_revision,
            repo.last_remote_revision
        )

    def test_update_remote(self):
        repo = GitRepository.clone(self.repo_path, self._tempdir)
        repo.update_remote()

    def test_push(self):
        repo = GitRepository.clone(self.repo_path, self._tempdir)
        repo.push('master')

    def test_reset(self):
        repo = GitRepository.clone(self.repo_path, self._tempdir)
        repo.reset('master')

    def test_merge(self):
        repo = GitRepository.clone(self.repo_path, self._tempdir)
        repo.merge('master')

    def test_rebase(self):
        repo = GitRepository.clone(self.repo_path, self._tempdir)
        repo.rebase('master')

    def test_status(self):
        repo = GitRepository.clone(self.repo_path, self._tempdir)
        status = repo.status()
        self.assertTrue(
            "Your branch is up-to-date with 'origin/master'." in status
        )

    def test_needs_commit(self):
        repo = GitRepository.clone(self.repo_path, self._tempdir)
        self.assertFalse(repo.needs_commit())

    def test_revision_info(self):
        repo = GitRepository.clone(self.repo_path, self._tempdir)
        info = repo.get_revision_info(repo.last_revision)
        self.assertTrue('summary' in info)
        self.assertTrue('author' in info)
        self.assertTrue('authordate' in info)
        self.assertTrue('commit' in info)
        self.assertTrue('commitdate' in info)

    def test_needs_merge(self):
        repo = GitRepository.clone(self.repo_path, self._tempdir)
        self.assertFalse(repo.needs_merge('master'))
        self.assertFalse(repo.needs_push('master'))
