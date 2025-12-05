# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING

import fedora_messaging.api
import fedora_messaging.config
from django.conf import settings
from django.utils.translation import gettext_lazy
from siphashc import siphash
from weblate_schemas.messages import WeblateV1Message

from weblate.addons.base import ChangeBaseAddon
from weblate.trans.util import split_plural
from weblate.utils.data import data_path
from weblate.utils.site import get_site_url

from .forms import FedoraMessagingAddonForm

if TYPE_CHECKING:
    from weblate.trans.models import Change, Component, Project


class FedoraMessagingAddon(ChangeBaseAddon):
    icon = "webhook.svg"
    settings_form = FedoraMessagingAddonForm
    name = "weblate.fedora_messaging.publish"
    verbose = gettext_lazy("Fedora Messaging")
    description = gettext_lazy(
        "Sends notifications to a Fedora Messaging compatible AMQP exchange."
    )
    multiple = False

    @classmethod
    def can_install(
        cls,
        *,
        component: Component | None = None,
        project: Project | None = None,
    ) -> bool:
        # Can be installed only once site-wide
        return project is None and component is None

    @classmethod
    def can_process(
        cls,
        *,
        component: Component | None = None,  # noqa: ARG003
        project: Project | None = None,  # noqa: ARG003
    ) -> bool:
        return True

    def change_event(
        self, change: Change, activity_log_id: int | None = None
    ) -> dict | None:
        config = self.instance.configuration

        # Filter event
        events = {int(event) for event in config["events"]}
        if change.action not in events:
            return None

        # Apply configuration
        self.configure_fedora_messaging(
            amqp_host=config["amqp_host"],
            amqp_ssl=config.get("amqp_ssl", False),
            ca_cert=config.get("ca_cert"),
            client_key=config.get("client_key"),
            client_cert=config.get("client_cert"),
        )

        # Build message payload
        message = WeblateV1Message(
            topic=self.get_change_topic(change),
            headers=self.get_change_headers(change),
            body=self.get_change_body(change),
        )
        # Publish the message
        # We might want to handle PublishReturned and PublishTimeout exceptions from publish here
        fedora_messaging.api.publish(message)
        return {"message_id": message.id}

    @staticmethod
    def get_change_topic(change: Change) -> str:
        """
        Generate a topic for the change.

        It is in the form weblate.<action>.<project>.<component>.<translation>
        """
        parts = ["weblate", change.get_action_display().lower().replace(" ", "_")]
        if change.project:
            parts.append(change.project.slug)
        if change.component:
            parts.append(change.component.slug)
        if change.translation:
            parts.append(change.translation.language.code)
        return ".".join(parts)

    @staticmethod
    def get_change_body(change: Change) -> dict[str, str | int | list[str]]:
        result: dict[str, str | int | list[str]] = {
            "change_id": change.id,
            "action": change.get_action_display(),
            "timestamp": change.timestamp.isoformat(),
        }
        url = change.get_absolute_url()
        if url:
            result["url"] = get_site_url(url)
        if change.target:
            result["target"] = split_plural(change.target)
        if change.old:
            result["old"] = split_plural(change.old)
        if change.author:
            result["author"] = change.author.username
        if change.user:
            result["user"] = change.user.username
        if change.project:
            result["project"] = change.project.slug
        if change.component:
            result["component"] = change.component.slug
        if change.translation:
            result["translation"] = change.translation.language.code
        if change.unit:
            result["source"] = split_plural(change.unit.source)
            result["context"] = change.unit.context
        return result

    @staticmethod
    def get_change_headers(change: Change) -> dict[str, str]:
        result = {
            "action": change.get_action_display(),
        }
        if change.project:
            result["project"] = change.project.slug
        if change.component:
            result["component"] = change.component.slug
        return result

    @staticmethod
    def configure_fedora_messaging(
        *,
        amqp_host: str,
        amqp_ssl: bool,
        ca_cert: str | None,
        client_key: str | None,
        client_cert: str | None,
        force_update: bool = False,
    ) -> None:
        """Configure Fedora Messaging."""
        # Build AMQP URL, the parameters might be configurable
        amqp_url = f"{'amqps' if amqp_ssl else 'amqp'}://{amqp_host}?connection_attempts=3&retry_delay=5"

        # Hash certificates to detect configuration changes
        cert_hash = siphash(
            "Fedora Messaging", f"CA:{ca_cert},KEY:{client_key},CERT:{client_cert}"
        )

        messaging_config = fedora_messaging.config.conf

        if (
            not force_update
            and messaging_config.loaded
            and messaging_config["amqp_url"] == amqp_url
            and messaging_config["consumer_config"].get("weblate_cert_hash")
            == cert_hash
        ):
            return

        # Discard existing Twisted service as configuration has changed
        fedora_messaging.api._twisted_service = None  # noqa: SLF001

        # Avoid loading settings file
        messaging_config.loaded = True

        # Apply defaults
        messaging_config.update(deepcopy(fedora_messaging.config.DEFAULTS))

        # We misuse consumer configuration to store certificate info to allow fast change detection
        messaging_config["consumer_config"]["weblate_cert_hash"] = cert_hash

        # Update AMQP URL
        messaging_config["amqp_url"] = amqp_url

        # Store TLS configuration
        certs_path = data_path("cache") / "fedora-messaging"
        certs_path.mkdir(parents=True, exist_ok=True)
        if ca_cert:
            ca_cert_file = certs_path / "ca.crt"
            ca_cert_file.write_text(ca_cert)
            messaging_config["tls"]["ca_cert"] = ca_cert_file.as_posix()
        if client_key:
            key_file = certs_path / "client.key"
            key_file.write_text(client_key)
            messaging_config["tls"]["keyfile"] = key_file.as_posix()
        if client_cert:
            cert_file = certs_path / "client.crt"
            cert_file.write_text(client_cert)
            messaging_config["tls"]["certfile"] = cert_file.as_posix()

        # Update client properties
        messaging_config["client_properties"]["app"] = settings.SITE_TITLE
        messaging_config["client_properties"]["app_url"] = settings.SITE_URL
        messaging_config["client_properties"]["app_contacts_email"] = ", ".join(
            admin[1] for admin in settings.ADMINS
        )

        # Validate the configuration, there is currently no public API for this
        messaging_config._validate()  # noqa: SLF001
