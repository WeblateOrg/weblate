# Copyright © Maciej Olko <maciej.olko@gmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from json import loads

from django.utils.translation import gettext_lazy

from weblate.vcs.base import Repository
from weblate.vcs.models import VCS_REGISTRY


class MultipleRepositories(Repository):
    name = "Many repositories"  # limit length to 20
    push_label = gettext_lazy("This will push changes to the upstream repositories.")
    identifier = "many-repositories"

    def __init__(
        self,
        path: str,
        branch: str | None = None,
        component=None,
        local: bool = False,
        skip_init: bool = False,
    ):
        super().__init__(path, branch, component, local, skip_init)
        self.repositories: list[Repository] = []

    @classmethod
    def is_supported(cls):
        return True  # cannot check internal repos without instantiating the class, assuming True

    @classmethod
    def is_configured(cls):
        return True  # cannot check internal repos without instantiating the class, assuming True

    @classmethod
    def get_version(cls):
        return 1  # cannot check internal repos without instantiating the class, assuming True

    def is_valid(self):
        return True

    def configure_remote(
        self, pull_url: str, push_url: str, branch: str, fast: bool = True
    ):
        pull_urls = loads(pull_url)
        push_urls = push_url and loads(push_url)
        branches = loads(branch)
        repositories = []
        for key, repo in pull_urls.items():
            repository = VCS_REGISTRY[repo["vcs"]](self.path, branches.get(key))
            repository.configure_remote(repo["repo"], push_urls and push_urls.get(key), branches.get(key), fast)
            repositories.append(repository)
        self.repositories = repositories

    def set_committer(self, name, mail) -> None:
        for repository in self.repositories:
            repository.set_committer(name, mail)

    @property
    def last_remote_revision(self):
        return self.repositories[0].last_remote_revision

    def update_remote(self) -> None:
        for repository in self.repositories:
            repository.update_remote()
