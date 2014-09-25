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
"""
Minimal distributed version control system abstraction for Weblate needs.
"""
import subprocess


class RepositoryException(Exception):
    """
    Error while working with a repository.
    """


class Repository(object):
    """
    Basic repository object.
    """
    _last_revision = None
    _last_remote_revision = None
    _cmd = 'false'
    _cmd_last_revision = None
    _cmd_last_remote_revision = None
    _cmd_clone = 'clone'
    _cmd_update_remote = None
    _cmd_push = None
    _cmd_status = ['status']

    def __init__(self, path):
        self.path = path

    @classmethod
    def _popen(cls, args, cwd=None):
        if args is None:
            raise RepositoryException('Not supported functionality')
        args = [cls._cmd] + args
        process = subprocess.Popen(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        output, output_err = process.communicate()
        retcode = process.poll()
        if retcode:
            raise RepositoryException(output_err)
        return output

    def _execute(self, args):
        return self._popen(args, self.path)

    @property
    def last_revision(self):
        if self._last_revision is None:
            self._last_revision = self._execute(
                self._cmd_last_revision
            )
        return self._last_revision

    @property
    def last_remote_revision(self):
        if self._last_remote_revision is None:
            self._last_remote_revision = self._execute(
                self._cmd_last_remote_revision
            )
        return self._last_remote_revision

    @classmethod
    def clone(cls, source, target):
        """
        Clones repository and returns Repository object for cloned
        repository.
        """
        cls._popen([cls._cmd_clone, source, target])
        return cls(target)

    def update_remote(self):
        """
        Updates remote repository.
        """
        self._execute(self._cmd_update_remote)

    def status(self):
        """
        Returns status of the repository.
        """
        return self._execute(self._cmd_status)

    def push(self, branch):
        """
        Pushes given branch to remote repository.
        """
        self._execute(self._cmd_push + [branch])

    def reset(self, branch):
        """
        Resets working copy to match remote branch.
        """
        raise NotImplementedError()

    def merge(self, branch):
        """
        Merges remote branch into working copy.
        """
        raise NotImplementedError()

    def rebase(self, branch):
        """
        Rebases working copy on top of remote branch.
        """
        raise NotImplementedError()

    def needs_commit(self):
        """
        Checks whether repository needs commit.
        """
        raise NotImplementedError()


class GitRepository(Repository):
    """
    Repository implementation for Git.
    """
    _cmd = 'git'
    _cmd_last_revision = [
        'log', '-n', '1', '--format=format:%H', '@'
    ]
    _cmd_last_remote_revision = [
        'log', '-n', '1', '--format=format:%H', '@{upstream}'
    ]
    _cmd_update_remote = ['remote', 'update', 'origin']
    _cmd_push = ['push', 'origin']

    def reset(self, branch):
        """
        Resets working copy to match remote branch.
        """
        self._execute(['reset', '--hard', 'origin/{0}'.format(branch)])

    def rebase(self, branch):
        """
        Rebases working copy on top of remote branch.
        """
        self._execute(['rebase', 'origin/{0}'.format(branch)])

    def merge(self, branch):
        """
        Resets working copy to match remote branch.
        """
        self._execute(['merge', 'origin/{0}'.format(branch)])

    def needs_commit(self):
        """
        Checks whether repository needs commit.
        """
        return self._execute(['status', '--porcelain']) != ''
