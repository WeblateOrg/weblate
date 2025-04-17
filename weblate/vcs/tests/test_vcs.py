# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import copy
import os.path
import re
import shutil
import tempfile
from typing import Any, NoReturn
from unittest.mock import patch

import responses
from django.test import TestCase
from django.test.utils import override_settings
from django.utils import timezone
from responses import matchers

from weblate.trans.models import Component, Project
from weblate.trans.tests.utils import RepoTestMixin, TempDirMixin
from weblate.vcs.base import Repository, RepositoryError
from weblate.vcs.git import (
    AzureDevOpsRepository,
    BitbucketCloudRepository,
    BitbucketServerRepository,
    GiteaRepository,
    GitForcePushRepository,
    GithubRepository,
    GitLabRepository,
    GitRepository,
    GitWithGerritRepository,
    LocalRepository,
    PagureRepository,
    SubversionRepository,
)
from weblate.vcs.mercurial import HgRepository


class AzureDevOpsFakeRepository(AzureDevOpsRepository):
    _is_supported = None
    _version = None


class GithubFakeRepository(GithubRepository):
    _is_supported = None
    _version = None


class GitLabFakeRepository(GitLabRepository):
    _is_supported = None
    _version = None


class GiteaFakeRepository(GiteaRepository):
    _is_supported = None
    _version = None


class PagureFakeRepository(PagureRepository):
    _is_supported = None
    _version = None


class BitbucketServerFakeRepository(BitbucketServerRepository):
    _is_supported = None
    _version = None


class BitbucketCloudFakeRepository(BitbucketCloudRepository):
    _is_supported = None
    _version = None


class GitTestRepository(GitRepository):
    _is_supported = None
    _version = None


class NonExistingRepository(GitRepository):
    _is_supported = None
    _version = None
    _cmd = "nonexisting-command"


class GitVersionRepository(GitRepository):
    _is_supported = None
    _version = None
    req_version = "200000"


class GitNoVersionRepository(GitRepository):
    _is_supported = None
    _version = None
    req_version = None


class RepositoryTest(TestCase):
    def test_not_supported(self) -> None:
        self.assertFalse(NonExistingRepository.is_supported())
        with self.assertRaises(FileNotFoundError):
            NonExistingRepository.get_version()
        # Test exception caching
        with self.assertRaises(FileNotFoundError):
            NonExistingRepository.get_version()

    def test_not_supported_version(self) -> None:
        self.assertFalse(GitVersionRepository.is_supported())

    def test_is_supported(self) -> None:
        self.assertTrue(GitTestRepository.is_supported())

    def test_is_supported_no_version(self) -> None:
        self.assertTrue(GitNoVersionRepository.is_supported())

    def test_is_supported_cache(self) -> None:
        GitTestRepository.is_supported()
        self.assertTrue(GitTestRepository.is_supported())


class VCSGitTest(TestCase, RepoTestMixin, TempDirMixin):
    _class: type[Repository] = GitRepository
    _vcs = "git"
    _sets_push = True
    _remote_branches = ["main", "translations"]
    _remote_branch = "main"

    def setUp(self) -> None:
        super().setUp()
        if not self._class.is_supported():
            self.skipTest("Not supported")

        self.clone_test_repos()

        self.create_temp()
        self.repo = self.clone_repo(self.tempdir)
        self.fixup_repo(self.repo)

    def fixup_repo(self, repo) -> None:
        return

    def get_remote_repo_url(self):
        return self.format_local_path(getattr(self, f"{self._vcs}_repo_path"))

    def get_fake_component(self):
        return Component(
            slug="test",
            name="Test",
            project=Project(name="Test", slug="test", pk=-1),
            pk=-1,
        )

    def clone_repo(self, path):
        return self._class.clone(
            self.get_remote_repo_url(),
            path,
            self._remote_branch,
            component=self.get_fake_component(),
        )

    def test_weblate_repo_init(self) -> None:
        """Test repo workflow as used by Weblate."""
        with tempfile.TemporaryDirectory() as tempdir:
            repo = self._class(
                tempdir, branch=self._remote_branch, component=self.get_fake_component()
            )
            with repo.lock:
                repo.configure_remote(
                    self.get_remote_repo_url(),
                    "",
                    self._remote_branch,
                )
                repo.update_remote()
                repo.configure_branch(self._remote_branch)
                repo.merge()

    def tearDown(self) -> None:
        self.remove_temp()

    def add_remote_commit(self, conflict=False, rename=False) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo = self.clone_repo(tempdir)
            self.fixup_repo(repo)

            with repo.lock:
                repo.set_committer("Second Bar", "second@example.net")
                if rename:
                    shutil.move(
                        os.path.join(tempdir, "README.md"),
                        os.path.join(tempdir, "READ ME.md"),
                    )
                    if self._vcs == "mercurial":
                        repo.remove(["README.md"], "Removed readme")
                        filenames = ["READ ME.md"]
                    else:
                        filenames = None
                else:
                    filename = "testfile" if conflict else "test2"
                    # Create test file
                    with open(os.path.join(tempdir, filename), "w") as handle:
                        handle.write("SECOND TEST FILE\n")
                    filenames = [filename]

                # Commit it
                repo.commit(
                    "Test commit", "Foo Bar <foo@bar.com>", timezone.now(), filenames
                )

                # Push it
                repo.push("")

    def test_clone(self) -> None:
        # Verify that VCS directory exists
        if self._vcs == "mercurial":
            dirname = ".hg"
        elif self._vcs == "local":
            dirname = ".git"
        else:
            dirname = f".{self._vcs}"
        self.assertTrue(os.path.exists(os.path.join(self.tempdir, dirname)))

    def test_revision(self) -> None:
        self.assertEqual(self.repo.last_revision, self.repo.last_remote_revision)

    def test_update_remote(self) -> None:
        with self.repo.lock:
            self.repo.update_remote()

    def test_push(self, branch: str = "") -> None:
        with self.repo.lock:
            self.repo.push(branch)

    def test_push_commit(self) -> None:
        self.test_commit()
        self.test_push()

    def test_push_branch(self) -> None:
        self.test_commit()
        self.test_push("push-branch")

    def test_reset(self) -> None:
        with self.repo.lock:
            original = self.repo.last_revision
            self.repo.reset()
            self.assertEqual(original, self.repo.last_revision)
        self.test_commit()
        with self.repo.lock:
            self.assertNotEqual(original, self.repo.last_revision)
            self.repo.reset()
            self.assertEqual(original, self.repo.last_revision)

    def test_cleanup(self) -> None:
        with self.repo.lock:
            self.repo.cleanup()

    def test_merge_commit(self) -> None:
        self.test_commit()
        self.test_merge()

    def test_rebase_commit(self) -> None:
        self.test_commit()
        self.test_rebase()

    def test_merge_remote(self) -> None:
        self.add_remote_commit()
        self.test_merge()

    def test_merge_remote_no_ff(self) -> None:
        self.add_remote_commit()
        self.test_merge(no_ff=True)

    def test_rebase_remote(self) -> None:
        self.add_remote_commit()
        self.test_rebase()

    def test_merge_both(self) -> None:
        self.add_remote_commit()
        self.test_commit()
        self.test_merge()

    def test_rebase_both(self) -> None:
        self.add_remote_commit()
        self.test_commit()
        self.test_rebase()

    def test_merge_conflict(self) -> None:
        self.add_remote_commit(conflict=True)
        self.test_commit()
        with self.assertRaises(RepositoryError):
            self.test_merge()

    def test_rebase_conflict(self) -> None:
        self.add_remote_commit(conflict=True)
        self.test_commit()
        with self.assertRaises(RepositoryError):
            self.test_rebase()

    def test_upstream_changes(self) -> None:
        self.add_remote_commit()
        with self.repo.lock:
            self.repo.update_remote()
        self.assertEqual(["test2"], self.repo.get_changed_files())

    def test_upstream_changes_rename(self) -> None:
        self.add_remote_commit(rename=True)
        with self.repo.lock:
            self.repo.update_remote()
        self.assertEqual(["README.md", "READ ME.md"], self.repo.get_changed_files())

    def test_merge(self, **kwargs) -> None:
        self.test_update_remote()
        with self.repo.lock:
            self.repo.merge(**kwargs)

    def test_rebase(self) -> None:
        self.test_update_remote()
        with self.repo.lock:
            self.repo.rebase()

    def test_status(self) -> None:
        status = self.repo.status()
        # Older git print up-to-date, newer up to date
        self.assertIn("date with 'origin/main'.", status)

    def test_needs_commit(self) -> None:
        self.assertFalse(self.repo.needs_commit())
        with open(os.path.join(self.tempdir, "README.md"), "a") as handle:
            handle.write("CHANGE")
        self.assertTrue(self.repo.needs_commit())
        self.assertTrue(self.repo.needs_commit(["README.md"]))
        self.assertFalse(self.repo.needs_commit(["dummy"]))

    def check_valid_info(self, info) -> None:
        self.assertIn("summary", info)
        self.assertNotEqual(info["summary"], "")
        self.assertIn("author", info)
        self.assertNotEqual(info["author"], "")
        self.assertIn("authordate", info)
        self.assertNotEqual(info["authordate"], "")
        self.assertIn("commit", info)
        self.assertNotEqual(info["commit"], "")
        self.assertIn("commitdate", info)
        self.assertNotEqual(info["commitdate"], "")
        self.assertIn("revision", info)
        self.assertNotEqual(info["revision"], "")
        self.assertIn("shortrevision", info)
        self.assertNotEqual(info["shortrevision"], "")

    def test_revision_info(self) -> None:
        # Latest commit
        info = self.repo.get_revision_info(self.repo.last_revision)
        self.check_valid_info(info)

    def test_needs_merge(self) -> None:
        self.assertFalse(self.repo.needs_merge())
        self.assertFalse(self.repo.needs_push())

    def test_needs_push(self) -> None:
        self.test_commit()
        self.assertTrue(self.repo.needs_push())

    def test_is_supported(self) -> None:
        self.assertTrue(self._class.is_supported())

    def test_get_version(self) -> None:
        self.assertNotEqual(self._class.get_version(), "")

    def test_set_committer(self) -> None:
        with self.repo.lock:
            self.repo.set_committer("Foo Bar Žač", "foo@example.net")
        self.assertEqual(self.repo.get_config("user.name"), "Foo Bar Žač")
        self.assertEqual(self.repo.get_config("user.email"), "foo@example.net")

    def test_commit(self, committer="Foo Bar") -> None:
        committer_email = f"{committer} <foo@example.com>"
        with self.repo.lock:
            self.repo.set_committer(committer, "foo@example.net")
        # Create test file
        with open(os.path.join(self.tempdir, "testfile"), "wb") as handle:
            handle.write(b"TEST FILE\n")

        oldrev = self.repo.last_revision
        # Commit it
        with self.repo.lock:
            self.repo.commit(
                "Test commit",
                committer_email,
                timezone.now(),
                ["testfile", "nonexistingfile"],
            )
        # Check we have new revision
        self.assertNotEqual(oldrev, self.repo.last_revision)
        info = self.repo.get_revision_info(self.repo.last_revision)
        self.assertEqual(info["author"], committer_email)

        # Check file hash
        self.assertEqual(
            self.repo.get_object_hash("testfile"),
            "fafd745150eb1f20fc3719778942a96e2106d25b",
        )

        # Check no-op commit
        oldrev = self.repo.last_revision
        with self.repo.lock:
            self.repo.commit("test commit", committer_email)
        self.assertEqual(oldrev, self.repo.last_revision)

    def test_delete(self, committer="Foo Bar") -> None:
        self.test_commit(committer)
        committer_email = f"{committer} <foo@example.com>"

        # Delete the file created before
        oldrev = self.repo.last_revision
        os.unlink(os.path.join(self.tempdir, "testfile"))

        # Commit it
        with self.repo.lock:
            self.repo.commit(
                "Test remove commit",
                committer_email,
                timezone.now(),
                ["testfile"],
            )

        # Check we have new revision
        self.assertNotEqual(oldrev, self.repo.last_revision)
        info = self.repo.get_revision_info(self.repo.last_revision)
        self.assertEqual(info["author"], committer_email)

    def test_commit_unicode(self) -> None:
        self.test_commit("Zkouška Sirén")

    def test_remove(self) -> None:
        with self.repo.lock:
            self.repo.set_committer("Foo Bar", "foo@example.net")
        self.assertTrue(os.path.exists(os.path.join(self.tempdir, "po/cs.po")))
        with self.repo.lock:
            self.repo.remove(["po/cs.po"], "Remove Czech translation")
        self.assertFalse(os.path.exists(os.path.join(self.tempdir, "po/cs.po")))

    def test_object_hash(self) -> None:
        obj_hash = self.repo.get_object_hash("README.md")
        self.assertEqual(len(obj_hash), 40)

    def test_configure_remote(self) -> None:
        with self.repo.lock:
            self.repo.configure_remote("pullurl", "pushurl", "branch")
            self.assertEqual(self.repo.get_config("remote.origin.url"), "pullurl")
            if self._sets_push:
                self.assertEqual(
                    self.repo.get_config("remote.origin.pushURL"), "pushurl"
                )
            # Test that we handle not set fetching
            self.repo.execute(["config", "--unset", "remote.origin.fetch"])
            self.repo.configure_remote("pullurl", "pushurl", "branch")
            self.assertEqual(
                self.repo.get_config("remote.origin.fetch"),
                "+refs/heads/branch:refs/remotes/origin/branch",
            )
            self.repo.configure_remote("pullurl", "pushurl", "branch", fast=False)
            self.assertEqual(
                self.repo.get_config("remote.origin.fetch"),
                "+refs/heads/*:refs/remotes/origin/*",
            )

    def test_configure_remote_no_push(self) -> None:
        with self.repo.lock:
            if self._sets_push:
                self.repo.configure_remote("pullurl", "", "branch")
                with self.assertRaises(RepositoryError):
                    self.repo.get_config("remote.origin.pushURL")
                self.repo.configure_remote("pullurl", "push", "branch")
                self.assertEqual(self.repo.get_config("remote.origin.pushURL"), "push")

                # Inject blank value
                self.repo.config_update(('remote "origin"', "pushurl", ""))

                # Try to remove it
                self.repo.configure_remote("pullurl", None, "branch")

                with self.assertRaises(RepositoryError):
                    self.repo.get_config("remote.origin.pushURL")

    def test_configure_branch(self) -> None:
        # Existing branch
        with self.repo.lock:
            self.repo.configure_branch(self.repo.get_remote_branch(self.tempdir))

            with self.assertRaises(RepositoryError):
                self.repo.configure_branch("branch")

    def test_get_file(self) -> None:
        self.assertIn("msgid", self.repo.get_file("po/cs.po", self.repo.last_revision))

    def test_remote_branches(self) -> None:
        # The initial setup clones just single branch
        self.assertEqual(
            [self._remote_branch] if self._remote_branches else [],
            self.repo.list_remote_branches(),
        )

        # Full configure adds all other branches
        with self.repo.lock:
            self.repo.configure_remote(
                self.get_remote_repo_url(), "", self.repo.branch, fast=False
            )
            self.repo.update_remote()
        self.assertEqual(self._remote_branches, self.repo.list_remote_branches())

    def test_remote_branch(self) -> None:
        self.assertEqual(self._remote_branch, self.repo.get_remote_branch(self.tempdir))


