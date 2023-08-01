# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Git-based version-control-system abstraction for Weblate needs."""

from __future__ import annotations

import logging
import os
import os.path
import random
import urllib.parse
from configparser import NoOptionError, NoSectionError, RawConfigParser
from json import JSONDecodeError, dumps
from time import sleep, time
from typing import TYPE_CHECKING
from zipfile import ZipFile

import requests
import sentry_sdk
from django.conf import settings
from django.core.cache import cache
from django.utils.functional import cached_property
from django.utils.translation import gettext, gettext_lazy
from git.config import GitConfigParser
from requests.exceptions import HTTPError

from weblate.utils.data import data_dir
from weblate.utils.errors import report_error
from weblate.utils.files import is_excluded, remove_tree
from weblate.utils.lock import WeblateLock, WeblateLockTimeoutError
from weblate.utils.render import render_template
from weblate.utils.xml import parse_xml
from weblate.vcs.base import Repository, RepositoryError
from weblate.vcs.gpg import get_gpg_sign_key

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import datetime


class GitRepository(Repository):
    """Repository implementation for Git."""

    _cmd = "git"
    _cmd_last_revision = ["log", "-n", "1", "--format=format:%H", "HEAD"]
    _cmd_last_remote_revision = ["log", "-n", "1", "--format=format:%H", "@{upstream}"]
    _cmd_list_changed_files = ["diff", "--name-status"]
    _cmd_push = ["push"]
    _cmd_status = ["--no-optional-locks", "status"]

    name = "Git"
    push_label = gettext_lazy("This will push changes to the upstream Git repository.")
    req_version = "2.12"
    default_branch = "master"
    ref_to_remote = "..{0}"
    ref_from_remote = "{0}.."

    def is_valid(self):
        """Check whether this is a valid repository."""
        return os.path.exists(
            os.path.join(self.path, ".git", "config")
        ) or os.path.exists(os.path.join(self.path, "config"))

    @classmethod
    def _init(cls, path: str):
        cls._popen(["init", path])
        if cls.default_branch != "master":
            # We could do here just init --initial-branch {branch}, but that does not
            # work in Git before 2.28.0
            with open(os.path.join(path, ".git/HEAD"), "w") as handle:
                handle.write("ref: refs/heads/main\n")

    def init(self):
        """Initialize the repository."""
        self._init(self.path)

    @classmethod
    def get_remote_branch(cls, repo: str):
        if not repo:
            return super().get_remote_branch(repo)
        try:
            result = cls._popen(["ls-remote", "--symref", "--", repo, "HEAD"])
        except RepositoryError:
            report_error(cause="Listing remote branch")
            return super().get_remote_branch(repo)
        for line in result.splitlines():
            if not line.startswith("ref: "):
                continue
            # Parses 'ref: refs/heads/main\tHEAD'
            return line.split("\t")[0].split("refs/heads/")[1]

        raise RepositoryError(0, "Could not figure out remote branch")

    @staticmethod
    def git_config_update(filename: str, *updates: tuple[str, str, str]):
        # First, open file read-only to check current settings
        modify = False
        with GitConfigParser(file_or_files=filename, read_only=True) as config:
            for section, key, value in updates:
                try:
                    old = config.get(section, key)
                    if value is None:
                        modify = True
                        break
                    if old == value:
                        continue
                except (NoSectionError, NoOptionError):
                    pass
                if value is not None:
                    modify = True
        if not modify:
            return
        # In case changes are needed, open it for writing as that creates a lock
        # file
        with GitConfigParser(file_or_files=filename, read_only=False) as config:
            for section, key, value in updates:
                try:
                    old = config.get(section, key)
                    if value is None:
                        config.remove_option(section, key)
                        continue
                    if old == value:
                        continue
                except (NoSectionError, NoOptionError):
                    pass
                if value is not None:
                    config.set_value(section, key, value)

    def config_update(self, *updates: tuple[str, str, str]):
        filename = os.path.join(self.path, ".git", "config")
        self.git_config_update(filename, *updates)

    def check_config(self):
        """Check VCS configuration."""
        self.config_update(("push", "default", "current"))

    @staticmethod
    def get_depth():
        if settings.VCS_CLONE_DEPTH:
            return ["--depth", str(settings.VCS_CLONE_DEPTH)]
        return []

    @classmethod
    def _clone(cls, source: str, target: str, branch: str):
        """Clone repository."""
        cls._popen(
            ["clone", *cls.get_depth(), "--branch", branch, "--", source, target]
        )

    def get_config(self, path):
        """Read entry from configuration."""
        return self.execute(["config", path], needs_lock=False, merge_err=False).strip()

    def set_committer(self, name, mail):
        """Configure committer name."""
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
            cmd = ["rebase"]
            cmd.extend(self.get_gpg_sign_args())
            cmd.append(self.get_remote_branch_name())
            self.execute(cmd)
        self.clean_revision_cache()

    def has_git_file(self, name):
        return os.path.exists(os.path.join(self.path, ".git", name))

    def has_rev(self, rev):
        try:
            self.execute(["rev-parse", "--verify", rev], needs_lock=False)
        except RepositoryError:
            return False
        return True

    def merge(
        self, abort: bool = False, message: str | None = None, no_ff: bool = False
    ):
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
                message or f"Merge branch {remote!r} into Weblate",
            ]
            if no_ff:
                cmd.append("--no-ff")
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
        self.clean_revision_cache()

    def delete_branch(self, name):
        if self.has_branch(name):
            self.execute(["branch", "-D", name])

    def needs_commit(self, filenames: list[str] | None = None):
        """Check whether repository needs commit."""
        cmd = ["--no-optional-locks", "status", "--porcelain"]
        if filenames:
            cmd.extend(["--untracked-files=all", "--ignored=traditional", "--"])
            cmd.extend(filenames)
        with self.lock:
            status = self.execute(cmd, merge_err=False)
        return bool(status)

    def show(self, revision):
        """
        Helper method to get the content of the revision.

        Used in tests.
        """
        return self.execute(["show", revision], needs_lock=False, merge_err=False)

    @staticmethod
    def get_gpg_sign_args():
        sign_key = get_gpg_sign_key()
        if sign_key:
            return [f"--gpg-sign={sign_key}"]
        return []

    def _get_revision_info(self, revision):
        """Return dictionary with detailed revision info."""
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
                        result[f"{name}_name"] = parsed[0].strip()
                        result[f"{name}_email"] = parsed[1].rstrip(">")
            else:
                message.append(line.strip())

        result["message"] = "\n".join(message)
        result["summary"] = message[0] if message else ""

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
        author: str | None = None,
        timestamp: datetime | None = None,
        files: list[str] | None = None,
    ) -> bool:
        """Create new revision."""
        # Add files one by one, this has to deal with
        # removed, untracked and non existing files
        if files:
            for name in files:
                try:
                    self.execute(["add", "--force", "--", self.resolve_symlinks(name)])
                except RepositoryError:
                    continue
        else:
            self.execute(["add", self.path])

        # Bail out if there is nothing to commit.
        # This can easily happen with squashing and reverting changes.
        if not self.needs_commit(files):
            return False

        # Build the commit command
        cmd = ["commit", "--file", "-"]
        if author:
            cmd.extend(["--author", author])
        if timestamp is not None:
            cmd.extend(["--date", timestamp.isoformat()])
        cmd.extend(self.get_gpg_sign_args())

        # Execute it
        self.execute(cmd, stdin=message)
        # Clean cache
        self.clean_revision_cache()

        return True

    def remove(self, files: list[str], message: str, author: str | None = None):
        """Remove files and creates new revision."""
        self.execute(["rm", "--force", "--", *files])
        self.commit(message, author)

    def configure_remote(
        self, pull_url: str, push_url: str, branch: str, fast: bool = True
    ):
        """Configure remote repository."""
        escaped_branch = dumps(branch, ensure_ascii=False)
        self.config_update(
            # Pull url
            ('remote "origin"', "url", pull_url),
            # Push URL, None remove it
            ('remote "origin"', "pushurl", push_url or None),
            # Fetch only current branch, others are fetched later in post_configure
            (
                'remote "origin"',
                "fetch",
                dumps(
                    f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
                    ensure_ascii=False,
                )
                if fast
                else "+refs/heads/*:refs/remotes/origin/*",
            ),
            # Disable fetching tags
            ('remote "origin"', "tagOpt", "--no-tags"),
            # Set branch to track
            (f"branch {escaped_branch}", "remote", "origin"),
            (
                f"branch {escaped_branch}",
                "merge",
                dumps(f"refs/heads/{branch}", ensure_ascii=False),
            ),
        )
        self.branch = branch

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
            self.execute(["checkout", "-b", branch, f"origin/{branch}"])
        else:
            # Ensure it tracks correct upstream
            self.config_update((f'branch "{branch}"', "remote", "origin"))  # noqa: B028

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
        updates = [
            ("user", "email", settings.DEFAULT_COMMITER_EMAIL),
            ("user", "name", settings.DEFAULT_COMMITER_NAME),
        ]
        if merge_driver is not None:
            updates.append(
                (
                    'merge "weblate-merge-gettext-po"',
                    "name",
                    "Weblate merge driver for gettext PO files",
                )
            )
            updates.append(
                (
                    'merge "weblate-merge-gettext-po"',
                    "driver",
                    f"{merge_driver} %O %A %B %P",
                )
            )

        filename = os.path.join(data_dir("home"), ".gitconfig")
        attempts = 0
        while attempts < 5:
            try:
                cls.git_config_update(filename, *updates)
                break
            except OSError:
                attempts += 1
                sleep(attempts * 0.1)

    def get_file(self, path, revision):
        """Return content of file at given revision."""
        return self.execute(
            ["show", f"{revision}:{path}"],
            needs_lock=False,
            merge_err=False,
        )

    def cleanup(self):
        """Remove not tracked files from the repository."""
        self.execute(["clean", "-f", "-d"])
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
            try:
                self.execute(["fetch", "origin", *self.get_depth()])
            except RepositoryError as error:
                if error.retcode == 1 and not error.args[0]:
                    # Fetch with --depth fails on blank repo
                    self.execute(["fetch", "origin"])
                else:
                    raise

        self.clean_revision_cache()

    def push(self, branch):
        """Push given branch to remote repository."""
        refspec = f"{self.branch}:{branch}" if branch else self.branch
        self.execute([*self._cmd_push, "origin", refspec])

    def unshallow(self):
        self.execute(["fetch", "--unshallow"])

    def parse_changed_files(self, lines: list[str]) -> Iterator[str]:
        """Parses output with changed files."""
        # Strip action prefix we do not use
        for line in lines:
            yield from line.split("\t")[1:]

    def status(self):
        result = [super().status()]
        cleanups = self.execute(["clean", "-f", "-d", "-n"], needs_lock=False)
        if cleanups:
            result.append("")
            result.append(gettext("Possible cleanups:"))
            result.append("")
            result.append(cleanups)

        return "\n".join(result)


