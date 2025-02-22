# Copyright © Loïc LEUILLIOT <loic.leuilliot@gmail.com>
# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
import requests
from django.utils import timezone
from django.utils.translation import gettext_lazy

from weblate.addons.base import ChangeBaseAddon
from weblate.addons.forms import WebhooksAddonForm
from weblate.api import serializers


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
            payload = self.build_webhook_payload(change)
            requests.post(
                config["webhook_url"],
                json=payload,
                timeout=30,
                headers=self.build_headers(change, payload),
            )

    def build_webhook_payload(self, change) -> dict:
        from weblate.trans.models import Change

        # reload change with prefetched content
        change = Change.objects.prefetch_for_get().get(pk=change.pk)

        payload = {
            "type": change.get_type(),
            "timestamp": change.timestamp().isoformat(),
            "data": serializers.ChangeSerializer(change).data,
        }

        if secret := self.instance.configuration.get("secret", None):
            payload["secret"] = secret

        return payload

    def build_headers(self, change, payload: dict) -> dict:
        return {
            "webhook-timestamp": timezone.now().timestamp(),
            "webhook-id": change.get_uuid().hex,
        }