class VCSGitForcePushTest(VCSGitTest):
    _class = GitForcePushRepository


class VCSGitUpstreamTest(VCSGitTest):
    def add_remote_commit(self, conflict=False, rename=False) -> None:
        # Use Git to create changed upstream repo
        backup = self._class
        self._class = GitRepository
        try:
            super().add_remote_commit(conflict, rename)
        finally:
            self._class = backup


@override_settings(
    GITEA_CREDENTIALS={"try.gitea.io": {"username": "test", "token": "token"}}
)
class VCSGiteaTest(VCSGitUpstreamTest):
    _class = GiteaFakeRepository
    _vcs = "git"
    _sets_push = False

    def mock_responses(self, pr_response, pr_status=200) -> None:
        """
        Mock response helper function.

        This function will mock request responses for both fork and PRs
        """
        responses.add(
            responses.POST,
            "https://try.gitea.io/api/v1/repos/WeblateOrg/test/forks",
            json={
                "ssh_url": "git@gitea.io:test/test.git",
                "clone_url": "https://gitea.io/test/test.git",
            },
            match=[matchers.header_matcher({"Content-Type": "application/json"})],
        )
        responses.add(
            responses.POST,
            "https://try.gitea.io/api/v1/repos/WeblateOrg/test/pulls",
            json=pr_response,
            status=pr_status,
            match=[matchers.header_matcher({"Content-Type": "application/json"})],
        )

    def test_api_url_try_gitea(self) -> None:
        self.repo.component.repo = "https://try.gitea.io/WeblateOrg/test.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://try.gitea.io/api/v1/repos/WeblateOrg/test",
        )
        self.repo.component.repo = "http://try.gitea.io/WeblateOrg/test.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "http://try.gitea.io/api/v1/repos/WeblateOrg/test",
        )
        self.repo.component.repo = "git@try.gitea.io:WeblateOrg/test.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://try.gitea.io/api/v1/repos/WeblateOrg/test",
        )
        self.repo.component.repo = "https://try.gitea.io/WeblateOrg/test"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://try.gitea.io/api/v1/repos/WeblateOrg/test",
        )
        self.repo.component.repo = "https://try.gitea.io/WeblateOrg/test/"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://try.gitea.io/api/v1/repos/WeblateOrg/test",
        )
        self.repo.component.repo = "git@try.gitea.io:WeblateOrg/test.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://try.gitea.io/api/v1/repos/WeblateOrg/test",
        )
        self.repo.component.repo = "try.gitea.io:WeblateOrg/test.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://try.gitea.io/api/v1/repos/WeblateOrg/test",
        )
        self.repo.component.repo = "try.gitea.io:WeblateOrg/test.github.io"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://try.gitea.io/api/v1/repos/WeblateOrg/test.github.io",
        )
        with override_settings(
            GITEA_CREDENTIALS={
                "try.gitea.io": {"username": "test", "token": "token", "scheme": "http"}
            }
        ):
            self.repo.component.repo = "git@try.gitea.io:WeblateOrg/test.git"
            self.assertEqual(
                self.repo.get_credentials()["url"],
                "http://try.gitea.io/api/v1/repos/WeblateOrg/test",
            )

        with override_settings(
            GITEA_CREDENTIALS={
                "try.gitea.io": {
                    "username": "test",
                    "token": "token",
                    "scheme": "https",
                }
            }
        ):
            self.repo.component.repo = "http://try.gitea.io/WeblateOrg/test/"
            self.assertEqual(
                self.repo.get_credentials()["url"],
                "https://try.gitea.io/api/v1/repos/WeblateOrg/test",
            )

    @responses.activate
    def test_push(self, branch: str = "") -> None:
        self.repo.component.repo = "https://try.gitea.io/WeblateOrg/test.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        self.mock_responses(
            pr_response={"url": "https://try.gitea.io/WeblateOrg/test/pull/1"}
        )
        super().test_push(branch)
        mock_push_to_fork.stop()

    @responses.activate
    def test_pull_request_error(self, branch: str = "") -> None:
        self.repo.component.repo = "https://try.gitea.io/WeblateOrg/test.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        # Mock PR to return error
        self.mock_responses(pr_status=422, pr_response={"message": "Some error"})

        with self.assertRaises(RepositoryError):
            super().test_push(branch)
        mock_push_to_fork.stop()

    @responses.activate
    def test_pull_request_exists(self, branch: str = "") -> None:
        self.repo.component.repo = "https://try.gitea.io/WeblateOrg/test.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        # Check that it doesn't raise error when pull request already exists
        self.mock_responses(
            pr_status=422,
            pr_response={"message": "pull request already exists for these targets"},
        )

        super().test_push(branch)
        mock_push_to_fork.stop()


