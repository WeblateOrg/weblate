# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import atexit
import json
import os
import socket
import ssl as ssl_module
import threading
import time
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, cast, override
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from amqp.exceptions import AccessRefused, MessageNacked, RecoverableConnectionError
from amqp.transport import SSLTransport, TCPTransport
from celery.signals import worker_process_shutdown
from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.utils.translation import gettext, gettext_lazy
from kombu import Connection, Producer
from kombu.transport.pyamqp import Connection as KombuAMQPConnection
from kombu.transport.pyamqp import Transport as KombuAMQPTransport
from weblate_schemas import validate_schema

from weblate.addons.base import ChangeBaseAddon
from weblate.addons.defaults import (
    DEFAULT_FEDORA_MESSAGING_CONNECTION_ATTEMPTS,
    DEFAULT_FEDORA_MESSAGING_PUBLISH_TIMEOUT,
    DEFAULT_FEDORA_MESSAGING_RETRY_DELAY,
)
from weblate.trans.actions import get_change_action_identifier
from weblate.trans.util import split_plural
from weblate.utils.errors import add_breadcrumb, report_error
from weblate.utils.outbound import validate_connected_peer
from weblate.utils.site import get_site_url
from weblate.utils.validators import validate_fedora_messaging_url

from .forms import FedoraMessagingAddonForm

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    from django.forms.boundfield import BoundField
    from django_stubs_ext import StrOrPromise

    from weblate.addons.models import AddonActivityLog
    from weblate.auth.models import User
    from weblate.trans.models import Category, Change, Component, Project


PEM_BEGIN_PREFIX = "-----BEGIN "
PEM_END_PREFIX = "-----END "
PEM_BOUNDARY_SUFFIX = "-----"
PEM_LABEL_CHARACTERS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ")
TLS_CREDENTIAL_FIELDS = frozenset({"ca_cert", "client_key", "client_cert"})
TLS_PROBE_TIMEOUT = 5
PUBLISH_TIMEOUT_REPORT_INTERVAL = 3600
TOPIC_PREFIX_MAX_LENGTH = 50

# Prefork workers have independent state; threaded workers must serialize
# access to their shared connection, configuration, and publish deadline.
FEDORA_MESSAGING_PUBLISH_LOCK = threading.RLock()


class FedoraMessagingConfigurationError(ValueError):
    """Invalid publisher configuration, shared with the settings form."""

    @property
    def message(self) -> str:
        return str(self)


