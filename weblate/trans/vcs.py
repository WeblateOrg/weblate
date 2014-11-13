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
import email.utils
import re
import ConfigParser
import hashlib
from dateutil import parser
from weblate.trans.util import get_clean_env


class RepositoryException(Exception):
    """
    Error while working with a repository.
    """
    def __init__(self, retcode, stderr, stdout):
        self.retcode = retcode
        self.stderr = stderr.strip()
        self.stdout = stdout.strip()

    def __str__(self):
        if self.stderr:
            message = self.stderr
        else:
            message = self.stdout
        if self.retcode != 0:
            return '{0} ({1})'.format(message, self.retcode)
        return message


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
        self.last_output = ''
        if not self.is_valid():
            self.init()

    def is_valid(self):
        '''
        Checks whether this is a valid repository.
        '''
        raise NotImplementedError()

    def init(self):
        '''
        Initializes the repository.
        '''
        raise NotImplementedError()

    def resolve_symlinks(self, path):
        """
        Resolves any symlinks in the path.
        """
        # Resolve symlinks first
        real_path = os.path.realpath(os.path.join(self.path, path))
        repository_path = os.path.realpath(self.path)

        if not real_path.startswith(repository_path):
            print real_path, repository_path
            raise ValueError('Too many symlinks or link outside tree')

        return real_path[len(repository_path):].lstrip('/')

    @classmethod
    def _popen(cls, args, cwd=None):
        '''
        Executes the command using popen.
        '''
        if args is None:
            raise RepositoryException(0, 'Not supported functionality', '')
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
            raise RepositoryException(retcode, output_err, output)
        return output

    def execute(self, args):
        '''
        Executes command and caches it's output.
        '''
        self.last_output = self._popen(args, self.path)
        return self.last_output

    @property
    def last_revision(self):
        '''
        Returns last local revision.
        '''
        if self._last_revision is None:
            self._last_revision = self.execute(
                self._cmd_last_revision
            )
        return self._last_revision

    @property
    def last_remote_revision(self):
        '''
        Returns last remote revision.
        '''
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

    def merge(self, branch=None, abort=False):
        """
        Merges remote branch into working copy.
        """
        raise NotImplementedError()

    def rebase(self, branch=None, abort=False):
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

    def set_committer(self, name, mail):
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
        real_path = os.path.join(
            self.path,
            self.resolve_symlinks(path)
        )

        with open(real_path, 'rb') as f:
            return hashlib.sha1(f.read()).hexdigest()

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
        '''
        Checks whether this is a valid repository.
        '''
        return (
            os.path.exists(os.path.join(self.path, '.git', 'config'))
            or os.path.exists(os.path.join(self.path, 'config'))
        )

    def init(self):
        '''
        Initializes the repository.
        '''
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
        return self.execute(['config', path]).strip().decode('utf-8')

    def set_config(self, path, value):
        """
        Set entry in local configuration.
        """
        self.execute(['config', path, value])

    def set_committer(self, name, mail):
        """
        Configures commiter name.
        """
        self.set_config('user.name', name)
        self.set_config('user.email', mail)

    def reset(self, branch):
        """
        Resets working copy to match remote branch.
        """
        self.execute(['reset', '--hard', 'origin/{0}'.format(branch)])

    def rebase(self, branch=None, abort=False):
        """
        Rebases working copy on top of remote branch.
        """
        if abort:
            self.execute(['rebase', '--abort'])
        else:
            self.execute(['rebase', 'origin/{0}'.format(branch)])

    def merge(self, branch=None, abort=False):
        """
        Resets working copy to match remote branch.
        """
        if abort:
            self.execute(['merge', '--abort'])
        else:
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
        text = self.execute([
            'log',
            '-1',
            '--format=fuller',
            '--date=rfc',
            '--abbrev-commit',
            revision
        ])

        result = {
            'revision': revision,
        }

        message = []

        header = True

        for line in text.splitlines():
            if header:
                if not line:
                    header = False
                elif line.startswith('commit'):
                    result['shortrevision'] = line.split()[1]
                else:
                    name, value = line.strip().split(':', 1)
                    value = value.strip()
                    name = name.lower()
                    if 'date' in name:
                        result[name] = parser.parse(value)
                    else:
                        result[name] = value
                        if '@' in value:
                            parsed = email.utils.parseaddr(value)
                            result['{0}_name'.format(name)] = parsed[0]
                            result['{0}_email'.format(name)] = parsed[1]
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
        real_path = self.resolve_symlinks(path)

        return self.execute(['ls-tree', 'HEAD', real_path]).split()[2]

    def configure_remote(self, pull_url, push_url, branch):
        """
        Configure remote repository.
        """
        old_pull = None
        old_push = None
        # Parse existing remotes
        for remote in self.execute(['remote', '-v']).splitlines():
            name, url = remote.split('\t')
            if name != 'origin':
                continue
            url, kind = url.rsplit(' ', 1)
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
        self.execute([
            'config',
            'remote.origin.fetch',
            '+refs/heads/{0}:refs/remotes/origin/{0}'.format(branch)
        ])

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


