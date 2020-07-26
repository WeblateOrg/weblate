#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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
"""Git based version control system abstraction for Weblate needs."""

import os
import os.path
from datetime import datetime
from typing import List, Optional
from zipfile import ZipFile

import requests
from django.conf import settings
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy
from git.config import GitConfigParser

from weblate.utils.errors import report_error
from weblate.utils.xml import parse_xml
from weblate.vcs.base import Repository, RepositoryException
from weblate.vcs.gpg import get_gpg_sign_key


class GitRepository(Repository):
    """Repository implementation for Git."""

    _cmd = "git"
    _cmd_last_revision = ["log", "-n", "1", "--format=format:%H", "HEAD"]
    _cmd_last_remote_revision = ["log", "-n", "1", "--format=format:%H", "@{upstream}"]
    _cmd_list_changed_files = ["diff", "--name-status"]
    _cmd_push = ["push"]

    name = "Git"
    req_version = "2.12"
    default_branch = "master"
    ref_to_remote = "..{0}"
    ref_from_remote = "{0}.."

    def is_valid(self):
        """Check whether this is a valid repository."""
        return os.path.exists(
            os.path.join(self.path, ".git", "config")
        ) or os.path.exists(os.path.join(self.path, "config"))

    def init(self):
        """Initialize the repository."""
        self._popen(["init", self.path])

    def config_update(self, *updates):
        filename = os.path.join(self.path, ".git", "config")
        with GitConfigParser(file_or_files=filename, read_only=False) as config:
            for section, key, value in updates:
                old = config.get_value(section, key, -1)
                if value is None and old:
                    config.remove_option(section, key)
                elif old != value:
                    config.set_value(section, key, value)

    def check_config(self):
        """Check VCS configuration."""
        self.config_update(("push", "default", "current"))

    @staticmethod
    def get_depth():
        if settings.VCS_CLONE_DEPTH:
            return ["--depth", str(settings.VCS_CLONE_DEPTH)]
        return []

    @classmethod
    def _clone(cls, source, target, branch=None):
        """Clone repository."""
        cls._popen(["clone"] + cls.get_depth() + ["--no-single-branch", source, target])

    def get_config(self, path):
        """Read entry from configuration."""
        return self.execute(["config", path], needs_lock=False, merge_err=False).strip()

    def set_committer(self, name, mail):
        """Configure commiter name."""
        self.config_update(("user", "name", name), ("user", "email", mail))

    def reset(self):
        """Reset working copy to match remote branch."""
        self.execute(["reset", "--hard", self.get_remote_branch_name()])
        self.clean_revision_cache()

    def rebase(self, abort=False):
        """Rebase working copy on top of remote branch."""
        if abort:
            if self.has_git_file("rebase-apply") or self.has_git_file("rebase-merge"):
                self.execute(["rebase", "--abort"])
            if self.needs_commit():
                self.execute(["reset", "--hard"])
        else:
            self.execute(["rebase", self.get_remote_branch_name()])

    def has_git_file(self, name):
        return os.path.exists(os.path.join(self.path, ".git", name))

    def has_rev(self, rev):
        try:
            self.execute(["rev-parse", "--verify", rev], needs_lock=False)
            return True
        except RepositoryException:
            return False

    def merge(self, abort=False, message=None):
        """Merge remote branch or reverts the merge."""
        tmp = "weblate-merge-tmp"
        if abort:
            # Abort merge if there is one to abort
            if self.has_rev("MERGE_HEAD"):
                self.execute(["merge", "--abort"])
            if self.needs_commit():
                self.execute(["reset", "--hard"])
            # Checkout original branch (we might be on tmp)
            self.execute(["checkout", self.branch])
        else:
            self.delete_branch(tmp)
            # We don't do simple git merge origin/branch as that leads
            # to different merge order than expected and most GUI tools
            # then show confusing diff (not changes done by Weblate, but
            # changes merged into Weblate)
            remote = self.get_remote_branch_name()
            # Create local branch for upstream
            self.execute(["branch", tmp, remote])
            # Checkout upstream branch
            self.execute(["checkout", tmp])
            # Merge current Weblate changes, this can lead to conflict
            cmd = [
                "merge",
                "--message",
                message or "Merge branch '{}' into Weblate".format(remote),
            ]
            cmd.extend(self.get_gpg_sign_args())
            cmd.append(self.branch)
            self.execute(cmd)
            # Checkout branch with Weblate changes
            self.execute(["checkout", self.branch])
            # Merge temporary branch (this is fast forward so does not create
            # merge commit)
            self.execute(["merge", tmp])

        # Delete temporary branch
        self.delete_branch(tmp)

    def delete_branch(self, name):
        if self.has_branch(name):
            self.execute(["branch", "-D", name])

    def needs_commit(self, *filenames):
        """Check whether repository needs commit."""
        cmd = ("status", "--porcelain", "--") + filenames
        with self.lock:
            status = self.execute(cmd, merge_err=False)
        return status != ""

    def show(self, revision):
        """Helper method to get content of revision.

        Used in tests.
        """
        return self.execute(["show", revision], needs_lock=False, merge_err=False)

    @staticmethod
    def get_gpg_sign_args():
        sign_key = get_gpg_sign_key()
        if sign_key:
            return ["--gpg-sign={}".format(sign_key)]
        return []

    def _get_revision_info(self, revision):
        """Return dictionary with detailed revision information."""
        text = self.execute(
            ["log", "-1", "--format=fuller", "--date=rfc", "--abbrev-commit", revision],
            needs_lock=False,
            merge_err=False,
        )

        result = {"revision": revision}

        message = []

        header = True

        for line in text.splitlines():
            if header:
                if not line:
                    header = False
                elif line.startswith("commit"):
                    result["shortrevision"] = line.split()[1]
                else:
                    name, value = line.strip().split(":", 1)
                    value = value.strip()
                    name = name.lower()
                    result[name] = value
                    if "<" in value:
                        parsed = value.split("<", 1)
                        result["{0}_name".format(name)] = parsed[0].strip()
                        result["{0}_email".format(name)] = parsed[1].rstrip(">")
            else:
                message.append(line.strip())

        result["message"] = "\n".join(message)
        result["summary"] = message[0]

        return result

    def log_revisions(self, refspec):
        """Return revisin log for given refspec."""
        return self.execute(
            ["log", "--format=format:%H", refspec, "--"],
            needs_lock=False,
            merge_err=False,
        ).splitlines()

    @classmethod
    def _get_version(cls):
        """Return VCS program version."""
        return cls._popen(["--version"], merge_err=False).split()[2]

    def commit(
        self,
        message: str,
        author: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        files: Optional[List[str]] = None,
    ):
        """Create new revision."""
        # Add files (some of them might not be in the index)
        if files:
            self.execute(["add", "--force", "--"] + files)
        else:
            self.execute(["add", self.path])

        # Build the commit command
        cmd = ["commit", "--message", message]
        if author:
            cmd.extend(["--author", author])
        if timestamp is not None:
            cmd.extend(["--date", timestamp.isoformat()])
        cmd.extend(self.get_gpg_sign_args())

        # Execute it
        self.execute(cmd)
        # Clean cache
        self.clean_revision_cache()

    def remove(self, files: List[str], message: str, author: Optional[str] = None):
        """Remove files and creates new revision."""
        self.execute(["rm", "--force", "--"] + files)
        self.commit(message, author)

    def configure_remote(self, pull_url, push_url, branch):
        """Configure remote repository."""
        self.config_update(
            # Pull url
            ('remote "origin"', "url", pull_url),
            # Push URL, None remove it
            ('remote "origin"', "pushurl", push_url or None),
            # Fetch all branches (needed for clone branch)
            ('remote "origin"', "fetch", "+refs/heads/*:refs/remotes/origin/*"),
            # Disable fetching tags
            ('remote "origin"', "tagOpt", "--no-tags"),
            # Set branch to track
            ('branch "{0}"'.format(branch), "remote", "origin"),
            ('branch "{0}"'.format(branch), "merge", "refs/heads/{0}".format(branch)),
        )
        self.branch = branch

    def api_url(self):
        return self.component.repo.replace(".git", "").replace(
            "github.com", "api.github.com/repos"
        )

    def configure_fork_remote(self, pull_url, remote_name):
        """Configure fork remote repository."""
        self.config_update(
            # Pull url
            ('remote "{}"'.format(remote_name), "url", pull_url),
            # Push url
            ('remote "{}"'.format(remote_name), "pushurl", pull_url),
        )

    def fork(self):
        fork_url = "{}/forks".format(self.api_url())
        r = requests.post(
            fork_url,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "Authorization": "token {}".format(settings.GITHUB_TOKEN),
            },
            data={},
        )
        response = r.json()
        self.configure_fork_remote(response["clone_url"], self.get_username())

    def list_branches(self, *args):
        cmd = ["branch", "--list"]
        cmd.extend(args)
        # (we get additional * there indicating current branch)
        return [
            x.lstrip("*").strip()
            for x in self.execute(cmd, needs_lock=False, merge_err=False).splitlines()
        ]

    def has_branch(self, branch):
        branches = self.list_branches()
        return branch in branches

    def configure_branch(self, branch):
        """Configure repository branch."""
        # Add branch
        if not self.has_branch(branch):
            self.execute(["checkout", "-b", branch, "origin/{0}".format(branch)])
        else:
            # Ensure it tracks correct upstream
            self.config_update(('branch "{0}"'.format(branch), "remote", "origin"))

        # Checkout
        self.execute(["checkout", branch])
        self.branch = branch

    def describe(self):
        """Verbosely describes current revision."""
        return self.execute(
            ["describe", "--always"], needs_lock=False, merge_err=False
        ).strip()

    @classmethod
    def global_setup(cls):
        """Perform global settings."""
        merge_driver = cls.get_merge_driver("po")
        if merge_driver is not None:
            cls._popen(
                [
                    "config",
                    "--global",
                    "merge.weblate-merge-gettext-po.name",
                    "Weblate merge driver for Gettext PO files",
                ]
            )
            cls._popen(
                [
                    "config",
                    "--global",
                    "merge.weblate-merge-gettext-po.driver",
                    "{0} %O %A %B".format(merge_driver),
                ]
            )
        cls._popen(
            ["config", "--global", "user.email", settings.DEFAULT_COMMITER_EMAIL]
        )
        cls._popen(["config", "--global", "user.name", settings.DEFAULT_COMMITER_NAME])

    def get_file(self, path, revision):
        """Return content of file at given revision."""
        return self.execute(
            ["show", "{0}:{1}".format(revision, path)],
            needs_lock=False,
            merge_err=False,
        )

    def cleanup(self):
        """Remove not tracked files from the repository."""
        self.execute(["clean", "-f"])
        # Remove possible stale branches
        for branch in self.list_branches():
            if branch != self.branch:
                self.execute(["branch", "--delete", "--force", branch])
        # Remove any tags
        for tag in self.execute(["tag", "--list"], merge_err=False).splitlines():
            self.execute(["tag", "--delete", tag])

    def list_remote_branches(self):
        return [
            branch[7:]
            for branch in self.list_branches("--remote", "origin/*")
            if not branch.startswith("origin/HEAD")
        ]

    def update_remote(self):
        """Update remote repository."""
        self.execute(["remote", "prune", "origin"])
        if self.list_remote_branches():
            # Updating existing fork
            self.execute(["fetch", "origin"])
        else:
            # Doing initial fetch
            self.execute(["fetch", "origin"] + self.get_depth())
        self.clean_revision_cache()

    def push(self, branch):
        """Push given branch to remote repository."""
        if branch:
            refspec = f"{self.branch}:{branch}"
        else:
            refspec = self.branch
        self.execute(self._cmd_push + ["origin", refspec])

    def unshallow(self):
        self.execute(["fetch", "--unshallow"])

    def parse_changed_files(self, lines):
        """Parses output with chanaged files."""
        # Strip action prefix we do not use
        for line in lines:
            yield from line.split("\t")[1:]