@override_settings(
    AZURE_DEVOPS_CREDENTIALS={
        "dev.azure.com": {
            "username": "test",
            "token": "token",
            "organization": "organization",
        }
    }
)
class VCSAzureDevOpsTest(VCSGitUpstreamTest):
    _class = AzureDevOpsFakeRepository
    _vcs = "git"
    _sets_push = False
    _mock_push_to_fork = None

    def setUp(self) -> None:
        super().setUp()
        self.repo.component.repo = (
            "https://dev.azure.com/organization/WeblateOrg/test.git"
        )

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        self._mock_push_to_fork = mock_push_to_fork_patcher.start()
        self._mock_push_to_fork.return_value = ""

    def tearDown(self) -> None:
        self._mock_push_to_fork.stop()
        super().tearDown()

    def mock_responses(self, pr_response, pr_status=200) -> None:
        """
        Mock response helper function.

        This function will mock request responses for PRs
        """
        responses.add(
            responses.POST,
            "https://dev.azure.com/organization/WeblateOrg/_apis/git/repositories/test/pullrequests",
            json=pr_response,
            status=pr_status,
        )
        responses.add(
            responses.POST,
            "https://dev.azure.com/organization/WeblateOrg/_apis/git/repositories",
            json={
                "sshUrl": "git@ssh.dev.azure.com:v3/organization/WeblateOrg/test",
                "remoteUrl": "https://dev.azure.com/v3/organization/WeblateOrg/test.git",
            },
        )
        responses.add(
            responses.GET,
            "https://dev.azure.com/organization/WeblateOrg/_apis/git/repositories/test",
            json={"id": "repo-id", "project": {"id": "org-id"}},
        )
        responses.add(
            responses.GET,
            "https://dev.azure.com/organization/_apis/projects/WeblateOrg",
            json={"id": "proj-id"},
        )
        responses.add(
            responses.POST,
            "https://dev.azure.com/organization/_apis/Contribution/HierarchyQuery?api-version=5.0-preview.1",
            json={
                "dataProviders": {
                    "ms.vss-features.my-organizations-data-provider": {
                        "organizations": [{"id": "org-id"}]
                    }
                }
            },
        )
        responses.add(
            responses.GET,
            "https://dev.azure.com/organization/WeblateOrg/_apis/git/repositories/test/forks/org-id",
            json={"value": []},
        )

    def test_api_url_devops_com(self) -> None:
        # https with .git
        self.repo.component.repo = (
            "https://WeblateOrg@dev.azure.com/organization/WeblateOrg/_git/test.git"
        )
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://dev.azure.com/organization/WeblateOrg/_apis/git/repositories/test",
        )
        # http with .git
        self.repo.component.repo = (
            "http://WeblateOrg@dev.azure.com/organization/WeblateOrg/_git/test.git"
        )
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "http://dev.azure.com/organization/WeblateOrg/_apis/git/repositories/test",
        )
        # https with without .git
        self.repo.component.repo = (
            "https://WeblateOrg@dev.azure.com/organization/WeblateOrg/_git/test"
        )
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://dev.azure.com/organization/WeblateOrg/_apis/git/repositories/test",
        )
        # https with without .git
        self.repo.component.repo = (
            "http://WeblateOrg@dev.azure.com/organization/WeblateOrg/_git/test"
        )
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "http://dev.azure.com/organization/WeblateOrg/_apis/git/repositories/test",
        )
        # https with trailing slash
        self.repo.component.repo = (
            "https://WeblateOrg@dev.azure.com/organization/WeblateOrg/_git/test/"
        )
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://dev.azure.com/organization/WeblateOrg/_apis/git/repositories/test",
        )
        # http with trailing slash
        self.repo.component.repo = (
            "http://WeblateOrg@dev.azure.com/organization/WeblateOrg/_git/test"
        )
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "http://dev.azure.com/organization/WeblateOrg/_apis/git/repositories/test",
        )
        # ssh with username
        self.repo.component.repo = (
            "git@ssh.dev.azure.com:v3/organization/WeblateOrg/test"
        )
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://dev.azure.com/organization/WeblateOrg/_apis/git/repositories/test",
        )
        # ssh without username
        self.repo.component.repo = "ssh.dev.azure.com:v3/organization/WeblateOrg/test"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://dev.azure.com/organization/WeblateOrg/_apis/git/repositories/test",
        )

    @responses.activate
    def test_pull_request_error(self, branch: str = "") -> None:
        # Mock PR to return error
        self.mock_responses(pr_status=403, pr_response={"message": "Some error"})

        with self.assertRaises(RepositoryError):
            super().test_push(branch)

    @responses.activate
    def test_pull_request_exists(self, branch: str = "") -> None:
        # Check that it doesn't raise error when pull request already exists
        self.mock_responses(
            pr_status=409,
            pr_response={
                "message": "TF401179: An active pull request for the source and target branch already exists."
            },
        )

        super().test_push(branch)

    @override_settings(
        AZURE_DEVOPS_CREDENTIALS={
            "dev.azure.com": {
                "username": "test",
                "token": "token",
                "organization": "organization",
                "workItemIds": [1111, 2222],
            }
        }
    )
    @responses.activate
    def test_pull_request_work_item_refs(self, branch: str = "") -> None:
        # Mock PR to return success
        response = {"url": "https://example.com"}
        self.mock_responses(response)
        responses.remove(
            responses.POST,
            "https://dev.azure.com/organization/WeblateOrg/_apis/git/repositories/test/pullrequests",
        )
        responses.post(
            "https://dev.azure.com/organization/WeblateOrg/_apis/git/repositories/test/pullrequests",
            match=[
                matchers.json_params_matcher(
                    {"workItemRefs": [{"id": "1111"}, {"id": "2222"}]},
                    strict_match=False,
                )
            ],
            json=response,
            status=201,
        )

        super().test_push(branch)

    @responses.activate
    def test_push(self, branch: str = "") -> None:
        self.mock_responses(
            pr_response={
                "url": "https://dev.azure.com/organization/WeblateOrg/_apis/git/repositories/test/pullRequests/1"
            }
        )
        super().test_push(branch)

    @responses.activate
    def test_fork_repository_already_exists(self, branch: str = "") -> None:
        # Mock PR to return success
        repositories_url = (
            "https://dev.azure.com/organization/WeblateOrg/_apis/git/repositories"
        )
        responses.add(
            responses.POST,
            repositories_url,
            json={
                "message": "TF400948: A Git repository with the name already exists."
            },
            status=409,
        )
        self.mock_responses({"url": f"{repositories_url}/test/pullRequests/1"})

        super().test_push(branch)

        responses.assert_call_count(repositories_url, 2)

    @responses.activate
    def test_push_where_finds_existing_fork(self, branch: str = "") -> None:
        repositories_url = (
            "https://dev.azure.com/organization/WeblateOrg/_apis/git/repositories"
        )
        self.mock_responses(
            pr_response={"url": f"{repositories_url}/test/pullRequests/1"}
        )

        fork_url = f"{repositories_url}/test/forks/org-id"

        responses.replace(
            responses.GET,
            fork_url,
            json={
                "value": [
                    {
                        "project": {"name": "test"},
                        "sshUrl": "git@ssh.dev.azure.com:v3/organization/WeblateOrg/test",
                        "remoteUrl": "https://dev.azure.com/organization/WeblateOrg/test.git",
                    }
                ]
            },
        )

        super().test_push(branch)

        responses.assert_call_count(repositories_url, 0)

    @responses.activate
    def test_push_when_remote_fork_is_deleted(self, branch: str = "") -> None:
        self.mock_responses(
            pr_response={
                "url": "https://dev.azure.com/organization/WeblateOrg/_apis/git/repositories/test/pullRequests/1"
            }
        )

        with self.repo.lock:
            self.repo.execute(
                [
                    "remote",
                    "add",
                    "test",
                    "git@ssh.this.does.not.exist:v3/org/proj/repo",
                ]
            )

        responses.post(
            "https://this.does.not.exist/org/proj/_apis/git/repositories/repo",
            json={"message": "Not found"},
            status=404,
        )

        super().test_push(branch)

    @responses.activate
    def test_fork_parent_repo_not_found(self, branch: str = "") -> None:
        self.mock_responses(pr_response={})

        responses.replace(
            responses.GET,
            "https://dev.azure.com/organization/WeblateOrg/_apis/git/repositories/test",
            json={"message": "Not found"},
        )

        with self.assertRaises(RepositoryError):
            super().test_push(branch)

    @responses.activate
    def test_creating_fork_fails(self, branch: str = "") -> None:
        self.mock_responses(pr_response={})

        responses.replace(
            responses.POST,
            "https://dev.azure.com/organization/WeblateOrg/_apis/git/repositories",
            json={"message": "Some error"},
        )

        with self.assertRaises(RepositoryError):
            super().test_push(branch)

    @responses.activate
    def test_getting_organization_id_fails(self, branch: str = "") -> None:
        self.mock_responses(
            pr_response={
                "url": "https://dev.azure.com/organization/WeblateOrg/_apis/git/repositories/test/pullRequests/1"
            }
        )

        responses.replace(
            responses.POST,
            "https://dev.azure.com/organization/_apis/Contribution/HierarchyQuery?api-version=5.0-preview.1",
            json={"message": "Some error"},
        )

        with self.assertRaises(RepositoryError):
            super().test_push(branch)

    @responses.activate
    def test_getting_existing_forks_fails(self, branch: str = "") -> None:
        self.mock_responses(
            pr_response={
                "url": "https://dev.azure.com/organization/WeblateOrg/_apis/git/repositories/test/pullRequests/1"
            }
        )

        responses.replace(
            responses.GET,
            "https://dev.azure.com/organization/WeblateOrg/_apis/git/repositories/test/forks/org-id",
            json={"message": "Some error"},
            status=418,
        )

        with self.assertRaises(RepositoryError):
            super().test_push(branch)

    @responses.activate
    def test_fails_when_token_is_considered_invalid(self, branch: str = "") -> None:
        responses.add(
            method=responses.GET,
            url=re.compile(r".*"),
            body="<html><head>Sign in please</head><body></body></html>",
            status=203,
        )

        with self.assertRaises(RepositoryError) as cm:
            super().test_push(branch)

        self.assertEqual("Invalid token", cm.exception.get_message())


