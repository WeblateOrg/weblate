# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.apps import AppConfig
from django.core.checks import register

from weblate.gitexport.utils import find_git_http_backend
from weblate.utils.checks import weblate_check


class GitExportConfig(AppConfig):
    name = "weblate.gitexport"
    label = "gitexport"
    verbose_name = "Git Exporter"

    def ready(self):
        super().ready()
        register(check_git_backend)


def check_git_backend(app_configs, **kwargs):
    if find_git_http_backend() is None:
        return [
            weblate_check(
                "weblate.E022",
                "Could not find git-http-backend, the git exporter will not work.",
            )
        ]
    return []
