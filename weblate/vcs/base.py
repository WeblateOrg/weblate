# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Version control system abstraction for Weblate needs."""

from __future__ import annotations

import hashlib
import logging
import os
import os.path
import signal
import subprocess  # ruff: ignore[suspicious-subprocess-import]
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Literal,
    NotRequired,
    Required,
    Self,
    TypedDict,
)

from dateutil import parser
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy, gettext_noop
from packaging.version import Version

from weblate.trans.util import path_separator
from weblate.utils.commands import get_clean_env
from weblate.utils.data import data_path
from weblate.utils.errors import add_breadcrumb
from weblate.utils.files import (
    REPO_TEMP_DIRNAME,
    is_path_within_resolved_directory,
    is_unsafe_path,
    is_vcs_metadata_path,
    remove_tree,
)
from weblate.utils.lock import WeblateLock
from weblate.utils.outbound import get_environment_proxy
from weblate.vcs.ssh import SSH_WRAPPER

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable, Iterator

    import httpx2
    from django_stubs_ext import StrOrPromise

    from weblate.trans.models import Component
    from weblate.utils.validators import ResolvedRepositoryURL

LOGGER = logging.getLogger("weblate.vcs")

SSH_HOST_KEY_VERIFICATION_FAILED = "Host key verification failed"
# Bump when check_config() gains settings existing repositories must refresh.
CONFIG_CHECK_CACHE_VERSION = 2


def get_config_check_cache_key(component_pk: int) -> str:
    """Build cache key for repository configuration refresh."""
    wrapper_hash = hashlib.sha256(
        SSH_WRAPPER.filename.as_posix().encode("utf-8")
    ).hexdigest()
    return (
        f"sp-config-check-v{CONFIG_CHECK_CACHE_VERSION}-{wrapper_hash}-{component_pk}"
    )


def get_repository_lock_key(base_path: str, component: Component | None) -> int | str:
    """Build lock key for repository operations."""
    if component is not None and component.pk is not None:
        return component.pk
    return hashlib.sha256(base_path.encode("utf-8")).hexdigest()


class SubprocessArgs(TypedDict, total=False):
    stdin: int
    input: str


class RawCommitInfo(TypedDict):
    """Detailed revision information returned by VCS implementations."""

    revision: Required[str]
    shortrevision: Required[str]
    author: Required[str]
    authordate: Required[str]
    commit: Required[str]
    commitdate: Required[str]
    message: Required[str]
    summary: Required[str]
    author_name: NotRequired[str]
    author_email: NotRequired[str]
    commit_name: NotRequired[str]
    commit_email: NotRequired[str]
    committerdate: NotRequired[str]
    date: NotRequired[str]


class CommitInfo(TypedDict):
    """Detailed revision information exposed to callers."""

    revision: Required[str]
    shortrevision: Required[str]
    author: Required[str]
    authordate: Required[datetime]
    commit: Required[str]
    commitdate: Required[datetime]
    message: Required[str]
    summary: Required[str]
    author_name: NotRequired[str]
    author_email: NotRequired[str]
    commit_name: NotRequired[str]
    commit_email: NotRequired[str]
    committerdate: NotRequired[datetime]
    date: NotRequired[datetime]


