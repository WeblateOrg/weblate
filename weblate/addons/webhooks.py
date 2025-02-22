# Copyright © Loïc LEUILLIOT <loic.leuilliot@gmail.com>
# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
import requests
from django.utils.translation import gettext_lazy

from weblate.addons.base import ChangeBaseAddon
from weblate.addons.forms import WebhooksAddonForm


class WebhookAddon(ChangeBaseAddon):
    name = "weblate.webhook.webhook"
    # TODO: improve verbose and description
    verbose = gettext_lazy("Webhooks")
    description = gettext_lazy("some desc")

    settings_form = WebhooksAddonForm
    # TODO: find a webhook icon

    def change_event(self, change) -> None:
        config = self.instance.configuration
        if change.action in config["events"]:
            requests.post(
                config["webhook_url"],
                json=self.build_webhook_payload(change),
                timeout=30,
            )
        # What to do if request fail ??

    def build_webhook_payload(self, change) -> dict:
        # TODO: improve payload build
        payload = {
            "event": change.action,
            "url": change.get_absolute_url(),
            "old": change.old,
            "target": change.target,
            "details": change.details,
            "timestamp": change.timestamp.isoformat(),
        }

        if secret := self.instance.configuration.get("secret", None):
            payload["secret"] = secret

        return payload
