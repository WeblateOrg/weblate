# Copyright © Maciej Olko <maciej.olko@gmail.com>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.utils.translation import gettext_lazy

from weblate.vcs.base import Repository


class MultipleRepositories(Repository):
    name = "Many repositories"  # limit length to 20
    push_label = gettext_lazy("This will push changes to the upstream repositories.")
    identifier = "many-repositories"

    @classmethod
    def is_supported(cls):
        return True  # cannot check internal repos without instantiating the class, assuming True

    @classmethod
    def is_configured(cls):
        return True  # cannot check internal repos without instantiating the class, assuming True

    @classmethod
    def get_version(cls):
        return 1  # cannot check internal repos without instantiating the class, assuming True