class GitWithGerritRepository(GitRepository):
    name = "Gerrit"
    req_version = "1.27.0"
    push_label = gettext_lazy("This will push changes to Gerrit for a review.")

    _version = None

    @classmethod
    def _get_version(cls):
        """Return VCS program version."""
        return cls._popen(["review", "--version"], merge_err=True).split()[-1]

    def push(self, branch):
        if self.needs_push():
            try:
                self.execute(["review", "--yes", self.branch])
            except RepositoryError as error:
                if "(no new changes)" in str(error):
                    return
                raise


class SubversionRepository(GitRepository):
    name = "Subversion"
    req_version = "2.12"
    default_branch = "master"
    push_label = gettext_lazy("This will commit changes to the Subversion repository.")

    _version = None

    _fetch_revision = None

    needs_push_url = False

    @classmethod
    def global_setup(cls):
        """Perform global settings."""
        dirname = os.path.join(data_dir("home"), ".subversion")
        filename = os.path.join(dirname, "config")
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        config = RawConfigParser()
        config.read(filename)
        section = "auth"
        option = "password-stores"
        value = ""
        if not config.has_section(section):
            config.add_section(section)
        if config.has_option(section, option) and config.get(section, option) == value:
            return
        config.set(section, option, value)
        with open(filename, "w") as handle:
            config.write(handle)

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
        result = ["--prefix=origin/", "--", source, target]
        if cls.is_stdlayout(source):
            result.insert(0, "--stdlayout")
            revision = cls.get_last_repo_revision(source + "/trunk/")
        else:
            revision = cls.get_last_repo_revision(source)
        if revision:
            revision = f"--revision={revision}:HEAD"

        return result, revision

    def configure_remote(
        self, pull_url: str, push_url: str, branch: str, fast: bool = True
    ):
        """
        Initialize the git-svn repository.

        This does not support switching remote as it's quite complex:
        https://git.wiki.kernel.org/index.php/GitSvnSwitch

        The git svn init errors in case the URL is not matching.
        """
        try:
            existing = self.get_config("svn-remote.svn.url")
        except RepositoryError:
            existing = None
        if existing:
            # The URL is root of the repository, while we get full path
            if not pull_url.startswith(existing):
                raise RepositoryError(-1, "Can not switch subversion URL")
            return
        args, self._fetch_revision = self.get_remote_args(pull_url, self.path)
        self.execute(["svn", "init", *args])

    def update_remote(self):
        """Update remote repository."""
        if self._fetch_revision:
            self.execute(["svn", "fetch", self._fetch_revision])
            self._fetch_revision = None
        else:
            self.execute(["svn", "fetch", "--parent"])
        self.clean_revision_cache()

    @classmethod
    def _clone(
        cls,
        source: str,
        target: str,
        branch: str,  # noqa: ARG003
    ):
        """Clone svn repository with git-svn."""
        args, revision = cls.get_remote_args(source, target)
        if revision:
            args.insert(0, revision)
        cls._popen(["svn", "clone", *args])

    def merge(
        self, abort: bool = False, message: str | None = None, no_ff: bool = False
    ):
        """
        Rebases.

        Git-svn does not support merge.
        """
        self.rebase(abort)
        self.clean_revision_cache()

    def rebase(self, abort=False):
        """
        Rebase remote branch or reverts the rebase.

        Git-svn does not support merge.
        """
        if abort:
            self.execute(["rebase", "--abort"])
        else:
            self.execute(["svn", "rebase"])
        self.clean_revision_cache()

    @cached_property
    def last_remote_revision(self):
        """Return last remote revision."""
        return self.execute(
            ["log", "-n", "1", "--format=format:%H", self.get_remote_branch_name()],
            needs_lock=False,
            merge_err=False,
        )

    def get_remote_branch_name(self):
        """
        Return the remote branch name.

        trunk if local branch is master, local branch otherwise.
        """
        if self.branch == self.default_branch:
            fetch = self.get_config("svn-remote.svn.fetch")
            if "origin/trunk" in fetch:
                return "origin/trunk"
            if "origin/git-svn" in fetch:
                return "origin/git-svn"
        return f"origin/{self.branch}"

    def list_remote_branches(self):
        return []

    def push(self, branch):
        """Push given branch to remote repository."""
        self.execute(["svn", "dcommit", self.branch])