@override_settings(
    GITHUB_CREDENTIALS={"api.github.com": {"username": "test", "token": "token"}}
)
class VCSGitHubTest(VCSGitUpstreamTest):
    _class = GithubFakeRepository
    _vcs = "git"
    _sets_push = False

    def mock_responses(self, pr_response, pr_status=200) -> None:
        """
        Mock response helper function.

        This function will mock request responses for both fork and PRs
        """
        responses.add(
            responses.POST,
            "https://api.github.com/repos/WeblateOrg/test/forks",
            json={
                "ssh_url": "git@github.com:test/test.git",
                "clone_url": "https://github.com/test/test.git",
            },
        )
        responses.add(
            responses.POST,
            "https://api.github.com/repos/WeblateOrg/test/pulls",
            json=pr_response,
            status=pr_status,
        )

    def test_api_url_github_com(self) -> None:
        self.repo.component.repo = "https://github.com/WeblateOrg/test.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://api.github.com/repos/WeblateOrg/test",
        )
        self.repo.component.repo = "http://github.com/WeblateOrg/test.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "http://api.github.com/repos/WeblateOrg/test",
        )
        self.repo.component.repo = "https://github.com/WeblateOrg/test"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://api.github.com/repos/WeblateOrg/test",
        )
        self.repo.component.repo = "https://github.com/WeblateOrg/test/"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://api.github.com/repos/WeblateOrg/test",
        )
        self.repo.component.repo = "git@github.com:WeblateOrg/test.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://api.github.com/repos/WeblateOrg/test",
        )
        self.repo.component.repo = "github.com:WeblateOrg/test.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://api.github.com/repos/WeblateOrg/test",
        )
        self.repo.component.repo = "github.com:WeblateOrg/test.github.io"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://api.github.com/repos/WeblateOrg/test.github.io",
        )

    @override_settings(
        GITHUB_CREDENTIALS={
            "self-hosted-ghes.com": {
                "username": "test",
                "token": "token",
            }
        }
    )
    def test_api_url_ghes(self) -> None:
        self.repo.component.repo = "https://self-hosted-ghes.com/WeblateOrg/test.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://self-hosted-ghes.com/api/v3/repos/WeblateOrg/test",
        )
        self.repo.component.repo = "https://self-hosted-ghes.com/WeblateOrg/test"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://self-hosted-ghes.com/api/v3/repos/WeblateOrg/test",
        )
        self.repo.component.repo = "https://self-hosted-ghes.com/WeblateOrg/test/"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://self-hosted-ghes.com/api/v3/repos/WeblateOrg/test",
        )
        self.repo.component.repo = "git@self-hosted-ghes.com:WeblateOrg/test.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://self-hosted-ghes.com/api/v3/repos/WeblateOrg/test",
        )
        self.repo.component.repo = "self-hosted-ghes.com:WeblateOrg/test.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://self-hosted-ghes.com/api/v3/repos/WeblateOrg/test",
        )
        self.repo.component.repo = "self-hosted-ghes.com:WeblateOrg/test.github.io"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://self-hosted-ghes.com/api/v3/repos/WeblateOrg/test.github.io",
        )

    @responses.activate
    def test_push(self, branch: str = "") -> None:
        self.repo.component.repo = "https://github.com/WeblateOrg/test.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        self.mock_responses(
            pr_response={"url": "https://github.com/WeblateOrg/test/pull/1"}
        )
        super().test_push(branch)
        mock_push_to_fork.stop()

    @responses.activate
    def test_pull_request_error(self, branch: str = "") -> None:
        self.repo.component.repo = "https://github.com/WeblateOrg/test.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        # Mock PR to return error
        self.mock_responses(pr_status=422, pr_response={"message": "Some error"})

        with self.assertRaises(RepositoryError):
            super().test_push(branch)
        mock_push_to_fork.stop()

    @responses.activate
    def test_pull_request_exists(self, branch: str = "") -> None:
        self.repo.component.repo = "https://github.com/WeblateOrg/test.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        # Check that it doesn't raise error when pull request already exists
        self.mock_responses(
            pr_status=422,
            pr_response={"errors": [{"message": "A pull request already exists"}]},
        )

        super().test_push(branch)
        mock_push_to_fork.stop()

    def test_merge_message(self) -> None:
        repo = self.repo
        component = repo.component
        component.pull_message = "Test message\n\nBody"
        self.assertEqual(repo.get_merge_message(), ("Test message", "Body"))
        component.pull_message = "Test message\r\n\r\nBody"
        self.assertEqual(repo.get_merge_message(), ("Test message", "Body"))
        component.pull_message = "Test message"
        self.assertEqual(repo.get_merge_message(), ("Test message", ""))
        component.pull_message = "\nTest message\n\n\nBody"
        self.assertEqual(repo.get_merge_message(), ("Test message", "Body"))


