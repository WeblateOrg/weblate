# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from collections import defaultdict
from itertools import chain
from typing import TYPE_CHECKING, cast

from django.utils.translation import gettext_lazy

from weblate.addons.base import BaseAddon
from weblate.addons.events import AddonEvent
from weblate.addons.forms import GitSquashForm
from weblate.utils.errors import report_error
from weblate.vcs.base import RepositoryError
from weblate.vcs.models import VCS_REGISTRY

if TYPE_CHECKING:
    from weblate.trans.models import Component
    from weblate.vcs.git import GitRepository


class GitSquashAddon(BaseAddon):
    name = "weblate.git.squash"
    verbose = gettext_lazy("Squash Git commits")
    description = gettext_lazy("Squash Git commits prior to pushing changes.")
    settings_form = GitSquashForm
    compat = {
        "vcs": VCS_REGISTRY.git_based,
    }
    events: set[AddonEvent] = {
        AddonEvent.EVENT_POST_COMMIT,
    }
    icon = "compress.svg"
    repo_scope = True

    def squash_repo(
        self,
        component: Component,
        repository: GitRepository,
        remote: str,
        author: str | None = None,
    ) -> None:
        message = self.get_squash_commit_message(repository, "%B", remote)
        repository.execute(["reset", "--mixed", remote])
        # Can happen for added and removed translation
        component.commit_files(
            author=author, message=message, signals=False, skip_push=True
        )

    def squash_all(self, component: Component, repository: GitRepository) -> None:
        self.squash_repo(component, repository, repository.get_remote_branch_name())

    def get_filenames(self, component: Component) -> dict[str, list[str]]:
        languages: dict[str, list[str]] = defaultdict(list)
        for origin in [component, *list(component.linked_childs)]:
            for translation in origin.translation_set.prefetch_related("language"):
                code = translation.language.code
                if not translation.filename:
                    continue
                languages[code].extend(translation.filenames)
        return languages

    def get_git_commit_messages(self, repository, log_format, remote, filenames):
        command = [
            "log",
            f"--format={log_format}",
            f"{remote}..HEAD",
        ]
        if filenames:
            command += ["--", *filenames]

        return repository.execute(command)

    def get_squash_commit_message(
        self,
        repository: GitRepository,
        log_format: str,
        remote: str,
        filenames: list[str] | None = None,
    ) -> str:
        commit_message = self.instance.configuration.get("commit_message")

        if self.instance.configuration.get("append_trailers", True):
            command = [
                "log",
                "--format=%(trailers)%nCo-authored-by: %an <%ae>",
                f"{remote}..HEAD",
            ]
            if filenames:
                command += ["--", *filenames]

            trailer_lines = set()
            change_id_line = None
            for trailer in repository.execute(command).split("\n"):
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

        repository.execute(["reset", "--mixed", remote])

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

        repository.execute(["reset", "--mixed", remote])

        for filename, message in messages.items():
            if not message:
                continue
            component.commit_files(
                message=message, files=[filename], signals=False, skip_push=True
            )

    def squash_author(self, component: Component, repository: GitRepository) -> None:
        remote = repository.get_remote_branch_name()
        # Get list of pending commits with authors
        commits: list[tuple[str, str]] = [
            x.split(None, 1)
            for x in reversed(
                repository.execute(
                    ["log", "--no-merges", "--format=%H %aE", f"{remote}..HEAD"]
                ).splitlines()
            )
        ]
        gpg_sign = repository.get_gpg_sign_args()

        tmp = "weblate-squash-tmp"
        repository.delete_branch(tmp)
        try:
            # Create local branch for upstream
            repository.execute(["branch", tmp, remote])
            # Checkout upstream branch
            repository.execute(["checkout", tmp])
            while commits:
                commit, author = commits.pop(0)
                # Remember current revision for final squash
                base = repository.get_last_revision()
                # Cherry pick current commit (this should work
                # unless something is messed up)
                repository.execute(
                    ["cherry-pick", commit, *gpg_sign],
                    environment={"WEBLATE_MERGE_SKIP": "1"},
                )
                handled = []
                # Pick other commits by same author
                for i, other in enumerate(commits):
                    if other[1] != author:
                        continue
                    try:
                        repository.execute(
                            ["cherry-pick", other[0], *gpg_sign],
                            environment={"WEBLATE_MERGE_SKIP": "1"},
                        )
                        handled.append(i)
                    except RepositoryError:
                        # If fails, continue to another author, we will
                        # pick this commit later (it depends on some other)
                        repository.execute(["cherry-pick", "--abort"])
                        break
                # Remove processed commits from list
                for i in reversed(handled):
                    del commits[i]
                # Squash all current commits from one author
                self.squash_repo(component, repository, base, author)

            # Update working copy with squashed commits
            repository.execute(["checkout", repository.branch])
            repository.execute(["reset", "--hard", tmp])
            repository.delete_branch(tmp)

        except Exception:
            report_error("Failed squash", project=component.project)
            # Revert to original branch without any changes
            repository.execute(["reset", "--hard"])
            repository.execute(["checkout", repository.branch])
            repository.delete_branch(tmp)

    def post_commit(self, component: Component, store_hash: bool) -> None:
        # Operate on parent
        if component.linked_component:
            component = component.linked_component

        repository = cast("GitRepository", component.repository)
        branch_updated = False
        with repository.lock:
            # Ensure repository is rebased on current remote prior to squash, otherwise
            # we might be squashing upstream changes as well due to reset.
            if component.repo_needs_merge():
                try:
                    branch_updated = component.update_branch(
                        method="rebase", skip_push=True
                    )
                except RepositoryError:
                    return
            if not repository.needs_push():
                return
            match self.instance.configuration["squash"]:
                case "all":
                    self.squash_all(component, repository)
                case "language":
                    self.squash_language(component, repository)
                case "file":
                    self.squash_file(component, repository)
                case "author":
                    self.squash_author(component, repository)
                case _:
                    msg = f"Unsupported squash style: {self.instance.configuration['squash']}"
                    raise ValueError(msg)
            # Commit any left files, those were most likely generated
            # by addon and do not exactly match patterns above
            component.commit_files(
                template=component.addon_message,
                extra_context={"addon_name": self.verbose},
                signals=False,
                skip_push=True,
            )
            # Parse translation files to process any updates fetched by update_branch
            if branch_updated:
                component.create_translations()