class GitWithGerritRepository(GitRepository):

    name = "Gerrit"
    req_version = "1.27.0"

    _version = None

    @classmethod
    def _get_version(cls):
        """Return VCS program version."""
        return cls._popen(["review", "--version"], merge_err=True).split()[-1]

    def push(self, branch):
        if self.needs_push():
            self.execute(["review", "--yes", self.branch])


class SubversionRepository(GitRepository):

    name = "Subversion"
    req_version = "2.12"

    _version = None

    _fetch_revision = None

    needs_push_url = False

    @classmethod
    def _get_version(cls):
        """Return VCS program version."""
        return cls._popen(["svn", "--version"], merge_err=False).split()[2]

    @classmethod
    def is_stdlayout(cls, url):
        output = cls._popen(["svn", "ls", url], fullcmd=True).splitlines()
        return "trunk/" in output

    @classmethod
    def get_last_repo_revision(cls, url):
        output = cls._popen(
            ["svn", "log", url, "--limit=1", "--xml"],
            fullcmd=True,
            raw=True,
            merge_err=False,
        )
        tree = parse_xml(output)
        entry = tree.find("logentry")
        if entry is not None:
            return entry.get("revision")
        return None

    @classmethod
    def get_remote_args(cls, source, target):
        result = ["--prefix=origin/", source, target]
        if cls.is_stdlayout(source):
            result.insert(0, "--stdlayout")
            revision = cls.get_last_repo_revision(source + "/trunk/")
        else:
            revision = cls.get_last_repo_revision(source)
        if revision:
            revision = "--revision={}:HEAD".format(revision)

        return result, revision

    def configure_remote(self, pull_url, push_url, branch):
        """Initialize the git-svn repository.

        This does not support switching remote as it's quite complex:
        https://git.wiki.kernel.org/index.php/GitSvnSwitch

        The git svn init errors in case the URL is not matching.
        """
        try:
            existing = self.get_config("svn-remote.svn.url")
        except RepositoryException:
            existing = None
        if existing:
            # The URL is root of the repository, while we get full path
            if not pull_url.startswith(existing):
                raise RepositoryException(-1, "Can not switch subversion URL")
            return
        args, self._fetch_revision = self.get_remote_args(pull_url, self.path)
        self.execute(["svn", "init"] + args)

    def update_remote(self):
        """Update remote repository."""
        if self._fetch_revision:
            self.execute(["svn", "fetch", self._fetch_revision])
            self._fetch_revision = None
        else:
            self.execute(["svn", "fetch", "--parent"])
        self.clean_revision_cache()

    @classmethod
    def _clone(cls, source, target, branch=None):
        """Clone svn repository with git-svn."""
        args, revision = cls.get_remote_args(source, target)
        if revision:
            args.insert(0, revision)
        cls._popen(["svn", "clone"] + args)

    def merge(self, abort=False, message=None):
        """Rebases.

        Git-svn does not support merge.
        """
        self.rebase(abort)

    def rebase(self, abort=False):
        """Rebase remote branch or reverts the rebase.

        Git-svn does not support merge.
        """
        if abort:
            self.execute(["rebase", "--abort"])
        else:
            self.execute(["svn", "rebase"])

    @cached_property
    def last_remote_revision(self):
        """Return last remote revision."""
        return self.execute(
            ["log", "-n", "1", "--format=format:%H", self.get_remote_branch_name()],
            needs_lock=False,
            merge_err=False,
        )

    def get_remote_branch_name(self):
        """Return the remote branch name.

        trunk if local branch is master, local branch otherwise.
        """
        if self.branch == "master":
            fetch = self.get_config("svn-remote.svn.fetch")
            if "origin/trunk" in fetch:
                return "origin/trunk"
            if "origin/git-svn" in fetch:
                return "origin/git-svn"
        return "origin/{0}".format(self.branch)

    def list_remote_branches(self):
        return []

    def push(self, branch):
        """Push given branch to remote repository."""
        self.execute(["svn", "dcommit", self.branch])