@override_settings(
    GITLAB_CREDENTIALS={
        "gitlab.com": {"username": "test", "token": "token"},
        "gitlab.company": {"username": "test", "token": "token"},
    }
)
class VCSGitLabTest(VCSGitUpstreamTest):
    _class = GitLabFakeRepository
    _vcs = "git"
    _sets_push = False

    def mock_fork_responses(self, get_forks, repo_state=200) -> None:
        if repo_state == 409:
            # Response to mock existing of repo with duplicate name
            # In case repo name already taken, append number at the end
            responses.add(
                responses.POST,
                "https://gitlab.com/api/v4/projects/WeblateOrg%2Ftest/fork",
                json={
                    "message": {
                        "name": ["has already been taken"],
                        "path": ["has already been taken"],
                    }
                },
                status=409,
            )
            responses.add(
                responses.POST,
                "https://gitlab.com/api/v4/projects/WeblateOrg%2Ftest/fork",
                json={
                    "ssh_url_to_repo": "git@gitlab.com:test/test-6184.git",
                    "http_url_to_repo": "https://gitlab.com/test/test-6184.git",
                    "_links": {"self": "https://gitlab.com/api/v4/projects/20227391"},
                },
            )
        elif repo_state == 403:
            responses.add(
                responses.POST,
                "https://gitlab.com/api/v4/projects/WeblateOrg%2Ftest/fork",
                json={
                    "message": "error",
                },
                status=403,
            )
        else:
            responses.add(
                responses.POST,
                "https://gitlab.com/api/v4/projects/WeblateOrg%2Ftest/fork",
                json={
                    "ssh_url_to_repo": "git@gitlab.com:test/test.git",
                    "http_url_to_repo": "https://gitlab.com/test/test.git",
                    "_links": {"self": "https://gitlab.com/api/v4/projects/20227391"},
                },
            )
        # Mock GET responses to get forks for the repo
        responses.add(
            responses.GET,
            "https://gitlab.com/api/v4/projects/WeblateOrg%2Ftest/forks?owned=True",
            json=get_forks or [],
        )

    def mock_pr_responses(self, pr_response, pr_status) -> None:
        # PR response in case fork is create with a suffix due to duplicate
        # repo name
        responses.add(
            responses.POST,
            "https://gitlab.com/api/v4/projects/test%2Ftest-6184/merge_requests",
            json=pr_response,
            status=pr_status,
        )

        # In case the remote is origin, we send the PR to itself
        responses.add(
            responses.POST,
            "https://gitlab.com/api/v4/projects/WeblateOrg%2Ftest/merge_requests",
            json=pr_response,
            status=pr_status,
        )

        # General PR response
        responses.add(
            responses.POST,
            "https://gitlab.com/api/v4/projects/test%2Ftest/merge_requests",
            json=pr_response,
            status=pr_status,
        )

    def mock_configure_fork_features(self) -> None:
        responses.add(
            responses.PUT,
            "https://gitlab.com/api/v4/projects/20227391",
            json={"web_url": "https://gitlab.com/test/test"},
        )

    def mock_get_project_id(self) -> None:
        responses.add(
            responses.GET,
            "https://gitlab.com/api/v4/projects/WeblateOrg%2Ftest",
            json={"id": 20227391},
        )

    def mock_responses(
        self, pr_response, pr_status=200, get_forks=None, repo_state: int = 409
    ) -> None:
        """
        Mock response helper function.

        This function will mock request responses for both fork and PRs,
        GET request to get all forks and target project id, and PUT request
        to disable fork features
        """
        self.mock_fork_responses(get_forks, repo_state)
        self.mock_pr_responses(pr_response, pr_status)
        self.mock_configure_fork_features()
        self.mock_get_project_id()

    def test_api_url(self) -> None:
        self.repo.component.repo = "https://gitlab.com/WeblateOrg/test.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://gitlab.com/api/v4/projects/WeblateOrg%2Ftest",
        )
        self.repo.component.repo = "http://gitlab.com/WeblateOrg/test.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "http://gitlab.com/api/v4/projects/WeblateOrg%2Ftest",
        )
        self.repo.component.repo = "https://user:pass@gitlab.com/WeblateOrg/test.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://gitlab.com/api/v4/projects/WeblateOrg%2Ftest",
        )
        self.repo.component.repo = "git@gitlab.com:WeblateOrg/test.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://gitlab.com/api/v4/projects/WeblateOrg%2Ftest",
        )
        self.repo.component.repo = "ssh://git@gitlab.company:222/aaa/bbb.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://gitlab.company/api/v4/projects/aaa%2Fbbb",
        )
        self.repo.component.repo = "git@gitlab.company:222/aaa/bbb.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://gitlab.company/api/v4/projects/222%2Faaa%2Fbbb",
        )

    def test_get_fork_path(self) -> None:
        self.assertEqual(
            self.repo.get_fork_path("git@gitlab.com:WeblateOrg/test.git"),
            "WeblateOrg%2Ftest",
        )
        self.assertEqual(
            self.repo.get_fork_path("ssh://git@gitlab.company:222/aaa/bbb.git"),
            "aaa%2Fbbb",
        )
        self.assertEqual(
            self.repo.get_fork_path(
                "git@gitlab.domain.com:group1/subgroup/project.git"
            ),
            "group1%2Fsubgroup%2Fproject",
        )

    def test_parse_repo_url(self) -> None:
        self.assertEqual(
            self.repo.parse_repo_url(
                "git@gitlab.domain.com:group1/subgroup/project.git"
            ),
            (None, None, None, "gitlab.domain.com", "group1", "subgroup/project"),
        )
        self.assertEqual(
            self.repo.parse_repo_url(
                "https://bot:glpat@gitlab.com/path/group/repo.git"
            ),
            ("https", "bot", "glpat", "gitlab.com", "path", "group/repo"),
        )

    @override_settings(
        GITLAB_CREDENTIALS={
            "gitlab.example.com": {"username": "test", "token": "token"}
        }
    )
    def test_api_url_self_hosted(self) -> None:
        self.repo.component.repo = "git@gitlab.example.com:WeblateOrg/test.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            "https://gitlab.example.com/api/v4/projects/WeblateOrg%2Ftest",
        )
        self.repo.component.repo = "git@gitlab.example.com:WeblateOrg/test.git"
        self.assertEqual(
            self.repo.get_credentials(),
            {
                "url": "https://gitlab.example.com/api/v4/projects/WeblateOrg%2Ftest",
                "owner": "WeblateOrg",
                "slug": "test",
                "hostname": "gitlab.example.com",
                "scheme": "https",
                "push_scheme": "ssh",
                "username": "test",
                "token": "token",
            },
        )
        self.repo.component.repo = "git@gitlab.example.com:foo/bar/test.git"
        self.assertEqual(
            self.repo.get_credentials(),
            {
                "url": "https://gitlab.example.com/api/v4/projects/foo%2Fbar%2Ftest",
                "owner": "foo",
                "slug": "bar/test",
                "hostname": "gitlab.example.com",
                "scheme": "https",
                "push_scheme": "ssh",
                "username": "test",
                "token": "token",
            },
        )
        self.repo.component.repo = "https://bot:pat@gitlab.example.com/foo/bar/test.git"
        self.assertEqual(
            self.repo.get_credentials(),
            {
                "url": "https://gitlab.example.com/api/v4/projects/foo%2Fbar%2Ftest",
                "owner": "foo",
                "slug": "bar/test",
                "hostname": "gitlab.example.com",
                "scheme": "https",
                "push_scheme": "https",
                "username": "bot",
                "token": "pat",
            },
        )

    @responses.activate
    def test_push(self, branch: str = "") -> None:
        self.repo.component.repo = "https://gitlab.com/WeblateOrg/test.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        # Mock post, put and get requests for both the fork and PR requests sent.
        self.mock_responses(
            pr_response={
                "web_url": "https://gitlab.com/WeblateOrg/test/-/merge_requests/1"
            }
        )
        super().test_push(branch)
        mock_push_to_fork.stop()

    @responses.activate
    def test_push_with_existing_fork(self, branch: str = "") -> None:
        self.repo.component.repo = "https://gitlab.com/WeblateOrg/test.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        # Mock post, put and get requests for both the fork and PR requests sent.
        self.mock_responses(
            pr_response={
                "web_url": "https://gitlab.com/WeblateOrg/test/-/merge_requests/1"
            },
            get_forks=[
                {
                    "ssh_url_to_repo": "git@gitlab.com:test/test.git",
                    "http_url_to_repo": "https://gitlab.com/test/test.git",
                    "owner": {"username": "test"},
                    "_links": {"self": "https://gitlab.com/api/v4/projects/20227391"},
                }
            ],
        )
        super().test_push(branch)
        mock_push_to_fork.stop()

        # Test that the POST request to create a new fork was not called
        call_count = len(
            [1 for call in responses.calls if call.request.method == "POST"]
        )
        self.assertEqual(call_count, 1)

    @responses.activate
    def test_push_duplicate_repo_name(self, branch: str = "") -> None:
        self.repo.component.repo = "https://gitlab.com/WeblateOrg/test.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        # Mock post, put and get requests for both the fork and PR requests sent.
        self.mock_responses(
            pr_response={
                "web_url": "https://gitlab.com/WeblateOrg/test/-/merge_requests/1"
            },
            repo_state=409,
        )
        super().test_push(branch)
        mock_push_to_fork.stop()

        # Test that the POST request to create a new fork was called again to
        # create different repo name
        call_count = len(
            [1 for call in responses.calls if call.request.method == "POST"]
        )
        self.assertEqual(call_count, 3)

    @responses.activate
    def test_push_rejected(self, branch: str = "") -> None:
        self.repo.component.repo = "https://gitlab.com/WeblateOrg/test.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        # Mock post, put and get requests for both the fork and PR requests sent.
        self.mock_responses(
            pr_response={
                "web_url": "https://gitlab.com/WeblateOrg/test/-/merge_requests/1"
            },
            repo_state=403,
        )
        with self.assertRaises(RepositoryError):
            super().test_push(branch)
        mock_push_to_fork.stop()

        # Test that the POST request to create a new fork was called again to
        # create different repo name
        call_count = len(
            [1 for call in responses.calls if call.request.method == "POST"]
        )
        self.assertEqual(call_count, 1)

    @responses.activate
    def test_pull_request_error(self, branch: str = "") -> None:
        self.repo.component.repo = "https://gitlab.com/WeblateOrg/test.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        # Mock post, put and get requests for both the fork and PR requests sent.
        self.mock_responses(pr_status=422, pr_response={"message": "Some error"})
        with self.assertRaises(RepositoryError):
            super().test_push(branch)
        mock_push_to_fork.stop()

    @responses.activate
    def test_pull_request_exists(self, branch: str = "") -> None:
        self.repo.component.repo = "https://gitlab.com/WeblateOrg/test.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        # Check that it doesn't raise error when pull request already exists
        self.mock_responses(
            pr_status=409,
            pr_response={"message": ["Another open merge request already exists"]},
        )
        super().test_push(branch)
        mock_push_to_fork.stop()