type RemoteOperation = Literal["none", "pull", "push"]
type RepositoryDiagnosisCode = Literal[
    "branch_behind",
    "gerrit_permission",
    "github_pull_request_creation_restricted",
    "missing_credentials",
    "repository_not_found",
    "repository_permission",
    "repository_redirect",
    "ssh_host_key_mismatch",
    "ssh_host_key_unverified",
    "temporary_failure",
]
type RepositoryErrorCode = Literal[
    "api_error",
    "api_error_retry",
    "api_request_failed",
    "api_request_failed_retry",
    "api_request_failed_with_error",
    "api_request_failed_with_error_retry",
    "github_app_branch_required",
    "github_app_installation_invalid",
    "github_app_installation_missing",
    "github_app_installation_missing_for_host",
    "github_app_token_failed",
    "github_app_workspace_required",
    "gitlab_project_failed",
    "gitlab_project_failed_unknown",
    "pull_request_listing_failed",
    "pull_request_listing_failed_retry",
    "repository_fork_failed",
    "repository_fork_not_found",
    "repository_fork_failed_retry",
    "repository_fork_failed_with_error",
    "repository_fork_failed_with_error_retry",
    "repository_interrupted_operation",
    "repository_recovery_failed",
    "repository_redirect",
    "repository_redirect_credentials",
    "repository_redirect_cross_host",
    "repository_redirect_insecure",
    "repository_redirect_invalid",
    "repository_redirect_invalid_hostname",
    "repository_redirect_loop",
    "repository_redirect_missing_address",
    "repository_redirect_missing_target",
    "repository_redirect_not_smart_http",
    "repository_redirect_probe_failed",
    "repository_redirect_query_changed",
    "repository_redirect_target_invalid",
    "repository_redirect_target_unverified",
    "repository_redirect_too_many",
    "repository_redirect_unsupported_scheme",
    "repository_remote_branch_shallow",
    "repository_remote_branch_unrelated",
    "repository_ssh_destination_unresolved",
    "repository_ssh_destination_unresolved_with_error",
    "repository_unsupported_interrupted_operation",
    "repository_url_backend_unsupported",
    "repository_url_host_not_allowed",
    "repository_url_invalid",
    "repository_url_parse_invalid",
    "repository_url_parse_failed",
    "repository_url_private_target",
    "repository_url_scheme_not_allowed",
    "repository_url_unresolved",
    "repository_url_unresolved_with_error",
]


class RepositoryDiagnosis(TypedDict):
    """Machine-readable diagnosis for a repository error."""

    code: RepositoryDiagnosisCode
    params: NotRequired[dict[str, str]]


class RepositoryStructuredError(TypedDict):
    """Machine-readable repository error stored in an alert."""

    code: RepositoryErrorCode
    retcode: int
    params: NotRequired[dict[str, str]]


class RepositoryAlertDetails(TypedDict):
    """Persistent details for a repository failure alert."""

    error: str | RepositoryStructuredError
    diagnoses: list[RepositoryDiagnosis]