class GitForcePushRepository(GitRepository):
    name = gettext_lazy("Git with force push")
    _cmd_push = ["push", "--force"]
    identifier = "git-force-push"
    push_label = gettext_lazy(
        "This will force push changes to the upstream repository."
    )


class GitMergeRequestBase(GitForcePushRepository):
    needs_push_url = False
    identifier = None
    API_TEMPLATE = ""

    def merge(
        self, abort: bool = False, message: str | None = None, no_ff: bool = False
    ):
        """Merge remote branch or reverts the merge."""
        # This reverts merge behavior of pure git backend
        # as we're expecting there will be an additional merge
        # commit created from the merge request.
        if abort:
            self.execute(["merge", "--abort"])
            # Needed for compatibility with original merge code
            self.execute(["checkout", self.branch])
        else:
            cmd = ["merge"]
            if no_ff:
                cmd.append("--no-ff")
            cmd.extend(self.get_gpg_sign_args())
            cmd.append(self.get_remote_branch_name())
            self.execute(cmd)
        self.clean_revision_cache()

    def parse_repo_url(self) -> tuple[str, str, str, str]:
        repo = self.component.repo
        parsed = urllib.parse.urlparse(repo)
        host = parsed.hostname
        scheme = parsed.scheme
        if not host:
            # Assume SSH URL
            host, path = repo.split(":")
            host = host.split("@")[-1]
            scheme = None
        else:
            path = parsed.path
        parts = path.split(":")[-1].rstrip("/").split("/")
        last_part = parts[-1]
        if last_part.endswith(".git"):
            last_part = last_part[:-4]
        slug_parts = [last_part]
        owner = ""
        for part in parts[:-1]:
            if not part:
                continue
            if not owner:
                owner = part
                continue
            slug_parts.insert(-1, part)
        slug = "/".join(slug_parts)
        return (scheme, host, owner, slug)

    def format_url(
        self, scheme: str, hostname: str, owner: str, slug: str, **extra: str
    ) -> str:
        return self.API_TEMPLATE.format(
            host=hostname,
            owner=owner,
            slug=slug,
            owner_url=urllib.parse.quote_plus(owner),
            slug_url=urllib.parse.quote_plus(slug),
            scheme=scheme,
            **extra,
        )

    def get_credentials(self) -> dict[str, str]:
        scheme, host, owner, slug = self.parse_repo_url()
        hostname = self.format_api_host(host).lower()

        configuration = getattr(settings, f"{self.identifier.upper()}_CREDENTIALS")
        try:
            credentials = configuration[hostname]
        except KeyError as exc:
            raise RepositoryError(
                0, f"{self.name} API access for {hostname} is not configured"
            ) from exc

        # Scheme override
        if "scheme" in credentials:
            scheme = credentials["scheme"]
        # Fallback to https
        if not scheme or scheme == "ssh":
            scheme = "https"

        return {
            "url": self.format_url(scheme, hostname, owner, slug),
            "owner": owner,
            "slug": slug,
            "hostname": hostname,
            "username": credentials["username"],
            "token": credentials["token"],
            "scheme": scheme,
        }

    @classmethod
    def uses_deprecated_setting(cls) -> bool:
        return not getattr(settings, f"{cls.identifier.upper()}_CREDENTIALS") and (
            getattr(settings, f"{cls.identifier.upper()}_USERNAME", None)
            or getattr(settings, f"{cls.identifier.upper()}_TOKEN", None)
        )

    @classmethod
    def is_configured(cls) -> bool:
        return getattr(settings, f"{cls.identifier.upper()}_USERNAME", None) or getattr(
            settings, f"{cls.identifier.upper()}_CREDENTIALS"
        )

    def push_to_fork(self, credentials: dict, local_branch: str, fork_branch: str):
        """Push given local branch to branch in forked repository."""
        self.execute(
            [
                "push",
                "--force",
                credentials["username"],
                f"{local_branch}:{fork_branch}",
            ]
        )

    def configure_fork_remote(self, push_url: str, remote_name: str):
        """Configure fork remote repository."""
        self.log(
            f"Configuring fork remote '{remote_name}': {push_url}", level=logging.INFO
        )
        self.config_update(
            # Push url
            (f'remote "{remote_name}"', "pushurl", push_url),  # noqa: B028
        )

    def fork(self, credentials: dict):
        """Create fork of original repository if one doesn't exist yet."""
        remotes = self.execute(["remote"]).splitlines()
        if credentials["username"] not in remotes:
            self.create_fork(credentials)

    def push(self, branch: str):
        """
        Fork repository on GitHub and push changes.

        Pushes changes to *-weblate branch on fork and creates pull request against
        original repository.
        """
        credentials = self.get_credentials()
        if branch and branch != self.branch:
            fork_remote = "origin"
            fork_branch = branch
            super().push(branch)
        else:
            fork_remote = credentials["username"]
            self.fork(credentials)
            if self.component is not None:
                fork_branch = (
                    f"weblate-{self.component.project.slug}-{self.component.slug}"
                )
            else:
                fork_branch = f"weblate-{self.branch}"
            self.push_to_fork(credentials, self.branch, fork_branch)
        self.create_pull_request(credentials, self.branch, fork_remote, fork_branch)

    def create_fork(self, credentials: dict):
        raise NotImplementedError

    def get_fork_failed_message(
        self, error: str, credentials: dict, response: requests.Response
    ) -> str:
        hostname = credentials["hostname"]
        username = credentials["username"]
        if response.status_code == 404:
            error = f"Repository not found. Check whether exists and {username} has access to it."
        if error.strip():
            return f"Could not fork repository at {hostname}: {error}"
        return f"Could not fork repository at {hostname}"

    def create_pull_request(
        self, credentials: dict, origin_branch: str, fork_remote: str, fork_branch: str
    ):
        raise NotImplementedError

    def get_merge_message(self):
        lines = render_template(
            self.component.pull_message.strip(), component=self.component
        ).splitlines()
        return lines[0], "\n".join(lines[1:]).strip()

    def format_api_host(self, host):
        return host

    def get_headers(self, credentials: dict):
        return {
            "Accept": "application/json",
            "Authorization": f"token {credentials['token']}",
        }

    def get_error_message(self, response_data: dict) -> str:
        """
        Log and parse all errors.

        Sometimes GitHub returns the error
        messages in an errors list instead of the message. Sometimes, there
        is no errors list. Hence the different logics.
        """
        if not isinstance(response_data, dict):
            return ""
        errors = []
        for extra in ("message", "error", "error_description", "errors"):
            messages = response_data.get(extra)
            if messages is None:
                continue
            if isinstance(messages, str):
                errors.append(messages)
            elif isinstance(messages, list):
                for error in messages:
                    if isinstance(error, str):
                        line = error
                    else:
                        line = error.get("message", str(error))
                    errors.append(line)
            elif isinstance(messages, dict):
                errors.extend(f"{key}: {error}" for key, error in messages.items())
            else:
                self.log(
                    f"failed to parse HTTP response message: {messages!r}",
                    level=logging.WARNING,
                )

        if errors:
            for error in errors:
                self.log(error, level=logging.DEBUG)

        return ", ".join(errors)

    def should_retry(self, response, response_data):
        retry_after = response.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            # Cap sleeping to 60 seconds
            self.set_next_request_time(
                min(int(retry_after), 6 * max(settings.VCS_API_DELAY, 10))
            )
            return True
        return False

    @cached_property
    def request_time_cache_key(self):
        vcs_id = self.get_identifier()
        return f"vcs:request-time:{vcs_id}"

    def set_next_request_time(self, delay: int):
        cache.set(self.request_time_cache_key, time() + delay)

    def request(
        self,
        method: str,
        credentials: dict,
        url: str,
        data: dict | None = None,
        params: dict | None = None,
        json: dict | None = None,
        retry: int = 0,
    ) -> tuple[dict, requests.Response, str]:
        do_retry = False
        vcs_id = self.get_identifier()
        cache_id = self.request_time_cache_key
        lock = WeblateLock(
            data_dir("home"),
            f"vcs:api:{vcs_id}",
            0,
            vcs_id,
            timeout=3 * max(settings.VCS_API_DELAY, 10),
        )
        try:
            with lock:
                next_api_time = cache.get(cache_id)
                now = time()
                if next_api_time is not None and now < next_api_time:
                    with sentry_sdk.start_span(op="api_sleep", description=vcs_id):
                        sleep(next_api_time - now)
                try:
                    response = requests.request(
                        method,
                        url,
                        headers=self.get_headers(credentials),
                        data=data,
                        params=params,
                        json=json,
                    )
                except (OSError, HTTPError) as error:
                    report_error(cause="request")
                    raise RepositoryError(0, str(error)) from error

                # GitHub recommends a delay between 2 requests of at least 1s,
                # but in reality this hits secondary rate limits.
                self.set_next_request_time(settings.VCS_API_DELAY)

                self.add_response_breadcrumb(response)
                try:
                    response_data = response.json()
                except JSONDecodeError as error:
                    report_error(cause="request json decoding")
                    response.raise_for_status()
                    raise RepositoryError(0, str(error)) from error

                if self.should_retry(response, response_data):
                    do_retry = True
        except WeblateLockTimeoutError:
            do_retry = True

        if do_retry:
            retry += 1
            if retry > 10:
                raise RepositoryError(0, "Too many retries")
            return self.request(method, credentials, url, data, params, json, retry)

        return response_data, response, self.get_error_message(response_data)