@override_settings(
    PAGURE_CREDENTIALS={"pagure.io": {"username": "test", "token": "token"}}
)
class VCSPagureTest(VCSGitUpstreamTest):
    _class = PagureFakeRepository
    _vcs = "git"
    _sets_push = False

    def mock_responses(self, pr_response: dict, existing_response: dict) -> None:
        """Mock response helper function."""
        responses.add(
            responses.POST,
            "https://pagure.io/api/0/fork",
            json=pr_response,
            status=200,
        )
        responses.add(
            responses.POST,
            "https://pagure.io/api/0/fork/test/testrepo/pull-request/new",
            json={"id": 1},
            status=200,
        )
        responses.add(
            responses.GET,
            "https://pagure.io/api/0/testrepo/pull-requests",
            json=existing_response,
            status=200,
        )
        responses.add(
            responses.POST,
            "https://pagure.io/api/0/testrepo/pull-request/new",
            json={"id": 1},
            status=200,
        )

    @responses.activate
    def test_push(self, branch: str = "") -> None:
        self.repo.component.repo = "https://pagure.io/testrepo.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        # Mock post, put and get requests for both the fork and PR requests sent.
        self.mock_responses(
            {"message": 'Repo "im-chooser" cloned to "nijel/im-chooser"'},
            {"total_requests": 0},
        )
        super().test_push(branch)
        mock_push_to_fork.stop()

    @responses.activate
    def test_push_with_existing_fork(self, branch: str = "") -> None:
        self.repo.component.repo = "https://pagure.io/testrepo.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        # Mock post, put and get requests for both the fork and PR requests sent.
        self.mock_responses(
            {
                "error": 'Repo "forks/nijel/im-chooser" already exists',
                "error_code": "ENOCODE",
            },
            {"total_requests": 0},
        )
        super().test_push(branch)
        mock_push_to_fork.stop()

        # Test that the POST request to create a new fork was not called
        call_count = len(
            [1 for call in responses.calls if call.request.method == "POST"]
        )
        self.assertEqual(call_count, 2)

    @responses.activate
    def test_push_with_existing_request(self, branch: str = "") -> None:
        self.repo.component.repo = "https://pagure.io/testrepo.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        # Mock post, put and get requests for both the fork and PR requests sent.
        self.mock_responses(
            {
                "error": 'Repo "forks/nijel/im-chooser" already exists',
                "error_code": "ENOCODE",
            },
            {"total_requests": 1},
        )
        super().test_push(branch)
        mock_push_to_fork.stop()

        # Test that the POST request to create a new fork and pull request were
        # not called
        call_count = len(
            [1 for call in responses.calls if call.request.method == "POST"]
        )
        self.assertEqual(call_count, 1)


class VCSGerritTest(VCSGitUpstreamTest):
    _class = GitWithGerritRepository
    _vcs = "git"
    _sets_push = True

    def fixup_repo(self, repo) -> None:
        # Create commit-msg hook, so that git-review doesn't try
        # to create one
        hook = os.path.join(repo.path, ".git", "hooks", "commit-msg")
        with open(hook, "w") as handle:
            handle.write("#!/bin/sh\nexit 0\n")
        os.chmod(hook, 0o755)  # noqa: S103, nosec

    def test_set_gitreview_username_git(self) -> None:
        with self.repo.lock:
            self.repo.configure_remote(
                "pullurl", "git@domain.com:gituser/repo.git", "branch"
            )
            self.assertEqual(self.repo.get_config("gitreview.username"), "gituser")

    def test_set_gitreview_username_ssh(self) -> None:
        with self.repo.lock:
            self.repo.configure_remote(
                "pullurl", "ssh://sshuser@domain.com:29418/repo.git", "branch"
            )
            self.assertEqual(self.repo.get_config("gitreview.username"), "sshuser")

    def test_set_gitreview_username_https(self) -> None:
        with self.repo.lock:
            self.repo.configure_remote(
                "pullurl", "https://httpsuser@domain.com/user/repo.git", "branch"
            )
            self.assertEqual(self.repo.get_config("gitreview.username"), "httpsuser")

    def test_set_gitreview_username_https_pathuser(self) -> None:
        with self.repo.lock:
            self.repo.configure_remote(
                "pullurl", "https://domain.com/httpspathuser/repo.git", "branch"
            )
            self.assertEqual(
                self.repo.get_config("gitreview.username"), "httpspathuser"
            )


class VCSSubversionTest(VCSGitTest):
    _class = SubversionRepository
    _vcs = "subversion"
    _remote_branches = []
    _remote_branch = "master"

    def test_clone(self) -> None:
        self.assertTrue(os.path.exists(os.path.join(self.tempdir, ".git", "svn")))

    def test_revision_info(self) -> None:
        # Latest commit
        info = self.repo.get_revision_info(self.repo.last_revision)
        self.check_valid_info(info)

    def test_status(self) -> None:
        status = self.repo.status()
        self.assertIn("nothing to commit", status)

    def test_configure_remote(self) -> None:
        with self.repo.lock, self.assertRaises(RepositoryError):
            self.repo.configure_remote("pullurl", "pushurl", "branch")
        self.verify_pull_url()

    def test_configure_remote_no_push(self) -> None:
        with self.repo.lock:
            self.repo.configure_remote(
                self.format_local_path(self.subversion_repo_path),
                self.format_local_path(self.subversion_repo_path),
                "main",
            )
            with self.assertRaises(RepositoryError):
                self.repo.configure_remote("pullurl", "", "branch")
        self.verify_pull_url()

    def verify_pull_url(self) -> None:
        self.assertEqual(
            self.repo.get_config("svn-remote.svn.url"),
            self.format_local_path(self.subversion_repo_path),
        )


class VCSSubversionBranchTest(VCSSubversionTest):
    """Cloning subversion branch directly."""

    def clone_test_repos(self) -> None:
        super().clone_test_repos()
        self.subversion_repo_path += "/trunk"


class VCSHgTest(VCSGitTest):
    """Mercurial repository testing."""

    _class = HgRepository
    _vcs = "mercurial"
    _remote_branches = []
    _remote_branch = "default"

    def test_configure_remote(self) -> None:
        with self.repo.lock:
            self.repo.configure_remote("/pullurl", "/pushurl", "branch")
        self.assertEqual(self.repo.get_config("paths", "default"), "/pullurl")
        self.assertEqual(self.repo.get_config("paths", "default-push"), "/pushurl")

    def test_configure_remote_no_push(self) -> None:
        with self.repo.lock:
            self.repo.configure_remote("/pullurl", "", "branch")
        self.assertEqual(self.repo.get_config("paths", "default-push"), "")
        with self.repo.lock:
            self.repo.configure_remote("/pullurl", "/push", "branch")
        self.assertEqual(self.repo.get_config("paths", "default-push"), "/push")

    def test_revision_info(self) -> None:
        # Latest commit
        info = self.repo.get_revision_info(self.repo.last_revision)
        self.check_valid_info(info)

    def test_set_committer(self) -> None:
        with self.repo.lock:
            self.repo.set_committer("Foo Bar Žač", "foo@example.net")
        self.assertEqual(
            self.repo.get_config("ui", "username"), "Foo Bar Žač <foo@example.net>"
        )

    def test_status(self) -> None:
        status = self.repo.status()
        self.assertEqual(status, "")


class VCSLocalTest(VCSGitTest):
    """Local repository testing."""

    _class = LocalRepository
    _vcs = "local"
    _remote_branches = []
    _remote_branch = "main"

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        # Global setup to configure git committer
        GitRepository.global_setup()

    def test_status(self) -> None:
        status = self.repo.status()
        # Older git print up-to-date, newer up to date
        self.assertIn("On branch main", status)

    def test_upstream_changes(self) -> NoReturn:
        self.skipTest("Not supported")

    def test_upstream_changes_rename(self) -> NoReturn:
        self.skipTest("Not supported")

    def test_get_file(self) -> NoReturn:
        self.skipTest("Not supported")

    def test_remove(self) -> NoReturn:
        self.skipTest("Not supported")

    def test_needs_push(self) -> None:
        self.test_commit()
        self.assertFalse(self.repo.needs_push())

    def test_reset(self) -> NoReturn:
        self.skipTest("Not supported")

    def test_merge_conflict(self) -> NoReturn:
        self.skipTest("Not supported")

    def test_rebase_conflict(self) -> NoReturn:
        self.skipTest("Not supported")

    def test_configure_remote(self) -> NoReturn:
        self.skipTest("Not supported")

    def test_configure_remote_no_push(self) -> NoReturn:
        self.skipTest("Not supported")


