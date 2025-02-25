# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Version control system abstraction for Weblate needs."""

from __future__ import annotations

import hashlib
import logging
import os
import os.path
import subprocess
from typing import TYPE_CHECKING

from dateutil import parser
from django.core.cache import cache
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy
from packaging.version import Version

from weblate.trans.util import get_clean_env, path_separator
from weblate.utils.data import data_path
from weblate.utils.errors import add_breadcrumb
from weblate.utils.lock import WeblateLock
from weblate.vcs.ssh import SSH_WRAPPER

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import datetime

    from django_stubs_ext import StrOrPromise

    from weblate.trans.models import Component

LOGGER = logging.getLogger("weblate.vcs")


class RepositoryError(Exception):
    """Error while working with a repository."""

    def __init__(self, retcode, message) -> None:
        super().__init__(message)
        self.retcode = retcode

    def get_message(self):
        if self.retcode != 0:
            return f"{self.args[0]} ({self.retcode})"
        return self.args[0]

    def __str__(self) -> str:
        return self.get_message()


class Repository:
    """Basic repository object."""

    _cmd = "false"
    _cmd_last_revision: list[str]
    _cmd_last_remote_revision: list[str]
    _cmd_status = ["status"]
    _cmd_list_changed_files: list[str]

    name: StrOrPromise = ""
    identifier: str = ""
    req_version: str | None = None
    default_branch: str = ""
    needs_push_url: bool = True
    supports_push: bool = True
    push_label: StrOrPromise = gettext_lazy(
        "This will push changes to the upstream repository."
    )
    ref_to_remote: str
    ref_from_remote: str

    _version = None

    @classmethod
    def get_identifier(cls):
        return cls.identifier or cls.name.lower()

    def __init__(
        self,
        path: str,
        *,
        branch: str | None = None,
        component: Component | None = None,
        local: bool = False,
        skip_init: bool = False,
    ) -> None:
        self.path = path
        if branch is None:
            self.branch = self.default_branch
        else:
            self.branch = branch
        self.component = component
        self.last_output = ""
        base_path = self.path.rstrip("/").rstrip("\\")
        self.lock = WeblateLock(
            lock_path=os.path.dirname(base_path),
            scope="repo",
            key=component.pk if component else os.path.basename(base_path),
            slug=os.path.basename(base_path),
            file_template="{slug}.lock",
            timeout=120,
            origin=component.full_slug if component else base_path,
        )
        self._config_updated = False
        self.local = local
        if not local:
            # Create ssh wrapper for possible use
            SSH_WRAPPER.create()
            if not skip_init and not self.is_valid():
                with self.lock:
                    self.create_blank_repository(self.path)

    @classmethod
    def get_remote_branch(cls, repo: str):  # noqa: ARG003
        return cls.default_branch

    @classmethod
    def add_breadcrumb(cls, message, **data) -> None:
        add_breadcrumb(category="vcs", message=message, **data)

    @classmethod
    def add_response_breadcrumb(cls, response) -> None:
        cls.add_breadcrumb(
            "http.response",
            status_code=response.status_code,
            text=response.text,
            headers=response.headers,
        )

    @classmethod
    def log(cls, message, level: int = logging.DEBUG):
        return LOGGER.log(level, "%s: %s", cls._cmd, message)

    def ensure_config_updated(self) -> None:
        """Ensure the configuration is periodically checked."""
        if self._config_updated:
            return
        cache_key = f"sp-config-check-{self.component.pk}"
        if cache.get(cache_key) is None:
            self.check_config()
            cache.set(cache_key, True, 86400)
        self._config_updated = True

    def check_config(self) -> None:
        """Check VCS configuration."""
        raise NotImplementedError

    def is_valid(self) -> bool:
        """Check whether this is a valid repository."""
        raise NotImplementedError

    @classmethod
    def create_blank_repository(cls, path: str) -> None:
        """Initialize the repository."""
        raise NotImplementedError

    def resolve_symlinks(self, path):
        """Resolve any symlinks in the path."""
        # Resolve symlinks first
        real_path = path_separator(os.path.realpath(os.path.join(self.path, path)))
        repository_path = path_separator(os.path.realpath(self.path))

        if not real_path.startswith(repository_path):
            msg = "Too many symlinks or link outside tree"
            raise ValueError(msg)

        return real_path[len(repository_path) :].lstrip("/")

    @staticmethod
    def _getenv(environment: dict[str, str] | None = None) -> dict[str, str]:
        """Generate environment for process execution."""
        base: dict[str, str] = {
            # Avoid prompts from Git
            "GIT_TERMINAL_PROMPT": "0",
            # Avoid Git traversing outside the data dir
            "GIT_CEILING_DIRECTORIES": data_path("vcs").as_posix(),
            # Use ssh wrapper
            "GIT_SSH": SSH_WRAPPER.filename.as_posix(),
            "SVN_SSH": SSH_WRAPPER.filename.as_posix(),
        }
        if environment:
            base.update(environment)
        return get_clean_env(base, extra_path=SSH_WRAPPER.path.as_posix())

    @classmethod
    def _popen(
        cls,
        args: list[str],
        *,
        cwd: str | None = None,
        merge_err: bool = True,
        fullcmd: bool = False,
        raw: bool = False,
        local: bool = False,
        stdin: str | None = None,
        environment: dict[str, str] | None = None,
    ):
        """Execute the command using popen."""
        if args is None:
            raise RepositoryError(0, "Not supported functionality")
        if not fullcmd:
            args = [cls._cmd, *list(args)]
        text_cmd = " ".join(args)
        try:
            process = subprocess.run(
                args,
                cwd=cwd,
                env=environment or {} if local else cls._getenv(environment),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT if merge_err else subprocess.PIPE,
                text=not raw,
                check=False,
                # These are mutually exclusive
                input=stdin,
                stdin=subprocess.PIPE if stdin is None else None,
                # Excessively long timeout to catch misbehaving processes
                timeout=3600,
            )
        except subprocess.TimeoutExpired as error:
            raise RepositoryError(
                0,
                f"Subprocess didn't complete before {error.timeout} seconds\n{error.stdout}{error.stderr or ''}",
            ) from error
        cls.add_breadcrumb(
            text_cmd,
            retcode=process.returncode,
            output=process.stdout,
            stderr=process.stderr,
            cwd=cwd,
        )
        if process.returncode:
            raise RepositoryError(
                process.returncode, process.stdout + (process.stderr or "")
            )
        return process.stdout

    def execute(
        self,
        args: list[str],
        *,
        needs_lock: bool = True,
        fullcmd: bool = False,
        merge_err: bool = True,
        stdin: str | None = None,
        environment: dict[str, str] | None = None,
    ):
        """Execute command and caches its output."""
        if needs_lock:
            if not self.lock.is_locked:
                msg = "Repository operation without lock held!"
                raise RuntimeError(msg)
            if self.component:
                self.ensure_config_updated()
        is_status = args[0] == self._cmd_status[0]
        try:
            self.last_output = self._popen(
                args,
                cwd=self.path,
                fullcmd=fullcmd,
                local=self.local,
                merge_err=merge_err,
                stdin=stdin,
                environment=environment,
            )
        except RepositoryError as error:
            if not is_status and not self.local:
                self.log_status(error)
            raise
        return self.last_output

    def log_status(self, error) -> None:
        try:
            self.log(f"failure {error}")
            self.log(self.status())
        except RepositoryError:
            pass

    def clean_revision_cache(self) -> None:
        if "last_revision" in self.__dict__:
            del self.__dict__["last_revision"]
        if "last_remote_revision" in self.__dict__:
            del self.__dict__["last_remote_revision"]

    @cached_property
    def last_revision(self):
        """Return last local revision."""
        return self.get_last_revision()

    def get_last_revision(self):
        return self.execute(self._cmd_last_revision, needs_lock=False, merge_err=False)

    @cached_property
    def last_remote_revision(self):
        """Return last remote revision."""
        return self.execute(
            self._cmd_last_remote_revision, needs_lock=False, merge_err=False
        )

    @classmethod
    def _clone(cls, source: str, target: str, branch: str) -> None:
        """Clone repository."""
        raise NotImplementedError

    @classmethod
    def clone(cls, source: str, target: str, branch: str, component=None):
        """Clone repository and return object for cloned repository."""
        repo = cls(target, branch=branch, component=component, skip_init=True)
        with repo.lock:
            cls._clone(source, target, branch)
        return repo

    def update_remote(self) -> None:
        """Update remote repository."""
        raise NotImplementedError

    def status(self):
        """Return status of the repository."""
        return self.execute(self._cmd_status, needs_lock=False)

    def push(self, branch) -> None:
        """Push given branch to remote repository."""
        raise NotImplementedError

    def unshallow(self) -> None:
        """Unshallow working copy."""
        return

    def reset(self) -> None:
        """Reset working copy to match remote branch."""
        raise NotImplementedError

    def merge(
        self, abort: bool = False, message: str | None = None, no_ff: bool = False
    ) -> None:
        """Merge remote branch or reverts the merge."""
        raise NotImplementedError

    def rebase(self, abort=False) -> None:
        """Rebase working copy on top of remote branch."""
        raise NotImplementedError

    def needs_commit(self, filenames: list[str] | None = None) -> bool:
        """Check whether repository needs commit."""
        raise NotImplementedError

    def count_missing(self):
        """Count missing commits."""
        return len(
            self.log_revisions(self.ref_to_remote.format(self.get_remote_branch_name()))
        )

    def count_outgoing(self, branch: str | None = None):
        """Count outgoing commits."""
        return len(
            self.log_revisions(
                self.ref_from_remote.format(self.get_remote_branch_name(branch))
            )
        )

    def needs_merge(self):
        """
        Check whether repository needs merge with upstream.

        It is missing some revisions.
        """
        return self.count_missing() > 0

    def needs_push(self):
        """
        Check whether repository needs push to upstream.

        It has additional revisions.
        """
        return self.count_outgoing() > 0

    def _get_revision_info(self, revision) -> dict[str, str]:
        """Return dictionary with detailed revision information."""
        raise NotImplementedError

    def get_revision_info(self, revision):
        """Return dictionary with detailed revision information."""
        key = f"rev-info-{self.get_identifier()}-{revision}"
        result = cache.get(key)
        if not result:
            result = self._get_revision_info(revision)
            # Keep the cache for one day
            cache.set(key, result, 86400)

        # Parse timestamps into datetime objects
        for name, value in result.items():
            if "date" in name:
                result[name] = parser.parse(value)

        return result

    @classmethod
    def is_configured(cls) -> bool:
        return True

    @classmethod
    def validate_configuration(cls) -> list[str]:
        return []

    @classmethod
    def is_supported(cls):
        """Check whether this VCS backend is supported."""
        try:
            version = cls.get_version()
        except Exception:
            return False
        return cls.req_version is None or Version(version) >= Version(cls.req_version)

    @classmethod
    def get_version(cls):
        """Get cached backend version."""
        if cls._version is None:
            try:
                cls._version = cls._get_version()
            except Exception as error:
                cls._version = error
        if isinstance(cls._version, Exception):
            raise cls._version
        return cls._version

    @classmethod
    def _get_version(cls):
        """Return VCS program version."""
        return cls._popen(["--version"], merge_err=False)

    def set_committer(self, name, mail) -> None:
        """Configure committer name."""
        raise NotImplementedError

    def commit(
        self,
        message: str,
        author: str | None = None,
        timestamp: datetime | None = None,
        files: list[str] | None = None,
    ) -> bool:
        """Create new revision."""
        raise NotImplementedError

    def remove(self, files: list[str], message: str, author: str | None = None) -> None:
        """Remove files and creates new revision."""
        raise NotImplementedError

    @staticmethod
    def update_hash(objhash, filename, extra=None) -> None:
        if os.path.islink(filename):
            objtype = "symlink"
            data = os.readlink(filename).encode()
        else:
            objtype = "blob"
            with open(filename, "rb") as handle:
                data = handle.read()
        if extra:
            objhash.update(extra.encode())
        objhash.update(f"{objtype} {len(data)}\0".encode("ascii"))
        objhash.update(data)

    def get_object_hash(self, path):
        """
        Return hash of object in the VCS.

        For files in a way compatible with Git (equivalent to git ls-tree HEAD), for
        dirs it behaves differently as we do not need to track some attributes (for
        example permissions).
        """
        real_path = os.path.join(self.path, self.resolve_symlinks(path))
        objhash = hashlib.sha1(usedforsecurity=False)

        if os.path.isdir(real_path):
            files = []
            for root, _unused, filenames in os.walk(real_path):
                for filename in filenames:
                    full_name = os.path.join(root, filename)
                    files.append((full_name, os.path.relpath(full_name, self.path)))
            for filename, name in sorted(files):
                self.update_hash(objhash, filename, name)
        else:
            self.update_hash(objhash, real_path)

        return objhash.hexdigest()

    def configure_remote(
        self, pull_url: str, push_url: str, branch: str, fast: bool = True
    ) -> None:
        """Configure remote repository."""
        raise NotImplementedError

    def configure_branch(self, branch) -> None:
        """Configure repository branch."""
        raise NotImplementedError

    def describe(self) -> str:
        """Verbosely describes current revision."""
        raise NotImplementedError

    def get_file(self, path, revision) -> str:
        """Return content of file at given revision."""
        raise NotImplementedError

    @staticmethod
    def get_examples_paths():
        """
        List possible paths for shipped examples.

        Used to locate merge drivers which are shipped there.
        """
        yield os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples")

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
        if file_format == "po":
            merge_driver = cls.find_merge_driver("git-merge-gettext-po")
        if merge_driver is None or not os.path.exists(merge_driver):
            return None
        return merge_driver

    def cleanup(self) -> None:
        """Remove not tracked files from the repository."""
        raise NotImplementedError

    def log_revisions(self, refspec) -> list[str]:
        """
        Log revisions for given refspec.

        This is not universal as refspec is different per vcs.
        """
        raise NotImplementedError

    def list_changed_files(self, refspec: str) -> list:
        """
        List changed files for given refspec.

        This is not universal as refspec is different per vcs.
        """
        lines = self.execute(
            [*self._cmd_list_changed_files, refspec], needs_lock=False, merge_err=False
        ).splitlines()
        return list(self.parse_changed_files(lines))

    def parse_changed_files(self, lines: list[str]) -> Iterator[str]:
        """Parse output with changed files."""
        raise NotImplementedError

    def get_changed_files(self, compare_to: str | None = None):
        """Get files missing upstream or changes between revisions."""
        if compare_to is None:
            compare_to = self.get_remote_branch_name()

        return self.list_changed_files(self.ref_to_remote.format(compare_to))

    def get_remote_branch_name(self, branch: str | None = None) -> str:
        return f"origin/{self.branch if branch is None else branch}"

    def list_remote_branches(self):
        return []

    def compact(self) -> None:
        return