class GithubRepository(GitMergeRequestBase):
    name = gettext_lazy("GitHub pull request")
    identifier = "github"
    _version = None
    API_TEMPLATE = "{scheme}://{host}/{suffix}repos/{owner}/{slug}"
    push_label = gettext_lazy(
        "This will push changes and create a GitHub pull request."
    )

    def format_api_host(self, host):
        if host == "github.com":
            return "api.github.com"
        return host

    def format_url(
        self, scheme: str, hostname: str, owner: str, slug: str, **extra: str
    ) -> str:
        suffix = ""
        # In case the hostname of the repository does not point to "github.com" assume
        # that it is on a GitHub Enterprise server, which has uses a different base URL
        # for the API:
        if hostname != "api.github.com":
            suffix = "api/v3/"
        return super().format_url(scheme, hostname, owner, slug, suffix=suffix, **extra)

    def get_headers(self, credentials: dict):
        headers = super().get_headers(credentials)
        headers["Accept"] = "application/vnd.github.v3+json"
        return headers

    def should_retry(self, response, response_data):
        if super().should_retry(response, response_data):
            return True
        # https://docs.github.com/rest/overview/resources-in-the-rest-api#secondary-rate-limits
        if (
            "message" in response_data
            and "You have exceeded a secondary rate limit" in response_data["message"]
        ):
            self.set_next_request_time(6 * max(settings.VCS_API_DELAY, 10))
            return True
        return False

    def create_fork(self, credentials: dict):
        fork_url = "{}/forks".format(credentials["url"])

        # GitHub API returns the entire data of the fork, in case the fork
        # already exists. Hence this is perfectly handled, if the fork already
        # exists in the remote side.
        response_data, response, error = self.request("post", credentials, fork_url)
        if "ssh_url" not in response_data:
            raise RepositoryError(
                0, self.get_fork_failed_message(error, credentials, response)
            )
        self.configure_fork_remote(response_data["ssh_url"], credentials["username"])

    def create_pull_request(
        self,
        credentials: dict,
        origin_branch: str,
        fork_remote: str,
        fork_branch: str,
        retry_fork: bool = True,
    ):
        """
        Create pull request.

        Use to merge branch in forked repository into branch of remote repository.
        """
        if fork_remote == "origin":
            head = fork_branch
        else:
            head = f"{fork_remote}:{fork_branch}"
        pr_url = "{}/pulls".format(credentials["url"])
        title, description = self.get_merge_message()
        request = {
            "head": head,
            "base": origin_branch,
            "title": title,
            "body": description,
        }
        response_data, _response, error_message = self.request(
            "post", credentials, pr_url, json=request
        )

        # Check for an error. If the error has a message saying A pull request already
        # exists, then we ignore that, else raise an error. Currently, since the API
        # doesn't return any other separate indication for a pull request existing
        # compared to other errors, checking message seems to be the only option
        if "url" not in response_data:
            # Gracefully handle pull request already exists or nothing to merge cases
            if (
                "A pull request already exists" in error_message
                or "No commits between " in error_message
            ):
                return

            if "Validation Failed" in error_message:
                for error in response_data["errors"]:
                    if error.get("field") == "head" and retry_fork:
                        # This most likely indicates that Weblate repository has moved
                        # and we should create a fresh fork.
                        self.create_fork(credentials)
                        self.create_pull_request(
                            credentials,
                            origin_branch,
                            fork_remote,
                            fork_branch,
                            retry_fork=False,
                        )
                        return

            raise RepositoryError(0, f"Pull request failed: {error_message}")


