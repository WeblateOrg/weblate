#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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

from collections import defaultdict
from itertools import chain

from django.utils.translation import gettext_lazy as _

from weblate.addons.base import BaseAddon
from weblate.addons.events import EVENT_POST_COMMIT
from weblate.addons.forms import GitSquashForm
from weblate.utils.errors import report_error
from weblate.vcs.base import RepositoryException


class GitSquashAddon(BaseAddon):
    name = "weblate.git.squash"
    verbose = _("Squash Git commits")
    description = _("Squash Git commits prior to pushing changes.")
    settings_form = GitSquashForm
    compat = {
        "vcs": {
            "git",
            "gerrit",
            "subversion",
            "github",
            "pagure",
            "gitlab",
            "git-force-push",
        }
    }
    events = (EVENT_POST_COMMIT,)
    icon = "compress.svg"
    repo_scope = True

    def squash_all(self, component, repository, base=None, author=None):
        remote = base if base else repository.get_remote_branch_name()
        message = self.get_squash_commit_message(repository, "%B", remote)
        repository.execute(["reset", "--mixed", remote])
        # Can happen for added and removed translation
        if repository.needs_commit():
            repository.commit(message, author)

    def get_filenames(self, component):
        languages = defaultdict(list)
        for origin in [component] + list(component.linked_childs):
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
            command += ["--"] + filenames

        return repository.execute(command)

    def get_squash_commit_message(self, repository, log_format, remote, filenames=None):
        commit_message = self.instance.configuration.get("commit_message")

        if self.instance.configuration.get("append_trailers", True):
            command = [
                "log",
                "--format=%(trailers)%nCo-authored-by: %an <%ae>",
                f"{remote}..HEAD",
            ]
            if filenames:
                command += ["--"] + filenames

            trailer_lines = {
                trailer
                for trailer in repository.execute(command).split("\n")
                if trailer.strip()
            }

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

    def squash_language(self, component, repository):
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
            repository.commit(message, files=languages[code])

    def squash_file(self, component, repository):
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
            repository.commit(message, files=[filename])

    def squash_author(self, component, repository):
        remote = repository.get_remote_branch_name()
        # Get list of pending commits with authors
        commits = [
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
                repository.execute(["cherry-pick", commit] + gpg_sign)
                handled = []
                # Pick other commits by same author
                for i, other in enumerate(commits):
                    if other[1] != author:
                        continue
                    try:
                        repository.execute(["cherry-pick", other[0]] + gpg_sign)
                        handled.append(i)
                    except RepositoryException:
                        # If fails, continue to another author, we will
                        # pick this commit later (it depends on some other)
                        repository.execute(["cherry-pick", "--abort"])
                        break
                # Remove processed commits from list
                for i in reversed(handled):
                    del commits[i]
                # Squash all current commits from one author
                self.squash_all(component, repository, base, author)

            # Update working copy with squashed commits
            repository.execute(["checkout", repository.branch])
            repository.execute(["reset", "--hard", tmp])
            repository.delete_branch(tmp)

        except RepositoryException:
            report_error(cause="Failed squash")
            # Revert to original branch without any changes
            repository.execute(["reset", "--hard"])
            repository.execute(["checkout", repository.branch])
            repository.delete_branch(tmp)

    def post_commit(self, component):
        repository = component.repository
        with repository.lock:
            # Ensure repository is rebased on current remote prior to squash, otherwise
            # we might be squashing upstream changes as well due to reset.
            if component.repo_needs_merge() and not component.update_branch(
                method="rebase", skip_push=True
            ):
                return
            if not repository.needs_push():
                return
            method = getattr(
                self, "squash_{}".format(self.instance.configuration["squash"])
            )
            method(component, repository)
            # Commit any left files, those were most likely generated
            # by addon and do not exactly match patterns above
            component.commit_files(
                template=component.addon_message,
                extra_context={"addon_name": self.verbose},
                signals=False,
                skip_push=True,
            )
