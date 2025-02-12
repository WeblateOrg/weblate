# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import os
from typing import TYPE_CHECKING

from django.apps import AppConfig
from django.core.checks import CheckMessage, register
from django.core.checks import Warning as DjangoWarning
from django.db.models.signals import post_migrate

import weblate.vcs.gpg
from weblate.utils.checks import weblate_check
from weblate.utils.data import data_dir
from weblate.utils.lock import WeblateLock
from weblate.vcs.base import RepositoryError
from weblate.vcs.git import GitRepository, SubversionRepository
from weblate.vcs.mercurial import HgRepository
from weblate.vcs.ssh import ensure_ssh_key

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

GIT_ERRORS: list[str] = []


@register(deploy=True)
def check_gpg(
    *,
    app_configs: Sequence[AppConfig] | None,
    databases: Sequence[str] | None,
    **kwargs,
) -> Iterable[CheckMessage]:
    from weblate.vcs.gpg import get_gpg_public_key

    get_gpg_public_key()
    template = "{}: {}"
    return [
        weblate_check("weblate.C036", template.format(key, message))
        for key, message in weblate.vcs.gpg.GPG_ERRORS.items()
    ]


@register
def check_vcs(
    *,
    app_configs: Sequence[AppConfig] | None,
    databases: Sequence[str] | None,
    **kwargs,
) -> Iterable[CheckMessage]:
    from weblate.vcs.models import VCS_REGISTRY

    message = "Failure in loading VCS module for {}: {}"
    return [
        weblate_check(
            f"weblate.W033.{key}",
            message.format(key, str(value).strip()),
            DjangoWarning,
        )
        for key, value in VCS_REGISTRY.errors.items()
    ]


@register(deploy=True)
def check_git(
    *,
    app_configs: Sequence[AppConfig] | None,
    databases: Sequence[str] | None,
    **kwargs,
) -> Iterable[CheckMessage]:
    template = "Failure in configuring Git: {}"
    return [
        weblate_check("weblate.C035", template.format(message))
        for message in GIT_ERRORS
    ]


@register
def check_vcs_credentials(
    *,
    app_configs: Sequence[AppConfig] | None,
    databases: Sequence[str] | None,
    **kwargs,
) -> Iterable[CheckMessage]:
    from weblate.vcs.models import VCS_REGISTRY

    return [
        weblate_check("weblate.C040", error)
        for instance in VCS_REGISTRY.values()
        for error in instance.validate_configuration()
    ]


class VCSConfig(AppConfig):
    name = "weblate.vcs"
    label = "vcs"
    verbose_name = "VCS"

    def ready(self) -> None:
        super().ready()
        post_migrate.connect(self.post_migrate, sender=self)

    def post_migrate(self, sender: AppConfig, **kwargs) -> None:
        ensure_ssh_key()
        home = data_dir("home")

        if not os.path.exists(home):
            os.makedirs(home)

        # Configure merge driver for Gettext PO
        # We need to do this behind lock to avoid errors when servers
        # start in parallel
        lockfile = WeblateLock(
            lock_path=home,
            scope="gitlock",
            key=0,
            slug="",
            cache_template="lock:{scope}",
            file_template="{scope}",
            timeout=120,
        )
        with lockfile:
            try:
                GitRepository.global_setup()
            except RepositoryError as error:
                GIT_ERRORS.append(str(error))
            if SubversionRepository.is_supported():
                try:
                    SubversionRepository.global_setup()
                except RepositoryError as error:
                    GIT_ERRORS.append(str(error))
            if HgRepository.is_supported():
                try:
                    HgRepository.global_setup()
                except RepositoryError as error:
                    GIT_ERRORS.append(str(error))
