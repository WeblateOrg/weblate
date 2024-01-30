# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os

from django.apps import AppConfig
from django.core.checks import Warning, register
from django.db.models.signals import post_migrate

import weblate.vcs.gpg
from weblate.utils.checks import weblate_check
from weblate.utils.data import data_dir
from weblate.utils.lock import WeblateLock
from weblate.vcs.base import RepositoryError
from weblate.vcs.git import GitRepository, SubversionRepository
from weblate.vcs.ssh import ensure_ssh_key

GIT_ERRORS: list[str] = []


def check_gpg(app_configs, **kwargs):
    from weblate.vcs.gpg import get_gpg_public_key

    get_gpg_public_key()
    template = "{}: {}"
    return [
        weblate_check("weblate.C036", template.format(key, message))
        for key, message in weblate.vcs.gpg.GPG_ERRORS.items()
    ]


def check_vcs(app_configs, **kwargs):
    from weblate.vcs.models import VCS_REGISTRY

    message = "Failure in loading VCS module for {}: {}"
    return [
        weblate_check(
            f"weblate.W033.{key}", message.format(key, value.strip()), Warning
        )
        for key, value in VCS_REGISTRY.errors.items()
    ]


def check_git(app_configs, **kwargs):
    template = "Failure in configuring Git: {}"
    return [
        weblate_check("weblate.C035", template.format(message))
        for message in GIT_ERRORS
    ]


def check_vcs_credentials(app_configs, **kwargs):
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

    def ready(self):
        super().ready()
        register(check_vcs)
        register(check_git, deploy=True)
        register(check_gpg, deploy=True)
        register(check_vcs_credentials)

        post_migrate.connect(self.post_migrate, sender=self)

    def post_migrate(self, sender, **kwargs):
        ensure_ssh_key()
        home = data_dir("home")

        if not os.path.exists(home):
            os.makedirs(home)

        # Configure merge driver for Gettext PO
        # We need to do this behind lock to avoid errors when servers
        # start in parallel
        lockfile = WeblateLock(
            home, "gitlock", 0, "", "lock:{scope}", "{scope}", timeout=120
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

        # Use it for *.po by default
        configdir = os.path.join(home, ".config", "git")
        configfile = os.path.join(configdir, "attributes")
        if not os.path.exists(configfile):
            if not os.path.exists(configdir):
                os.makedirs(configdir)
            with open(configfile, "w") as handle:
                handle.write("*.po merge=weblate-merge-gettext-po\n")
