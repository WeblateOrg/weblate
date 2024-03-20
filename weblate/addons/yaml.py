# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.utils.translation import gettext_lazy

from weblate.addons.base import StoreBaseAddon
from weblate.addons.forms import YAMLCustomizeForm

BREAKS = {"dos": "\r\n", "mac": "\r", "unix": "\n"}


class YAMLCustomizeAddon(StoreBaseAddon):
    name = "weblate.yaml.customize"
    verbose = gettext_lazy("Customize YAML output")
    description = gettext_lazy(
        "Allows adjusting YAML output behavior, for example line-length or newlines."
    )
    settings_form = YAMLCustomizeForm
    compat = {"file_format": {"yaml", "ruby-yaml"}}

    def store_post_load(self, translation, store) -> None:
        config = self.instance.configuration

        args = store.store.dump_args

        args["indent"] = int(config.get("indent", 2))
        args["width"] = int(config.get("width", 80))
        args["line_break"] = BREAKS[config.get("line_break", "unix")]
