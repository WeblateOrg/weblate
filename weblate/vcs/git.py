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
"""Git based version control system abstraction for Weblate needs."""

from __future__ import unicode_literals
import email.utils
import os
import os.path

from dateutil import parser

from defusedxml import ElementTree

from django.conf import settings
from django.utils.functional import cached_property

from weblate.trans.util import get_clean_env
from weblate.vcs.ssh import get_wrapper_filename
from weblate.vcs.base import Repository, RepositoryException
from weblate.vcs.gpg import get_gpg_sign_key


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
        cls._popen([
            'clone',
            '--depth', '1',
            '--no-single-branch',
            source, target
        ])

    def get_config(self, path):
        """Read entry from configuration."""
        return self.execute(
            ['config', path],
            needs_lock=False
        ).strip()

    def set_config(self, path, value):
        """Set entry in local configuration."""
        self.execute(
            ['config', path, value]
        )

    def set_committer(self, name, mail):
        """Configure commiter name."""
        self.set_config('user.name', name)
        self.set_config('user.email', mail)

    def reset(self):
        """Reset working copy to match remote branch."""
        self.execute(['reset', '--hard', 'origin/{0}'.format(self.branch)])
        self.clean_revision_cache()

    def rebase(self, abort=False):
        """Rebase working copy on top of remote branch."""
        if abort:
            self.execute(['rebase', '--abort'])
        else:
            self.execute(['rebase', 'origin/{0}'.format(self.branch)])

    def has_rev(self, rev):
        try:
            self.execute(['rev-parse', '--verify', rev], needs_lock=False)
            return True
        except RepositoryException:
            return False

    def merge(self, abort=False):
        """Merge remote branch or reverts the merge."""
        tmp = 'weblate-merge-tmp'
        if abort:
            # Abort merge if there is one to abort
            if self.has_rev('MERGE_HEAD'):
                self.execute(['merge', '--abort'])
            # Checkout original branch (we might be on tmp)
            self.execute(['checkout', self.branch])
        else:
            if self.has_branch(tmp):
                self.execute(['branch', '-D', tmp])
            # We don't do simple git merge origin/branch as that leads
            # to different merge order than expected and most GUI tools
            # then show confusing diff (not changes done by Weblate, but
            # changes merged into Weblate)
            remote = 'origin/{}'.format(self.branch)
            # Create local branch for upstream
            self.execute(['branch', tmp, remote])
            # Checkout upstream branch
            self.execute(['checkout', tmp])
            # Merge current Weblate changes, this can lead to conflict
            cmd = [
                'merge',
                '--message',
                "Merge branch '{}' into Weblate".format(remote),
            ]
            cmd.extend(self._get_gpg_sign())
            cmd.append(self.branch)
            self.execute(cmd)
            # Checkout branch with Weblate changes
            self.execute(['checkout', self.branch])
            # Merge temporary branch (this is fast forward so does not create
            # merge commit)
            self.execute(['merge', tmp])

        # Delete temporary branch
        self.execute(['branch', '-D', tmp])

    def needs_commit(self, filename=None):
        """Check whether repository needs commit."""
        if filename is None:
            cmd = ['status', '--porcelain']
        else:
            cmd = ['status', '--porcelain', '--', filename]
        status = self.execute(cmd, needs_lock=False)
        return status != ''

    def show(self, revision):
        """Helper method to get content of revision.

        Used in tests.
        """
        return self.execute(['show', revision], needs_lock=False)

    @staticmethod
    def _get_gpg_sign():
        sign_key = get_gpg_sign_key()
        if sign_key:
            return ['--gpg-sign={}'.format(sign_key)]
        return []

    def _get_revision_info(self, revision):
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
        cmd = ['commit', '--message', message]
        if author is not None:
            cmd.extend(['--author', author])
        if timestamp is not None:
            cmd.extend(['--date', timestamp.isoformat()])
        cmd.extend(self._get_gpg_sign())
        # Execute it
        self.execute(cmd)
        # Clean cache
        self.clean_revision_cache()

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

    def has_branch(self, branch):
        # Get List of current branches in local repository
        # (we get additional * there indicating current branch)
        branches = [
            x.lstrip('*').strip()
            for x in self.execute(['branch']).splitlines()
        ]
        return branch in branches

    def configure_branch(self, branch):
        """Configure repository branch."""
        # Add branch
        if not self.has_branch(branch):
            self.execute(
                ['checkout', '-b', branch, 'origin/{0}'.format(branch)]
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

    def get_file(self, path, revision):
        """Return content of file at given revision."""
        return self.execute(
            ['show', '{0}:{1}'.format(revision, path)],
            needs_lock=False
        )


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
            self.execute(['review', '--yes', self.branch])
        except RepositoryException as error:
            if error.retcode == 1:
                # Nothing to push
                return
            raise


class SubversionRepository(GitRepository):

    name = 'Subversion'
    req_version = '1.6'

    _cmd_update_remote = ['svn', 'fetch']
    _cmd_push = ['svn', 'dcommit']
    _is_supported = None
    _version = None

    _fetch_revision = None

    @classmethod
    def _get_version(cls):
        """Return VCS program version."""
        return cls._popen(['svn', '--version']).split()[2]

    @classmethod
    def is_stdlayout(cls, url):
        output = cls._popen(['svn', 'ls', url], fullcmd=True).splitlines()
        return 'trunk/' in output

    @classmethod
    def get_last_repo_revision(cls, url):
        output = cls._popen(
            ['svn', 'log', url, '--limit=1', '--xml'],
            fullcmd=True,
            raw=True,
        )
        tree = ElementTree.fromstring(output)
        entry = tree.find('logentry')
        if entry is not None:
            return entry.get('revision')
        return None

    @classmethod
    def get_remote_args(cls, source, target):
        result = ['--prefix=origin/', source, target]
        if cls.is_stdlayout(source):
            result.insert(0, '--stdlayout')
            revision = cls.get_last_repo_revision(source + '/trunk/')
        else:
            revision = cls.get_last_repo_revision(source)
        if revision:
            revision = '--revision={}:HEAD'.format(revision)

        return result, revision

    def configure_remote(self, pull_url, push_url, branch):
        """Initialize the git-svn repository.

        This does not support switching remote as it's quite complex:
        https://git.wiki.kernel.org/index.php/GitSvnSwitch

        The git svn init errors in case the URL is not matching.
        """
        try:
            existing = self.get_config('svn-remote.svn.url')
        except RepositoryException:
            existing = None
        if existing:
            # The URL is root of the repository, while we get full path
            if not pull_url.startswith(existing):
                raise RepositoryException(
                    -1, 'Can not switch subversion URL', ''
                )
            return
        args, self._fetch_revision = self.get_remote_args(pull_url, self.path)
        self.execute(['svn', 'init'] + args)

    def update_remote(self):
        """Update remote repository."""
        if self._fetch_revision:
            self.execute(self._cmd_update_remote + [self._fetch_revision])
            self._fetch_revision = None
        else:
            self.execute(self._cmd_update_remote + ['--parent'])
        self.clean_revision_cache()

    @classmethod
    def _clone(cls, source, target, branch=None):
        """Clone svn repository with git-svn."""
        args, revision = cls.get_remote_args(source, target)
        if revision:
            args.insert(0, revision)
        cls._popen(['svn', 'clone'] + args)

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
        self.clean_revision_cache()

    @cached_property
    def last_remote_revision(self):
        """Return last remote revision."""
        return self.execute(
            [
                'log', '-n', '1', '--format=format:%H',
                self.get_remote_branch_name()
            ],
            needs_lock=False
        )

    def get_remote_branch_name(self):
        """Return the remote branch name: trunk if local branch is master,
        local branch otherwise.
        """
        if self.branch == 'master':
            fetch = self.get_config('svn-remote.svn.fetch')
            if 'origin/trunk' in fetch:
                return 'origin/trunk'
            if 'origin/git-svn' in fetch:
                return 'origin/git-svn'
        return 'origin/{0}'.format(self.branch)


class GithubRepository(GitRepository):

    name = 'GitHub'

    _cmd = 'hub'

    _is_supported = None
    _version = None

    @classmethod
    def is_supported(cls):
        if not settings.GITHUB_USERNAME:
            return False
        return super(GithubRepository, cls).is_supported()

    @staticmethod
    def _getenv():
        """Generate environment for process execution."""
        env = {'GIT_SSH': get_wrapper_filename()}

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
            '-h', '{0}:{1}'.format(settings.GITHUB_USERNAME, fork_branch),
            '-b', origin_branch,
            '-m', 'Update from Weblate.',
        ]
        self.execute(cmd)

    def push_to_fork(self, local_branch, fork_branch):
        """Push given local branch to branch in forked repository."""
        if settings.GITHUB_USERNAME:
            cmd_push = ['push', '--force', settings.GITHUB_USERNAME]
        else:
            cmd_push = ['push', 'origin']
        self.execute(cmd_push + ['{0}:{1}'.format(local_branch, fork_branch)])

    def fork(self):
        """Create fork of original repository if one doesn't exist yet."""
        remotes = self.execute(['remote']).splitlines()
        if settings.GITHUB_USERNAME not in remotes:
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
