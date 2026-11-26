# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Disposable worktrees for Git branch updates."""

from __future__ import annotations

import logging
import os
from contextlib import suppress
from dataclasses import asdict, dataclass
from json import dumps, loads
from typing import TYPE_CHECKING, Literal

from weblate.utils.files import REPO_TEMP_DIRNAME, remove_tree
from weblate.vcs.base import (
    RepositoryCommandError,
    RepositoryError,
    RepositoryInternalError,
    RepositoryRecoveryEvent,
    RepositoryWorktreeError,
    is_valid_revision_hash,
)

if TYPE_CHECKING:
    from weblate.vcs.git import GitRepository


BRANCH_UPDATE_DIR = "branch-update"


@dataclass(frozen=True, slots=True)
class Publication:
    branch: str
    result: str


class GitUpdateWorktree:
    def __init__(self, repository: GitRepository) -> None:
        self.repository = repository
        self.directory = (
            repository.get_git_file_path(REPO_TEMP_DIRNAME).absolute()
            / BRANCH_UPDATE_DIR
        )
        self.checkout = self.directory / "checkout"
        self.marker = self.directory / "publication.json"
        self.marker_temp = self.directory / "publication.tmp"

    @staticmethod
    def recovery_error() -> RepositoryInternalError:
        return RepositoryInternalError(
            1, "repository_recovery_failed", params={"operation": "branch update"}
        )

    def validate_directory(self) -> None:
        # The worktree also has a registration in the main Git directory.
        # Validate the owned path before asking Git to remove that registration.
        if any(
            path.is_symlink()
            for path in (
                self.directory.parent.parent,
                self.directory.parent,
                self.directory,
                self.checkout,
                self.marker,
                self.marker_temp,
            )
        ):
            raise self.recovery_error()

    def execute(self, args: list[str]) -> str:
        return self.repository.execute(
            ["-C", str(self.checkout), "-c", "submodule.recurse=false", *args],
            remote_op="none",
            environment={
                "GIT_DIR": str(self.checkout / ".git"),
                "GIT_WORK_TREE": str(self.checkout),
                # Used by the gettext merge driver for rebases.
                **({"WEBLATE_MERGE_SKIP": "1"} if args[0] == "rebase" else {}),
            },
            log_status=False,
        )

    def remove(self) -> None:
        if not self.directory.exists() and not self.directory.is_symlink():
            return
        try:
            self.validate_directory()
            if not self.marker.exists():
                self.remove_checkout()
                self.marker_temp.unlink(missing_ok=True)
                self.directory.rmdir()
        except (OSError, RepositoryError) as error:
            self.repository.log(
                f"Could not remove branch update worktree: {error}",
                level=logging.WARNING,
            )

    def remove_checkout(self) -> None:
        registration = self.repository.execute(
            ["worktree", "list", "--porcelain", "-z"],
            remote_op="none",
            raw=True,
            merge_err=False,
        )
        path = self.checkout.resolve()
        if b"worktree " + os.fsencode(path) in registration.split(b"\0"):
            # An interrupted worktree add can leave its initialization lock.
            self.repository.execute(
                ["worktree", "remove", "--force", "--force", str(path)],
                remote_op="none",
            )
        elif path.is_dir():
            # Git can be interrupted before registering the new directory.
            remove_tree(path)

    def record_publication(self, publication: Publication) -> None:
        with self.marker_temp.open("x", encoding="utf-8") as handle:
            handle.write(dumps(asdict(publication)))
            handle.flush()
            os.fsync(handle.fileno())
        self.marker_temp.replace(self.marker)

    def complete_publication(self) -> None:
        self.validate_directory()
        try:
            self.marker.unlink(missing_ok=True)
        except OSError as error:
            raise self.recovery_error() from error

    def tracked_changes(self) -> list[bytes]:
        status = self.repository.execute(
            [
                "--no-optional-locks",
                "status",
                "--porcelain=v1",
                "-z",
                "--no-renames",
                "--untracked-files=no",
                "--ignore-submodules=all",
            ],
            remote_op="none",
            raw=True,
            merge_err=False,
        )
        if status:
            return [item[3:] for item in status.rstrip(b"\0").split(b"\0")]
        # Inspect the parent index without requiring nested checkouts to move.
        staged = self.repository.execute(
            ["diff", "--cached", "--name-only", "-z", "--ignore-submodules=none"],
            remote_op="none",
            raw=True,
            merge_err=False,
        )
        return staged.rstrip(b"\0").split(b"\0") if staged else []

    def untracked_paths(self) -> bytes:
        return self.repository.execute(
            ["ls-files", "--others", "-z"],
            remote_op="none",
            raw=True,
            merge_err=False,
        )

    def check_live_checkout(self, branch: str, revision: str) -> None:
        if (
            self.repository.get_current_branch() != branch
            or self.repository.get_last_revision().strip() != revision
        ):
            raise RepositoryInternalError(1, "repository_branch_update_changed")
        if changes := self.tracked_changes():
            paths = ", ".join(
                path.decode(errors="backslashreplace") for path in changes
            )
            raise RepositoryInternalError(
                1, "repository_branch_update_dirty", params={"paths": paths}
            )

    def run(
        self,
        *,
        operation: Literal["merge", "rebase"],
        arguments: list[str],
        upstream_first: bool,
    ) -> None:
        repository = self.repository
        branch = repository.validate_branch_name(repository.get_local_branch_name())
        original = repository.get_last_revision().strip()
        self.check_live_checkout(branch, original)
        upstream = repository.execute(
            [
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"refs/remotes/{repository.get_remote_branch_name()}^{{commit}}",
            ],
            remote_op="none",
            merge_err=False,
        ).strip()
        start, other = (upstream, original) if upstream_first else (original, upstream)
        if not (is_valid_revision_hash(start) and is_valid_revision_hash(other)):
            raise RepositoryInternalError(1, "repository_branch_update_changed")
        self.validate_directory()
        try:
            self.directory.parent.mkdir(exist_ok=True)
            self.directory.mkdir()
        except OSError as error:
            raise RepositoryError(1, str(error)) from error
        try:
            result = self.calculate_result(start, [operation, *arguments, other])
            if result == original:
                return
            # The detached worktree keeps the result reachable during checkout.
            self.publish(
                Publication(branch, result),
                original=original,
                merge=operation == "merge",
            )
            self.complete_publication()
        except OSError as error:
            raise RepositoryError(1, str(error)) from error
        finally:
            repository.clean_revision_cache()
            self.remove()

    def calculate_result(self, start: str, args: list[str]) -> str:
        self.repository.execute(
            [
                "-c",
                "submodule.recurse=false",
                "worktree",
                "add",
                "--no-checkout",
                "--detach",
                str(self.checkout),
                start,
            ],
            remote_op="none",
        )
        self.execute(["reset", "--hard", start])
        try:
            self.execute(args)
        except RepositoryCommandError as error:
            try:
                status = self.execute(["--no-optional-locks", "status"])
            except RepositoryError as status_error:
                raise RepositoryWorktreeError(
                    error, "", status_error.get_message()
                ) from error
            raise RepositoryWorktreeError(error, status) from error
        result = self.execute(["rev-parse", "--verify", "HEAD"]).strip()
        if not is_valid_revision_hash(result):
            raise self.recovery_error()
        return result

    def publish(self, publication: Publication, *, original: str, merge: bool) -> None:
        if merge:
            self.repository.execute(
                [
                    "merge-base",
                    "--is-ancestor",
                    original,
                    publication.result,
                ],
                remote_op="none",
            )
        self.check_live_checkout(publication.branch, original)
        untracked = self.untracked_paths()
        self.record_publication(publication)
        try:
            self.repository.execute(
                [
                    "checkout",
                    "--no-overwrite-ignore",
                    "--no-recurse-submodules",
                    "-B",
                    publication.branch,
                    publication.result,
                ],
                remote_op="none",
            )
        except RepositoryCommandError:
            # Ordinary checkout refusals must not block later operations. Only
            # the running process can verify that nothing changed on disk.
            with suppress(RepositoryError):
                self.check_live_checkout(publication.branch, original)
                if self.untracked_paths() == untracked:
                    self.complete_publication()
            raise
        self.check_live_checkout(publication.branch, publication.result)

    def read_publication(self) -> Publication:
        try:
            fields = loads(self.marker.read_bytes())
            record = Publication(fields["branch"], fields["result"])
        except (KeyError, OSError, TypeError, ValueError) as error:
            raise self.recovery_error() from error
        if (
            not isinstance(record.branch, str)
            or not isinstance(record.result, str)
            or not is_valid_revision_hash(record.result)
        ):
            raise self.recovery_error()
        return record

    def recover_publication(self) -> RepositoryRecoveryEvent | None:
        self.validate_directory()
        if not self.marker.exists():
            return None
        publication = self.read_publication()
        repository = self.repository
        try:
            self.check_live_checkout(publication.branch, publication.result)
        except RepositoryError as error:
            raise self.recovery_error() from error
        repository.clean_revision_cache()
        if (
            repository.component is not None and not repository.component._state.adding  # ruff: ignore[private-member-access]
        ):
            repository.component.store_local_revision()
            repository.component.drop_template_store_cache()
        self.complete_publication()
        return RepositoryRecoveryEvent(
            operation="branch-update-publication",
            details={"branch": publication.branch, "outcome": "completed"},
        )
