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
"""Mercurial version control system abstraction for Weblate needs."""

import os
import os.path
import re
from configparser import RawConfigParser
from datetime import datetime
from typing import List, Optional

from weblate.vcs.base import Repository, RepositoryException
from weblate.vcs.ssh import SSH_WRAPPER


class HgRepository(Repository):
    """Repository implementation for Mercurial."""

    _cmd = "hg"
    _cmd_last_revision = ["log", "--limit", "1", "--template", "{node}"]
    _cmd_last_remote_revision = [
        "log",
        "--limit",
        "1",
        "--template",
        "{node}",
        "--branch",
        ".",
    ]
    _cmd_list_changed_files = ["status", "--rev"]
    _version = None

    name = "Mercurial"
    req_version = "2.8"
    default_branch = "default"
    ref_to_remote = "head() and branch(.) and not closed() - ."
    ref_from_remote = "outgoing()"

    VERSION_RE = re.compile(r".*\(version ([^)]*)\).*")

    def is_valid(self):
        """Check whether this is a valid repository."""
        return os.path.exists(os.path.join(self.path, ".hg", "requires"))

    def init(self):
        """Initialize the repository."""
        self._popen(["init", self.path])

    def check_config(self):
        """Check VCS configuration."""
        # We directly set config as it takes same time as reading it
        self.set_config("ui.ssh", SSH_WRAPPER.filename)

    @classmethod
    def _clone(cls, source: str, target: str, branch: str):
        """Clone repository."""
        cls._popen(["clone", "--branch", branch, source, target])

    def get_config(self, path):
        """Read entry from configuration."""
        result = None
        section, option = path.split(".", 1)
        filename = os.path.join(self.path, ".hg", "hgrc")
        config = RawConfigParser()
        config.read(filename)
        if config.has_option(section, option):
            result = config.get(section, option)
        return result

    def set_config(self, path, value):
        """Set entry in local configuration."""
        if not self.lock.is_locked:
            raise RuntimeError("Repository operation without lock held!")
        section, option = path.split(".", 1)
        filename = os.path.join(self.path, ".hg", "hgrc")
        config = RawConfigParser()
        config.read(filename)
        if not config.has_section(section):
            config.add_section(section)
        if config.has_option(section, option) and config.get(section, option) == value:
            return
        config.set(section, option, value)
        with open(filename, "w") as handle:
            config.write(handle)

    def set_committer(self, name, mail):
        """Configure commiter name."""
        self.set_config("ui.username", f"{name} <{mail}>")

    def reset(self):
        """Reset working copy to match remote branch."""
        self.set_config("extensions.strip", "")
        self.execute(["update", "--clean", "remote(.)"])
        if self.needs_push():
            self.execute(["strip", "roots(outgoing())"])
        self.clean_revision_cache()

    def configure_merge(self):
        """Select the correct merge tool."""
        self.set_config("ui.merge", "internal:merge")
        merge_driver = self.get_merge_driver("po")
        if merge_driver is not None:
            self.set_config(
                "merge-tools.weblate-merge-gettext-po.executable", merge_driver
            )
            self.set_config("merge-patterns.**.po", "weblate-merge-gettext-po")

    def rebase(self, abort=False):
        """Rebase working copy on top of remote branch."""
        self.set_config("extensions.rebase", "")
        if abort:
            self.execute(["rebase", "--abort"])
        elif self.needs_merge():
            if self.needs_ff():
                self.execute(["update", "--clean", "remote(.)"])
            else:
                self.configure_merge()
                try:
                    self.execute(["rebase", "-d", "remote(.)"])
                except RepositoryException as error:
                    # Mercurial 3.8 changed error code and output
                    if (
                        error.retcode in (1, 255)
                        and "nothing to rebase" in error.args[0]
                    ):
                        self.execute(["update", "--clean", "remote(.)"])
                        return
                    raise

    def merge(self, abort=False, message=None):
        """Merge remote branch or reverts the merge."""
        if abort:
            self.execute(["update", "--clean", "."])
        elif self.needs_merge():
            if self.needs_ff():
                self.execute(["update", "--clean", "remote(.)"])
            else:
                self.configure_merge()
                # Fallback to merge
                try:
                    self.execute(["merge", "-r", "remote(.)"])
                except RepositoryException as error:
                    if error.retcode == 255:
                        # Nothing to merge
                        return
                    raise
                self.execute(["commit", "--message", "Merge"])

    def needs_commit(self, filenames: Optional[List[str]] = None):
        """Check whether repository needs commit."""
        cmd = ["status", "--"]
        if filenames:
            cmd.extend(filenames)
        status = self.execute(cmd, needs_lock=False)
        return status != ""

    def _get_revision_info(self, revision):
        """Return dictionary with detailed revision information."""
        template = """
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
        """
        text = self.execute(
            ["log", "--limit", "1", "--template", template, "--rev", revision],
            needs_lock=False,
            merge_err=False,
        )

        result = {"revision": revision}

        message = []
        header = True

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if not header:
                message.append(line)
                continue
            if line == "message:":
                header = False
                continue
            name, value = line.strip().split(":", 1)
            value = value.strip()
            name = name.lower()
            result[name] = value

        result["message"] = "\n".join(message)
        result["summary"] = message[0]

        return result

    def log_revisions(self, refspec):
        """Return revisin log for given refspec."""
        return self.execute(
            ["log", "--template", "{node}\n", "--rev", refspec],
            needs_lock=False,
            merge_err=False,
        ).splitlines()

    def needs_ff(self):
        """Check whether repository needs a fast-forward to upstream.

        Checks whether the path to the upstream is linear.
        """
        return bool(self.log_revisions(".::remote(.) - ."))

    @classmethod
    def _get_version(cls):
        """Return VCS program version."""
        output = cls._popen(["version", "-q"], merge_err=False)
        matches = cls.VERSION_RE.match(output)
        if matches is None:
            raise OSError(f"Failed to parse version string: {output}")
        return matches.group(1)

    def commit(
        self,
        message: str,
        author: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        files: Optional[List[str]] = None,
    ):
        """Create new revision."""
        # Build the commit command
        cmd = ["commit", "--message", message]
        if author is not None:
            cmd.extend(["--user", author])
        if timestamp is not None:
            cmd.extend(["--date", timestamp.ctime()])

        # Add files one by one, this has to deal with
        # removed, untracked and non existing files
        if files is not None:
            for name in files:
                try:
                    self.execute(["add", "--", name])
                except RepositoryException:
                    try:
                        self.execute(["remove", "--", name])
                    except RepositoryException:
                        continue
                cmd.append(name)

        # Bail out if there is nothing to commit.
        # This can easily happen with squashing and reverting changes.
        if not self.needs_commit(files):
            return

        # Execute it
        self.execute(cmd)
        # Clean cache
        self.clean_revision_cache()

    def remove(self, files: List[str], message: str, author: Optional[str] = None):
        """Remove files and creates new revision."""
        self.execute(["remove", "--force", "--"] + files)
        self.commit(message, author)

    def configure_remote(
        self, pull_url: str, push_url: str, branch: str, fast: bool = True
    ):
        """Configure remote repository."""
        old_pull = self.get_config("paths.default")
        old_push = self.get_config("paths.default-push")

        if old_pull != pull_url:
            # No origin existing or URL changed?
            self.set_config("paths.default", pull_url)

        if old_push != push_url:
            self.set_config("paths.default-push", push_url)

        # We also enable some necessary extensions here
        self.set_config("extensions.strip", "")
        self.set_config("extensions.rebase", "")
        self.set_config("experimental.evolution", "all")
        self.set_config("phases.publish", "False")

        self.branch = branch

    def on_branch(self, branch):
        return branch == self.execute(["branch"], merge_err=False).strip()

    def configure_branch(self, branch):
        """Configure repository branch."""
        if not self.on_branch(branch):
            self.execute(["update", branch])
        self.branch = branch

    def describe(self):
        """Verbosely describes current revision."""
        return self.execute(
            [
                "log",
                "-r",
                ".",
                "--template",
                "{latesttag}-{latesttagdistance}-{node|short}",
            ],
            needs_lock=False,
            merge_err=False,
        ).strip()

    def push(self, branch):
        """Push given branch to remote repository."""
        try:
            self.execute(["push", "-b", self.branch])
        except RepositoryException as error:
            if error.retcode == 1:
                # No changes found
                return
            raise

    def get_file(self, path, revision):
        """Return content of file at given revision."""
        return self.execute(
            ["cat", "--rev", revision, path], needs_lock=False, merge_err=False
        )

    def cleanup(self):
        """Remove not tracked files from the repository."""
        self.set_config("extensions.purge", "")
        self.execute(["purge"])

    def update_remote(self):
        """Update remote repository."""
        self.execute(["pull", "--branch", self.branch])
        self.clean_revision_cache()

    def parse_changed_files(self, lines):
        """Parses output with chanaged files."""
        # Strip action prefix we do not use
        yield from (line[2:] for line in lines)

    def list_changed_files(self, refspec):
        try:
            return super().list_changed_files(refspec)
        except RepositoryException as error:
            if error.retcode == 255:
                # Empty revision set
                return []
            raise
