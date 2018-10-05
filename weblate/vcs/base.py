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
"""Version control system abstraction for Weblate needs."""

from __future__ import unicode_literals
from distutils.version import LooseVersion
import hashlib
import os
import os.path
import sys
import subprocess
import logging

from django.core.cache import cache
from django.utils.encoding import force_text
from django.utils.functional import cached_property

from filelock import FileLock

from pkg_resources import Requirement, resource_filename

from weblate.trans.util import (
    get_clean_env, path_separator,
    add_configuration_error, delete_configuration_error,
)
from weblate.vcs.ssh import SSH_WRAPPER

LOGGER = logging.getLogger('weblate-vcs')


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

    @classmethod
    def get_identifier(cls):
        return cls.name.lower()

    def __init__(self, path, branch=None, component=None, local=False):
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
        self.local = local
        if not local:
            # Create ssh wrapper for possible use
            SSH_WRAPPER.create()
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
        return get_clean_env({'GIT_SSH': SSH_WRAPPER.filename})

    @classmethod
    def _popen(cls, args, cwd=None, err=False, fullcmd=False, raw=False,
               local=False):
        """Execute the command using popen."""
        if args is None:
            raise RepositoryException(0, 'Not supported functionality', '')
        if not fullcmd:
            args = [cls._cmd] + args
        process = subprocess.Popen(
            args,
            cwd=cwd,
            env={} if local else cls._getenv(),
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
        if raw:
            return output
        return output.decode('utf-8')

    def execute(self, args, needs_lock=True, fullcmd=False):
        """Execute command and caches its output."""
        if needs_lock and not self.lock.is_locked:
            raise RuntimeError('Repository operation without lock held!')
        # On Windows we pass Unicode object, on others UTF-8 encoded bytes
        if sys.platform != "win32":
            args = [arg.encode('utf-8') for arg in args]
        self.last_output = self._popen(
            args, self.path, fullcmd=fullcmd, local=self.local
        )
        return self.last_output

    def clean_revision_cache(self):
        if 'last_revision' in self.__dict__:
            del self.__dict__['last_revision']
        if 'last_remote_revision' in self.__dict__:
            del self.__dict__['last_remote_revision']

    @cached_property
    def last_revision(self):
        """Return last local revision."""
        return self.execute(self._cmd_last_revision, needs_lock=False)

    @cached_property
    def last_remote_revision(self):
        """Return last remote revision."""
        return self.execute(
            self._cmd_last_remote_revision,
            needs_lock=False
        )

    @classmethod
    def _clone(cls, source, target, branch=None):
        """Clone repository."""
        raise NotImplementedError()

    @classmethod
    def clone(cls, source, target, branch=None):
        """Clone repository and return object for cloned repository."""
        SSH_WRAPPER.create()
        cls._clone(source, target, branch)
        return cls(target, branch)

    def update_remote(self):
        """Update remote repository."""
        self.execute(self._cmd_update_remote)
        self.clean_revision_cache()

    def status(self):
        """Return status of the repository."""
        with self.lock:
            return self.execute(self._cmd_status)

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

    def count_missing(self):
        """Count missing commits."""
        return len(self.log_revisions(
            self.ref_to_remote.format(self.get_remote_branch_name())
        ))

    def count_outgoing(self):
        """Count outgoing commits."""
        return len(self.log_revisions(
            self.ref_from_remote.format(self.get_remote_branch_name())
        ))

    def needs_merge(self):
        """Check whether repository needs merge with upstream
        (is missing some revisions).
        """
        return self.count_missing() > 0

    def needs_push(self):
        """Check whether repository needs push to upstream
        (has additional revisions).
        """
        return self.count_outgoing() > 0

    def _get_revision_info(self, revision):
        """Return dictionary with detailed revision information."""
        raise NotImplementedError()

    def get_revision_info(self, revision):
        """Return dictionary with detailed revision information."""
        key = 'rev-info-{}'.format(revision)
        result = cache.get(key)
        if not result:
            result = self._get_revision_info(revision)
            # Keep the cache for one day
            cache.set(key, result, 86400)
        return result

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
        if (cls.req_version is None or
                LooseVersion(version) >= LooseVersion(cls.req_version)):
            cls._is_supported = True
            delete_configuration_error(cls.name.lower())
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
        return cls._popen(['--version'], local=True)

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

    def get_file(self, path, revision):
        """Return content of file at given revision."""
        raise NotImplementedError()

    @staticmethod
    def get_examples_paths():
        """Generator of possible paths for examples."""
        yield os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.dirname(__file__))
            ),
            'examples'
        )
        yield resource_filename(Requirement.parse('weblate'), 'examples')
        yield '/usr/share/weblate/examples/'
        yield '/usr/local/share/weblate/examples/'

    @classmethod
    def find_merge_driver(cls, name):
        for path in cls.get_examples_paths():
            result = os.path.join(path, name)
            if os.path.exists(result):
                return os.path.abspath(result)
        return None

    @classmethod
    def get_merge_driver(cls, file_format):
        merge_driver = None
        if file_format == 'po':
            merge_driver = cls.find_merge_driver('git-merge-gettext-po')
        if merge_driver is None or not os.path.exists(merge_driver):
            return None
        return merge_driver

    def cleanup(self):
        """Remove not tracked files from the repository."""
        raise NotImplementedError()

    def log_revisions(self, refspec):
        """Log revisions for given refspec.

        This is not universal as refspec is different per vcs.
        """
        raise NotImplementedError()

    def get_remote_branch_name(self):
        return 'origin/{0}'.format(self.branch)