class GitForcePushRepository(GitRepository):
    name = gettext_lazy("Git with force push")
    _cmd_push = ["push", "--force"]
    identifier = "git-force-push"


class GitMergeRequestBase(GitForcePushRepository):
    needs_push_url = False
    identifier = None

    @staticmethod
    def get_username():
        raise NotImplementedError()

    @classmethod
    def is_configured(cls):
        return cls.get_username() is not None

    def push_to_fork(self, local_branch, fork_branch):
        """Push given local branch to branch in forked repository."""
        self.execute(
            [
                "push",
                "--force",
                self.get_username(),
                "{0}:{1}".format(local_branch, fork_branch),
            ]
        )

    def fork(self):
        """Create fork of original repository if one doesn't exist yet."""
        remotes = self.execute(["remote"]).splitlines()
        if self.get_username() not in remotes:
            super().fork()

    def push(self, branch):
        """Fork repository on Github and push changes.

        Pushes changes to *-weblate branch on fork and creates pull request against
        original repository.
        """
        if branch and branch != self.branch:
            fork_remote = "origin"
            fork_branch = branch
            super().push(branch)
        else:
            fork_remote = self.get_username()
            self.fork()
            if self.component is not None:
                fork_branch = "weblate-{0}-{1}".format(
                    self.component.project.slug, self.component.slug
                )
            else:
                fork_branch = "weblate-{0}".format(self.branch)
            self.push_to_fork(self.branch, fork_branch)
        try:
            self.create_pull_request(self.branch, fork_remote, fork_branch)
        except RepositoryException as error:
            report_error(cause="Failed pull request")
            if error.retcode == 1:
                # Pull request already exists.
                return
            raise

    def create_pull_request(self, origin_branch, fork_remote, fork_branch):
        raise NotImplementedError()

    def get_merge_message(self):
        from weblate.utils.render import render_template

        return render_template(settings.DEFAULT_PULL_MESSAGE, component=self.component)


