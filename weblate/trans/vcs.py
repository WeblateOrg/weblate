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
import os.path
from dateutil import parser
from weblate.trans.util import get_clean_env


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
    _cmd_update_remote = None
    _cmd_push = None
    _cmd_status = ['status']

    def __init__(self, path):
        self.path = path
        if not self.is_valid():
            self.init()

    def is_valid(self):
        raise NotImplementedError()

    def init(self):
        raise NotImplementedError()

    @classmethod
    def _popen(cls, args, cwd=None):
        if args is None:
            raise RepositoryException('Not supported functionality')
        args = [cls._cmd] + args
        process = subprocess.Popen(
            args,
            cwd=cwd,
            env=get_clean_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        output, output_err = process.communicate()
        retcode = process.poll()
        if retcode:
            raise RepositoryException(output_err)
        return output

    def execute(self, args):
        return self._popen(args, self.path)

    @property
    def last_revision(self):
        if self._last_revision is None:
            self._last_revision = self.execute(
                self._cmd_last_revision
            )
        return self._last_revision

    @property
    def last_remote_revision(self):
        if self._last_remote_revision is None:
            self._last_remote_revision = self.execute(
                self._cmd_last_remote_revision
            )
        return self._last_remote_revision

    @classmethod
    def clone(cls, source, target, bare=False):
        """
        Clones repository and returns Repository object for cloned
        repository.
        """
        raise NotImplementedError()

    def update_remote(self):
        """
        Updates remote repository.
        """
        self.execute(self._cmd_update_remote)
        self._last_remote_revision = None

    def status(self):
        """
        Returns status of the repository.
        """
        return self.execute(self._cmd_status)

    def push(self, branch):
        """
        Pushes given branch to remote repository.
        """
        self.execute(self._cmd_push + [branch])

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

    def needs_commit(self, filename=None):
        """
        Checks whether repository needs commit.
        """
        raise NotImplementedError()

    def needs_merge(self, branch):
        """
        Checks whether repository needs merge with upstream
        (is missing some revisions).
        """
        raise NotImplementedError()

    def needs_push(self, branch):
        """
        Checks whether repository needs push to upstream
        (has additional revisions).
        """
        raise NotImplementedError()

    def get_revision_info(self, revision):
        """
        Returns dictionary with detailed revision information.
        """
        raise NotImplementedError()

    @classmethod
    def get_version(cls):
        """
        Returns VCS program version.
        """
        return cls._popen(['--version'])

    def set_committer(self, name, email):
        """
        Configures commiter name.
        """
        raise NotImplementedError()

    def commit(self, message, author, timestamp, files):
        """
        Creates new revision.
        """
        raise NotImplementedError()

    def get_object_hash(self, path):
        """
        Returns hash of object in the VCS.
        """
        raise NotImplementedError()

    def configure_remote(self, pull_url, push_url, branch):
        """
        Configure remote repository.
        """
        raise NotImplementedError()

    def configure_branch(self, branch):
        """
        Configure repository branch.
        """
        raise NotImplementedError()

    def describe(self):
        """
        Verbosely describes current revision.
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

    def is_valid(self):
        return (
            os.path.exists(os.path.join(self.path, '.git', 'config'))
            or os.path.exists(os.path.join(self.path, 'config'))
        )

    def init(self):
        self._popen(['init', self.path])

    @classmethod
    def clone(cls, source, target, bare=False):
        """
        Clones repository and returns Repository object for cloned
        repository.
        """
        if bare:
            cls._popen(['clone', '--bare', source, target])
        else:
            cls._popen(['clone', source, target])
        return cls(target)

    def get_config(self, path):
        """
        Reads entry from configuration.
        """
        return self.execute(['config', path]).strip()

    def set_config(self, path, value):
        """
        Set entry in local configuration.
        """
        self.execute(['config', path, value])

    def set_committer(self, name, email):
        """
        Configures commiter name.
        """
        self.set_config('user.name', name)
        self.set_config('user.email', email)

    def reset(self, branch):
        """
        Resets working copy to match remote branch.
        """
        self.execute(['reset', '--hard', 'origin/{0}'.format(branch)])

    def rebase(self, branch):
        """
        Rebases working copy on top of remote branch.
        """
        self.execute(['rebase', 'origin/{0}'.format(branch)])

    def merge(self, branch):
        """
        Resets working copy to match remote branch.
        """
        self.execute(['merge', 'origin/{0}'.format(branch)])

    def needs_commit(self, filename=None):
        """
        Checks whether repository needs commit.
        """
        if filename is None:
            status = self.execute(['status', '--porcelain'])
        else:
            status = self.execute(['status', '--porcelain', '--', filename])
        return status != ''

    def get_revision_info(self, revision):
        """
        Returns dictionary with detailed revision information.
        """
        text = self.execute(
            ['show', '--format=fuller', '--date=rfc', '--no-patch', revision]
        )
        result = {}

        message = []

        header = True

        for line in text.splitlines():
            if header:
                if not line:
                    header = False
                elif line.startswith('commit'):
                    continue
                else:
                    name, value = line.strip().split(':', 1)
                    if 'Date' in name:
                        result[name.lower()] = parser.parse(value.strip())
                    else:
                        result[name.lower()] = value.strip()

            else:
                message.append(line.strip())

        result['message'] = '\n'.join(message)
        result['summary'] = message[0]

        return result

    def _log_revisions(self, refspec):
        """
        Returns revisin log for given refspec.
        """
        return self.execute(
            ['log', '--oneline', refspec, '--']
        )

    def needs_merge(self, branch):
        """
        Checks whether repository needs merge with upstream
        (is missing some revisions).
        """
        return self._log_revisions('..origin/{0}'.format(branch)) != ''

    def needs_push(self, branch):
        """
        Checks whether repository needs push to upstream
        (has additional revisions).
        """
        return self._log_revisions('origin/{0}..'.format(branch)) != ''

    @classmethod
    def get_version(cls):
        """
        Returns VCS program version.
        """
        return cls._popen(['--version']).split()[-1]

    def commit(self, message, author=None, timestamp=None, files=None):
        """
        Creates new revision.
        """
        # Add files
        if files is not None:
            self.execute(['add', '--'] + files)

        # Build the commit command
        cmd = [
            'commit',
            '--message', message.encode('utf-8'),
        ]
        if author is not None:
            cmd.extend(['--author', author.encode('utf-8')])
        if timestamp is not None:
            cmd.extend(['--date', timestamp.isoformat()])
        # Execute it
        self.execute(cmd)
        # Clean cache
        self._last_revision = None

    def get_object_hash(self, path):
        """
        Returns hash of object in the VCS.
        """
        # Resolve symlinks first
        real_path = os.path.realpath(os.path.join(self.path, path))
        repository_path = os.path.realpath(self.path)

        if not real_path.startswith(repository_path):
            print real_path, repository_path
            raise ValueError('Too many symlinks or link outside tree')

        real_path = real_path[len(repository_path):].lstrip('/')

        return self.execute(['ls-tree', 'HEAD', real_path]).split()[2]

    def configure_remote(self, pull_url, push_url, branch):
        """
        Configure remote repository.
        """
        old_pull = None
        old_push = None
        # Parse existing remotes
        for remote in self.execute(['remote', '-v']).splitlines():
            name, url, kind = remote.split()
            if name != 'origin':
                continue
            if kind == '(fetch)':
                old_pull = url
            elif kind == '(push)':
                old_push = url

        if old_pull is None:
            # No origin existing
            self.execute(['remote', 'add', 'origin', pull_url])
        elif old_pull != pull_url:
            # URL changed?
            self.execute(['remote', 'set-url', 'origin', pull_url])

        if old_push != push_url:
            self.execute(['remote', 'set-url', 'origin', '--push', push_url])

        # Set branch to track
        try:
            self.execute(
                ['remote', 'set-branches', 'origin', branch]
            )
        except RepositoryException:
            self.execute(
                ['remote', 'set-branches', '--add', 'origin', branch]
            )

    def configure_branch(self, branch):
        """
        Configure repository branch.
        """
        # List of branches (we get additional * there, but we don't care)
        branches = self.execute(['branch']).split()
        if branch in branches:
            return

        # Add branch
        self.execute(
            ['branch', '--track', branch, 'origin/{0}'.format(branch)]
        )

        # Checkout
        self.execute(['checkout', branch])

    def describe(self):
        """
        Verbosely describes current revision.
        """
        return self.execute(['describe', '--always']).strip()
