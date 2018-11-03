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
"""Mericurial version control system abstraction for Weblate needs."""

from __future__ import unicode_literals
import os
import os.path
import re

from dateutil import parser

import six
from six.moves.configparser import RawConfigParser

from weblate.vcs.ssh import SSH_WRAPPER
from weblate.vcs.base import Repository, RepositoryException


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
    ref_to_remote = 'heads(branch(.)) - .'
    ref_from_remote = 'outgoing()'

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
        self.set_config('ui.ssh', SSH_WRAPPER.filename)

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
        if not self.lock.is_locked:
            raise RuntimeError('Repository operation without lock held!')
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
        self.clean_revision_cache()

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
                    message = error.stdout if error.stdout else error.stderr
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

    def _get_revision_info(self, revision):
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

    def log_revisions(self, refspec):
        """Return revisin log for given refspec."""
        return self.execute(
            ['log', '--template', '"{node}\n"', '--rev', refspec],
            needs_lock=False
        ).splitlines()

    def needs_ff(self):
        """Check whether repository needs a fast-forward to upstream
        (the path to the upstream is linear).
        """
        return bool(self.log_revisions('.::remote(.) - .'))

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
        cmd = ['commit', '--message', message]
        if author is not None:
            cmd.extend(['--user', author])
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
        self.clean_revision_cache()

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

    def get_file(self, path, revision):
        """Return content of file at given revision."""
        return self.execute(
            ['cat', '--rev', revision, path],
            needs_lock=False
        )

    def cleanup(self):
        """Remove not tracked files from the repository."""
        self.set_config('extensions.purge', '')
        self.execute(['purge'])
