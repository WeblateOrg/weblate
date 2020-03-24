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


from django.apps import AppConfig
from django.core.checks import Critical, register

from weblate.gitexport.utils import find_git_http_backend
from weblate.utils.docs import get_doc_url


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
            Critical(
                "Failed to find git-http-backend, " "the git exporter will not work.",
                hint=get_doc_url("admin/optionals", "git-exporter"),
                id="weblate.E022",
            )
        ]
    return []
