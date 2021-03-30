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

import os

from django.apps import AppConfig
from django.core.checks import Warning, register
from filelock import FileLock

from weblate.trans.util import add_configuration_error, delete_configuration_error
from weblate.utils.checks import weblate_check
from weblate.utils.data import data_dir
from weblate.vcs.base import RepositoryException
from weblate.vcs.git import GitRepository


def check_vcs(app_configs, **kwargs):
    from weblate.vcs.models import VCS_REGISTRY

    message = "Failure in loading VCS module for {}: {}"
    return [
        weblate_check(
            "weblate.W033.{}".format(key), message.format(key, value.strip()), Warning
        )
        for key, value in VCS_REGISTRY.errors.items()
    ]


class VCSConfig(AppConfig):
    name = "weblate.vcs"
    label = "vcs"
    verbose_name = "VCS"

    def ready(self):
        super().ready()
        register(check_vcs)
        home = data_dir("home")
        if not os.path.exists(home):
            os.makedirs(home)
        # Configure merge driver for Gettext PO
        # We need to do this behind lock to avoid errors when servers
        # start in parallel
        lockfile = FileLock(os.path.join(home, "gitlock"))
        with lockfile:
            try:
                GitRepository.global_setup()
                delete_configuration_error("Git global setup")
            except RepositoryException as error:
                add_configuration_error(
                    "Git global setup", "Failed to do git setup: {0}".format(error)
                )

        # Use it for *.po by default
        configdir = os.path.join(home, ".config", "git")
        configfile = os.path.join(configdir, "attributes")
        if not os.path.exists(configfile):
            if not os.path.exists(configdir):
                os.makedirs(configdir)
            with open(configfile, "w") as handle:
                handle.write("*.po merge=weblate-merge-gettext-po\n")
