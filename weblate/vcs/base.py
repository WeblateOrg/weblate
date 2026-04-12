# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Version control system abstraction for Weblate needs."""

from __future__ import annotations

import hashlib
import logging
import os
import os.path
import subprocess  # noqa: S404
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Self, TypedDict

from dateutil import parser
from django.core.cache import cache
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy
from packaging.version import Version

from weblate.trans.util import path_separator
from weblate.utils.commands import get_clean_env
from weblate.utils.data import data_path
from weblate.utils.errors import add_breadcrumb
from weblate.utils.files import (
    REPO_TEMP_DIRNAME,
    is_excluded,
    is_path_within_resolved_directory,
    remove_tree,
)
from weblate.utils.lock import WeblateLock
from weblate.vcs.ssh import SSH_WRAPPER

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator
    from datetime import datetime

    import requests
    from django_stubs_ext import StrOrPromise

    from weblate.trans.models import Component

LOGGER = logging.getLogger("weblate.vcs")

SSH_HOST_KEY_VERIFICATION_FAILED = "Host key verification failed"


def get_config_check_cache_key(component_pk: int) -> str:
    """Build cache key for repository configuration refresh."""
    wrapper_hash = hashlib.sha256(
        SSH_WRAPPER.filename.as_posix().encode("utf-8")
    ).hexdigest()
    return f"sp-config-check-{wrapper_hash}-{component_pk}"


class SubprocessArgs(TypedDict, total=False):
    stdin: int
    input: str


class RepositoryLock:
    def __init__(self, repository: Repository, lock: WeblateLock) -> None:
        self.repository = repository
        self._lock = lock
        self._recovery_pending = False
        self._recovering = False

    def __enter__(self) -> None:
        outermost_enter = not self._lock.is_locked
        self._lock.__enter__()
        if outermost_enter:
            self._recovery_pending = True
        try:
            self.repository.ensure_lock_session_recovered()
        except Exception as error:
            self._lock.__exit__(type(error), error, error.__traceback__)
            if not self._lock.is_locked:
                self._reset_recovery_state()
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback,
    ) -> None:
        self._lock.__exit__(exc_type, exc_value, traceback)
        if not self._lock.is_locked:
            self._reset_recovery_state()

    def begin_recovery(self) -> bool:
        if not self.is_locked or self._recovering or not self._recovery_pending:
            return False
        self._recovering = True
        self._recovery_pending = False
        return True

    def fail_recovery(self) -> None:
        self._recovering = False
        self._recovery_pending = True

    def finish_recovery(self) -> None:
        self._recovering = False

    def _reset_recovery_state(self) -> None:
        self._recovering = False
        self._recovery_pending = False

    def __getattr__(self, name: str):
        return getattr(self._lock, name)


class RepositoryError(Exception):
    """Error while working with a repository."""

    def __init__(self, retcode: int, message: str) -> None:
        super().__init__(message)
        self.retcode = retcode

    def get_message(self):
        if self.retcode != 0:
            return f"{self.args[0]} ({self.retcode})"
        return self.args[0]

    def __str__(self) -> str:
        return self.get_message()


class RepositorySymlinkError(ValueError):
    """Raised when symlink resolution fails due to links outside the repository tree or excessive symlink depth."""


def is_ssh_host_key_verification_error(errormessage: str) -> bool:
    """Detect SSH host key verification failures."""
    return SSH_HOST_KEY_VERIFICATION_FAILED.lower() in errormessage.lower()


def is_ssh_host_key_mismatch_error(errormessage: str) -> bool:
    """Detect SSH host key mismatch warnings for changed remote identities."""
    normalized = errormessage.lower()
    return (
        "remote host identification has changed" in normalized
        or "possible dns spoofing detected" in normalized
        or ("host key for" in normalized and "has changed" in normalized)
    )


def should_auto_add_ssh_host_key(errormessage: str) -> bool:
    """Allow TOFU host key acceptance only for first-seen hosts."""
    return is_ssh_host_key_verification_error(
        errormessage
    ) and not is_ssh_host_key_mismatch_error(errormessage)


