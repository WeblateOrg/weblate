# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from django.utils import timezone
from django.utils.translation import gettext_lazy

from weblate.addons.base import ChangeBaseAddon
from weblate.addons.forms import WebhooksAddonForm
from weblate.api.tasks import webhook_delivery_task
from weblate.trans.util import split_plural


class WebhookAddon(ChangeBaseAddon):
    name = "weblate.webhook.webhook"
    # TODO: improve description
    verbose = gettext_lazy("Webhooks")
    description = gettext_lazy("some desc")

    settings_form = WebhooksAddonForm
    icon = "webhook.svg"

    def change_event(self, change) -> None:
        config = self.instance.configuration
        if change.action in config["events"]:
            payload = self.build_webhook_payload(change)
            webhook_delivery_task.delay(
                url=config["webhook_url"],
                headers=self.build_headers(change, payload),
                data=payload,
            )

    def build_webhook_payload(self, change) -> dict:
        from weblate.trans.models import Change

        # reload change with prefetched content
        change = Change.objects.prefetch_for_get().get(pk=change.pk)
        data = {
            "id": change.id,
            "action": change.get_action_display(),
        }
        if url := change.get_absolute_url():
            data["url"] = url
        if change.target:
            data["target"] = split_plural(change.target)
        if change.old:
            data["old"] = split_plural(change.old)
        if change.author:
            data["author"] = change.author.username
        if change.user:
            data["user"] = change.user.username
        if change.project:
            data["project"] = change.project.slug
        if change.component:
            data["component"] = change.component.slug
        if change.translation:
            data["translation"] = change.translation.language.code
        if change.unit:
            data["source"] = split_plural(change.unit.source)
            data["context"] = change.unit.context

        payload = {
            "type": change.get_type(),
            "timestamp": change.timestamp.isoformat(),
            "data": data,
        }

        if secret := self.instance.configuration.get("secret", None):
            payload["secret"] = secret

        return payload

    def build_headers(self, change, payload: dict) -> dict:
        return {
            "webhook-timestamp": timezone.now().isoformat(),
            "webhook-id": change.get_uuid().hex,
        }
