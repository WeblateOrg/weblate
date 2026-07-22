# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from collections import defaultdict
from itertools import chain
from typing import TYPE_CHECKING, ClassVar, TypedDict, cast

from django.utils.translation import gettext_lazy

from weblate.addons.base import BaseAddon
from weblate.addons.events import (
    AddonActivityLogReason,
    AddonEvent,
    AddonEventOutcome,
)
from weblate.addons.forms import GitSquashForm
from weblate.utils.errors import report_error
from weblate.vcs.base import RepositoryError
from weblate.vcs.models import VCS_REGISTRY

if TYPE_CHECKING:
    from weblate.addons.base import CompatDict
    from weblate.trans.models import Component
    from weblate.vcs.git import GitRepository


class GitSquashAddonStoredConfiguration(TypedDict, total=False):
    squash: str
    append_trailers: bool
    commit_message: str


class GitSquashAddonConfiguration(TypedDict):
    squash: str
    append_trailers: bool
    commit_message: str


class GitSquashAddon(
    BaseAddon[GitSquashAddonStoredConfiguration, GitSquashAddonConfiguration]
):
    name = "weblate.git.squash"
    verbose = gettext_lazy("Squash Git commits")
    description = gettext_lazy("Squash Git commits prior to pushing changes.")
    settings_form = GitSquashForm
    compat: ClassVar[CompatDict] = {
        "vcs": VCS_REGISTRY.git_based,
    }
    events: ClassVar[set[AddonEvent]] = {
        AddonEvent.EVENT_POST_COMMIT,
    }
    icon = "compress.svg"
    repo_scope = True

    @staticmethod
    def ensure_repository_clean(
        component: Component, repository: GitRepository
    ) -> None:
        try:
            repository.ensure_no_interrupted_operation()
        except RepositoryError as error:
            component.add_alert(
                "RepositoryOperationFailure", error=component.error_text(error)
            )
            raise

    def squash_repo(
        self,
        component: Component,
        repository: GitRepository,
        remote: str,
        author: str | None = None,
    ) -> None:
        self.ensure_repository_clean(component, repository)
        message = self.get_squash_commit_message(repository, "%B", remote)
        repository.execute(["reset", "--mixed", remote], remote_op="none")
        self.ensure_repository_clean(component, repository)
        # Can happen for added and removed translation
        component.commit_files(
            author=author, message=message, signals=False, skip_push=True
        )

    def squash_all(self, component: Component, repository: GitRepository) -> None:
        self.squash_repo(component, repository, repository.get_remote_branch_name())

    def get_filenames(self, component: Component) -> dict[str, list[str]]:
        languages: dict[str, list[str]] = defaultdict(list)
        for origin in [component, *list(component.linked_children)]:
            for translation in origin.translation_set.prefetch_related("language"):
                code = translation.language.code
                if not translation.filename:
                    continue
                languages[code].extend(translation.filenames)
        return languages

    def get_git_commit_messages(
        self,
        repository: GitRepository,
        log_format: str,
        remote: str,
        filenames: list[str] | None,
    ) -> str:
        command = [
            "log",
            f"--format={log_format}",
            f"{remote}..HEAD",
        ]
        if filenames:
            command += ["--", *filenames]

        return repository.execute(command, remote_op="none")

    def get_squash_commit_message(
        self,
        repository: GitRepository,
        log_format: str,
        remote: str,
        filenames: list[str] | None = None,
    ) -> str:
        configuration = self.configuration
        commit_message = configuration["commit_message"]

        if configuration["append_trailers"]:
            command = [
                "log",
                "--format=%(trailers)%nCo-authored-by: %an <%ae>",
                f"{remote}..HEAD",
            ]
            if filenames:
                command += ["--", *filenames]

            trailer_lines = set()
            change_id_line = None
            for trailer in repository.execute(command, remote_op="none").split("\n"):
                # Skip blank lines
                if not trailer.strip():
                    continue

                # Pick only last Change-Id, there suppose to be only one in the
                # commit (used by Gerrit)
                if trailer.startswith("Change-Id:"):
                    change_id_line = trailer
                    continue

                trailer_lines.add(trailer)

            if change_id_line is not None:
                trailer_lines.add(change_id_line)

            if commit_message:
                # Predefined commit message
                body = [commit_message]
            else:
                # Extract commit messages from the log
                body = [
                    line
                    for line in self.get_git_commit_messages(
                        repository, log_format, remote, filenames
                    ).split("\n")
                    if line not in trailer_lines
                ]

            commit_message = "\n".join(
                chain(
                    # Body
                    body,
                    # Blank line
                    [""],
                    # Trailers
                    sorted(trailer_lines),
                )
            ).strip("\n")
        elif not commit_message:
            commit_message = self.get_git_commit_messages(
                repository, log_format, remote, filenames
            )

        return commit_message

    def squash_language(self, component: Component, repository: GitRepository) -> None:
        remote = repository.get_remote_branch_name()
        languages = self.get_filenames(component)

        messages = {}
        for code, filenames in languages.items():
            if not filenames:
                continue
            messages[code] = self.get_squash_commit_message(
                repository, "%B", remote, filenames
            )

        repository.execute(["reset", "--mixed", remote], remote_op="none")

        for code, message in messages.items():
            if not message:
                continue
            component.commit_files(
                message=message, files=languages[code], signals=False, skip_push=True
            )

    def squash_file(self, component: Component, repository: GitRepository) -> None:
        remote = repository.get_remote_branch_name()
        languages = self.get_filenames(component)

        messages = {}
        for filenames in languages.values():
            for filename in filenames:
                messages[filename] = self.get_squash_commit_message(
                    repository, "%B", remote, [filename]
                )

        repository.execute(["reset", "--mixed", remote], remote_op="none")

        for filename, message in messages.items():
            if not message:
                continue
            component.commit_files(
                message=message, files=[filename], signals=False, skip_push=True
            )

    def get_commit_language(
        self, repository: GitRepository, commit: str, filename_languages: dict[str, str]
    ) -> str:
        filenames = repository.execute(
            ["diff-tree", "--no-commit-id", "--name-only", "-r", commit],
            remote_op="none",
        ).splitlines()
        codes = set()
        for filename in filenames:
            try:
                codes.add(filename_languages[filename])
            except KeyError:
                # The commit touches a non-translation file, so it can not be
                # attributed to a single language and stays in its own group.
                return commit
        if len(codes) == 1:
            return codes.pop()
        # Empty commit or a commit spanning multiple languages is kept separate.
        return commit

    def squash_author_commits(
        self,
        component: Component,
        repository: GitRepository,
        commits: list[tuple[str, str, tuple[str, str]]],
        remote: str,
        tmp: str,
        gpg_sign: list[str],
    ) -> None:
        # Create local branch for upstream
        repository.execute(["branch", tmp, remote], remote_op="none")
        # Checkout upstream branch
        repository.execute(["checkout", tmp], remote_op="none")
        while commits:
            commit, author, group_key = commits.pop(0)
            # Remember current revision for final squash
            base = repository.get_last_revision()
            # Cherry pick current commit (this should work
            # unless something is messed up)
            try:
                repository.execute(
                    ["cherry-pick", "--empty=drop", commit, *gpg_sign],
                    remote_op="none",
                    environment={"WEBLATE_MERGE_SKIP": "1"},
                )
            except RepositoryError:
                if repository.has_git_file("CHERRY_PICK_HEAD"):
                    repository.execute(["cherry-pick", "--abort"], remote_op="none")
                raise
            handled = []
            # Pick other commits matching the requested squash grouping key.
            for i, other in enumerate(commits):
                if other[2] != group_key:
                    continue
                try:
                    repository.execute(
                        ["cherry-pick", "--empty=drop", other[0], *gpg_sign],
                        remote_op="none",
                        environment={"WEBLATE_MERGE_SKIP": "1"},
                    )
                    handled.append(i)
                except RepositoryError:
                    # If fails, continue to another author, we will
                    # pick this commit later (it depends on some other)
                    if repository.has_git_file("CHERRY_PICK_HEAD"):
                        repository.execute(["cherry-pick", "--abort"], remote_op="none")
                    break
            # Remove processed commits from list
            for i in reversed(handled):
                del commits[i]
            # Squash all current commits from one author, keeping the author metadata.
            self.squash_repo(component, repository, base, author)

        # Update working copy with squashed commits
        repository.execute(["checkout", repository.branch], remote_op="none")
        repository.execute(["reset", "--hard", tmp], remote_op="none")
        repository.delete_branch(tmp)

    def squash_author(
        self,
        component: Component,
        repository: GitRepository,
        *,
        include_language: bool = False,
    ) -> None:
        remote = repository.get_remote_branch_name()
        # Build a filename -> language code lookup once, so each commit can be
        # attributed in O(changed files) instead of scanning every language.
        filename_languages: dict[str, str] = {}
        if include_language:
            for code, filenames in self.get_filenames(component).items():
                for filename in filenames:
                    filename_languages[filename] = code
        # Get list of pending commits with authors
        commits: list[tuple[str, str, tuple[str, str]]] = []
        log_lines = reversed(
            repository.execute(
                ["log", "--no-merges", "--format=%H %aE", f"{remote}..HEAD"],
                remote_op="none",
            ).splitlines()
        )
        for line in log_lines:
            commit, author = line.split(None, 1)
            if include_language:
                language = self.get_commit_language(
                    repository, commit, filename_languages
                )
            else:
                language = ""
            commits.append((commit, author, (author, language)))
        gpg_sign = repository.get_gpg_sign_args()

        tmp = "weblate-squash-tmp"
        repository.delete_branch(tmp)
        try:
            self.squash_author_commits(
                component, repository, commits, remote, tmp, gpg_sign
            )
        except RepositoryError:
            if repository.get_interrupted_operation() is not None:
                raise
            report_error("Failed squash", project=component.project)
            # Revert to original branch without any changes
            repository.execute(["reset", "--hard"], remote_op="none")
            repository.execute(["checkout", repository.branch], remote_op="none")
            repository.delete_branch(tmp)
        except Exception:
            report_error("Failed squash", project=component.project)
            # Revert to original branch without any changes
            repository.execute(["reset", "--hard"], remote_op="none")
            repository.execute(["checkout", repository.branch], remote_op="none")
            repository.delete_branch(tmp)

    def post_commit(
        self, component: Component, store_hash: bool, activity_log_id: int | None = None
    ) -> AddonEventOutcome | None:
        # Operate on parent
        if component.linked_component:
            component = component.linked_component

        repository = cast("GitRepository", component.repository)
        branch_updated = False
        with repository.lock:
            self.ensure_repository_clean(component, repository)
            # Ensure repository is rebased on current remote prior to squash, otherwise
            # we might be squashing upstream changes as well due to reset.
            if component.repo_needs_merge():
                try:
                    branch_updated = component.update_branch(
                        method="rebase",
                        skip_push=True,
                        parse_after_update=True,
                    )
                except RepositoryError:
                    return AddonEventOutcome.error()
            if not repository.needs_push():
                return AddonEventOutcome.skipped(
                    AddonActivityLogReason.NO_OUTGOING_COMMITS
                )
            squash = self.configuration["squash"]
            match squash:
                case "all":
                    self.squash_all(component, repository)
                case "language":
                    self.squash_language(component, repository)
                case "file":
                    self.squash_file(component, repository)
                case "author":
                    self.squash_author(component, repository)
                case "author-language":
                    self.squash_author(component, repository, include_language=True)
                case _:
                    msg = f"Unsupported squash style: {squash}"
                    raise ValueError(msg)
            # Commit any left files, those were most likely generated
            # by addon and do not exactly match patterns above
            component.commit_files(
                template=component.effective_addon_message,
                extra_context={"addon_name": self.verbose},
                signals=False,
                skip_push=True,
            )
            # Parse translation files to process any updates fetched by update_branch
            if branch_updated:
                component.create_translations()
        return None

    def normalize_configuration(
        self, configuration: GitSquashAddonStoredConfiguration
    ) -> GitSquashAddonConfiguration:
        return {
            "squash": configuration.get("squash", "all"),
            "append_trailers": configuration.get("append_trailers", True),
            "commit_message": configuration.get("commit_message", ""),
        }