@override_settings(
    BITBUCKETSERVER_CREDENTIALS={
        "api.selfhosted.com": {"username": "test", "token": "token"}
    }
)
class VCSBitbucketServerTest(VCSGitUpstreamTest):
    _class = BitbucketServerFakeRepository
    _vcs = "git"
    _sets_push = False

    _bbhost = "https://api.selfhosted.com"
    _bb_api_error_stub = {"errors": [{"context": "<string>", "message": "<string>"}]}
    _bb_fork_stub = {
        "id": "222",
        "slug": "bb_fork",
        "project": {"key": "bb_fork_pk"},
        "links": {
            "clone": [
                {
                    "name": "http",
                    "href": "https://api.selfhosted.com/bb_fork_pk/bb_fork.git",
                },
                {
                    "name": "ssh",
                    "href": "ssh://git@api.selfhosted.com/bb_fork_pk/bb_fork.git",
                },
            ]
        },
    }

    def mock_fork_response(self, status: int) -> None:
        body: dict[str, Any] = {}
        if status == 201:
            body = self._bb_fork_stub
        elif status == 409:
            body = {
                "errors": [
                    {
                        "context": "name",
                        "message": "This repository URL is already taken.",
                    }
                ]
            }
        else:
            body = self._bb_api_error_stub

        responses.add(
            responses.POST,
            f"{self._bbhost}/rest/api/1.0/projects/bb_pk/repos/bb_repo",
            json=body,
            status=status,
        )

    def mock_repo_response(self, status: int) -> None:
        body = {"id": 111} if status == 200 else self._bb_api_error_stub

        responses.add(  # get remote repo id
            responses.GET,
            f"{self._bbhost}/rest/api/1.0/projects/bb_pk/repos/bb_repo",
            json=body,
            status=status,
        )

    def mock_repo_forks_response(self, status: int, pages: int = 0) -> None:
        body: dict[str, Any] = {}
        path = "rest/api/1.0/projects/bb_pk/repos/bb_repo/forks"
        if status == 200:
            origin: dict[str, Any] = copy.deepcopy(self._bb_fork_stub)
            origin["slug"] = "bb_repo"
            origin["project"]["key"] = "bb_pk"
            fork = copy.deepcopy(self._bb_fork_stub)
            fork["origin"] = origin
            body = {"values": [fork], "isLastPage": True}
        elif status == 204:
            body = {"values": [], "isLastPage": True}
        else:
            body = self._bb_api_error_stub

        if pages > 0:  # Add paginated irrelevant responses
            while pages > 0:
                fork_stub = copy.deepcopy(self._bb_fork_stub)
                fork_stub["slug"] = "not_the_slug_youre_looking_for"
                page_body = {"values": [{"origin": fork_stub}], "isLastPage": False}

                params = f"limit=1000&start={pages}"
                responses.add(  # get remote repo id
                    responses.GET,
                    f"{self._bbhost}/{path}?{params}",
                    json=page_body,
                    status=status,
                )
                pages -= 1

        params = f"limit=1000&start={pages}"
        responses.add(  # add actual relevant response
            responses.GET,
            f"{self._bbhost}/{path}?{params}",
            json=body,
            status=status,
        )

    def mock_reviewer_reponse(self, status, branch: str = "") -> None:
        path = "rest/default-reviewers/1.0/projects/bb_pk/repos/bb_repo/reviewers"
        body: dict[str, Any] | list = []
        if status == 200:
            body = {"name": "user name", "id": 123}
        elif status == 400:
            body = self._bb_api_error_stub

        if not branch:
            branch = "weblate-test-test"
        params = "targetRepoId=111&sourceRepoId=222"
        params += f"&targetRefId=main&sourceRefId={branch}"
        responses.add(
            responses.GET,
            f"{self._bbhost}/{path}?{params}",
            json=body,
            status=status,
        )

    def mock_pr_response(self, status) -> None:
        body: dict[str, Any] = {}
        if status == 201:
            body = {"id": "333"}
        elif status == 409:
            pr_exist_message = (
                "Only one pull request may be open for a given source and target branch"
            )
            body = {"errors": [{"context": "<string>", "message": pr_exist_message}]}
        else:
            body = self._bb_api_error_stub

        responses.add(
            responses.POST,
            f"{self._bbhost}/rest/api/1.0/projects/bb_pk/repos/bb_repo/pull-requests",
            json=body,
            status=status,
        )

    def test_api_url(self) -> None:
        self.repo.component.repo = f"{self._bbhost}/bb_pk/bb_repo.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            f"{self._bbhost}/rest/api/1.0/projects/bb_pk/repos/bb_repo",
        )
        self.repo.component.repo = f"{self._bbhost}/bb_pk/bb_repo"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            f"{self._bbhost}/rest/api/1.0/projects/bb_pk/repos/bb_repo",
        )
        self.repo.component.repo = f"{self._bbhost}/bb_pk/bb_repo/"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            f"{self._bbhost}/rest/api/1.0/projects/bb_pk/repos/bb_repo",
        )
        self.repo.component.repo = "git@api.selfhosted.com:bb_pk/bb_repo.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            f"{self._bbhost}/rest/api/1.0/projects/bb_pk/repos/bb_repo",
        )
        self.repo.component.repo = "api.selfhosted.com:bb_pk/bb_repo.git"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            f"{self._bbhost}/rest/api/1.0/projects/bb_pk/repos/bb_repo",
        )
        self.repo.component.repo = "api.selfhosted.com:bb_pk/bb_repo.com"
        self.assertEqual(
            self.repo.get_credentials()["url"],
            f"{self._bbhost}/rest/api/1.0/projects/bb_pk/repos/bb_repo.com",
        )

    def test_get_headers(self) -> None:
        stub_credentials = {"token": "bbs_token"}
        self.assertEqual(
            self.repo.get_headers(stub_credentials)["Authorization"], "Bearer bbs_token"
        )

    @responses.activate
    def test_default_reviewers_repo_error(self) -> None:
        self.repo.component.repo = f"{self._bbhost}/bb_pk/bb_repo.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        self.mock_repo_response(400)  # get target repo info
        credentials = {
            "url": f"{self._bbhost}/rest/api/1.0/projects/bb_pk/repos/bb_repo",
            "token": "bbs_token",
        }
        self.assertEqual(
            self.repo.get_default_reviewers(credentials, "test-branch"), []
        )
        mock_push_to_fork.stop()

    @responses.activate
    def test_default_reviewers_error(self) -> None:
        self.repo.component.repo = f"{self._bbhost}/bb_pk/bb_repo.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        self.mock_repo_response(200)  # get target repo info
        self.mock_reviewer_reponse(400)  # get default reviewers
        self.repo.bb_fork = {"id": "222"}
        credentials = {
            "url": f"{self._bbhost}/rest/api/1.0/projects/bb_pk/repos/bb_repo",
            "token": "bbs_token",
        }
        self.assertEqual(
            self.repo.get_default_reviewers(credentials, "weblate-test-test"), []
        )
        mock_push_to_fork.stop()

    @responses.activate
    def test_push(self, branch: str = "") -> None:
        self.repo.component.repo = f"{self._bbhost}/bb_pk/bb_repo.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        self.mock_fork_response(201)  # fork created
        self.mock_repo_response(200)  # get target repo info
        self.mock_reviewer_reponse(200, branch)  # get default reviewers
        self.mock_pr_response(201)  # create pr ok
        super().test_push(branch)
        mock_push_to_fork.stop()

    @responses.activate
    def test_push_with_existing_pr(self, branch: str = "") -> None:
        self.repo.component.repo = f"{self._bbhost}/bb_pk/bb_repo.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        self.mock_fork_response(201)  # fork created
        self.mock_repo_response(200)  # get target repo info
        self.mock_reviewer_reponse(200, branch)  # get default reviewers
        self.mock_pr_response(409)  # create pr error, PR already exists
        super().test_push(branch)
        mock_push_to_fork.stop()

    @responses.activate
    def test_push_pr_error_reponse(self, branch: str = "") -> None:
        self.repo.component.repo = f"{self._bbhost}/bb_pk/bb_repo.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        self.mock_fork_response(201)  # fork created
        self.mock_repo_response(200)  # get target repo info
        self.mock_reviewer_reponse(200, branch)  # get default reviewers
        self.mock_pr_response(401)  # create pr error
        with self.assertRaises(RepositoryError):
            super().test_push(branch)
        mock_push_to_fork.stop()

    @responses.activate
    def test_push_with_existing_fork(self, branch: str = "") -> None:
        self.repo.component.repo = f"{self._bbhost}/bb_pk/bb_repo.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        self.mock_fork_response(status=409)  # fork already exists
        self.mock_repo_forks_response(status=200, pages=3)  # simulate pagination
        self.mock_repo_response(200)  # get target repo info
        self.mock_reviewer_reponse(200, branch)  # get default reviewers
        self.mock_pr_response(201)  # create pr ok
        super().test_push(branch)
        mock_push_to_fork.stop()

    @responses.activate
    def test_create_fork_unexpected_fail(self, branch: str = "") -> None:
        self.repo.component.repo = f"{self._bbhost}/bb_pk/bb_repo.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        self.mock_fork_response(status=401)
        with self.assertRaises(RepositoryError):
            super().test_push(branch)
        mock_push_to_fork.stop()

    @responses.activate
    def test_existing_fork_not_found(self, branch: str = "") -> None:
        self.repo.component.repo = f"{self._bbhost}/bb_pk/bb_repo.git"

        # Patch push_to_fork() function because we don't want to actually
        # make a git push request
        mock_push_to_fork_patcher = patch(
            "weblate.vcs.git.GitMergeRequestBase.push_to_fork"
        )
        mock_push_to_fork = mock_push_to_fork_patcher.start()
        mock_push_to_fork.return_value = ""

        self.mock_fork_response(status=409)  # fork already exists
        # can't find fork that should exist
        self.mock_repo_forks_response(status=204, pages=3)
        with self.assertRaises(RepositoryError):
            super().test_push(branch)
        mock_push_to_fork.stop()


