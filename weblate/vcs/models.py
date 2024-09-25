# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from appconf import AppConf
from django.utils.functional import cached_property

from weblate.utils.classloader import ClassLoader

from .base import Repository


class VCSConf(AppConf):
    VCS_BACKENDS = (
        "weblate.vcs.git.GitRepository",
        "weblate.vcs.git.GitWithGerritRepository",
        "weblate.vcs.git.SubversionRepository",
        "weblate.vcs.git.GithubRepository",
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
    VCS_CLONE_DEPTH = 1
    VCS_API_DELAY = 10
    VCS_FILE_PROTOCOL = False

    # GitHub username for sending pull requests
    GITHUB_CREDENTIALS = {}

    # Azure DevOps username for sending pull requests
    AZURE_DEVOPS_CREDENTIALS = {}

    # GitLab username for sending merge requests
    GITLAB_CREDENTIALS = {}

    # Pagure username for sending merge requests
    PAGURE_CREDENTIALS = {}

    # Gitea username for sending pull requests
    GITEA_CREDENTIALS = {}

    # Bitbucket username for sending pull requests
    BITBUCKETSERVER_CREDENTIALS = {}

    # Bitbucket username for sending pull requests
    BITBUCKETCLOUD_CREDENTIALS = {}

    SSH_EXTRA_ARGS = ""

    class Meta:
        prefix = ""


class VcsClassLoader(ClassLoader):
    def __init__(self) -> None:
        super().__init__("VCS_BACKENDS", construct=False, base_class=Repository)

    def load_data(self):
        result = super().load_data()

        for key, vcs in list(result.items()):
            try:
                version = vcs.get_version()
            except Exception as error:
                supported = False
                self.errors[vcs.name] = str(error)
            else:
                supported = vcs.is_supported()
                if not supported:
                    self.errors[vcs.name] = f"Outdated version: {version}"

            if not supported or not vcs.is_configured():
                result.pop(key)

        return result

    @cached_property
    def git_based(self) -> set[str]:
        from weblate.vcs.git import GitRepository

        return {
            vcs.get_identifier()
            for vcs in self.values()
            if issubclass(vcs, GitRepository)
        }


# Initialize VCS list
VCS_REGISTRY = VcsClassLoader()