class HgRepository(Repository):
    """
    Repository implementation for Mercurial.
    """
    _cmd = 'hg'
    _cmd_last_revision = [
        'id', '--id'
    ]
    _cmd_last_remote_revision = [
        'log', 'TODO'
    ]
    _cmd_update_remote = ['pull']
    _cmd_push = ['push']

    VERSION_RE = re.compile(r'.*\(version ([^)]*)\).*')

    def is_valid(self):
        '''
        Checks whether this is a valid repository.
        '''
        return os.path.exists(os.path.join(self.path, '.hg', 'requires'))

    def init(self):
        '''
        Initializes the repository.
        '''
        self._popen(['init', self.path])

    @classmethod
    def clone(cls, source, target, bare=False):
        """
        Clones repository and returns Repository object for cloned
        repository.
        """
        if bare:
            cls._popen(['clone', '--updaterev', 'null', source, target])
        else:
            cls._popen(['clone', source, target])
        return cls(target)

    def get_config(self, section, key):
        """
        Reads entry from configuration.
        """
        return self.execute(
            ['config', '{0}.{1}'.format(section, key)]
        ).strip().decode('utf-8')

    def set_config(self, section, key, value):
        """
        Set entry in local configuration.
        """
        filename = os.path.join(self.path, '.hg', 'hgrc')
        config = ConfigParser.RawConfigParser()
        config.read(filename)
        if not config.has_section(section):
            config.add_section(section)
        config.set(section, key, value.encode('utf-8'))
        with open(filename, 'wb') as handle:
            config.write(handle)

    def set_committer(self, name, mail):
        """
        Configures commiter name.
        """
        self.set_config(
            'ui', 'username',
            u'{0} <{1}>'.format(
                name,
                mail
            )
        )

    def reset(self, branch):
        """
        Resets working copy to match remote branch.

        TODO
        """
        self.execute(['reset', '--hard', 'origin/{0}'.format(branch)])

    def rebase(self, branch=None, abort=False):
        """
        Rebases working copy on top of remote branch.

        TODO
        """
        if abort:
            self.execute(['rebase', '--abort'])
        else:
            self.execute(['rebase', 'origin/{0}'.format(branch)])

    def merge(self, branch=None, abort=False):
        """
        Resets working copy to match remote branch.

        TODO
        """
        if abort:
            self.execute(['merge', '--abort'])
        else:
            self.execute(['merge', 'origin/{0}'.format(branch)])

    def needs_commit(self, filename=None):
        """
        Checks whether repository needs commit.

        TODO
        """
        if filename is None:
            status = self.execute(['status', '--porcelain'])
        else:
            status = self.execute(['status', '--porcelain', '--', filename])
        return status != ''

    def get_revision_info(self, revision):
        """
        Returns dictionary with detailed revision information.

        TODO
        """
        text = self.execute([
            'log',
            '-1',
            '--format=fuller',
            '--date=rfc',
            '--abbrev-commit',
            revision
        ])

        result = {
            'revision': revision,
        }

        message = []

        header = True

        for line in text.splitlines():
            if header:
                if not line:
                    header = False
                elif line.startswith('commit'):
                    result['shortrevision'] = line.split()[1]
                else:
                    name, value = line.strip().split(':', 1)
                    value = value.strip()
                    name = name.lower()
                    if 'date' in name:
                        result[name] = parser.parse(value)
                    else:
                        result[name] = value
                        if '@' in value:
                            parsed = email.utils.parseaddr(value)
                            result['{0}_name'.format(name)] = parsed[0]
                            result['{0}_email'.format(name)] = parsed[1]
            else:
                message.append(line.strip())

        result['message'] = '\n'.join(message)
        result['summary'] = message[0]

        return result

    def _log_revisions(self, refspec):
        """
        Returns revisin log for given refspec.

        TODO
        """
        return self.execute(
            ['log', '--oneline', refspec, '--']
        )

    def needs_merge(self, branch):
        """
        Checks whether repository needs merge with upstream
        (is missing some revisions).

        TODO
        """
        return self._log_revisions('..origin/{0}'.format(branch)) != ''

    def needs_push(self, branch):
        """
        Checks whether repository needs push to upstream
        (has additional revisions).

        TODO
        """
        return self._log_revisions('origin/{0}..'.format(branch)) != ''

    @classmethod
    def get_version(cls):
        """
        Returns VCS program version.
        """
        output = cls._popen(['version'])
        return cls.VERSION_RE.match(output).group(1)

    def commit(self, message, author=None, timestamp=None, files=None):
        """
        Creates new revision.

        TODO
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

    def configure_remote(self, pull_url, push_url, branch):
        """
        Configure remote repository.
        """
        old_pull = self.get_config('paths', 'default')
        old_push = self.get_config('paths', 'default-push')

        if old_pull != pull_url:
            # No origin existing or URL changed?
            self.set_config('paths', 'default', pull_url)

        if old_push != push_url:
            self.set_config('paths', 'default-push', push_url)

    def configure_branch(self, branch):
        """
        Configure repository branch.

        TODO
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

        TODO
        """
        return self.execute(['describe', '--always']).strip()