REPOSITORY_ERROR_MESSAGES: dict[RepositoryErrorCode, str] = {
    "api_error": gettext_noop("%(detail)s"),
    "api_error_retry": gettext_noop("%(detail)s Please retry later."),
    "api_request_failed": gettext_noop(
        "%(service)s API request failed while creating a pull request: %(status)s"
    ),
    "api_request_failed_retry": gettext_noop(
        "%(service)s API request failed while creating a pull request: %(status)s Please retry later."
    ),
    "api_request_failed_with_error": gettext_noop(
        "%(service)s API request failed while creating a pull request (%(status)s): %(error)s"
    ),
    "api_request_failed_with_error_retry": gettext_noop(
        "%(service)s API request failed while creating a pull request (%(status)s): %(error)s Please retry later."
    ),
    "github_app_branch_required": gettext_noop(
        "GitHub App repositories must be imported with a branch."
    ),
    "github_app_installation_invalid": gettext_noop(
        "Invalid GitHub App installation ID."
    ),
    "github_app_installation_missing": gettext_noop(
        "No Weblate GitHub app installation available."
    ),
    "github_app_installation_missing_for_host": gettext_noop(
        "No Weblate GitHub app installation available for %(hostname)s"
    ),
    "github_app_token_failed": gettext_noop(
        "Could not obtain GitHub App access token: %(error)s"
    ),
    "github_app_workspace_required": gettext_noop(
        "GitHub App components require a project with a workspace."
    ),
    "gitlab_project_failed": gettext_noop(
        "Could not get GitLab project (%(status)s): %(error)s"
    ),
    "gitlab_project_failed_unknown": gettext_noop(
        "Could not get GitLab project (%(status)s): Unknown error"
    ),
    "pull_request_listing_failed": gettext_noop(
        "Pull request listing failed: %(error)s"
    ),
    "pull_request_listing_failed_retry": gettext_noop(
        "Pull request listing failed: %(error)s Please retry later."
    ),
    "repository_fork_failed": gettext_noop("Could not fork repository at %(hostname)s"),
    "repository_fork_failed_retry": gettext_noop(
        "Could not fork repository at %(hostname)s. Please retry later."
    ),
    "repository_fork_failed_with_error": gettext_noop(
        "Could not fork repository at %(hostname)s: %(error)s"
    ),
    "repository_fork_failed_with_error_retry": gettext_noop(
        "Could not fork repository at %(hostname)s: %(error)s Please retry later."
    ),
    "repository_fork_not_found": gettext_noop(
        "Could not fork repository at %(hostname)s: Repository not found. "
        "Check whether exists and user '%(username)s' has access to it."
    ),
    "repository_interrupted_operation": gettext_noop(
        "Repository has an interrupted Git %(operation)s operation."
    ),
    "repository_recovery_failed": gettext_noop(
        "Could not recover interrupted Git %(operation)s operation."
    ),
    "repository_redirect": gettext_noop(
        "The repository URL permanently redirects to a canonical URL."
    ),
    "repository_redirect_credentials": gettext_noop(
        "The repository HTTP redirect contains credentials and was rejected."
    ),
    "repository_redirect_cross_host": gettext_noop(
        "The repository URL redirects to a different host. Automatic cross-host redirects are disabled for security; update the repository URL manually."
    ),
    "repository_redirect_insecure": gettext_noop(
        "The repository URL redirects from HTTPS to an insecure URL and was rejected."
    ),
    "repository_redirect_invalid": gettext_noop(
        "The repository returned an invalid HTTP redirect."
    ),
    "repository_redirect_invalid_hostname": gettext_noop(
        "The repository returned an HTTP redirect with an invalid hostname."
    ),
    "repository_redirect_loop": gettext_noop(
        "The repository HTTP redirect contains a loop."
    ),
    "repository_redirect_missing_address": gettext_noop(
        "The repository redirect target has no validated address."
    ),
    "repository_redirect_missing_target": gettext_noop(
        "The repository returned a permanent HTTP redirect without a target URL."
    ),
    "repository_redirect_not_smart_http": gettext_noop(
        "The repository HTTP redirect does not point to a Git smart HTTP endpoint."
    ),
    "repository_redirect_probe_failed": gettext_noop(
        "Could not probe the repository HTTP redirect: %(error)s"
    ),
    "repository_redirect_query_changed": gettext_noop(
        "The repository HTTP redirect unexpectedly changed the URL query."
    ),
    "repository_redirect_target_invalid": gettext_noop(
        "The repository HTTP redirect target could not be validated."
    ),
    "repository_redirect_target_unverified": gettext_noop(
        "The repository HTTP redirect target could not be verified as a Git repository."
    ),
    "repository_redirect_too_many": gettext_noop(
        "The repository returned too many HTTP redirects."
    ),
    "repository_redirect_unsupported_scheme": gettext_noop(
        "The repository URL redirects to an unsupported URL scheme."
    ),
    "repository_remote_branch_shallow": gettext_noop(
        "Remote branch could not be verified against the shallow existing repository."
    ),
    "repository_remote_branch_unrelated": gettext_noop(
        "Remote branch does not share common history with the existing repository."
    ),
    "repository_ssh_destination_unresolved": gettext_noop(
        "Could not determine the effective SSH destination."
    ),
    "repository_ssh_destination_unresolved_with_error": gettext_noop(
        "Could not determine the effective SSH destination: %(error)s"
    ),
    "repository_unsupported_interrupted_operation": gettext_noop(
        "Unsupported interrupted Git operation: %(operation)s"
    ),
    "repository_url_backend_unsupported": gettext_noop(
        "This VCS backend cannot safely connect to this URL while private address restrictions are enabled."
    ),
    "repository_url_host_not_allowed": gettext_noop(
        "Fetching VCS repository from %(hostname)s is not allowed."
    ),
    "repository_url_invalid": gettext_noop("Enter a valid URL."),
    "repository_url_parse_invalid": gettext_noop("Could not parse URL."),
    "repository_url_parse_failed": gettext_noop("Could not parse URL: %(error)s"),
    "repository_url_private_target": gettext_noop(
        "This URL is prohibited because it points to an internal or non-public address."
    ),
    "repository_url_scheme_not_allowed": gettext_noop(
        "Fetching VCS repository using %(scheme)s is not allowed."
    ),
    "repository_url_unresolved": gettext_noop("Could not resolve the URL domain."),
    "repository_url_unresolved_with_error": gettext_noop(
        "Could not resolve the URL domain: %(error)s"
    ),
}