class Repository:
    """Basic repository object."""

    _cmd: ClassVar[str] = "false"
    _cmd_last_revision: ClassVar[list[str]]
    _cmd_last_remote_revision: ClassVar[list[str]]
    _cmd_status: ClassVar[list[str]] = ["status"]
    _cmd_list_changed_files: ClassVar[list[str]]

    name: ClassVar[StrOrPromise] = ""
    identifier: ClassVar[str] = ""
    req_version: ClassVar[str | None] = None
    default_branch: ClassVar[str] = ""
    needs_push_url: ClassVar[bool] = True
    supports_push: ClassVar[bool] = True
    pushes_to_different_location: ClassVar[bool] = False
    push_label: ClassVar[StrOrPromise] = gettext_lazy(
        "This will push changes to the upstream repository."
    )
    ref_to_remote: ClassVar[str]
    ref_from_remote: ClassVar[str]
    metadata_dir_name: ClassVar[str | None] = None
    _version: ClassVar[str | None] = None
    _version_error: ClassVar[Exception | None] = None

    @classmethod
    def get_identifier(cls) -> str:
        return cls.identifier or cls.name.lower()

    def __init__(
        self,
        path: str,
        *,
        branch: str | None = None,
        component: Component | None = None,
        local: bool = False,
    ) -> None:
        self.path: str = path
        if not branch:
            self.branch = self.default_branch
        else:
            self.branch = branch
        self.component = component
        self.last_output = ""
        base_path = self.path.rstrip("/").rstrip("\\")
        lock = WeblateLock(
            lock_path=os.path.dirname(base_path),
            scope="repo",
            key=component.pk if component else os.path.basename(base_path),
            slug=os.path.basename(base_path),
            file_template="{slug}.lock",
            timeout=120,
            origin=component.full_slug if component else base_path,
        )
        self.lock = RepositoryLock(self, lock)
        self._config_updated = False
        self.local = local
        # Create ssh wrapper for possible use
        if not local:
            SSH_WRAPPER.create()

    @classmethod
    def get_remote_branch(cls, repo: str) -> str:  # noqa: ARG003
        return cls.default_branch

    @classmethod
    def validate_branch_name(cls, branch: str) -> str:
        return branch

    @classmethod
    def add_breadcrumb(cls, message: str, **data) -> None:
        add_breadcrumb(category="vcs", message=message, **data)

    @classmethod
    def add_response_breadcrumb(cls, response: requests.Response) -> None:
        cls.add_breadcrumb(
            "http.response",
            status_code=response.status_code,
            text=response.text,
            headers=response.headers,
        )

    @classmethod
    def log(cls, message: str, level: int = logging.DEBUG) -> None:
        return LOGGER.log(level, "%s: %s", cls._cmd, message)

    def ensure_config_updated(self) -> None:
        """Ensure the configuration is periodically checked."""
        if self._config_updated:
            return
        if self.component is None:
            msg = "Component not set!"
            raise TypeError(msg)
        cache_key = get_config_check_cache_key(self.component.pk)
        if cache.get(cache_key) is None:
            self.check_config()
            cache.set(cache_key, True, 86400)
        self._config_updated = True

    def check_config(self) -> None:
        """Check VCS configuration."""
        raise NotImplementedError

    def get_metadata_dir(self) -> Path | None:
        if self.metadata_dir_name is None:
            return None
        metadata_dir = Path(self.path) / self.metadata_dir_name
        if not metadata_dir.is_dir():
            return None
        return metadata_dir

    def get_repo_temp_dir(self, create: bool = True) -> Path | None:
        metadata_dir = self.get_metadata_dir()
        if metadata_dir is None:
            return None
        temp_dir = metadata_dir / REPO_TEMP_DIRNAME
        if create:
            temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir

    def cleanup_repo_temp_dir(self) -> None:
        temp_dir = self.get_repo_temp_dir(create=False)
        if temp_dir is None or not temp_dir.is_dir():
            return
        for item in temp_dir.iterdir():
            try:
                if item.is_symlink() or not item.is_dir():
                    item.unlink(missing_ok=True)
                else:
                    remove_tree(item)
            except OSError as error:
                self.log(
                    f"Failed to clean repository temp entry {item}: {error}",
                    level=logging.WARNING,
                )

    def is_valid(self) -> bool:
        """Check whether this is a valid repository."""
        raise NotImplementedError

    @classmethod
    def create_blank_repository(cls, path: str) -> None:
        """Initialize the repository."""
        raise NotImplementedError

    def resolve_symlinks(self, path: str) -> str:
        """Resolve any symlinks in the path."""
        # Resolve symlinks first
        real_path = Path(os.path.realpath(os.path.join(self.path, path)))
        repository_path = Path(os.path.realpath(self.path))

        if not is_path_within_resolved_directory(real_path, repository_path):
            msg = "Too many symlinks or link outside tree"
            raise RepositorySymlinkError(msg)

        if is_excluded(path_separator(os.fspath(real_path))):
            msg = "Link to a restricted location"
            raise RepositorySymlinkError(msg)

        relative_path = os.path.relpath(real_path, repository_path)
        if relative_path == ".":
            return ""
        return path_separator(relative_path)

    @staticmethod
    def _getenv(
        environment: dict[str, str] | None = None,
        *,
        cwd: str | None = None,
    ) -> dict[str, str]:
        """Generate environment for process execution."""
        base: dict[str, str] = {
            # Avoid prompts from Git
            "GIT_TERMINAL_PROMPT": "0",
            # Avoid Git traversing outside the data dir
            "GIT_CEILING_DIRECTORIES": data_path("vcs").as_posix(),
            # Use ssh wrapper
            "GIT_SSH_COMMAND": SSH_WRAPPER.filename.as_posix(),
            "SVN_SSH": SSH_WRAPPER.filename.as_posix(),
        }
        if cwd:
            base["GIT_DIR"] = os.path.join(cwd, ".git")
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
        retry: bool = True,
    ):
        """Execute the command using popen."""
        if args is None:
            raise RepositoryError(0, "Not supported functionality")
        if not fullcmd:
            args = [cls._cmd, *list(args)]
        text_cmd = " ".join(args)
        try:
            # These are mutually exclusive, gevent actually checks
            # for their presence, not a avalue
            kwargs: SubprocessArgs = {}
            if stdin is None:
                kwargs["stdin"] = subprocess.PIPE
            else:
                kwargs["input"] = stdin

            process = subprocess.run(
                args=args,
                cwd=cwd,
                env=environment or {} if local else cls._getenv(environment, cwd=cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT if merge_err else subprocess.PIPE,
                text=not raw,
                check=False,
                # Excessively long timeout to catch misbehaving processes
                timeout=3600,
                **kwargs,
            )
        except subprocess.TimeoutExpired as error:
            stdout = (
                error.stdout.decode()
                if isinstance(error.stdout, bytes)
                else error.stdout
            )
            stderr = (
                error.stderr.decode()
                if isinstance(error.stderr, bytes)
                else error.stderr
            )
            raise RepositoryError(
                0,
                f"Subprocess didn't complete before {error.timeout} seconds\n{stdout}{stderr or ''}",
            ) from error
        cls.add_breadcrumb(
            text_cmd,
            retcode=process.returncode,
            output=process.stdout,
            stderr=process.stderr,
            cwd=cwd,
        )
        if process.returncode:
            errormessage: str = cls.sanitize_error_message(
                process.stdout + (process.stderr or "")
            )
            if retry and cls.should_retry_popen(errormessage):
                return cls._popen(
                    args,
                    cwd=cwd,
                    merge_err=merge_err,
                    fullcmd=fullcmd,
                    raw=raw,
                    local=local,
                    stdin=stdin,
                    environment=environment,
                    retry=False,
                )

            raise RepositoryError(process.returncode, errormessage)
        return process.stdout

    @staticmethod
    def sanitize_error_message(errormessage: str) -> str:
        return errormessage

    @staticmethod
    def should_retry_popen(errormessage: str) -> bool:  # noqa: ARG004
        return False

    def recover_lock_session(self) -> None:
        self.cleanup_repo_temp_dir()

    def ensure_lock_session_recovered(self) -> None:
        if not self.lock.begin_recovery():
            return
        try:
            self.recover_lock_session()
        except Exception:
            self.lock.fail_recovery()
            raise
        self.lock.finish_recovery()

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
        self.ensure_lock_session_recovered()
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

    def log_status(self, error: str | RepositoryError) -> None:
        with suppress(RepositoryError):
            self.log(f"failure {error}")
            self.log(self.status())

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

    @staticmethod
    def validate_remote_url(url: str) -> None:
        """Revalidate a remote URL before using it."""
        from django.core.exceptions import ValidationError

        from weblate.utils.validators import validate_repo_url

        try:
            validate_repo_url(url)
        except ValidationError as error:
            raise RepositoryError(0, "; ".join(error.messages)) from error

    def validate_pull_url(self, url: str | None = None) -> None:
        """Validate the pull URL in the current runtime context."""
        if url is None and self.component is not None:
            url = self.component.repo
        if url:
            self.validate_remote_url(url)

    def validate_push_url(self, url: str | None = None) -> None:
        """Validate the push URL in the current runtime context."""
        if url is None and self.component is not None:
            url = self.component.push or self.component.repo
        if url:
            self.validate_remote_url(url)

    def clone_from(self, source: str) -> None:
        """Clone repository into current one."""
        self.validate_pull_url(source)
        self._clone(source, self.path, self.branch)

    @classmethod
    def clone(
        cls, source: str, target: str, branch: str, component: Component | None = None
    ) -> Self:
        """Clone repository and return object for cloned repository."""
        repo = cls(target, branch=branch, component=component)
        with repo.lock:
            repo.clone_from(source)
        return repo

    def update_remote(self) -> None:
        """Update remote repository."""
        raise NotImplementedError

    def status(self) -> str:
        """Return status of the repository."""
        return self.execute(self._cmd_status, needs_lock=False)

    def push(self, branch: str) -> None:
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

    def rebase(self, abort: bool = False) -> None:
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

    def get_outgoing_revisions(self, branch: str | None = None) -> list[str]:
        """List outgoing revisions."""
        return self.log_revisions(
            self.ref_from_remote.format(self.get_remote_branch_name(branch))
        )

    def get_tracked_outgoing_revisions(self) -> list[str]:
        """List revisions missing from the tracked upstream branch."""
        return self.get_outgoing_revisions()

    def get_push_revisions(self, branch: str | None = None) -> list[str]:
        """
        List revisions that still need to be pushed.

        When a separate push branch is configured, only revisions missing from
        both the tracked upstream branch and the push branch need to be pushed.
        """
        outgoing = (
            self.get_tracked_outgoing_revisions()
            if branch
            else self.get_outgoing_revisions()
        )
        if not outgoing:
            return []
        if not branch:
            return outgoing
        try:
            branch_outgoing = set(self.get_outgoing_revisions(branch))
        except RepositoryError:
            return outgoing
        return [revision for revision in outgoing if revision in branch_outgoing]

    def count_outgoing(self, branch: str | None = None):
        """Count outgoing commits."""
        return len(self.get_outgoing_revisions(branch))

    def needs_merge(self):
        """
        Check whether repository needs merge with upstream.

        It is missing some revisions.
        """
        return self.count_missing() > 0

    def needs_push(self, branch: str | None = None):
        """Check whether repository needs push."""
        return bool(self.get_push_revisions(branch))

    def _get_revision_info(self, revision: str) -> dict[str, str]:
        """Return dictionary with detailed revision information."""
        raise NotImplementedError

    def get_revision_info(self, revision: str) -> dict[str, str]:
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
        version = cls.__dict__.get("_version")
        version_error = cls.__dict__.get("_version_error")

        if version is None and version_error is None:
            try:
                cls._version = cls._get_version()
            except Exception as error:
                cls._version_error = error
            version = cls.__dict__.get("_version")
            version_error = cls.__dict__.get("_version_error")

        if version_error is not None:
            raise version_error
        return version

    @classmethod
    def _get_version(cls):
        """Return VCS program version."""
        return cls._popen(["--version"], merge_err=False)

    def set_committer(self, name: str, mail: str) -> None:
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
    def update_hash(
        objhash: hashlib._Hash, filename: str, extra: str | None = None
    ) -> None:
        if os.path.islink(filename):
            objtype = "symlink"
            data = os.readlink(filename).encode()
        else:
            objtype = "blob"
            data = Path(filename).read_bytes()
        if extra:
            objhash.update(extra.encode())
        objhash.update(f"{objtype} {len(data)}\0".encode("ascii"))
        objhash.update(data)

    def get_object_hash(self, path: str) -> str:
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

    def configure_branch(self, branch: str) -> None:
        """Configure repository branch."""
        raise NotImplementedError

    def describe(self) -> str:
        """Verbosely describes current revision."""
        raise NotImplementedError

    def get_file(self, path: str, revision: str) -> str:
        """Return content of file at given revision."""
        raise NotImplementedError

    @staticmethod
    def get_examples_paths() -> Generator[str]:
        """
        List possible paths for shipped examples.

        Used to locate merge drivers which are shipped there.
        """
        yield os.path.join(os.path.dirname(os.path.dirname(__file__)), "examples")

    @classmethod
    def find_merge_driver(cls, name: str) -> str | None:
        for path in cls.get_examples_paths():
            result = os.path.join(path, name)
            if os.path.exists(result):
                return os.path.abspath(result)
        return None

    @classmethod
    def get_merge_driver(cls, file_format: str) -> str | None:
        merge_driver = None
        if file_format == "po":
            merge_driver = cls.find_merge_driver("git-merge-gettext-po")
        if merge_driver is None or not os.path.exists(merge_driver):
            return None
        return merge_driver

    def remove_stale_branches(self) -> None:
        """Remove stale branches and tags from the repository."""
        raise NotImplementedError

    def cleanup_files(self) -> None:
        """Remove not tracked files from the repository."""
        raise NotImplementedError

    def cleanup(self) -> None:
        """Cleanup repository status."""
        # Recover from failed merge/rebase
        with suppress(RepositoryError):
            self.merge(abort=True)
        with suppress(RepositoryError):
            self.rebase(abort=True)
        # Remove stale branches
        self.remove_stale_branches()
        # Cleanup files
        self.cleanup_files()

    def log_revisions(self, refspec: str) -> list[str]:
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
        branch_name = branch or self.branch
        return f"origin/{self.validate_branch_name(branch_name)}"

    def list_remote_branches(self) -> list[str]:
        return []

    def compact(self) -> None:
        return

    def show(self, revision: str) -> str:
        raise NotImplementedError

    def maintenance(self) -> None:
        self.remove_stale_branches()
        self.compact()