class GiteaRepository(GitMergeRequestBase):
    name = gettext_lazy("Gitea pull request")
    identifier = "gitea"
    _version = None
    API_TEMPLATE = "{scheme}://{host}/api/v1/repos/{owner}/{slug}"
    push_label = gettext_lazy("This will push changes and create a Gitea pull request.")

    def create_fork(self, credentials: dict):
        fork_url = "{}/forks".format(credentials["url"])

        # Empty json body is required here, otherwise we'll get an
        # "Empty Content-Type" error from gitea.
        response_data, response, error = self.request(
            "post", credentials, fork_url, json={}
        )
        if (
            "message" in response_data
            and "repository is already forked by user" in error
        ) or response.status_code == 409:
            # we have to get the repository again if it is already forked
            response_data, response, error = self.request(
                "get", credentials, credentials["url"]
            )
        if "ssh_url" not in response_data:
            raise RepositoryError(
                0, self.get_fork_failed_message(error, credentials, response)
            )
        self.configure_fork_remote(response_data["ssh_url"], credentials["username"])

    def create_pull_request(
        self,
        credentials: dict,
        origin_branch: str,
        fork_remote: str,
        fork_branch: str,
        retry_fork: bool = True,
    ):
        """
        Create pull request.

        Use to merge branch in forked repository into branch of remote repository.
        """
        if fork_remote == "origin":
            head = fork_branch
        else:
            head = f"{fork_remote}:{fork_branch}"
        pr_url = "{}/pulls".format(credentials["url"])
        title, description = self.get_merge_message()
        request = {
            "head": head,
            "base": origin_branch,
            "title": title,
            "body": description,
        }
        response_data, _response, error_message = self.request(
            "post", credentials, pr_url, json=request
        )

        # Check for an error. If the error has a message saying pull request already
        # exists, then we ignore that, else raise an error. Currently, since the API
        # doesn't return any other separate indication for a pull request existing
        # compared to other errors, checking message seems to be the only option
        if "url" not in response_data:
            # Gracefully handle pull request already exists
            if "pull request already exists for these targets" in error_message:
                return

            raise RepositoryError(0, f"Pull request failed: {error_message}")