REPOSITORY_REDIRECT_MESSAGES = (
    "returned error: 301",
    "returned error: 308",
    "http redirect",
    "permanently redirects",
    "repository url redirects",
)
REPOSITORY_BEHIND_MESSAGES = (
    "The tip of your current branch is behind its remote counterpart",
    "fetch first",
)
REPOSITORY_NOT_FOUND_MESSAGES = (
    "Repository not found.",
    "HTTP Error 404: Not Found",
    "Repository was archived so is read-only",
    "does not appear to be a git repository",
)
REPOSITORY_TEMPORARY_MESSAGES = (
    "Empty reply from server",
    "no suitable response from remote hg",
    "cannot lock ref",
    "Too many retries",
    "Connection timed out",
)
REPOSITORY_PERMISSION_MESSAGES = (
    "denied to",
    "The repository exists, but forking is disabled.",
    "protected branch hook declined",
    "GH006:",
)
REPOSITORY_GERRIT_PERMISSION_MESSAGES = (
    "is not registered in your account, and you lack 'forge",
    "prohibited by Gerrit",
)


@dataclass(slots=True)
class RepositoryRecoveryEvent:
    operation: str
    details: dict[str, Any]


@dataclass(slots=True)
class RepositoryLockSkipState:
    count: int = 0


def parse_commit_date(value: str | datetime) -> datetime:
    """Parse a commit date string into a datetime object."""
    result = value if isinstance(value, datetime) else parser.parse(value)
    if settings.USE_TZ and timezone.is_naive(result):
        return timezone.make_aware(result)
    return result


class RepositoryLock:
    def __init__(self, repository: Repository, lock: WeblateLock) -> None:
        self.repository = repository
        self._lock = lock
        self._recovery_pending = False
        self._recovering = False
        self._skip_recovery = RepositoryLockSkipState()

    @property
    def lock_object(self) -> WeblateLock:
        return self._lock

    def replace_lock(self, lock: Self) -> None:
        self._lock = lock._lock
        self._recovery_pending = lock._recovery_pending
        self._recovering = lock._recovering
        self._skip_recovery = lock._skip_recovery

    def replace_lock_if_matching(self, lock: Self) -> bool:
        if self._lock.name != lock._lock.name:
            return False
        self.replace_lock(lock)
        return True

    def __enter__(self) -> None:
        outermost_enter = not self._lock.is_locked
        self._lock.__enter__()
        if outermost_enter and not self._skip_recovery.count:
            self._recovery_pending = True
        try:
            if not self._skip_recovery.count:
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

    @contextmanager
    def without_recovery(self) -> Generator[None]:
        self._skip_recovery.count += 1
        try:
            yield
        finally:
            self._skip_recovery.count -= 1

    def _reset_recovery_state(self) -> None:
        self._recovering = False
        self._recovery_pending = False

    def __getattr__(self, name: str):
        return getattr(self._lock, name)


class RepositoryError(Exception):
    """Error while working with a repository."""

    def __init__(
        self,
        retcode: int,
        message: str,
        *,
        diagnoses: Iterable[RepositoryDiagnosis] = (),
    ) -> None:
        super().__init__(message)
        self.retcode = retcode
        self.diagnoses = list(diagnoses)

    def get_message(self, translator: Callable[[str], str] | None = None) -> str:
        if self.retcode != 0:
            return f"{self.args[0]} ({self.retcode})"
        return self.args[0]

    def __str__(self) -> str:
        return self.get_message()