class GithubRepository(GitMergeRequestBase):

    name = "GitHub"
    _cmd = "hub"
    _version = None
    req_version = "2.7"

    @classmethod
    def _get_version(cls):
        """Return VCS program version."""
        return cls._popen(["--version"], merge_err=False).split()[-1]

    @staticmethod
    def get_username():
        return settings.GITHUB_USERNAME

    @classmethod
    def _getenv(cls):
        """Generate environment for process execution."""
        env = super()._getenv()
        # Add path to config if it exists
        userconfig = os.path.expanduser("~/.config/hub")
        if os.path.exists(userconfig):
            env["HUB_CONFIG"] = userconfig

        return env

    def create_pull_request(self, origin_branch, fork_remote, fork_branch):
        """Create pull request.

        Use to merge branch in forked repository into branch of remote repository.
        """
        if fork_remote == "origin":
            head = fork_branch
        else:
            head = "{0}:{1}".format(fork_remote, fork_branch)
        pr_url = "{}/pulls".format(self.api_url())
        r = requests.post(
            pr_url,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "Authorization": "token {}".format(settings.GITHUB_TOKEN),
            },
            json={
                "head": head,
                "base": origin_branch,
                "title": self.get_merge_message(),
            },
        )
        response = r.json()
        if not response["url"]:
            report_error(cause=response["message"])


