# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import ClassVar

from appconf import AppConf
from django.utils.functional import cached_property

from weblate.utils.classloader import ClassLoader

from .base import Repository
from .defaults import (
    DEFAULT_AZURE_DEVOPS_CREDENTIALS,
    DEFAULT_BITBUCKETCLOUD_CREDENTIALS,
    DEFAULT_BITBUCKETSERVER_CREDENTIALS,
    DEFAULT_GITEA_CREDENTIALS,
    DEFAULT_GITHUB_CREDENTIALS,
    DEFAULT_GITLAB_CREDENTIALS,
    DEFAULT_PAGURE_CREDENTIALS,
    DEFAULT_SSH_EXTRA_ARGS,
    DEFAULT_VCS_ALLOW_HOSTS,
    DEFAULT_VCS_ALLOW_SCHEMES,
    DEFAULT_VCS_API_DELAY,
    DEFAULT_VCS_API_TIMEOUT,
    DEFAULT_VCS_BACKENDS,
    DEFAULT_VCS_CLONE_DEPTH,
    DEFAULT_VCS_RESTRICT_PRIVATE,
)


class VCSConf(AppConf):
    VCS_BACKENDS = DEFAULT_VCS_BACKENDS
    VCS_CLONE_DEPTH = DEFAULT_VCS_CLONE_DEPTH
    VCS_API_DELAY = DEFAULT_VCS_API_DELAY
    VCS_API_TIMEOUT = DEFAULT_VCS_API_TIMEOUT
    VCS_ALLOW_SCHEMES: ClassVar[set[str]] = set(DEFAULT_VCS_ALLOW_SCHEMES)
    VCS_ALLOW_HOSTS: ClassVar[set[str]] = set(DEFAULT_VCS_ALLOW_HOSTS)
    VCS_RESTRICT_PRIVATE = DEFAULT_VCS_RESTRICT_PRIVATE

    # GitHub username for sending pull requests
    GITHUB_CREDENTIALS: ClassVar[dict] = dict(DEFAULT_GITHUB_CREDENTIALS)

    # Azure DevOps username for sending pull requests
    AZURE_DEVOPS_CREDENTIALS: ClassVar[dict] = dict(DEFAULT_AZURE_DEVOPS_CREDENTIALS)

    # GitLab username for sending merge requests
    GITLAB_CREDENTIALS: ClassVar[dict] = dict(DEFAULT_GITLAB_CREDENTIALS)

    # Pagure username for sending merge requests
    PAGURE_CREDENTIALS: ClassVar[dict] = dict(DEFAULT_PAGURE_CREDENTIALS)

    # Gitea username for sending pull requests
    GITEA_CREDENTIALS: ClassVar[dict] = dict(DEFAULT_GITEA_CREDENTIALS)

    # Bitbucket username for sending pull requests
    BITBUCKETSERVER_CREDENTIALS: ClassVar[dict] = dict(
        DEFAULT_BITBUCKETSERVER_CREDENTIALS
    )

    # Bitbucket username for sending pull requests
    BITBUCKETCLOUD_CREDENTIALS: ClassVar[dict] = dict(
        DEFAULT_BITBUCKETCLOUD_CREDENTIALS
    )

    SSH_EXTRA_ARGS = DEFAULT_SSH_EXTRA_ARGS

    class Meta:
        prefix = ""


class VcsClassLoader(ClassLoader):
    def __init__(self) -> None:
        super().__init__("VCS_BACKENDS", construct=False, base_class=Repository)

    def get_unfiltered_choices(self):
        result = super().load_data()
        return [(x, result[x].name) for x in sorted(result)]

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
        # ruff: ignore[import-outside-top-level]
        from weblate.vcs.git import GitRepository

        return {
            vcs.get_identifier()
            for vcs in self.values()
            if issubclass(vcs, GitRepository)
        }

    @cached_property
    def merge_request_based(self) -> set[str]:
        # ruff: ignore[import-outside-top-level]
        from weblate.vcs.git import GitMergeRequestBase

        return {
            vcs.get_identifier()
            for vcs in self.values()
            if issubclass(vcs, GitMergeRequestBase)
        }


# Initialize VCS list
VCS_REGISTRY = VcsClassLoader()
