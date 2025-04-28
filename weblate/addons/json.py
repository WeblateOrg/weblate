# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.utils.translation import gettext_lazy

from weblate.addons.base import StoreBaseAddon
from weblate.addons.forms import JSONCustomizeForm


class JSONCustomizeAddon(StoreBaseAddon):
    name = "weblate.json.customize"
    verbose = gettext_lazy("Customize JSON output")
    description = gettext_lazy(
        "Allows adjusting JSON output behavior, for example indentation or sorting."
    )
    settings_form = JSONCustomizeForm
    compat = {
        "file_format": {
            "json",
            "json-nested",
            "webextension",
            "i18next",
            "i18nextv4",
            "arb",
            "go-i18n-json",
            "go-i18n-json-v2",
            "formatjs",
            "gotext",
        }
    }

    def store_post_load(self, translation, store) -> None:
        config = self.instance.configuration
        style = config.get("style", "spaces")
        indent = int(config.get("indent", 4))

        # dump_args are passed to json.dumps in translate-toolkit when saving the file
        if style == "spaces":
            store.store.dump_args["indent"] = indent
        else:
            store.store.dump_args["indent"] = "\t" * indent
        store.store.dump_args["sort_keys"] = bool(int(config.get("sort_keys", 0)))