class RepositoryInternalError(RepositoryError):
    """Structured error for failures generated by Weblate itself."""

    def __init__(
        self,
        retcode: int,
        code: RepositoryErrorCode,
        *,
        params: dict[str, str] | None = None,
        diagnoses: Iterable[RepositoryDiagnosis] = (),
    ) -> None:
        self.code = code
        self.params = params or {}
        super().__init__(retcode, code, diagnoses=diagnoses)

    def get_message(self, translator: Callable[[str], str] | None = None) -> str:
        template = REPOSITORY_ERROR_MESSAGES[self.code]
        if translator is not None:
            template = translator(template)
        message = template % self.params
        if self.retcode != 0:
            return f"{message} ({self.retcode})"
        return message

    def get_stored_error(self) -> RepositoryStructuredError:
        """Return a JSON-safe structured representation for persistent storage."""
        result: RepositoryStructuredError = {
            "code": self.code,
            "retcode": self.retcode,
        }
        if self.params:
            result["params"] = self.params
        return result


def format_stored_repository_error(
    error: str | RepositoryStructuredError,
    translator: Callable[[str], str] | None = None,
) -> str:
    """Format a raw or structured repository error for a consumer."""
    if isinstance(error, str):
        return error
    structured = RepositoryInternalError(
        error["retcode"],
        error["code"],
        params=error.get("params"),
    )
    return structured.get_message(translator)


class RepositoryCommandError(RepositoryError):
    """Error raised by the underlying VCS command."""

    def get_message(self, translator: Callable[[str], str] | None = None) -> str:
        if self.retcode < 0:
            signum = -self.retcode
            with suppress(ValueError):
                signal_name = signal.Signals(signum).name
                if signum == signal.SIGTERM:
                    hint = (
                        "The underlying command was terminated by signal "
                        f"{signal_name}, usually because the worker or host was "
                        "restarted or stopped during the operation."
                    )
                else:
                    hint = (
                        "The underlying command was terminated by signal "
                        f"{signal_name}."
                    )
                message = self.args[0].rstrip()
                if message:
                    return f"{message}\n\n{hint} ({self.retcode})"
                return f"{hint} ({self.retcode})"
        return super().get_message(translator)


class RepositoryValidationError(RepositoryInternalError):
    """Error raised when repository configuration violates runtime policy."""


class RepositoryRedirectError(RepositoryInternalError):
    """A repository URL permanently redirects to a validated canonical URL."""

    def __init__(
        self,
        original_url: str,
        canonical_url: str,
        status_code: int,
    ) -> None:
        super().__init__(
            0,
            "repository_redirect",
            diagnoses=({"code": "repository_redirect"},),
        )
        self.original_url = original_url
        self.canonical_url = canonical_url
        self.status_code = status_code


class RepositorySymlinkError(ValueError):
    """Raised when symlink resolution fails due to links outside the repository tree or excessive symlink depth."""


class RepositoryRestrictedPathError(RepositorySymlinkError):
    """Raised when a resolved repository path points to a restricted location."""


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