@override_settings(
    BITBUCKETCLOUD_CREDENTIALS={
        "bitbucket.org": {
            "username": "weblate",
            "token": "app-password",
            "workspace": "test-workspace",
        }
    }
)
class VCSBitbucketCloudTest(VCSGitUpstreamTest):
    _class = BitbucketCloudFakeRepository
    _vcs = "git"
    _sets_push = False
    _apihost = "bitbucket.org"

    def mock_responses(self) -> None:
        """
        Mock the successful responses Bitbucket Cloud API.

            - list repo forks
            - create a fork
            - list default reviewers
            - create a pull request
        """
        responses.add(
            responses.GET,
            "https://api.bitbucket.org/2.0/repositories/WeblateOrg/test/forks",
            json={
                "values": [],
                "pagelen": 10,
                "page": 1,
            },
            status=200,
        )

        responses.add(
            responses.POST,
            "https://api.bitbucket.org/2.0/repositories/WeblateOrg/test/forks",
            json={
                "type": "repository",
                "fullname": "test-workspace/test",
                "name": "test",
                "slug": "test",
                "parent": {
                    "type": "repository",
                    "full_name": "WeblateOrg/test",
                    "name": "test",
                },
                "links": {
                    "clone": [
                        {
                            "name": "https",
                            "href": "https://weblate@bitbucket.org/test-workspace/test.git",
                        },
                        {
                            "name": "ssh",
                            "href": "git@bitbucket.org:test-workspace/test.git",
                        },
                    ]
                },
                "owner": {"username": "test-workspace"},
            },
            status=200,
        )

        responses.add(
            responses.GET,
            "https://api.bitbucket.org/2.0/repositories/WeblateOrg/test/default-reviewers",
            json={
                "values": [
                    {
                        "type": "default_reviewer",
                        "display_name": "reviewer_1",
                        "uuid": "reviewer-uuid",
                    }
                ],
                "pagelen": 10,
                "page": 1,
            },
            status=200,
        )

        responses.add(
            responses.POST,
            "https://api.bitbucket.org/2.0/repositories/WeblateOrg/test/pullrequests",
            json={
                "type": "pullrequest",
                "id": 1,
                "title": "PR title",
                "description": "PR description",
                "state": "OPEN",
                "destination": {"branch": {"name": "main"}},
            },
            status=200,
        )

    @responses.activate
    def test_push(self, branch: str = "") -> None:
        """Test push to bitbucket cloud."""
        self.repo.component.repo = "git@bitbucket.org:WeblateOrg/test.git"
        self.mock_responses()
        with patch("weblate.vcs.git.GitMergeRequestBase.push_to_fork", return_value=""):
            super().test_push(branch)

    @responses.activate
    def test_push_with_http(self, branch: str = "") -> None:
        """Test push to bitbucket cloud with HTTP repo link."""
        self.repo.component.repo = "https://bitbucket.org/WeblateOrg/test.git"
        self.mock_responses()
        with patch("weblate.vcs.git.GitMergeRequestBase.push_to_fork", return_value=""):
            super().test_push(branch)

    @responses.activate
    def test_push_with_missing_permission(self, branch: str = "") -> None:
        """Test push with missing permission for App Password."""
        self.repo.component.repo = "git@bitbucket.org:WeblateOrg/test.git"

        self.mock_responses()
        responses.replace(
            responses.POST,
            "https://api.bitbucket.org/2.0/repositories/WeblateOrg/test/pullrequests",
            json={
                "type": "error",
                "error": {
                    "message": "Your credentials lack one or more required privilege scopes.",
                    "detail": {
                        "required": ["pullrequest:write"],
                        "granted": ["pullrequest"],
                    },
                },
            },
        )

        with (
            self.assertRaises(RepositoryError),
            patch("weblate.vcs.git.GitMergeRequestBase.push_to_fork", return_value=""),
        ):
            super().test_push(branch)

    @responses.activate
    def test_default_reviewers_error(self, branch: str = "") -> None:
        """Test default reviewers error, push expected to be successful."""
        self.repo.component.repo = "git@bitbucket.org:WeblateOrg/test.git"
        self.mock_responses()

        responses.replace(
            responses.GET,
            "https://api.bitbucket.org/2.0/repositories/WeblateOrg/test/default-reviewers",
            json={
                "type": "error",
                "error": {
                    "message": "Some unexpected error.",
                },
            },
            status=400,
        )
        credentials = {
            "url": "https://api.bitbucket.org/2.0/repositories/WeblateOrg/test",
            "token": "token",
            "username": "weblate",
        }
        self.assertEqual(self.repo.get_default_reviewers_uuids(credentials), [])

    @responses.activate
    def test_paginated_reviewers_list(self, branch: str = "") -> None:
        """Test the 'build_full_paginated_result' with default reviewers list."""
        self.repo.component.repo = "git@bitbucket.org:WeblateOrg/test.git"
        self.mock_responses()

        responses.replace(
            responses.GET,
            "https://api.bitbucket.org/2.0/repositories/WeblateOrg/test/default-reviewers",
            json={
                "values": [
                    {
                        "type": "default_reviewer",
                        "display_name": "reviewer_1",
                        "uuid": "reviewer-uuid-1",
                    }
                ],
                "pagelen": 1,
                "page": 1,
                "next": "https://api.bitbucket.org/2.0/repositories/WeblateOrg/test/default-reviewers?page=2",
            },
            status=200,
        )

        responses.add(
            responses.GET,
            "https://api.bitbucket.org/2.0/repositories/WeblateOrg/test/default-reviewers?page=2",
            json={
                "values": [
                    {
                        "type": "default_reviewer",
                        "display_name": "reviewer_2",
                        "uuid": "reviewer-uuid-2",
                    }
                ],
                "pagelen": 1,
                "page": 2,
            },
            status=200,
        )

        credentials = {
            "url": "https://api.bitbucket.org/2.0/repositories/WeblateOrg/test",
            "token": "token",
            "username": "weblate",
        }
        self.assertEqual(
            self.repo.get_default_reviewers_uuids(credentials),
            ["reviewer-uuid-1", "reviewer-uuid-2"],
        )

    @responses.activate
    def test_push_nothing_to_merge(self, branch: str = "") -> None:
        """Test push to bitbucket cloud with no changes to be merged."""
        self.repo.component.repo = "git@bitbucket.org:WeblateOrg/test.git"
        self.mock_responses()

        responses.replace(
            responses.POST,
            "https://api.bitbucket.org/2.0/repositories/WeblateOrg/test/pullrequests",
            json={
                "type": "error",
                "error": {"message": "There are no changes to be pulled"},
            },
            status=400,
        )

        with patch("weblate.vcs.git.GitMergeRequestBase.push_to_fork", return_value=""):
            super().test_push(branch)

    @responses.activate
    def test_fork_already_exists(self, branch: str = "") -> None:
        """Test push to bitbucket cloud with HTTP repo link."""
        self.repo.component.repo = "git@bitbucket.org:WeblateOrg/test.git"
        self.mock_responses()

        responses.replace(
            responses.GET,
            "https://api.bitbucket.org/2.0/repositories/WeblateOrg/test/forks",
            json={
                "values": [
                    {
                        "type": "repository",
                        "full_name": "test-workspace/test",
                        "links": {
                            "clone": [
                                {
                                    "name": "https",
                                    "href": "https://weblate@bitbucket.org/test-workspace/test.git",
                                },
                                {
                                    "name": "ssh",
                                    "href": "git@bitbucket.org:test-workspace/test.git",
                                },
                            ]
                        },
                        "owner": {"username": "test-workspace"},
                    }
                ],
                "pagelen": 10,
                "page": 1,
            },
            status=200,
        )

        with patch("weblate.vcs.git.GitMergeRequestBase.push_to_fork", return_value=""):
            super().test_push(branch)

    @responses.activate
    def test_fork_name_already_taken(self, branch: str = "") -> None:
        """Test push to bitbucket cloud with HTTP repo link."""
        self.repo.component.repo = "git@bitbucket.org:WeblateOrg/test.git"
        responses.add(
            responses.POST,
            "https://api.bitbucket.org/2.0/repositories/WeblateOrg/test/forks",
            json={
                "type": "error",
                "error": {
                    "message": "name: weblate already has a repository with this name.",
                    "fields": {
                        "name": ["weblate already has a repository with this name."]
                    },
                },
            },
            status=400,
        )
        self.mock_responses()
        with patch("weblate.vcs.git.GitMergeRequestBase.push_to_fork", return_value=""):
            super().test_push(branch)

    @responses.activate
    def test_fork_error(self, branch: str = "") -> None:
        """Test push to bitbucket cloud with HTTP repo link."""
        self.repo.component.repo = "git@bitbucket.org:WeblateOrg/test.git"
        self.mock_responses()
        responses.replace(
            responses.POST,
            "https://api.bitbucket.org/2.0/repositories/WeblateOrg/test/forks",
            json={
                "type": "error",
                "error": {
                    "message": "name: Unknown error not related to name.",
                    "fields": {"name": ["Unknown error not related to name."]},
                },
            },
            status=400,
        )
        with (
            self.assertRaises(RepositoryError),
            patch("weblate.vcs.git.GitMergeRequestBase.push_to_fork", return_value=""),
        ):
            super().test_push(branch)