class LocalRepository(GitRepository):
    """Local filesystem driver with no upstream repo."""

    name = gettext_lazy("No remote repository")
    identifier = "local"
    default_branch = "main"
    supports_push = False

    def configure_remote(
        self, pull_url: str, push_url: str, branch: str, fast: bool = True
    ):
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

    def merge(
        self, abort: bool = False, message: str | None = None, no_ff: bool = False
    ):
        return

    def list_remote_branches(self):
        return []

    @classmethod
    def get_remote_branch(cls, repo: str):  # noqa: ARG003
        return cls.default_branch

    @classmethod
    def _init(cls, path: str):
        super()._init(path)
        with open(os.path.join(path, "README.md"), "w") as handle:
            handle.write("Translations repository created by Weblate\n")
            handle.write("==========================================\n")
            handle.write("\n")
            handle.write("See https://weblate.org/ for more info.\n")
        cls._popen(["add", "README.md"], path)
        cls._popen(["commit", "--message", "Repository created by Weblate"], path)

    @classmethod
    def _clone(
        cls,
        source: str,  # noqa: ARG003
        target: str,
        branch: str,  # noqa: ARG003
    ):
        if not os.path.exists(target):
            os.makedirs(target)
        cls._init(target)

    @cached_property
    def last_remote_revision(self):
        return self.last_revision

    @classmethod
    def from_zip(cls, target, zipfile):
        # Create empty repo
        if os.path.exists(target):
            remove_tree(target)
        cls._clone("local:", target, cls.default_branch)
        # Extract zip file content, ignoring some files
        zipobj = ZipFile(zipfile)
        names = [name for name in zipobj.namelist() if not is_excluded(name)]
        zipobj.extractall(path=target, members=names)
        # Add to repository
        repo = cls(target)
        with repo.lock:
            repo.execute(["add", target])
            if repo.needs_commit():
                repo.commit("ZIP file uploaded into Weblate")
        return repo

    @classmethod
    def from_files(cls, target, files):
        # Create empty repo
        if os.path.exists(target):
            remove_tree(target)
        cls._clone("local:", target, cls.default_branch)
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
                repo.commit("Started translation using Weblate")
        return repo


