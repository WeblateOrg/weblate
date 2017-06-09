# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2017 Michal Čihař <michal@cihar.com>
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
"""Minimal distributed version control system abstraction for Weblate needs."""
from __future__ import unicode_literals
# For some reasons, this fails in PyLint sometimes...
# pylint: disable=E0611,F0401
from distutils.version import LooseVersion
import email.utils
import hashlib
import os
import os.path
import re
import subprocess
import logging

from dateutil import parser

from django.conf import settings
from django.utils.encoding import force_text

import six
from six.moves.configparser import RawConfigParser

from weblate.trans.util import (
    get_clean_env, add_configuration_error, path_separator
)
from weblate.trans.filelock import FileLock
from weblate.trans.ssh import ssh_file, SSH_WRAPPER

LOGGER = logging.getLogger('weblate-vcs')

VCS_REGISTRY = {}
VCS_CHOICES = []


def register_vcs(vcs):
    """Register VCS if it's supported."""
    if vcs.is_supported():
        key = vcs.name.lower()
        VCS_REGISTRY[key] = vcs
        VCS_CHOICES.append(
            (key, vcs.name)
        )
    return vcs


class RepositoryException(Exception):
    """Error while working with a repository."""
    def __init__(self, retcode, stderr, stdout):
        super(RepositoryException, self).__init__(stderr or stdout)
        self.retcode = retcode
        self.stderr = stderr.strip()
        self.stdout = stdout.strip()

    def get_message(self):
        if self.stderr:
            message = self.stderr
        else:
            message = self.stdout
        if self.retcode != 0:
            return '{0} ({1})'.format(message, self.retcode)
        return message

    def __str__(self):
        return self.get_message()


