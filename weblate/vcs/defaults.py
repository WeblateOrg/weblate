# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

DEFAULT_VCS_BACKENDS: tuple[str, ...] = (
    "weblate.vcs.git.GitRepository",
    "weblate.vcs.git.GitWithGerritRepository",
    "weblate.vcs.git.SubversionRepository",
    "weblate.vcs.git.GithubRepository",
    "weblate.vcs.github.GithubAppRepository",
    "weblate.vcs.git.AzureDevOpsRepository",
    "weblate.vcs.git.GiteaRepository",
    "weblate.vcs.git.GitLabRepository",
    "weblate.vcs.git.PagureRepository",
    "weblate.vcs.git.LocalRepository",
    "weblate.vcs.git.GitForcePushRepository",
    "weblate.vcs.git.BitbucketServerRepository",
    "weblate.vcs.git.BitbucketCloudRepository",
    "weblate.vcs.mercurial.HgRepository",
)

DEFAULT_VCS_CLONE_DEPTH = 1
DEFAULT_VCS_API_DELAY = 10
DEFAULT_VCS_API_TIMEOUT = 10
DEFAULT_VCS_ALLOW_SCHEMES: frozenset[str] = frozenset({"https", "ssh"})
DEFAULT_VCS_ALLOW_HOSTS: frozenset[str] = frozenset()
DEFAULT_VCS_RESTRICT_PRIVATE = True
DEFAULT_SSH_EXTRA_ARGS = ""

DEFAULT_GITHUB_CREDENTIALS: dict = {}
DEFAULT_AZURE_DEVOPS_CREDENTIALS: dict = {}
DEFAULT_GITLAB_CREDENTIALS: dict = {}
DEFAULT_PAGURE_CREDENTIALS: dict = {}
DEFAULT_GITEA_CREDENTIALS: dict = {}
DEFAULT_BITBUCKETSERVER_CREDENTIALS: dict = {}
DEFAULT_BITBUCKETCLOUD_CREDENTIALS: dict = {}
