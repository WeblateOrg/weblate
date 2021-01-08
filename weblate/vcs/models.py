#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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


from appconf import AppConf

from weblate.utils.classloader import ClassLoader


class VCSConf(AppConf):
    VCS_BACKENDS = (
        "weblate.vcs.git.GitRepository",
        "weblate.vcs.git.GitWithGerritRepository",
        "weblate.vcs.git.SubversionRepository",
        "weblate.vcs.git.GithubRepository",
        "weblate.vcs.git.GitLabRepository",
        "weblate.vcs.git.PagureRepository",
        "weblate.vcs.git.LocalRepository",
        "weblate.vcs.git.GitForcePushRepository",
        "weblate.vcs.mercurial.HgRepository",
    )
    VCS_CLONE_DEPTH = 1

    # GitHub username for sending pull requests
    GITHUB_USERNAME = None
    GITHUB_TOKEN = None
    GITHUB_CREDENTIALS = {}

    # GitLab username for sending merge requests
    GITLAB_USERNAME = None
    GITLAB_TOKEN = None
    GITLAB_CREDENTIALS = {}

    # GitLab username for sending merge requests
    PAGURE_USERNAME = None
    PAGURE_TOKEN = None
    PAGURE_CREDENTIALS = {}

    class Meta:
        prefix = ""


class VcsClassLoader(ClassLoader):
    def __init__(self):
        super().__init__("VCS_BACKENDS", False)
        self.errors = {}

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


# Initialize VCS list
VCS_REGISTRY = VcsClassLoader()