class Repository(object):
    """Basic repository object."""
    _last_revision = None
    _last_remote_revision = None
    _cmd = 'false'
    _cmd_last_revision = None
    _cmd_last_remote_revision = None
    _cmd_update_remote = None
    _cmd_push = None
    _cmd_status = ['status']

    name = None
    req_version = None
    default_branch = ''

    _is_supported = None
    _version = None

    def __init__(self, path, branch=None, component=None):
        self.path = path
        if branch is None:
            self.branch = self.default_branch
        else:
            self.branch = branch
        self.component = component
        self.last_output = ''
        self.lock = FileLock(
            self.path.rstrip('/').rstrip('\\') + '.lock',
            timeout=120
        )
        if not self.is_valid():
            self.init()

    @classmethod
    def log(cls, message):
        return LOGGER.debug('weblate: %s: %s', cls._cmd, message)

    def check_config(self):
        """Check VCS configuration."""
        raise NotImplementedError()

    def is_valid(self):
        """Check whether this is a valid repository."""
        raise NotImplementedError()

    def init(self):
        """Initialize the repository."""
        raise NotImplementedError()

    def resolve_symlinks(self, path):
        """Resolve any symlinks in the path."""
        # Resolve symlinks first
        real_path = path_separator(
            os.path.realpath(os.path.join(self.path, path))
        )
        repository_path = path_separator(
            os.path.realpath(self.path)
        )

        if not real_path.startswith(repository_path):
            raise ValueError('Too many symlinks or link outside tree')

        return real_path[len(repository_path):].lstrip('/')

    @staticmethod
    def _getenv():
        """Generate environment for process execution."""
        return get_clean_env({'GIT_SSH': ssh_file(SSH_WRAPPER)})

    @classmethod
    def _popen(cls, args, cwd=None, err=False):
        """Execute the command using popen."""
        if args is None:
            raise RepositoryException(0, 'Not supported functionality', '')
        args = [cls._cmd] + args
        process = subprocess.Popen(
            args,
            cwd=cwd,
            env=cls._getenv(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
        )
        output, output_err = process.communicate()
        retcode = process.poll()
        cls.log(
            '{0} [retcode={1}]'.format(
                ' '.join([force_text(arg) for arg in args]),
                retcode,
            )
        )
        if retcode:
            raise RepositoryException(
                retcode,
                output_err.decode('utf-8'),
                output.decode('utf-8')
            )
        if not output and err:
            return output_err.decode('utf-8')
        return output.decode('utf-8')

    def execute(self, args, needs_lock=True):
        """Execute command and caches its output."""
        if needs_lock and not self.lock.is_locked:
            raise RuntimeWarning('Repository operation without lock held!')
        self.last_output = self._popen(args, self.path)
        return self.last_output

    @property
    def last_revision(self):
        """Return last local revision."""
        if self._last_revision is None:
            self._last_revision = self.execute(
                self._cmd_last_revision,
                needs_lock=False
            )
        return self._last_revision

    @property
    def last_remote_revision(self):
        """Return last remote revision."""
        if self._last_remote_revision is None:
            self._last_remote_revision = self.execute(
                self._cmd_last_remote_revision,
                needs_lock=False
            )
        return self._last_remote_revision

    @classmethod
    def _clone(cls, source, target, branch=None):
        """Clone repository."""
        raise NotImplementedError()

    @classmethod
    def clone(cls, source, target, branch=None):
        """Clone repository and return object for cloned repository."""
        cls._clone(source, target, branch)
        return cls(target, branch)

    def update_remote(self):
        """Update remote repository."""
        self.execute(self._cmd_update_remote)
        self._last_remote_revision = None

    def status(self):
        """Return status of the repository."""
        return self.execute(
            self._cmd_status,
            needs_lock=False
        )

    def push(self):
        """Push given branch to remote repository."""
        self.execute(self._cmd_push + [self.branch])

    def reset(self):
        """Reset working copy to match remote branch."""
        raise NotImplementedError()

    def merge(self, abort=False):
        """Merge remote branch or reverts the merge."""
        raise NotImplementedError()

    def rebase(self, abort=False):
        """Rebase working copy on top of remote branch."""
        raise NotImplementedError()

    def needs_commit(self, filename=None):
        """Check whether repository needs commit."""
        raise NotImplementedError()

    def needs_merge(self):
        """Check whether repository needs merge with upstream
        (is missing some revisions).
        """
        raise NotImplementedError()

    def needs_push(self):
        """Check whether repository needs push to upstream
        (has additional revisions).
        """
        raise NotImplementedError()

    def get_revision_info(self, revision):
        """Return dictionary with detailed revision information."""
        raise NotImplementedError()

    @classmethod
    def is_supported(cls):
        """Check whether this VCS backend is supported."""
        if cls._is_supported is not None:
            return cls._is_supported
        try:
            version = cls.get_version()
        except (OSError, RepositoryException):
            cls._is_supported = False
            return False
        if cls.req_version is None:
            cls._is_supported = True
        elif LooseVersion(version) >= LooseVersion(cls.req_version):
            cls._is_supported = True
        else:
            cls._is_supported = False
            add_configuration_error(
                cls.name.lower(),
                '{0} version is too old, please upgrade to {1}.'.format(
                    cls.name,
                    cls.req_version
                )
            )
        return cls._is_supported

    @classmethod
    def get_version(cls):
        """Cached getting of version."""
        if cls._version is None:
            cls._version = cls._get_version()
        return cls._version

    @classmethod
    def _get_version(cls):
        """Return VCS program version."""
        return cls._popen(['--version'])

    def set_committer(self, name, mail):
        """Configure commiter name."""
        raise NotImplementedError()

    def commit(self, message, author=None, timestamp=None, files=None):
        """Create new revision."""
        raise NotImplementedError()

    def remove(self, files, message, author=None):
        """Remove files and creates new revision."""
        raise NotImplementedError()

    def get_object_hash(self, path):
        """Return hash of object in the VCS in a way compatible with Git."""
        real_path = os.path.join(
            self.path,
            self.resolve_symlinks(path)
        )
        objhash = hashlib.sha1()

        with open(real_path, 'rb') as handle:
            data = handle.read()
            objhash.update('blob {0}\0'.format(len(data)).encode('ascii'))
            objhash.update(data)

        return objhash.hexdigest()

    def configure_remote(self, pull_url, push_url, branch):
        """Configure remote repository."""
        raise NotImplementedError()

    def configure_branch(self, branch):
        """Configure repository branch."""
        raise NotImplementedError()

    def describe(self):
        """Verbosely describes current revision."""
        raise NotImplementedError()

    @staticmethod
    def get_merge_driver(file_format):
        merge_driver = None
        if file_format == 'po':
            merge_driver = os.path.abspath(
                os.path.join(
                    os.path.dirname(
                        os.path.dirname(os.path.dirname(__file__))
                    ),
                    'examples',
                    'git-merge-gettext-po'
                )
            )
        if merge_driver is None or not os.path.exists(merge_driver):
            return None
        return merge_driver


@register_vcs
class GitRepository(Repository):
    """Repository implementation for Git."""
    _cmd = 'git'
    _cmd_last_revision = [
        'log', '-n', '1', '--format=format:%H', 'HEAD'
    ]
    _cmd_last_remote_revision = [
        'log', '-n', '1', '--format=format:%H', '@{upstream}'
    ]
    _cmd_update_remote = ['fetch', 'origin']
    _cmd_push = ['push', 'origin']
    name = 'Git'
    req_version = '1.6'
    default_branch = 'master'

    def is_valid(self):
        """Check whether this is a valid repository."""
        return (
            os.path.exists(os.path.join(self.path, '.git', 'config')) or
            os.path.exists(os.path.join(self.path, 'config'))
        )

    def init(self):
        """Initialize the repository."""
        self._popen(['init', self.path])

    def check_config(self):
        """Check VCS configuration."""
        # We directly set config as it takes same time as reading it
        self.set_config('push.default', 'current')

    @classmethod
    def _clone(cls, source, target, branch=None):
        """Clone repository."""
        cls._popen(['clone', source, target])

    def get_config(self, path):
        """Read entry from configuration."""
        return self.execute(
            ['config', path],
            needs_lock=False
        ).strip()

    def set_config(self, path, value):
        """Set entry in local configuration."""
        self.execute(
            ['config', path, value.encode('utf-8')],
            needs_lock=False
        )

    def set_committer(self, name, mail):
        """Configure commiter name."""
        self.set_config('user.name', name)
        self.set_config('user.email', mail)

    def reset(self):
        """Reset working copy to match remote branch."""
        self.execute(['reset', '--hard', 'origin/{0}'.format(self.branch)])
        self._last_revision = None

    def rebase(self, abort=False):
        """Rebase working copy on top of remote branch."""
        if abort:
            self.execute(['rebase', '--abort'])
        else:
            self.execute(['rebase', 'origin/{0}'.format(self.branch)])

    def merge(self, abort=False):
        """Merge remote branch or reverts the merge."""
        if abort:
            self.execute(['merge', '--abort'])
        else:
            self.execute(['merge', 'origin/{0}'.format(self.branch)])

    def needs_commit(self, filename=None):
        """Check whether repository needs commit."""
        if filename is None:
            cmd = ['status', '--porcelain']
        else:
            cmd = ['status', '--porcelain', '--', filename]
        status = self.execute(cmd, needs_lock=False)
        return status != ''

    def get_revision_info(self, revision):
        """Return dictionary with detailed revision information."""
        text = self.execute(
            [
                'log',
                '-1',
                '--format=fuller',
                '--date=rfc',
                '--abbrev-commit',
                revision
            ],
            needs_lock=False
        )

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
        """Return revisin log for given refspec."""
        return self.execute(
            ['log', '--oneline', refspec, '--'],
            needs_lock=False
        )

    def needs_merge(self):
        """Check whether repository needs merge with upstream
        (is missing some revisions).
        """
        return self._log_revisions(
            '..origin/{0}'.format(self.branch)
        ) != ''

    def needs_push(self):
        """Check whether repository needs push to upstream
        (has additional revisions).
        """
        return self._log_revisions(
            'origin/{0}..'.format(self.branch)
        ) != ''

    @classmethod
    def _get_version(cls):
        """Return VCS program version."""
        return cls._popen(['--version']).split()[-1]

    def commit(self, message, author=None, timestamp=None, files=None):
        """Create new revision."""
        # Add files
        if files is not None:
            self.execute(['add', '--force', '--'] + files)

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

    def remove(self, files, message, author=None):
        """Remove files and creates new revision."""
        self.execute(['rm', '--force', '--'] + files)
        self.commit(message, author)

    def configure_remote(self, pull_url, push_url, branch):
        """Configure remote repository."""
        old_pull = None
        old_push = None
        # Parse existing remotes
        for remote in self.execute(['remote', '-v']).splitlines():
            name, url = remote.split('\t')
            if name != 'origin':
                continue
            if ' ' in url:
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

        if push_url is not None and old_push != push_url:
            self.execute(['remote', 'set-url', '--push', 'origin', push_url])

        # Set branch to track
        self.set_config(
            'remote.origin.fetch',
            '+refs/heads/{0}:refs/remotes/origin/{0}'.format(branch)
        )
        self.set_config(
            'branch.{0}.remote'.format(branch),
            'origin'
        )
        self.set_config(
            'branch.{0}.merge'.format(branch),
            'refs/heads/{0}'.format(branch)
        )

        self.branch = branch

    def configure_branch(self, branch):
        """Configure repository branch."""
        # Get List of current branches in local repository
        # (we get additional * there indicating current branch)
        branches = self.execute(['branch']).splitlines()
        if '* {0}'.format(branch) in branches:
            return

        # Add branch
        if branch not in branches:
            self.execute(
                ['branch', '--track', branch, 'origin/{0}'.format(branch)]
            )
        else:
            # Ensure it tracks correct upstream
            self.set_config(
                'branch.{0}.remote'.format(branch),
                'origin',
            )

        # Checkout
        self.execute(['checkout', branch])
        self.branch = branch

    def describe(self):
        """Verbosely describes current revision."""
        return self.execute(
            ['describe', '--always'],
            needs_lock=False
        ).strip()

    @classmethod
    def global_setup(cls):
        """Perform global settings"""
        merge_driver = cls.get_merge_driver('po')
        if merge_driver is not None:
            cls._popen([
                'config', '--global',
                'merge.weblate-merge-gettext-po.name',
                'Weblate merge driver for Gettext PO files'
            ])
            cls._popen([
                'config', '--global',
                'merge.weblate-merge-gettext-po.driver',
                '{0} %O %A %B'.format(merge_driver),
            ])


@register_vcs
class GitWithGerritRepository(GitRepository):

    name = 'Gerrit'

    _is_supported = None
    _version = None

    @classmethod
    def _get_version(cls):
        """Return VCS program version."""
        return cls._popen(['review', '--version'], err=True).split()[-1]

    def push(self):
        try:
            self.execute(['review', '--yes'])
        except RepositoryException as error:
            if error.retcode == 1:
                # Nothing to push
                return
            raise


@register_vcs
class SubversionRepository(GitRepository):

    name = 'Subversion'
    req_version = '1.6'

    _cmd_update_remote = ['svn', 'fetch']
    _cmd_push = ['svn', 'dcommit']
    _is_supported = None
    _version = None

    @classmethod
    def _get_version(cls):
        """Return VCS program version."""
        return cls._popen(['svn', '--version']).split()[2]

    def configure_remote(self, pull_url, push_url, branch):
        """Initialize the git-svn repository."""
        try:
            oldurl = self.get_config('svn-remote.svn.url')
        except RepositoryException:
            oldurl = pull_url
            self.execute(
                ['svn', 'init', '-s', '--prefix=origin/', pull_url, self.path]
            )
        if oldurl != pull_url:
            self.set_config('svn-remote.svn.url', pull_url)

    @classmethod
    def _clone(cls, source, target, branch=None):
        """Clone svn repository with git-svn."""
        cls._popen([
            'svn', 'clone', '-s', '--prefix=origin/', source, target
        ])

    def merge(self, abort=False):
        """Rebases. Git-svn does not support merge."""
        self.rebase(abort)

    def rebase(self, abort=False):
        """Rebase remote branch or reverts the rebase.
        Git-svn does not support merge.
        """
        if abort:
            self.execute(['rebase', '--abort'])
        else:
            self.execute(['svn', 'rebase'])

    def needs_merge(self):
        """Check whether repository needs merge with upstream
        (is missing some revisions).
        """
        return self._log_revisions(
            '..{0}'.format(self.get_remote_branch_name())
        ) != ''

    def needs_push(self):
        """Check whether repository needs push to upstream
        (has additional revisions).
        """
        return self._log_revisions(
            '{0}..'.format(self.get_remote_branch_name())
        ) != ''

    def reset(self):
        """Reset working copy to match remote branch."""
        self.execute(['reset', '--hard', self.get_remote_branch_name()])
        self._last_revision = None

    @property
    def last_remote_revision(self):
        """Return last remote revision."""
        if self._last_remote_revision is None:
            self._last_remote_revision = self.execute(
                [
                    'log', '-n', '1', '--format=format:%H',
                    self.get_remote_branch_name()
                ],
                needs_lock=False
            )
        return self._last_remote_revision

    def get_remote_branch_name(self):
        """Return the remote branch name: trunk if local branch is master,
        local branch otherwise.
        """
        if self.branch == 'master':
            return 'origin/trunk'
        else:
            return 'origin/{0}'.format(self.branch)


@register_vcs
class GithubRepository(GitRepository):

    name = 'GitHub'

    _cmd = 'hub'

    _hub_user = settings.GITHUB_USERNAME

    _cmd_push = ['push', '--force', _hub_user] if _hub_user \
        else ['push', 'origin']

    _is_supported = False if _hub_user is None else None
    _version = None

    @staticmethod
    def _getenv():
        """Generate environment for process execution."""
        env = {'GIT_SSH': ssh_file(SSH_WRAPPER)}

        # Add path to config if it exists
        userconfig = os.path.expanduser('~/.config/hub')
        if os.path.exists(userconfig):
            env['HUB_CONFIG'] = userconfig

        return get_clean_env(env)

    def create_pull_request(self, origin_branch, fork_branch):
        """Create pull request to merge branch in forked repository into
        branch of remote repository.
        """
        cmd = [
            'pull-request',
            '-f',
            '-h', '{0}:{1}'.format(self._hub_user, fork_branch),
            '-b', origin_branch,
            '-m', 'Update from Weblate.'.encode('utf-8'),
        ]
        self.execute(cmd)

    def push_to_fork(self, local_branch, fork_branch):
        """Push given local branch to branch in forked repository."""
        self.execute(self._cmd_push + ['{0}:{1}'.format(local_branch,
                                                        fork_branch)])

    def fork(self):
        """Create fork of original repository if one doesn't exist yet."""
        if self._hub_user not in self.execute(['remote']).splitlines():
            self.execute(['fork'])

    def push(self):
        """Fork repository on Github, pushes changes to *-weblate branch
        on fork and creates pull request against original repository.
        """
        self.fork()
        if self.component is not None:
            fork_branch = 'weblate-{0}-{1}'.format(
                self.component.project.slug,
                self.component.slug,
            )
        else:
            fork_branch = '{0}-weblate'.format(self.branch)
        self.push_to_fork(self.branch, self.branch)
        self.push_to_fork(self.branch, fork_branch)
        try:
            self.create_pull_request(self.branch, fork_branch)
        except RepositoryException as error:
            if error.retcode == 1:
                # Pull request already exists.
                return
            raise

    def configure_remote(self, pull_url, push_url, branch):
        # We don't use push URL at all
        super(GithubRepository, self).configure_remote(pull_url, None, branch)


@register_vcs
class HgRepository(Repository):
    """Repository implementation for Mercurial."""
    _cmd = 'hg'
    _cmd_last_revision = [
        'log', '--limit', '1', '--template', '{node}'
    ]
    _cmd_last_remote_revision = [
        'log', '--limit', '1', '--template', '{node}', '--branch', '.'
    ]
    _cmd_update_remote = ['pull', '--branch', '.']
    name = 'Mercurial'
    req_version = '2.8'
    default_branch = 'default'

    VERSION_RE = re.compile(r'.*\(version ([^)]*)\).*')

    def is_valid(self):
        """Check whether this is a valid repository."""
        return os.path.exists(os.path.join(self.path, '.hg', 'requires'))

    def init(self):
        """Initialize the repository."""
        self._popen(['init', self.path])

    def check_config(self):
        """Check VCS configuration."""
        # We directly set config as it takes same time as reading it
        self.set_config('ui.ssh', ssh_file(SSH_WRAPPER))

    @classmethod
    def _clone(cls, source, target, branch=None):
        """Clone repository."""
        cls._popen(['clone', source, target])

    def get_config(self, path):
        """Read entry from configuration."""
        result = None
        section, option = path.split('.', 1)
        filename = os.path.join(self.path, '.hg', 'hgrc')
        config = RawConfigParser()
        config.read(filename)
        if config.has_option(section, option):
            result = config.get(section, option)
            if six.PY2:
                result = result.decode('utf-8')
        return result

    def set_config(self, path, value):
        """Set entry in local configuration."""
        section, option = path.split('.', 1)
        filename = os.path.join(self.path, '.hg', 'hgrc')
        if six.PY2:
            value = value.encode('utf-8')
            section = section.encode('utf-8')
            option = option.encode('utf-8')
        config = RawConfigParser()
        config.read(filename)
        if not config.has_section(section):
            config.add_section(section)
        if (config.has_option(section, option) and
                config.get(section, option) == value):
            return
        config.set(section, option, value)
        with open(filename, 'w') as handle:
            config.write(handle)

    def set_committer(self, name, mail):
        """Configure commiter name."""
        self.set_config(
            'ui.username',
            '{0} <{1}>'.format(name, mail)
        )

    def reset(self):
        """Reset working copy to match remote branch."""
        self.set_config('extensions.strip', '')
        self.execute(['update', '--clean', 'remote(.)'])
        if self.needs_push():
            self.execute(['strip', 'roots(outgoing())'])
        self._last_revision = None

    def configure_merge(self):
        """Select the correct merge tool"""
        self.set_config('ui.merge', 'internal:merge')
        merge_driver = self.get_merge_driver('po')
        if merge_driver is not None:
            self.set_config(
                'merge-tools.weblate-merge-gettext-po.executable',
                merge_driver
            )
            self.set_config(
                'merge-patterns.**.po',
                'weblate-merge-gettext-po'
            )

    def rebase(self, abort=False):
        """Rebase working copy on top of remote branch."""
        self.set_config('extensions.rebase', '')
        if abort:
            self.execute(['rebase', '--abort'])
        elif self.needs_merge():
            if self.needs_ff():
                self.execute(['update', '--clean', 'remote(.)'])
            else:
                self.configure_merge()
                try:
                    self.execute(['rebase', '-d', 'remote(.)'])
                except RepositoryException as error:
                    if error.stdout:
                        message = error.stdout
                    else:
                        message = error.stderr
                    # Mercurial 3.8 changed error code and output
                    if (error.retcode in (1, 255) and
                            'nothing to rebase' in message):
                        self.execute(['update', '--clean', 'remote(.)'])
                        return
                    raise

    def merge(self, abort=False):
        """Merge remote branch or reverts the merge."""
        if abort:
            self.execute(['update', '--clean', '.'])
        elif self.needs_merge():
            if self.needs_ff():
                self.execute(['update', '--clean', 'remote(.)'])
            else:
                self.configure_merge()
                # Fallback to merge
                try:
                    self.execute(['merge', '-r', 'remote(.)'])
                except RepositoryException as error:
                    if error.retcode == 255:
                        # Nothing to merge
                        return
                    raise
                self.execute(['commit', '--message', 'Merge'])

    def needs_commit(self, filename=None):
        """Check whether repository needs commit."""
        if filename is None:
            cmd = ['status']
        else:
            cmd = ['status', '--', filename]
        status = self.execute(cmd, needs_lock=False)
        return status != ''

    def get_revision_info(self, revision):
        """Return dictionary with detailed revision information."""
        template = '''
        author_name: {person(author)}
        author_email: {email(author)}
        author: {author}
        authordate: {rfc822date(date)}
        commit_name: {person(author)}
        commit_email: {email(author)}
        commit: {author}
        commitdate: {rfc822date(date)}
        shortrevision: {short(node)}
        message:
        {desc}
        '''
        text = self.execute(
            [
                'log',
                '--limit', '1',
                '--template', template,
                '--rev', revision
            ],
            needs_lock=False
        )

        result = {
            'revision': revision,
        }

        message = []
        header = True

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if not header:
                message.append(line)
                continue
            if line == 'message:':
                header = False
                continue
            name, value = line.strip().split(':', 1)
            value = value.strip()
            name = name.lower()
            if 'date' in name:
                result[name] = parser.parse(value)
            else:
                result[name] = value

        result['message'] = '\n'.join(message)
        result['summary'] = message[0]

        return result

    def needs_ff(self):
        """Check whether repository needs a fast-forward to upstream
        (the path to the upstream is linear).
        """
        return self.execute(
            ['log', '-r', '.::remote(.) - .'],
            needs_lock=False
        ) != ''

    def needs_merge(self):
        """Check whether repository needs merge with upstream
        (has multiple heads or not up-to-date).
        """
        return self.execute(
            ['log', '-r', 'heads(branch(.)) - .'],
            needs_lock=False
        ) != ''

    def needs_push(self):
        """Check whether repository needs push to upstream
        (has additional revisions).
        """
        return self.execute(
            ['log', '-r', 'outgoing()'],
            needs_lock=False
        ) != ''

    @classmethod
    def _get_version(cls):
        """Return VCS program version."""
        output = cls._popen(['version', '-q'])
        matches = cls.VERSION_RE.match(output)
        if matches is None:
            raise OSError('Failed to parse version string: {0}'.format(output))
        return matches.group(1)

    def commit(self, message, author=None, timestamp=None, files=None):
        """Create new revision."""
        # Build the commit command
        cmd = [
            'commit',
            '--message', message.encode('utf-8'),
        ]
        if author is not None:
            cmd.extend(['--user', author.encode('utf-8')])
        if timestamp is not None:
            cmd.extend([
                '--date',
                timestamp.strftime("%a, %d %b %Y %H:%M:%S +0000")
            ])

        # Add files
        if files is not None:
            self.execute(['add', '--'] + files)
            cmd.extend(files)

        # Execute it
        self.execute(cmd)
        # Clean cache
        self._last_revision = None

    def remove(self, files, message, author=None):
        """Remove files and creates new revision."""
        self.execute(['remove', '--force', '--'] + files)
        self.commit(message, author)

    def configure_remote(self, pull_url, push_url, branch):
        """Configure remote repository."""
        old_pull = self.get_config('paths.default')
        old_push = self.get_config('paths.default-push')

        if old_pull != pull_url:
            # No origin existing or URL changed?
            self.set_config('paths.default', pull_url)

        if old_push != push_url:
            self.set_config('paths.default-push', push_url)

        # We also enable some necessary extensions here
        self.set_config('extensions.strip', '')
        self.set_config('extensions.rebase', '')
        self.set_config('experimental.evolution', 'all')
        self.set_config('phases.publish', 'False')

        self.branch = branch

    def configure_branch(self, branch):
        """Configure repository branch."""
        self.execute(['update', branch])
        self.branch = branch

    def describe(self):
        """Verbosely describes current revision."""
        return self.execute(
            [
                'log',
                '-r', '.',
                '--template', '{latesttag}-{latesttagdistance}-{node|short}'
            ],
            needs_lock=False
        ).strip()

    def push(self):
        """Push given branch to remote repository."""
        try:
            self.execute(['push', '-r', '.'])
        except RepositoryException as error:
            if error.retcode == 1:
                # No changes found
                return
            raise
