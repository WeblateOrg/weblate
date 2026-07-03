# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import socket
import ssl
import time
from copy import deepcopy
from typing import TYPE_CHECKING, Protocol, cast
from urllib.parse import SplitResult, parse_qsl, urlencode, urlsplit, urlunsplit

from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext, gettext_lazy
from OpenSSL import SSL
from siphashc import siphash

from weblate.addons.base import ChangeBaseAddon
from weblate.addons.defaults import (
    DEFAULT_FEDORA_MESSAGING_CONNECTION_ATTEMPTS,
    DEFAULT_FEDORA_MESSAGING_PUBLISH_TIMEOUT,
    DEFAULT_FEDORA_MESSAGING_RETRY_DELAY,
)
from weblate.trans.actions import get_change_action_identifier
from weblate.trans.util import split_plural
from weblate.utils.data import data_path
from weblate.utils.errors import add_breadcrumb, report_error
from weblate.utils.outbound import validate_connected_peer
from weblate.utils.site import get_site_url

from .forms import FedoraMessagingAddonForm

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from django.forms.boundfield import BoundField
    from django_stubs_ext import StrOrPromise
    from weblate_schemas.messages import WeblateV1Message

    from weblate.trans.models import Category, Change, Component, Project


PEM_BEGIN_PREFIX = "-----BEGIN "
PEM_END_PREFIX = "-----END "
PEM_BOUNDARY_SUFFIX = "-----"
PEM_LABEL_CHARACTERS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ")
TLS_CREDENTIAL_FIELDS = frozenset({"ca_cert", "client_key", "client_cert"})
TLS_PROBE_TIMEOUT = 5
SERVICE_STOP_TIMEOUT = 5


class BrokerParameters(Protocol):
    host: str
    port: int
    ssl_options: object | None


class BrokerTLSContextFactory(Protocol):
    def clientConnectionForTLS(  # noqa: N802
        self, tls_protocol: object
    ) -> SSL.Connection: ...


class BrokerTLSProbeFactory:
    wrappedFactory = object()  # noqa: N815


class BrokerTLSProbeProtocol:
    factory = BrokerTLSProbeFactory()

    def __init__(self) -> None:
        self.verification_failure: object | None = None
        self.aborted = False

    def failVerification(self, failure: object) -> None:  # noqa: N802
        self.verification_failure = failure

    def abortConnection(self) -> None:  # noqa: N802
        self.aborted = True


class FedoraMessagingPublishError(RuntimeError):
    """Publish failure reported with Fedora Messaging context."""

    _weblate_reported = True