class WeblateMessage:
    """Transport-independent Fedora Messaging v1 message."""

    def __init__(self, *, topic: str, headers: dict, body: dict) -> None:
        self.topic = topic
        self.body = body
        self.id = str(uuid4())
        self.headers = {
            **headers,
            "fedora_messaging_schema": "weblate.message.v1",
            "fedora_messaging_schema_package": "weblate-schemas",
            "fedora_messaging_severity": 20,
            "priority": 0,
            "sent-at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        }
        for username in sorted(
            {
                value
                for key in ("user", "author")
                if isinstance(value := body.get(key), str) and value
            }
        ):
            self.headers[f"fedora_messaging_user_{username}"] = True

    def validate(self) -> None:
        validate_schema(self.body, "weblate-messaging.schema.json")
        if not self.topic or len(self.topic.encode("utf-8")) > 255:
            msg = "Message topic must contain between 1 and 255 bytes"
            raise ValueError(msg)


class DeadlineTCPTransport(TCPTransport):
    """Bound each resolved address attempt by the remaining publish budget."""

    def _connect(self, host: str, port: int, timeout: float | None) -> None:
        entries = socket.getaddrinfo(
            host, port, socket.AF_UNSPEC, socket.SOCK_STREAM, socket.IPPROTO_TCP
        )
        if not entries:
            msg = "Broker hostname resolved to no addresses"
            raise OSError(msg)
        for index, (family, kind, protocol, _name, address) in enumerate(entries):
            remaining = FedoraMessagingAddon.remaining(PUBLISHER.deadline)
            self.sock = socket.socket(family, kind, protocol)
            try:
                self.sock.settimeout(
                    min(timeout, remaining) if timeout is not None else remaining
                )
                self.sock.connect(address)
            except OSError:
                self.close()
                if index + 1 == len(entries):
                    raise
            else:
                return

    def close(self) -> None:
        # Discard without TLS unwrap or shutdown, which can wait for the peer
        # and would affect a parent's socket when called after fork.
        sock, self.sock = self.sock, None
        self.connected = False
        if sock is not None:
            sock.close()

    def _setup_transport(self) -> None:
        super()._setup_transport()  # type: ignore[misc]
        self._quick_recv = self._deadline_recv

    def _deadline_recv(self, size: int) -> bytes:
        # py-amqp may perform several reads to assemble one frame. Each read
        # must use the remaining budget, even when the peer keeps sending data.
        assert self.sock is not None  # ruff: ignore[assert]
        remaining = FedoraMessagingAddon.remaining(PUBLISHER.deadline)
        timeout = self.sock.gettimeout()
        # Preserve py-amqp's zero-timeout polls for RabbitMQ broker events.
        self.sock.settimeout(
            min(timeout, remaining) if timeout is not None else remaining
        )
        return self.sock.recv(size)


class DeadlineSSLTransport(SSLTransport, DeadlineTCPTransport):
    """Use the remaining budget for TLS after TCP setup and certificate loading."""

    def _setup_transport(self) -> None:
        options = self.sslopts if isinstance(self.sslopts, dict) else {}
        # py-amqp's stubs omit these transport setup hooks.
        wrapped = self._wrap_socket(self.sock, **options)  # type: ignore[attr-defined]
        tls_socket = cast("ssl_module.SSLSocket", wrapped)
        self.sock = tls_socket
        tls_socket.settimeout(FedoraMessagingAddon.remaining(PUBLISHER.deadline))
        tls_socket.do_handshake()
        self._quick_recv = self._deadline_recv


class DeadlineConnection(KombuAMQPConnection):
    """Apply the publish budget to connection setup and AMQP protocol reads."""

    @override
    def Transport(
        self,
        host: str,
        connect_timeout: float | None,
        ssl: bool | dict = False,
        read_timeout: float | None = None,
        write_timeout: float | None = None,
        socket_settings: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ) -> DeadlineTCPTransport:
        transport = DeadlineSSLTransport if ssl else DeadlineTCPTransport
        return transport(
            host,
            connect_timeout=connect_timeout,
            ssl=ssl,
            read_timeout=read_timeout,
            write_timeout=write_timeout,
            socket_settings=socket_settings,
            **kwargs,
        )

    def blocking_read(self, timeout: float | None = None) -> None:
        remaining = FedoraMessagingAddon.remaining(PUBLISHER.deadline)
        return super().blocking_read(
            min(timeout, remaining) if timeout is not None else remaining
        )


class PublisherTransport(KombuAMQPTransport):
    Connection = DeadlineConnection


class PublisherState:
    """Connection state owned by exactly one process, guarded by the publish lock."""

    def __init__(self) -> None:
        self.deadline = 0.0
        self.configuration: tuple | None = None
        self.connection: Connection | None = None
        self.producer: Producer | None = None
        self.directory: TemporaryDirectory | None = None
        self.tls: dict = {}

    def disconnect(self) -> None:
        connection, self.connection = self.connection, None
        self.producer = None
        if connection is not None:
            # Our transport closes the socket without waiting for AMQP or TLS replies.
            connection.collect()

    def close(self, **kwargs: object) -> None:
        with FEDORA_MESSAGING_PUBLISH_LOCK:
            self.disconnect()
            if self.directory is not None:
                self.directory.cleanup()
                self.directory = None
            self.configuration = None
            self.tls = {}


PUBLISHER = PublisherState()


def close_publisher(**kwargs: object) -> None:
    PUBLISHER.close()


atexit.register(close_publisher)
worker_process_shutdown.connect(close_publisher, weak=False)


def reset_publisher_after_fork() -> None:
    # A fork needs fresh process-local state and an unlocked lock.
    # pylint: disable-next=global-statement
    global FEDORA_MESSAGING_PUBLISH_LOCK, PUBLISHER  # ruff: ignore[global-statement]
    # Do not send AMQP shutdown frames or delete the parent's certificate files.
    if PUBLISHER.connection is not None:
        connection = PUBLISHER.connection._connection  # type: ignore[attr-defined]  # ruff: ignore[private-member-access]
        if connection is not None and connection.transport.sock is not None:
            # shutdown() would affect the parent's shared socket after fork.
            connection.transport.sock.close()
            connection.transport.sock = None
        PUBLISHER.connection.collect()
    if PUBLISHER.directory is not None:
        PUBLISHER.directory._finalizer.detach()  # type: ignore[attr-defined]  # ruff: ignore[private-member-access]
    PUBLISHER = PublisherState()
    FEDORA_MESSAGING_PUBLISH_LOCK = threading.RLock()


os.register_at_fork(after_in_child=reset_publisher_after_fork)


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

    def get_integration_instructions(self, user: User) -> str:
        return render_to_string(
            "addons/fedora_messaging_integration.html", {"addon": self, "user": user}
        )

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
        amqp_url = config["amqp_url"]

        with FEDORA_MESSAGING_PUBLISH_LOCK:
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
            message = WeblateMessage(
                topic=self.get_prefixed_topic(
                    self.get_change_topic(change), config.get("topic_prefix")
                ),
                headers=self.get_change_headers(change),
                body=self.get_change_body(change),
            )
            self.publish_message(
                message,
                amqp_url,
                change.project,
                timeout=publish_timeout,
                connection_attempts=connection_attempts,
                retry_delay=retry_delay,
            )
        return {"message_id": message.id}

    def render_activity_log(self, activity: AddonActivityLog) -> str:
        result = activity.details.get("result")
        if isinstance(result, dict) and result.get("message_id"):
            return gettext("Message ID: %(message_id)s") % {
                "message_id": result["message_id"]
            }
        return super().render_activity_log(activity)

    @staticmethod
    def publish_message(
        message: WeblateMessage,
        amqp_url: str,
        project: Project | None,
        timeout: int = DEFAULT_FEDORA_MESSAGING_PUBLISH_TIMEOUT,
        connection_attempts: int = DEFAULT_FEDORA_MESSAGING_CONNECTION_ATTEMPTS,
        retry_delay: int = DEFAULT_FEDORA_MESSAGING_RETRY_DELAY,
    ) -> None:
        """Publish message and report Fedora Messaging failures with context."""
        with FEDORA_MESSAGING_PUBLISH_LOCK:
            deadline = time.monotonic() + timeout
            PUBLISHER.deadline = deadline
            try:
                FedoraMessagingAddon._publish_with_retries(
                    message, amqp_url, deadline, connection_attempts, retry_delay
                )
            except Exception as error:
                PUBLISHER.disconnect()
                FedoraMessagingAddon._report_publish_error(
                    message, amqp_url, project, error
                )
                raise FedoraMessagingPublishError(
                    FedoraMessagingAddon._get_publish_error_message(error)
                ) from error

    @staticmethod
    def _publish_with_retries(
        message: WeblateMessage,
        amqp_url: str,
        deadline: float,
        connection_attempts: int,
        retry_delay: int,
    ) -> None:
        validate_fedora_messaging_url(amqp_url)
        message.validate()
        for attempt in range(connection_attempts):
            try:
                FedoraMessagingAddon._publish_once(message, amqp_url, deadline)
            except (OSError, RecoverableConnectionError):
                PUBLISHER.disconnect()
                if attempt + 1 == connection_attempts:
                    raise
                time.sleep(min(retry_delay, FedoraMessagingAddon.remaining(deadline)))
            else:
                return

    @staticmethod
    def _publish_once(message: WeblateMessage, amqp_url: str, deadline: float) -> None:
        remaining = FedoraMessagingAddon.remaining(deadline)
        if PUBLISHER.connection is None:
            parsed = urlsplit(amqp_url)
            PUBLISHER.connection = Connection(
                hostname=unquote(parsed.hostname or "localhost"),
                port=parsed.port or (5671 if parsed.scheme == "amqps" else 5672),
                userid=unquote(parsed.username)
                if parsed.username is not None
                else None,
                password=unquote(parsed.password)
                if parsed.password is not None
                else None,
                virtual_host=unquote(parsed.path[1:]) or "/",
                transport=PublisherTransport,
                heartbeat=0,
                ssl=PUBLISHER.tls or False,
                login_method="EXTERNAL" if PUBLISHER.tls else "PLAIN",
                connect_timeout=remaining,
                transport_options={
                    "confirm_publish": True,
                    "read_timeout": remaining,
                    "write_timeout": remaining,
                    "client_properties": {
                        "app": settings.SITE_TITLE,
                        "app_url": settings.SITE_URL,
                        "app_contacts_email": ", ".join(settings.ADMINS),
                    },
                },
            )
            # Weblate owns retries and the overall publish deadline.
            PUBLISHER.connection.ensure_connection(
                max_retries=0, reraise_as_library_errors=False
            )
            PUBLISHER.producer = Producer(PUBLISHER.connection, auto_declare=False)
        remaining = FedoraMessagingAddon.remaining(deadline)
        PUBLISHER.connection.connection.transport.sock.settimeout(remaining)
        assert PUBLISHER.producer is not None  # ruff: ignore[assert]
        PUBLISHER.producer.publish(
            json.dumps(message.body),
            exchange="amq.topic",
            routing_key=message.topic,
            headers=message.headers,
            message_id=message.id,
            delivery_mode=2,
            priority=0,
            content_type="application/json",
            content_encoding="utf-8",
            retry=False,
            timeout=remaining,
            confirm_timeout=remaining,
        )

    @staticmethod
    def remaining(deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            msg = "Fedora Messaging publish timed out"
            raise TimeoutError(msg)
        return remaining

    @staticmethod
    def _report_publish_error(
        message: WeblateMessage,
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
        report_error(
            "Fedora Messaging publish failed",
            exception=error,
            level="error",
            project=project,
            skip_error_reporting=not FedoraMessagingAddon._should_report_publish_error(
                error, amqp_url, project
            ),
        )

    @staticmethod
    def _should_report_publish_error(
        error: Exception, amqp_url: str, project: Project | None
    ) -> bool:
        if not isinstance(error, TimeoutError):
            return True

        cache_key = "fedora-messaging-publish-timeout-report:{}".format(
            sha256(
                f"{project.slug if project else ''}\0{amqp_url}".encode()
            ).hexdigest()
        )
        try:
            return cache.add(cache_key, True, PUBLISH_TIMEOUT_REPORT_INTERVAL)
        except Exception:
            # Fail open so cache outages do not hide persistent publish failures.
            return True

    @staticmethod
    def _get_broker_context(amqp_url: str) -> dict[str, object]:
        parsed = urlsplit(amqp_url)
        return {
            "amqp_scheme": parsed.scheme,
            "amqp_host": parsed.hostname,
            "amqp_port": parsed.port or (5671 if parsed.scheme == "amqps" else 5672),
        }

    @staticmethod
    def _get_publish_error_message(error: Exception) -> str:
        if isinstance(error, TimeoutError):
            return gettext(
                "Fedora Messaging publish timed out; the broker connection or delivery confirmation did not complete: %(error)s"
            ) % {"error": error}
        if isinstance(error, MessageNacked):
            return gettext(
                "Fedora Messaging broker returned the message: %(error)s"
            ) % {"error": error}
        if isinstance(error, AccessRefused):
            return gettext(
                "Fedora Messaging broker rejected the message: %(error)s"
            ) % {"error": error}
        return gettext("Fedora Messaging publish failed: %(error)s") % {"error": error}

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
    def normalize_topic_prefix(prefix: str | None) -> str:
        """Normalize a configured topic prefix."""
        return (prefix or "").strip().strip(".")

    @classmethod
    def get_prefixed_topic(cls, topic: str, prefix: str | None) -> str:
        """Apply configured prefix to generated topic."""
        prefix = cls.normalize_topic_prefix(prefix)
        if not prefix:
            return topic
        return f"{prefix}.{topic}"

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
        validate_fedora_messaging_url(amqp_url)

        configuration = (
            amqp_url,
            ca_cert,
            client_key,
            client_cert,
            connection_attempts,
            retry_delay,
        )
        with FEDORA_MESSAGING_PUBLISH_LOCK:
            if not force_update and PUBLISHER.configuration == configuration:
                return
            FedoraMessagingAddon.validate_tls_credentials(
                ca_cert=ca_cert, client_key=client_key, client_cert=client_cert
            )
            # The cached publisher owns these files until reconfiguration or shutdown.
            directory = TemporaryDirectory(prefix="weblate-fedora-")  # pylint: disable=consider-using-with
            try:
                tls = FedoraMessagingAddon._prepare_tls(
                    directory.name, amqp_url, ca_cert, client_key, client_cert
                )
            except (OSError, ValueError) as error:
                directory.cleanup()
                raise FedoraMessagingConfigurationError(str(error)) from error
            PUBLISHER.close()
            PUBLISHER.directory = directory
            PUBLISHER.tls = tls
            PUBLISHER.configuration = configuration

    @staticmethod
    def _prepare_tls(
        directory: str,
        amqp_url: str,
        ca_cert: str | None,
        client_key: str | None,
        client_cert: str | None,
    ) -> dict:
        if urlsplit(amqp_url).scheme != "amqps":
            return {}
        tls: dict = {}
        for name, value in (
            ("ca_certs", ca_cert),
            ("keyfile", client_key),
            ("certfile", client_cert),
        ):
            if not value:
                raise FedoraMessagingConfigurationError(
                    gettext(
                        "The SSL certificates have to be provided for SSL connection."
                    )
                )
            if name == "ca_certs":
                # Match the previous publisher: custom CAs extend system trust.
                value += "\n" + "".join(
                    ssl_module.DER_cert_to_PEM_cert(cert)
                    for cert in ssl_module.create_default_context().get_ca_certs(
                        binary_form=True
                    )
                )
            path = Path(directory) / name
            path.write_text(value.strip() + "\n", encoding="utf-8")
            path.chmod(0o600)
            tls[name] = str(path)
        tls.update(
            cert_reqs=ssl_module.CERT_REQUIRED,
            server_hostname=urlsplit(amqp_url).hostname,
            ssl_version=ssl_module.PROTOCOL_TLS_CLIENT,
            tls_minimum_version=ssl_module.TLSVersion.TLSv1_2,
        )
        FedoraMessagingAddon._tls_context(tls)
        return tls

    @staticmethod
    def _tls_context(tls: dict) -> ssl_module.SSLContext:
        context = ssl_module.SSLContext(ssl_module.PROTOCOL_TLS_CLIENT)
        context.minimum_version = ssl_module.TLSVersion.TLSv1_2
        context.load_verify_locations(cafile=tls["ca_certs"])
        context.load_cert_chain(tls["certfile"], tls["keyfile"])
        return context

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
        if urlsplit(amqp_url).scheme != "amqps":
            return
        parsed = urlsplit(amqp_url)
        assert parsed.hostname is not None  # ruff: ignore[assert]
        try:
            context = FedoraMessagingAddon._tls_context(PUBLISHER.tls)
            with socket.create_connection(
                (parsed.hostname, parsed.port or 5671), timeout=timeout
            ) as connection:
                validate_connected_peer(
                    parsed.hostname,
                    FedoraMessagingAddon._get_socket_peer_ip(connection),
                    allow_private_targets=not settings.WEBHOOK_RESTRICT_PRIVATE,
                    private_allowlist=settings.WEBHOOK_PRIVATE_ALLOWLIST,
                )
                with context.wrap_socket(connection, server_hostname=parsed.hostname):
                    pass
        except (OSError, ValueError, ValidationError) as error:
            raise FedoraMessagingConfigurationError(
                gettext(
                    "Could not verify TLS connection to the Fedora Messaging broker: %(error)s"
                )
                % {"error": error}
            ) from error

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
        if not value:
            return
        labels = FedoraMessagingAddon._get_pem_block_labels(value)
        if not labels or any(label != "CERTIFICATE" for label in labels):
            raise FedoraMessagingConfigurationError(message)
        try:
            certificates = x509.load_pem_x509_certificates(value.encode())
        except ValueError as error:
            raise FedoraMessagingConfigurationError(message) from error
        if not certificates:
            raise FedoraMessagingConfigurationError(message)

    @staticmethod
    def _validate_pem_private_key(value: str | None, message: str) -> None:
        if not value:
            return
        labels = FedoraMessagingAddon._get_pem_block_labels(value)
        if len(labels) != 1 or not labels[0].endswith("PRIVATE KEY"):
            raise FedoraMessagingConfigurationError(message)
        try:
            serialization.load_pem_private_key(value.encode(), password=None)
        except (TypeError, ValueError, UnsupportedAlgorithm) as error:
            raise FedoraMessagingConfigurationError(message) from error

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