class GitLabRepository(GitMergeRequestBase):
    name = gettext_lazy("GitLab merge request")
    identifier = "gitlab"
    _version = None
    API_TEMPLATE = "{scheme}://{host}/api/v4/projects/{owner_url}%2F{slug_url}"
    push_label = gettext_lazy(
        "This will push changes and create a GitLab merge request."
    )

    def get_forked_url(self, credentials: dict) -> str:
        """
        Returns GitLab API URL for the forked repository.

        To send a MR to GitLab via API, one needs to send request to the
        API URL of the forked repository along with the target project ID
        (unlike GitHub where the PR is sent to the target project's API URL).
        """
        target_path = credentials["url"].split("/")[-1]
        cmd = ["remote", "get-url", "--push", credentials["username"]]
        fork_remotes = self.execute(cmd, needs_lock=False, merge_err=False).splitlines()
        fork_path = urllib.parse.quote(
            fork_remotes[0].split(":")[-1].replace(".git", ""),
            safe="",
        )
        return credentials["url"].replace(target_path, fork_path)

    def get_headers(self, credentials: dict):
        headers = super().get_headers(credentials)
        headers["Authorization"] = f"Bearer {credentials['token']}"
        return headers

    def get_target_project_id(self, credentials: dict):
        response_data, _response, error = self.request(
            "get", credentials, credentials["url"]
        )
        if "id" not in response_data:
            raise RepositoryError(0, f"Could not get project: {error}")
        return response_data["id"]

    def configure_fork_features(self, credentials: dict, forked_url: str):
        """
        Disable features in fork.

        GitLab initializes a lot of the features in the fork
        that are not desirable, such as merge requests, issues, etc.
        This function is intended to disable all such features by
        editing the forked repo.
        """
        access_level_dict = {
            "issues_access_level": "disabled",
            "forking_access_level": "disabled",
            "builds_access_level": "enabled",
            "wiki_access_level": "disabled",
            "snippets_access_level": "disabled",
            "pages_access_level": "disabled",
        }
        response_data, _response, error = self.request(
            "put", credentials, forked_url, json=access_level_dict
        )
        if "web_url" not in response_data:
            raise RepositoryError(0, f"Could not modify fork {error}")

    def create_fork(self, credentials: dict):
        get_fork_url = "{}/forks?owned=True".format(credentials["url"])
        fork_url = "{}/fork".format(credentials["url"])
        forked_repo = None

        # Check if a fork already exists owned by the current user.
        # If fork already exists, set that fork as remote.
        # Else, create a new fork
        response_data, response, error = self.request("get", credentials, get_fork_url)
        for fork in response_data:
            # Since owned=True returns forks from both the user's repo and the forks
            # in all the groups owned by the user, hence we need the below logic
            # to find the fork within the user repo and not the groups
            if "owner" in fork and fork["owner"]["username"] == credentials["username"]:
                forked_repo = fork

        if forked_repo is None:
            forked_repo, response, error = self.request("post", credentials, fork_url)
            # If a repo with the name of the fork already exist, append numeric
            # as suffix to name and path to use that as repo name and path.
            if (
                "ssh_url_to_repo" not in response_data
                and "has already been taken" in error
            ):
                fork_name = "{}-{}".format(
                    credentials["url"].split("%2F")[-1],
                    random.randint(1000, 9999),  # noqa: S311
                )
                forked_repo, response, error = self.request(
                    "post",
                    credentials,
                    fork_url,
                    json={"name": fork_name, "path": fork_name},
                )

            if "ssh_url_to_repo" not in forked_repo:
                raise RepositoryError(
                    0, self.get_fork_failed_message(error, credentials, response)
                )

        self.configure_fork_features(credentials, forked_repo["_links"]["self"])
        self.configure_fork_remote(
            forked_repo["ssh_url_to_repo"], credentials["username"]
        )

    def create_pull_request(
        self, credentials: dict, origin_branch: str, fork_remote: str, fork_branch: str
    ):
        """
        Create pull request.

        Use to merge branch in forked repository into branch of remote repository.
        """
        target_project_id = None
        pr_url = "{}/merge_requests".format(credentials["url"])
        if fork_remote != "origin":
            # GitLab MR works a little differently from GitHub. The MR needs
            # to be sent with the fork's API URL along with a parameter mentioning
            # the target project ID
            target_project_id = self.get_target_project_id(credentials)
            pr_url = f"{self.get_forked_url(credentials)}/merge_requests"

        title, description = self.get_merge_message()
        request = {
            "source_branch": fork_branch,
            "target_branch": origin_branch,
            "title": title,
            "description": description,
            "target_project_id": target_project_id,
        }
        response_data, _response, error = self.request(
            "post", credentials, pr_url, request
        )

        if (
            "web_url" not in response_data
            and "open merge request already exists" not in error
        ):
            raise RepositoryError(-1, f"Could not create pull request: {error}")


class PagureRepository(GitMergeRequestBase):
    name = gettext_lazy("Pagure merge request")
    identifier = "pagure"
    _version = None
    API_TEMPLATE = "{scheme}://{host}/api/0"
    push_label = gettext_lazy(
        "This will push changes and create a Pagure merge request."
    )

    def create_fork(self, credentials: dict):
        fork_url = "{}/fork".format(credentials["url"])

        base_params = {
            "repo": credentials["slug"],
            "wait": True,
        }

        if credentials["owner"]:
            # We have no info on whether the URL part is namespace
            # or username, try both
            params = [
                {"namespace": credentials["owner"]},
                {"username": credentials["owner"]},
            ]
        else:
            params = [{}]

        for param in params:
            param.update(base_params)
            _response_data, response, error = self.request(
                "post", credentials, fork_url, data=param
            )
            if '" cloned to "' in error or "already exists" in error:
                break

        if '" cloned to "' not in error and "already exists" not in error:
            raise RepositoryError(
                0, self.get_fork_failed_message(error, credentials, response)
            )

        url = "ssh://git@{hostname}/forks/{username}/{slug}.git".format(**credentials)
        self.configure_fork_remote(url, credentials["username"])

    def create_pull_request(
        self, credentials: dict, origin_branch: str, fork_remote: str, fork_branch: str
    ):
        """
        Create pull request.

        Use to merge a branch in the forked repository
        into a branch of thr remote repository.
        """
        if credentials["owner"]:
            pr_list_url = "{url}/{owner}/{slug}/pull-requests".format(**credentials)
            pr_create_url = "{url}/{owner}/{slug}/pull-request/new".format(
                **credentials
            )
        else:
            pr_list_url = "{url}/{slug}/pull-requests".format(**credentials)
            pr_create_url = "{url}/{slug}/pull-request/new".format(**credentials)

        # List existing pull requests
        response_data, _response, error_message = self.request(
            "get", credentials, pr_list_url, params={"author": credentials["username"]}
        )
        if error_message:
            raise RepositoryError(0, f"Pull request listing failed: {error_message}")

        if response_data["total_requests"] > 0:
            # Open pull request from us is already there
            return

        title, description = self.get_merge_message()
        request = {
            "branch_from": fork_branch,
            "branch_to": origin_branch,
            "title": title,
            "initial_comment": description,
        }
        if fork_remote != "origin":
            request["repo_from"] = credentials["slug"]
            request["repo_from_username"] = credentials["username"]

        response_data, _response, error_message = self.request(
            "post", credentials, pr_create_url, data=request
        )

        if "id" not in response_data:
            raise RepositoryError(0, f"Pull request failed: {error_message}")