class LocalRepository(GitRepository):
    """Local filesystem driver with no upstream repo."""

    name = gettext_lazy("No remote repository")
    identifier = "local"

    def configure_remote(self, pull_url, push_url, branch):
        return

    def get_remote_branch_name(self):
        return self.branch

    def update_remote(self):
        return

    def push(self, branch):
        return

    def reset(self):
        return

    def rebase(self, abort=False):
        return

    def merge(self, abort=False, message=None):
        return

    def list_remote_branches(self):
        return []

    @classmethod
    def _clone(cls, source, target, branch=None):
        if not os.path.exists(target):
            os.makedirs(target)
        cls._popen(["init", target])
        with open(os.path.join(target, "README.md"), "w") as handle:
            handle.write("Translations repository created by Weblate\n")
            handle.write("==========================================\n")
            handle.write("\n")
            handle.write("See https://weblate.org/ for more info.\n")
        cls._popen(["add", "README.md"], target)
        cls._popen(["commit", "--message", "Repository created by Weblate"], target)

    @cached_property
    def last_remote_revision(self):
        return self.last_revision

    @classmethod
    def from_zip(cls, target, zipfile):
        # Create empty repo
        if not os.path.exists(target):
            cls._clone("local:", target)
        # Extract zip file content
        ZipFile(zipfile).extractall(target)
        # Add to repository
        repo = cls(target)
        with repo.lock:
            repo.execute(["add", target])
            if repo.needs_commit():
                repo.commit("ZIP file upladed into Weblate")

    @classmethod
    def from_files(cls, target, files):
        # Create empty repo
        if not os.path.exists(target):
            cls._clone("local:", target)
        # Create files
        for name, content in files.items():
            fullname = os.path.join(target, name)
            dirname = os.path.dirname(fullname)
            if not os.path.exists(dirname):
                os.makedirs(dirname)
            with open(fullname, "wb") as handle:
                handle.write(content)
        # Add to repository
        repo = cls(target)
        with repo.lock:
            repo.execute(["add", target])
            if repo.needs_commit():
                repo.commit("Started tranlation using Weblate")


class GitLabRepository(GitMergeRequestBase):

    name = "GitLab"
    req_version = "0.16"

    _version = None

    # docs: https://zaquestion.github.io/lab/
    _cmd = "lab"

    @classmethod
    def _get_version(cls):
        """Return VCS program version."""
        try:
            return cls._popen(["--version"], merge_err=False).split()[-1]
        except RepositoryException as error:
            # It asks for configuration even with --version, see
            # https://github.com/zaquestion/lab/issues/374
            if error.retcode == 1 and "EOF" in error.get_message():
                return "0.16"
            raise

    @staticmethod
    def get_username():
        return settings.GITLAB_USERNAME

    def create_pull_request(self, origin_branch, fork_remote, fork_branch):
        """Create merge (a.k.a pull) request.

        Used to merge branch in forked repository into branch of remote
        repository.

        :param origin_branch: Git branch in the project's repo to create pull
            request against.
        :param fork_branch: Git branch in the fork's repo which contains the
            updates.
        """
        # Checkout the branch we want to use as the source for new MR.
        self.execute(
            ["checkout", "-B", fork_branch, "{}/{}".format(fork_remote, fork_branch)]
        )
        # Reset the branch to be up to date with our main branch
        self.execute(["reset", "--hard", self.branch])
        try:
            # Create a new MR against origin/<origin_branch> from the fork.
            self.execute(
                [
                    "mr",
                    "create",
                    "origin",
                    origin_branch,
                    "--message",
                    self.get_merge_message(),
                ]
            )
        finally:
            # Return to the previous checked out branch.
            self.execute(["checkout", "-"])
