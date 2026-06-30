# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from importlib import import_module
from typing import ClassVar

from appconf import AppConf
from django.db import models
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy

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


class InstallationProvider(models.TextChoices):
    """Code-hosting providers that can own an :class:`Installation`."""

    GITHUB = "github", gettext_lazy("GitHub")


class Installation(models.Model):
    """
    Generic code-hosting integration connecting a workspace to a remote account.

    The fields here are provider-agnostic: a provider-issued installation id, the
    account it targets, the host it lives on, and a cached repository list.
    Provider-specific authentication and API behaviour lives in proxy subclasses
    such as :class:`weblate.vcs.github.GitHubInstallation`; the ``provider``
    discriminator records which one owns each row so those proxies can scope
    their queries.
    """

    provider = models.CharField(
        max_length=20,
        choices=InstallationProvider,
        default=InstallationProvider.GITHUB,
        verbose_name=gettext_lazy("Provider"),
    )
    installation_id = models.CharField(
        max_length=50,
        verbose_name=gettext_lazy("Installation ID"),
    )
    target_type = models.CharField(
        max_length=20,
        verbose_name=gettext_lazy("Target type"),
        help_text=gettext_lazy("Organization or User"),
    )
    target_login = models.CharField(
        max_length=255,
        verbose_name=gettext_lazy("Target login"),
        help_text=gettext_lazy("Hosting organization or user login"),
    )
    workspace = models.ForeignKey(
        "workspaces.Workspace",
        on_delete=models.CASCADE,
        related_name="installations",
        verbose_name=gettext_lazy("Workspace"),
    )
    hostname = models.CharField(
        max_length=255,
        default="github.com",
        verbose_name=gettext_lazy("Hostname"),
    )
    enabled = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)
    repositories = models.JSONField(
        default=list,
        blank=True,
        verbose_name=gettext_lazy("Available repositories"),
    )
    repositories_updated = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = gettext_lazy("code-hosting installation")
        verbose_name_plural = gettext_lazy("code-hosting installations")
        unique_together = (("provider", "hostname", "installation_id", "workspace"),)

    def __str__(self) -> str:
        return f"{self.target_login} ({self.hostname}/{self.installation_id})"


class PendingInstallation(models.Model):
    """
    Signed provider webhook payload waiting for workspace authorization.

    Rows here are intentionally not workspace-scoped. A provider webhook can
    arrive before the redirect that proves which Weblate workspace may use the
    installation. Provider-specific setup code replays the payload only after
    that authority is validated.
    """

    provider = models.CharField(
        max_length=20,
        choices=InstallationProvider,
        verbose_name=gettext_lazy("Provider"),
    )
    hostname = models.CharField(
        max_length=255,
        verbose_name=gettext_lazy("Hostname"),
    )
    installation_id = models.CharField(
        max_length=50,
        verbose_name=gettext_lazy("Installation ID"),
    )
    payload = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=gettext_lazy("Webhook payload"),
    )
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = gettext_lazy("pending code-hosting installation")
        verbose_name_plural = gettext_lazy("pending code-hosting installations")
        unique_together = (("provider", "hostname", "installation_id"),)

    def __str__(self) -> str:
        return f"{self.provider}:{self.hostname}/{self.installation_id}"


# Import provider-specific proxies so Django registers them with the VCS app
# during app loading, regardless of backend-registry import order.  Placed after
# Installation so github.py can import it back without a circular-import failure.
import_module("weblate.vcs.github")


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