class BitbucketServerRepository(GitMergeRequestBase):
    name = gettext_lazy("Bitbucket Server pull request")
    identifier = "bitbucketserver"
    _version = None
    API_TEMPLATE = "{scheme}://{host}/rest/api/1.0/projects/{owner}/repos/{slug}"
    bb_fork: dict = {}
    push_label = gettext_lazy(
        "This will push changes and create a Bitbucket Server pull request."
    )

    def get_headers(self, credentials: dict):
        headers = super().get_headers(credentials)
        headers["Authorization"] = f"Bearer {credentials['token']}"
        return headers

    def create_fork(self, credentials: dict):
        bb_fork, response, error_message = self.request(
            "post", credentials, credentials["url"], json={}
        )
        self.bb_fork = bb_fork

        # If A fork already exists, get forks from origin and find the user's fork.
        # Since Bitbucket uses projectKey which can be any string (that is not
        # at all related to its name) we need to compare user's forks against
        # remote.
        if "This repository URL is already taken." in error_message:
            page = 0
            self.bb_fork = {}
            forks_url = f'{credentials["url"]}/forks'
            while True:
                forks, response, error_message = self.request(
                    "get", credentials, forks_url, params={"limit": 1000, "start": page}
                )
                if "values" in forks:
                    for f in forks["values"]:
                        fork_slug = f["origin"]["slug"]
                        fork_project_key = f["origin"]["project"]["key"]
                        if (
                            fork_slug == credentials["slug"]
                            and fork_project_key.upper() == credentials["owner"].upper()
                        ):
                            self.bb_fork = f
                            break

                if self.bb_fork or forks["isLastPage"] or not forks["values"]:
                    break

                page += 1

        remote_url = None
        if "links" in self.bb_fork:
            clone_urls = self.bb_fork["links"]["clone"]
            for link in clone_urls:
                if link["name"] == "ssh":
                    remote_url = link["href"]

        if not remote_url:
            raise RepositoryError(
                0, self.get_fork_failed_message(error_message, credentials, response)
            )

        self.configure_fork_remote(remote_url, credentials["username"])

    def get_default_reviewers(self, credentials: dict, fork_branch: str):
        target_repo, _response, error_message = self.request(
            "get", credentials, credentials["url"]
        )
        if "id" not in target_repo:
            return []

        url = credentials["url"].replace("/rest/api/", "/rest/default-reviewers/")
        url = f"{url}/reviewers"
        params = {
            "targetRepoId": target_repo["id"],
            "sourceRepoId": self.bb_fork["id"],
            "targetRefId": self.branch,
            "sourceRefId": fork_branch,
        }
        users, _response, error_message = self.request(
            "get", credentials, url, params=params
        )
        if error_message or not users:
            return []

        return [{"user": user} for user in users]

    def create_pull_request(
        self, credentials: dict, origin_branch: str, fork_remote: str, fork_branch: str
    ):
        # Make sure there's always a fork reference
        if not self.bb_fork:
            self.create_fork(credentials)

        pr_url = f'{credentials["url"]}/pull-requests'
        title, description = self.get_merge_message()
        request_body = {
            "title": title,
            "description": description,
            "toRef": {
                "id": f"refs/heads/{origin_branch}",
                "repository": {
                    "slug": credentials["slug"],
                    "project": {
                        "key": credentials["owner"].upper(),
                    },
                },
            },
            "fromRef": {
                "id": f"refs/heads/{fork_branch}",
                "repository": {
                    "slug": self.bb_fork["slug"],
                    "project": {"key": self.bb_fork["project"]["key"].upper()},
                },
            },
            "reviewers": self.get_default_reviewers(credentials, fork_branch),
        }

        response_data, _response, error_message = self.request(
            "post", credentials, pr_url, json=request_body
        )

        """
        Bitbucket Server will return an error if a PR already exists.
        The push method in the parent class pushes changes to the correct
        fork or branch, and always calls this create_pull_request method after.
        If the PR exists already just do nothing because Bitbucket will
        auto-update the PR if the from ref is updated.
        """
        if "id" not in response_data:
            pr_exist_message = (
                "Only one pull request may be open "
                "for a given source and target branch"
            )
            if pr_exist_message in error_message:
                return
            raise RepositoryError(0, f"Pull request failed: {error_message}")