class FedoraMessagingAddon(ChangeBaseAddon):
    icon = "webhook.svg"
    settings_form = FedoraMessagingAddonForm
    name = "weblate.fedora_messaging.publish"
    verbose = gettext_lazy("Fedora Messaging")
    description = gettext_lazy(
        "Sends notifications to a Fedora Messaging compatible AMQP exchange."
    )
    multiple = False
    version_added = "5.15"

    @classmethod
    def can_install(
        cls,
        *,
        component: Component | None = None,
        category: Category | None = None,
        project: Project | None = None,
    ) -> bool:
        # Can be installed only once site-wide
        return project is None and component is None and category is None

    @classmethod
    def can_process(
        cls,
        *,
        # ruff: ignore[unused-class-method-argument]
        component: Component | None = None,
        # ruff: ignore[unused-class-method-argument]
        category: Category | None = None,
        # ruff: ignore[unused-class-method-argument]
        project: Project | None = None,
    ) -> bool:
        return True

    def change_event(
        self, change: Change, activity_log_id: int | None = None
    ) -> dict | None:
        # ruff: ignore[import-outside-top-level]
        from weblate_schemas.messages import WeblateV1Message

        config = self.instance.configuration
        connection_attempts = int(
            config.get(
                "connection_attempts", DEFAULT_FEDORA_MESSAGING_CONNECTION_ATTEMPTS
            )
        )
        retry_delay = int(
            config.get("retry_delay", DEFAULT_FEDORA_MESSAGING_RETRY_DELAY)
        )
        publish_timeout = int(
            config.get("publish_timeout", DEFAULT_FEDORA_MESSAGING_PUBLISH_TIMEOUT)
        )
        amqp_url = self.get_configured_amqp_url(
            config["amqp_url"],
            connection_attempts=connection_attempts,
            retry_delay=retry_delay,
        )

        # Apply configuration
        self.configure_fedora_messaging(
            amqp_url=config["amqp_url"],
            ca_cert=config.get("ca_cert"),
            client_key=config.get("client_key"),
            client_cert=config.get("client_cert"),
            connection_attempts=connection_attempts,
            retry_delay=retry_delay,
        )

        # Build message payload
        message = WeblateV1Message(
            topic=self.get_change_topic(change),
            headers=self.get_change_headers(change),
            body=self.get_change_body(change),
        )
        self.publish_message(message, amqp_url, change.project, timeout=publish_timeout)
        return {"message_id": message.id}

    @staticmethod
    def publish_message(
        message: WeblateV1Message,
        amqp_url: str,
        project: Project | None,
        timeout: int = DEFAULT_FEDORA_MESSAGING_PUBLISH_TIMEOUT,
    ) -> None:
        """Publish message and report Fedora Messaging failures with context."""
        # ruff: ignore[import-outside-top-level]
        import fedora_messaging.api

        try:
            fedora_messaging.api.publish(message, timeout=timeout)
        except Exception as error:
            FedoraMessagingAddon._reset_fedora_messaging_service()
            FedoraMessagingAddon._report_publish_error(
                message, amqp_url, project, error
            )
            raise FedoraMessagingPublishError(
                FedoraMessagingAddon._get_publish_error_message(error)
            ) from error

    @staticmethod
    def _reset_fedora_messaging_service() -> None:
        # ruff: ignore[import-outside-top-level]
        import fedora_messaging.api

        # A timeout can leave the Twisted publisher service in a stale state.
        # Stop and reset it so the next publish attempt creates a fresh connection.
        # ruff: ignore[private-member-access]
        twisted_service = fedora_messaging.api._twisted_service
        stop_service = getattr(twisted_service, "stopService", None)
        if callable(stop_service):
            FedoraMessagingAddon._stop_fedora_messaging_service(stop_service)
        fedora_messaging.api._twisted_service = None  # noqa: SLF001

    @staticmethod
    def _stop_fedora_messaging_service(stop_service: Callable[[], object]) -> None:
        # ruff: ignore[import-outside-top-level]
        import crochet

        @crochet.run_in_reactor
        def stop_service_in_reactor() -> object:
            return stop_service()

        result = stop_service_in_reactor()
        try:
            result.wait(timeout=SERVICE_STOP_TIMEOUT)
        except crochet.TimeoutError:
            result.cancel()
            report_error("Fedora Messaging service shutdown timed out", level="error")
        except Exception:
            report_error("Fedora Messaging service shutdown failed", level="error")

    @staticmethod
    def _report_publish_error(
        message: WeblateV1Message,
        amqp_url: str,
        project: Project | None,
        error: Exception,
    ) -> None:
        add_breadcrumb(
            "fedora_messaging",
            "Fedora Messaging publish failed",
            level="error",
            message_id=message.id,
            topic=message.topic,
            exception_class=error.__class__.__name__,
            **FedoraMessagingAddon._get_broker_context(amqp_url),
        )
        report_error("Fedora Messaging publish failed", level="error", project=project)

    @staticmethod
    def _get_broker_context(amqp_url: str) -> dict[str, object]:
        # ruff: ignore[import-outside-top-level]
        import pika  # type: ignore[import-untyped]

        try:
            parameters = pika.URLParameters(amqp_url)
        except (TypeError, ValueError) as error:
            return {
                "amqp_url_parse_error": str(error),
            }
        return {
            "amqp_scheme": "amqps" if parameters.ssl_options else "amqp",
            "amqp_host": parameters.host,
            "amqp_port": parameters.port,
            "connection_attempts": parameters.connection_attempts,
            "retry_delay": parameters.retry_delay,
        }

    @staticmethod
    def _get_publish_error_message(error: Exception) -> str:
        # ruff: ignore[import-outside-top-level]
        from fedora_messaging import exceptions as fedora_messaging_exceptions

        if isinstance(error, fedora_messaging_exceptions.PublishTimeout):
            return gettext(
                "Fedora Messaging publish timed out; the broker did not confirm delivery: %(error)s"
            ) % {"error": error}
        if FedoraMessagingAddon._is_missing_publisher_error(error):
            return gettext(
                "Fedora Messaging publisher service was unavailable; the connection will be recreated on the next attempt: %(error)s"
            ) % {"error": error}
        if isinstance(error, fedora_messaging_exceptions.PublishReturned):
            return gettext(
                "Fedora Messaging broker returned the message: %(error)s"
            ) % {"error": error}
        if isinstance(error, fedora_messaging_exceptions.PublishForbidden):
            return gettext(
                "Fedora Messaging broker rejected the message: %(error)s"
            ) % {"error": error}
        return gettext("Fedora Messaging publish failed: %(error)s") % {"error": error}

    @staticmethod
    def _is_missing_publisher_error(error: Exception) -> bool:
        message = str(error)
        return (
            isinstance(error, AttributeError)
            and "NoneType" in message
            and "publish" in message
        )

    @staticmethod
    def get_change_topic(change: Change) -> str:
        """
        Generate a topic for the change.

        It is in the form
        weblate.<action>.<project>.<category...>.<component>.<translation>
        """
        parts = ["weblate", get_change_action_identifier(change.get_action_display())]
        for path_object in (
            change.translation,
            change.component,
            change.category,
            change.project,
        ):
            if path_object is not None:
                parts.extend(path_object.get_url_path())
                break
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

    def get_setting_value(self, field: BoundField) -> StrOrPromise:
        if field.name in TLS_CREDENTIAL_FIELDS:
            return gettext("configured")
        return super().get_setting_value(field)

    @staticmethod
    def configure_fedora_messaging(
        *,
        amqp_url: str,
        ca_cert: str | None,
        client_key: str | None,
        client_cert: str | None,
        connection_attempts: int = DEFAULT_FEDORA_MESSAGING_CONNECTION_ATTEMPTS,
        retry_delay: int = DEFAULT_FEDORA_MESSAGING_RETRY_DELAY,
        force_update: bool = False,
    ) -> None:
        """Configure Fedora Messaging."""
        # ruff: ignore[import-outside-top-level]

        import fedora_messaging.config

        ca_cert = FedoraMessagingAddon._normalize_pem(ca_cert)
        client_key = FedoraMessagingAddon._normalize_pem(client_key)
        client_cert = FedoraMessagingAddon._normalize_pem(client_cert)
        amqp_url = FedoraMessagingAddon.get_configured_amqp_url(
            amqp_url,
            connection_attempts=connection_attempts,
            retry_delay=retry_delay,
        )

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

        FedoraMessagingAddon.validate_tls_credentials(
            ca_cert=ca_cert, client_key=client_key, client_cert=client_cert
        )

        # Discard existing Twisted service as configuration has changed
        FedoraMessagingAddon._reset_fedora_messaging_service()

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
            FedoraMessagingAddon._write_pem_file(ca_cert_file, ca_cert)
            messaging_config["tls"]["ca_cert"] = ca_cert_file.as_posix()
        if client_key:
            key_file = certs_path / "client.key"
            FedoraMessagingAddon._write_pem_file(key_file, client_key)
            messaging_config["tls"]["keyfile"] = key_file.as_posix()
        if client_cert:
            cert_file = certs_path / "client.crt"
            FedoraMessagingAddon._write_pem_file(cert_file, client_cert)
            messaging_config["tls"]["certfile"] = cert_file.as_posix()

        # Update client properties
        messaging_config["client_properties"]["app"] = settings.SITE_TITLE
        messaging_config["client_properties"]["app_url"] = settings.SITE_URL
        messaging_config["client_properties"]["app_contacts_email"] = ", ".join(
            settings.ADMINS
        )

        # Validate the configuration, there is currently no public API for this
        # ruff: ignore[private-member-access]
        messaging_config._validate()

    @staticmethod
    def get_configured_amqp_url(
        amqp_url: str, *, connection_attempts: int, retry_delay: int
    ) -> str:
        parsed, query = FedoraMessagingAddon._parse_amqp_url_query(amqp_url)
        query["connection_attempts"] = str(connection_attempts)
        query["retry_delay"] = str(retry_delay)
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(query),
                parsed.fragment,
            )
        )

    @staticmethod
    def get_broker_amqp_url(amqp_url: str) -> str:
        parsed, query = FedoraMessagingAddon._parse_amqp_url_query(amqp_url)
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(query),
                parsed.fragment,
            )
        )

    @staticmethod
    def _parse_amqp_url_query(amqp_url: str) -> tuple[SplitResult, dict[str, str]]:
        parsed = urlsplit(amqp_url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query.pop("connection_attempts", None)
        query.pop("retry_delay", None)
        return parsed, query

    @staticmethod
    def validate_tls_credentials(
        *,
        ca_cert: str | None,
        client_key: str | None,
        client_cert: str | None,
    ) -> None:
        """Validate TLS credentials accepted by Fedora Messaging."""
        FedoraMessagingAddon._validate_pem_certificates(
            ca_cert,
            gettext("CA certificates must be valid PEM encoded X.509 certificates."),
        )
        FedoraMessagingAddon._validate_pem_private_key(
            client_key,
            gettext("Client SSL key must be an unencrypted PEM encoded private key."),
        )
        FedoraMessagingAddon._validate_pem_certificates(
            client_cert,
            gettext(
                "Client SSL certificates must be valid PEM encoded X.509 certificates."
            ),
        )

    @staticmethod
    def validate_broker_tls(
        amqp_url: str,
        timeout: float = TLS_PROBE_TIMEOUT,
    ) -> None:
        """Validate TLS trust against the configured Fedora Messaging broker."""
        # ruff: ignore[import-outside-top-level]
        import pika  # type: ignore[import-untyped]

        # ruff: ignore[import-outside-top-level]
        from fedora_messaging.exceptions import ConfigurationException

        try:
            parameters = pika.URLParameters(amqp_url)
        except (TypeError, ValueError) as error:
            raise ConfigurationException(
                gettext("Fedora Messaging broker URL is invalid: %(error)s")
                % {"error": error}
            ) from error

        if parameters.ssl_options is None:
            return

        try:
            tls_context_factory = FedoraMessagingAddon._configure_broker_tls_options(
                parameters
            )
            if tls_context_factory is None:
                return
            FedoraMessagingAddon._probe_broker_tls(
                parameters, tls_context_factory, timeout
            )
        except (
            ConfigurationException,
            ValidationError,
            OSError,
            SSL.Error,
            TimeoutError,
            ssl.SSLError,
        ) as error:
            raise ConfigurationException(
                gettext(
                    "Could not verify TLS connection to the Fedora Messaging broker: %(error)s"
                )
                % {"error": error}
            ) from error

    @staticmethod
    def _configure_broker_tls_options(
        parameters: BrokerParameters,
    ) -> BrokerTLSContextFactory | None:
        # ruff: ignore[import-outside-top-level]
        from fedora_messaging.twisted import service as fedora_messaging_service

        # Use Fedora Messaging to configure TLS options so URL and TLS
        # semantics stay aligned with the publisher implementation.
        # ruff: ignore[private-member-access]
        fedora_messaging_service._configure_tls_parameters(parameters)
        if parameters.ssl_options is None:
            return None
        # Use the same Twisted/pyOpenSSL context factory that Fedora Messaging
        # uses for the actual AMQP transport instead of duplicating certificate
        # verification policy with a stdlib SSLContext.
        # ruff: ignore[private-member-access]
        return cast(
            "BrokerTLSContextFactory",
            fedora_messaging_service._ssl_context_factory(parameters),
        )

    @staticmethod
    def _probe_broker_tls(
        parameters: BrokerParameters,
        tls_context_factory: BrokerTLSContextFactory,
        timeout: float,
    ) -> None:
        with socket.create_connection(
            (parameters.host, parameters.port), timeout=timeout
        ) as connection:
            connection.settimeout(timeout)
            validate_connected_peer(
                parameters.host,
                FedoraMessagingAddon._get_socket_peer_ip(connection),
                allow_private_targets=not settings.WEBHOOK_RESTRICT_PRIVATE,
                allowed_domains=settings.WEBHOOK_PRIVATE_ALLOWLIST,
            )
            FedoraMessagingAddon._perform_broker_tls_handshake(
                connection, tls_context_factory, timeout
            )

    @staticmethod
    def _perform_broker_tls_handshake(
        connection: socket.socket,
        tls_context_factory: BrokerTLSContextFactory,
        timeout: float,
    ) -> None:
        protocol = BrokerTLSProbeProtocol()
        tls_connection = tls_context_factory.clientConnectionForTLS(protocol)
        tls_connection.set_connect_state()
        deadline = time.monotonic() + timeout

        while True:
            FedoraMessagingAddon._set_broker_tls_timeout(connection, deadline)
            try:
                tls_connection.do_handshake()
            except SSL.WantReadError as error:
                FedoraMessagingAddon._flush_broker_tls_data(
                    tls_connection, connection, deadline
                )
                FedoraMessagingAddon._set_broker_tls_timeout(connection, deadline)
                data = connection.recv(2**15)
                if not data:
                    msg = "TLS connection closed during handshake"
                    raise OSError(msg) from error
                tls_connection.bio_write(data)
            except SSL.WantWriteError:
                FedoraMessagingAddon._flush_broker_tls_data(
                    tls_connection, connection, deadline
                )
            else:
                if protocol.verification_failure is not None:
                    raise SSL.Error(str(protocol.verification_failure))
                FedoraMessagingAddon._flush_broker_tls_data(
                    tls_connection, connection, deadline
                )
                return

    @staticmethod
    def _flush_broker_tls_data(
        tls_connection: SSL.Connection, connection: socket.socket, deadline: float
    ) -> None:
        while True:
            try:
                data = tls_connection.bio_read(2**15)
            except SSL.WantReadError:
                return
            if not data:
                return
            FedoraMessagingAddon._set_broker_tls_timeout(connection, deadline)
            connection.sendall(data)

    @staticmethod
    def _set_broker_tls_timeout(connection: socket.socket, deadline: float) -> None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            msg = "TLS handshake timed out"
            raise TimeoutError(msg)
        connection.settimeout(remaining)

    @staticmethod
    def _get_socket_peer_ip(connection: socket.socket) -> str | None:
        try:
            peer = connection.getpeername()
        except OSError:
            return None

        if isinstance(peer, tuple) and peer:
            return str(peer[0])
        return None

    @staticmethod
    def _validate_pem_certificates(value: str | None, message: str) -> None:
        # ruff: ignore[import-outside-top-level]
        from fedora_messaging.exceptions import ConfigurationException

        if not value:
            return
        labels = FedoraMessagingAddon._get_pem_block_labels(value)
        if not labels or any(label != "CERTIFICATE" for label in labels):
            raise ConfigurationException(message)
        try:
            certificates = x509.load_pem_x509_certificates(value.encode())
        except ValueError as error:
            raise ConfigurationException(message) from error
        if not certificates:
            raise ConfigurationException(message)

    @staticmethod
    def _validate_pem_private_key(value: str | None, message: str) -> None:
        # ruff: ignore[import-outside-top-level]
        from fedora_messaging.exceptions import ConfigurationException

        if not value:
            return
        labels = FedoraMessagingAddon._get_pem_block_labels(value)
        if len(labels) != 1 or not labels[0].endswith("PRIVATE KEY"):
            raise ConfigurationException(message)
        try:
            serialization.load_pem_private_key(value.encode(), password=None)
        except (TypeError, ValueError, UnsupportedAlgorithm) as error:
            raise ConfigurationException(message) from error

    @staticmethod
    def _get_pem_block_labels(value: str) -> list[str]:
        # Cryptography's PEM loaders ignore unrelated PEM blocks and text; validate
        # the full PEM container before handing it to the type-specific loader.
        labels: list[str] = []
        position = 0
        lines = value.strip().splitlines()
        while position < len(lines):
            if not lines[position].strip():
                position += 1
                continue
            label = FedoraMessagingAddon._get_pem_begin_label(lines[position])
            if label is None:
                return []
            end_boundary = f"{PEM_END_PREFIX}{label}{PEM_BOUNDARY_SUFFIX}"
            position += 1
            while position < len(lines) and lines[position].rstrip() != end_boundary:
                position += 1
            if position == len(lines):
                return []
            labels.append(label)
            position += 1
        return labels

    @staticmethod
    def _get_pem_begin_label(line: str) -> str | None:
        if not line.startswith(PEM_BEGIN_PREFIX) or not line.endswith(
            PEM_BOUNDARY_SUFFIX
        ):
            return None
        label = line[len(PEM_BEGIN_PREFIX) : -len(PEM_BOUNDARY_SUFFIX)]
        if not label or any(char not in PEM_LABEL_CHARACTERS for char in label):
            return None
        return label

    @staticmethod
    def _normalize_pem(value: str | None) -> str | None:
        if not value:
            return None
        value = value.strip()
        if not value:
            return None
        return f"{value}\n"

    @staticmethod
    def _write_pem_file(path: Path, value: str) -> None:
        path.write_text(value, encoding="utf-8")