def get_repository_error_diagnoses(error: str) -> list[RepositoryDiagnosis]:
    """Classify a repository error into stable machine-readable diagnoses."""
    diagnoses: list[RepositoryDiagnosis] = []
    normalized = error.lower()

    if any(message in normalized for message in REPOSITORY_REDIRECT_MESSAGES):
        diagnoses.append({"code": "repository_redirect"})
    if "terminal prompts disabled" in error:
        diagnoses.append({"code": "missing_credentials"})
    if any(message in error for message in REPOSITORY_BEHIND_MESSAGES):
        diagnoses.append({"code": "branch_behind"})
    if is_ssh_host_key_mismatch_error(error):
        diagnoses.append({"code": "ssh_host_key_mismatch"})
    elif is_ssh_host_key_verification_error(error):
        diagnoses.append({"code": "ssh_host_key_unverified"})
    if any(message in error for message in REPOSITORY_NOT_FOUND_MESSAGES):
        diagnoses.append({"code": "repository_not_found"})
    if any(message in error for message in REPOSITORY_PERMISSION_MESSAGES):
        diagnoses.append({"code": "repository_permission"})
    if any(message in error for message in REPOSITORY_GERRIT_PERMISSION_MESSAGES):
        diagnoses.append({"code": "gerrit_permission"})
    if any(message in error for message in REPOSITORY_TEMPORARY_MESSAGES):
        diagnoses.append({"code": "temporary_failure"})

    return diagnoses


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
    manual_component_creation: ClassVar[bool] = True
    component_lock_fields: ClassVar[tuple[str, ...]] = ()
    component_clear_fields: ClassVar[tuple[str, ...]] = ()
    component_requires_branch: ClassVar[bool] = False
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
    supports_remote_compatibility_validation: ClassVar[bool] = False
    pinned_remote_schemes: ClassVar[frozenset[str]] = frozenset()
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
            scope="repository",
            key=get_repository_lock_key(base_path, component),
            slug=os.path.basename(base_path),
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
    # ruff: ignore[unused-class-method-argument]
    def get_remote_branch(cls, repo: str) -> str:
        return cls.default_branch

    @classmethod
    def validate_branch_name(cls, branch: str) -> str:
        return branch

    @classmethod
    def validate_component(cls, component: Component) -> None:
        """Validate repository-specific component constraints."""

    @classmethod
    def add_breadcrumb(cls, message: str, **data) -> None:
        add_breadcrumb(category="vcs", message=message, **data)

    @classmethod
    def add_response_breadcrumb(cls, response: httpx2.Response) -> None:
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

        relative_path = os.path.relpath(real_path, repository_path)

        resolved_path = path_separator(relative_path)
        if is_unsafe_path(resolved_path) or is_vcs_metadata_path(resolved_path):
            msg = "Link to a restricted location"
            raise RepositoryRestrictedPathError(msg)

        if relative_path == ".":
            return ""
        return resolved_path

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
            # Avoid git advises like merge conflicts resolution
            "GIT_ADVICE": "0",
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
        cmd = args if fullcmd else [cls._cmd, *args]
        text_cmd = " ".join(cmd)
        # These are mutually exclusive, gevent actually checks
        # for their presence, not a value.
        kwargs: SubprocessArgs = {}
        if stdin is None:
            kwargs["stdin"] = subprocess.PIPE
        else:
            kwargs["input"] = stdin

        try:
            process = subprocess.run(
                args=cmd,
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
        except OSError as error:
            if cwd is None or error.filename != cwd:
                raise
            raise RepositoryCommandError(
                error.errno or 1, cls.sanitize_error_message(str(error))
            ) from error
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
            raise RepositoryCommandError(
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

            raise RepositoryCommandError(process.returncode, errormessage)
        return process.stdout

    @staticmethod
    def sanitize_error_message(errormessage: str) -> str:
        return errormessage

    @staticmethod
    # ruff: ignore[unused-static-method-argument]
    def should_retry_popen(errormessage: str) -> bool:
        return False

    def recover_lock_session(self) -> list[RepositoryRecoveryEvent]:
        self.cleanup_repo_temp_dir()
        return []

    def ensure_lock_session_recovered(self) -> None:
        if not self.lock.begin_recovery():
            return
        try:
            recovery_events = self.recover_lock_session()
            if self.component is not None:
                self.component.handle_repository_recovery(recovery_events)
        except Exception as error:
            if self.component is not None:
                with suppress(Exception):
                    self.component.handle_repository_recovery_failure(error)
            self.lock.fail_recovery()
            raise
        self.lock.finish_recovery()

    def execute(
        self,
        args: list[str],
        *,
        remote_op: RemoteOperation,
        needs_lock: bool = True,
        fullcmd: bool = False,
        merge_err: bool = True,
        stdin: str | None = None,
        environment: dict[str, str] | None = None,
        remote_url: str | None = None,
    ):
        """Execute command and caches its output."""
        self.ensure_lock_session_recovered()
        if needs_lock:
            if not self.lock.is_locked:
                msg = "Repository operation without lock held!"
                raise RuntimeError(msg)
            if self.component:
                self.ensure_config_updated()
        remote_target = None
        effective_remote_url = remote_url
        if remote_url:
            remote_target = self.validate_remote_url(remote_url)
        elif remote_op == "pull":
            remote_target = self.validate_pull_url()
            if self.component is not None:
                effective_remote_url = self.component.repo
        elif remote_op == "push":
            remote_target = self.validate_push_url()
            if self.component is not None:
                effective_remote_url = self.component.push or self.component.repo
        args, environment = self.prepare_remote_command(
            args, environment, remote_target
        )
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
        except RepositoryCommandError as error:
            if not is_status and not self.local:
                self.log_status(error)
            if effective_remote_url and remote_target is not None:
                self.handle_remote_command_error(
                    error,
                    effective_remote_url,
                    remote_target,
                    environment,
                )
            raise
        return self.last_output

    def log_status(self, error: str | RepositoryError) -> None:
        with suppress(RepositoryCommandError):
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
        return self.execute(
            self._cmd_last_revision,
            remote_op="none",
            needs_lock=False,
            merge_err=False,
        )

    @cached_property
    def last_remote_revision(self):
        """Return last remote revision."""
        return self.execute(
            self._cmd_last_remote_revision,
            remote_op="none",
            needs_lock=False,
            merge_err=False,
        )

    def _clone(self, source: str, target: str, branch: str) -> None:
        """Clone repository."""
        raise NotImplementedError

    def _clone_resolved(
        self,
        source: str,
        target: str,
        branch: str,
        remote_target: ResolvedRepositoryURL | None,
    ) -> None:
        """Clone with the resolved target available to capable backends."""
        self._clone(source, target, branch)

    @classmethod
    def validate_remote_url(cls, url: str) -> ResolvedRepositoryURL | None:
        """Revalidate a remote URL before using it."""
        from django.core.exceptions import ValidationError  # ruff: ignore[import-outside-top-level, unsorted-imports]

        from weblate.utils.validators import resolve_repo_url  # ruff: ignore[import-outside-top-level]

        try:
            target = resolve_repo_url(
                url,
                ssh_destination_resolver=cls.get_ssh_destination_resolver(),
                proxy_url=get_environment_proxy(url),
            )
        except ValidationError as error:
            validation_error = error.error_list[0]
            error_codes: dict[
                str | None, tuple[RepositoryErrorCode, tuple[str, ...]]
            ] = {
                "invalid": ("repository_url_invalid", ()),
                "private_target": ("repository_url_private_target", ()),
                "repository_host_not_allowed": (
                    "repository_url_host_not_allowed",
                    ("hostname",),
                ),
                "repository_scheme_not_allowed": (
                    "repository_url_scheme_not_allowed",
                    ("scheme",),
                ),
                "ssh_destination_unresolved": (
                    "repository_ssh_destination_unresolved",
                    (),
                ),
                "ssh_destination_unresolved_with_error": (
                    "repository_ssh_destination_unresolved_with_error",
                    ("error",),
                ),
                "url_parse_failed": ("repository_url_parse_failed", ("error",)),
                "url_parse_invalid": ("repository_url_parse_invalid", ()),
                "url_unresolved": ("repository_url_unresolved", ()),
                "url_unresolved_with_error": (
                    "repository_url_unresolved_with_error",
                    ("error",),
                ),
            }
            code, param_names = error_codes.get(
                validation_error.code, ("repository_url_invalid", ())
            )
            validation_params = validation_error.params or {}
            params = {
                name: str(validation_params[name])
                for name in param_names
                if name in validation_params
            }
            raise RepositoryValidationError(
                0,
                code,
                params=params,
            ) from error
        if (
            target is not None
            and target.requires_pinning
            and target.scheme not in cls.pinned_remote_schemes
        ):
            raise RepositoryValidationError(
                0,
                "repository_url_backend_unsupported",
            )
        return target

    @classmethod
    def get_ssh_destination_resolver(
        cls,
    ) -> Callable[[str, str | None, int | None], tuple[str, int]] | None:
        """Return an effective SSH destination resolver when supported."""
        return None

    def validate_pull_url(self, url: str | None = None) -> ResolvedRepositoryURL | None:
        """Validate the pull URL in the current runtime context."""
        if url is None and self.component is not None:
            url = self.component.repo
        if url:
            return self.validate_remote_url(url)
        return None

    def validate_push_url(self, url: str | None = None) -> ResolvedRepositoryURL | None:
        """Validate the push URL in the current runtime context."""
        if url is None and self.component is not None:
            url = self.component.push or self.component.repo
        if url:
            return self.validate_remote_url(url)
        return None

    @classmethod
    # ruff: ignore[unused-class-method-argument]
    def prepare_remote_command(
        cls,
        args: list[str],
        environment: dict[str, str] | None,
        target: ResolvedRepositoryURL | None,
    ) -> tuple[list[str], dict[str, str] | None]:
        """Bind a remote command to the addresses approved during validation."""
        return args, environment

    @classmethod
    def handle_remote_command_error(
        cls,
        _error: RepositoryCommandError,
        _remote_url: str,
        _target: ResolvedRepositoryURL,
        _environment: dict[str, str] | None,
    ) -> None:
        """Convert backend-specific failures into structured repository errors."""
        return

    def validate_remote_compatibility(self, pull_url: str, branch: str) -> None:
        """Validate that a remote branch is compatible with this checkout."""
        raise NotImplementedError

    def clone_from(self, source: str) -> None:
        """Clone repository into current one."""
        target = self.validate_pull_url(source)
        self._clone_resolved(source, self.path, self.branch, target)

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
        return self.execute(self._cmd_status, remote_op="none", needs_lock=False)

    def push(self, branch: str) -> None:
        """Push given branch to remote repository."""
        raise NotImplementedError

    def unshallow(self) -> None:
        """Unshallow working copy."""
        return

    def reset(self) -> None:
        """Reset working copy to match remote branch."""
        raise NotImplementedError

    def reset_to_revision(self, revision: str) -> None:
        """Reset working copy to a local revision."""
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

    def _get_revision_info(self, revision: str) -> RawCommitInfo:
        """Return dictionary with detailed revision information."""
        raise NotImplementedError

    def get_revision_info(self, revision: str) -> CommitInfo:
        """Return dictionary with detailed revision information."""
        key = f"rev-info-{self.get_identifier()}-{revision}"
        result: RawCommitInfo | None = cache.get(key)
        if not result:
            result = self._get_revision_info(revision)
            # Keep the cache for one day
            cache.set(key, result, 86400)

        commit_info: CommitInfo = {
            "revision": result["revision"],
            "shortrevision": result["shortrevision"],
            "author": result["author"],
            "authordate": parse_commit_date(result["authordate"]),
            "commit": result["commit"],
            "commitdate": parse_commit_date(result["commitdate"]),
            "message": result["message"],
            "summary": result["summary"],
        }
        if "author_name" in result:
            commit_info["author_name"] = result["author_name"]
        if "author_email" in result:
            commit_info["author_email"] = result["author_email"]
        if "commit_name" in result:
            commit_info["commit_name"] = result["commit_name"]
        if "commit_email" in result:
            commit_info["commit_email"] = result["commit_email"]
        if "committerdate" in result:
            commit_info["committerdate"] = parse_commit_date(result["committerdate"])
        if "date" in result:
            commit_info["date"] = parse_commit_date(result["date"])

        return commit_info

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

    def remove(
        self,
        files: list[str],
        message: str,
        author: str | None = None,
        extra_commit_files: list[str] | None = None,
    ) -> None:
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
        with suppress(RepositoryCommandError):
            self.merge(abort=True)
        with suppress(RepositoryCommandError):
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
            [*self._cmd_list_changed_files, refspec],
            remote_op="none",
            needs_lock=False,
            merge_err=False,
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
