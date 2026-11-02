# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import errno
import ssl
import time
from pathlib import Path
from struct import pack
from unittest.mock import MagicMock, call, patch

from amqp import Message, spec
from amqp.exceptions import AccessRefused, MessageNacked
from amqp.method_framing import frame_handler
from django.test import SimpleTestCase

from weblate.addons import fedora_messaging as messaging
from weblate.utils.validators import validate_fedora_messaging_url


class PublisherTest(SimpleTestCase):
    def setUp(self) -> None:
        self.clock = MagicMock(wraps=time)
        clock_patch = patch.object(messaging, "time", self.clock)
        clock_patch.start()
        self.addCleanup(clock_patch.stop)
        self.state = messaging.PublisherState()
        self.state_patch = patch.object(messaging, "PUBLISHER", self.state)
        self.state_patch.start()
        self.addCleanup(self.state_patch.stop)
        self.addCleanup(self.state.close)
        self.validation = patch.object(messaging, "validate_fedora_messaging_url")
        self.validation.start()
        self.addCleanup(self.validation.stop)
        self.connection_patch = patch.object(messaging, "Connection")
        self.connection = self.connection_patch.start().return_value
        self.addCleanup(self.connection_patch.stop)
        self.producer_patch = patch.object(messaging, "Producer")
        self.producer = self.producer_patch.start().return_value
        self.addCleanup(self.producer_patch.stop)
        self.report_patch = patch.object(messaging, "report_error")
        self.report = self.report_patch.start()
        self.addCleanup(self.report_patch.stop)
        self.message = messaging.WeblateMessage(
            topic="weblate.test",
            headers={"action": "New translation"},
            body={
                "change_id": 1,
                "action": "New translation",
                "timestamp": "2026-10-29T10:00:00+00:00",
                "user": "alice",
                "author": "bob",
            },
        )
        self.configure()

    @staticmethod
    def configure(retry_delay: int = 2) -> None:
        messaging.FedoraMessagingAddon.configure_fedora_messaging(
            amqp_url="amqp://broker.example",
            ca_cert=None,
            client_cert=None,
            client_key=None,
            retry_delay=retry_delay,
        )

    def publish(self, **kwargs: int) -> None:
        messaging.FedoraMessagingAddon.publish_message(
            self.message, "amqp://broker.example", None, **kwargs
        )

    def test_reuses_confirmed_connection(self) -> None:
        self.publish()
        self.publish()
        self.connection.ensure_connection.assert_called_once()
        self.assertEqual(self.producer.publish.call_count, 2)
        properties = self.producer.publish.call_args.kwargs
        self.assertEqual(properties["message_id"], self.message.id)
        self.assertEqual(properties["delivery_mode"], 2)
        self.assertEqual(properties["exchange"], "amq.topic")
        self.assertFalse(properties["retry"])

    def test_changed_configuration_discards_connection(self) -> None:
        self.publish()
        self.configure(retry_delay=3)
        self.connection.collect.assert_called_once()
        self.assertIsNone(self.state.connection)
        self.publish()
        self.assertEqual(self.connection.ensure_connection.call_count, 2)

    def test_unchanged_configuration_preserves_connection(self) -> None:
        self.publish()
        self.configure()
        self.connection.collect.assert_not_called()

    def test_stale_connection_retries_same_message_id(self) -> None:
        self.producer.publish.side_effect = [OSError("closed"), None]
        self.publish(connection_attempts=2, retry_delay=0)
        self.assertEqual(self.connection.ensure_connection.call_count, 2)
        self.assertEqual(
            {
                call.kwargs["message_id"]
                for call in self.producer.publish.call_args_list
            },
            {self.message.id},
        )

    def test_rejections_are_not_retried(self) -> None:
        for error in (AccessRefused("forbidden"), MessageNacked()):
            with self.subTest(error=type(error)):
                self.producer.publish.reset_mock()
                self.producer.publish.side_effect = error
                with self.assertRaises(messaging.FedoraMessagingPublishError):
                    self.publish(connection_attempts=3, retry_delay=0)
                self.producer.publish.assert_called_once()
                self.assertIsNone(self.state.connection)

    def test_exhausted_attempts_report_once_and_allow_recovery(self) -> None:
        self.producer.publish.side_effect = OSError("closed")
        with self.assertRaises(messaging.FedoraMessagingPublishError):
            self.publish(connection_attempts=2, retry_delay=0)
        self.assertEqual(self.producer.publish.call_count, 2)
        self.report.assert_called_once()
        self.assertIsNone(self.state.connection)
        self.producer.publish.side_effect = None
        self.publish()

    def test_expired_budget_does_not_connect(self) -> None:
        with self.assertRaises(messaging.FedoraMessagingPublishError):
            self.publish(timeout=0)
        self.connection.ensure_connection.assert_not_called()

    def test_connection_attempts_use_only_explicit_retries(self) -> None:
        self.connection_patch.stop()
        for attempts, delay in ((1, 0), (3, 0), (3, 2)):
            with self.subTest(attempts=attempts, delay=delay):
                self.check_connection_attempts(attempts, delay)

    def check_connection_attempts(self, attempts: int, delay: int) -> None:
        now = 0.0
        budgets = []

        def fail_connection(transport: messaging.PublisherTransport) -> None:
            nonlocal now
            assert transport.client is not None  # ruff: ignore[assert]
            budgets.append(transport.client.connect_timeout)
            now += 0.25
            msg = "broker unavailable"
            raise OSError(msg)

        def sleep(seconds: float) -> None:
            nonlocal now
            now += seconds

        with (
            patch.object(self.clock, "monotonic", side_effect=lambda: now),
            patch.object(self.clock, "sleep", side_effect=sleep) as retry_sleep,
            patch("kombu.utils.functional.sleep") as kombu_sleep,
            patch.object(
                messaging.PublisherTransport,
                "establish_connection",
                autospec=True,
                side_effect=fail_connection,
            ) as establish,
            self.assertRaises(messaging.FedoraMessagingPublishError),
        ):
            self.publish(connection_attempts=attempts, retry_delay=delay, timeout=30)

        self.assertEqual(establish.call_count, attempts)
        self.assertEqual(retry_sleep.call_count, attempts - 1)
        self.assertEqual(
            budgets, [30 - index * (0.25 + delay) for index in range(attempts)]
        )
        kombu_sleep.assert_not_called()
        self.assertIsNone(self.state.connection)

    def test_connection_retry_stops_at_deadline(self) -> None:
        self.connection_patch.stop()
        now = 0.0

        def sleep(seconds: float) -> None:
            nonlocal now
            now += seconds

        with (
            patch.object(self.clock, "monotonic", side_effect=lambda: now),
            patch.object(self.clock, "sleep", side_effect=sleep) as retry_sleep,
            patch("kombu.utils.functional.sleep") as kombu_sleep,
            patch.object(
                messaging.PublisherTransport,
                "establish_connection",
                side_effect=OSError("broker unavailable"),
            ) as establish,
            self.assertRaises(messaging.FedoraMessagingPublishError) as error,
        ):
            self.publish(connection_attempts=3, retry_delay=2, timeout=1)

        establish.assert_called_once()
        retry_sleep.assert_called_once_with(1)
        kombu_sleep.assert_not_called()
        self.assertIsInstance(error.exception.__cause__, TimeoutError)

    def test_headers_preserve_consumer_contract(self) -> None:
        self.assertEqual(
            self.message.headers["fedora_messaging_schema"], "weblate.message.v1"
        )
        self.assertEqual(
            self.message.headers["fedora_messaging_schema_package"], "weblate-schemas"
        )
        self.assertTrue(self.message.headers["fedora_messaging_user_alice"])
        self.assertTrue(self.message.headers["fedora_messaging_user_bob"])
        self.message.validate()

    def test_tls_files_private_and_removed_on_configuration_change(self) -> None:
        cert = Path("weblate/trans/tests/data/saml.crt").read_text(encoding="utf-8")
        key = Path("weblate/trans/tests/data/saml.key").read_text(encoding="utf-8")
        messaging.FedoraMessagingAddon.configure_fedora_messaging(
            amqp_url="amqps://broker.example",
            ca_cert=cert,
            client_cert=cert,
            client_key=key,
        )
        path = Path(self.state.tls["keyfile"])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        context = messaging.FedoraMessagingAddon._tls_context(self.state.tls)  # ruff: ignore[private-member-access]
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.configure()
        self.assertFalse(path.exists())

    def test_query_and_fragment_rejected(self) -> None:
        from django.core.exceptions import ValidationError  # ruff: ignore[import-outside-top-level]

        for suffix in ("?heartbeat=10", "#fragment", "?", "#"):
            with self.subTest(suffix=suffix), self.assertRaises(ValidationError):
                validate_fedora_messaging_url("amqp://broker.example" + suffix)

    def test_parsed_credentials_reach_kombu_unchanged(self) -> None:
        self.connection_patch.stop()
        cases = (
            (
                "amqp://alice:pa;ss@broker.example/vhost",
                "alice",
                "pa;ss",
                "vhost",
                5672,
            ),
            (
                "amqp://ali%3Bce:pa%3Bss@broker.example/%2Fpubsub",
                "ali;ce",
                "pa;ss",
                "/pubsub",
                5672,
            ),
            (
                "amqp://alice:pa%253Bss@broker.example/vhost",
                "alice",
                "pa%3Bss",
                "vhost",
                5672,
            ),
            (
                "amqps://weblate:@rabbitmq.fedoraproject.org/%2Fpubsub",
                "weblate",
                "",
                "/pubsub",
                5671,
            ),
            ("amqp://broker.example:1234", None, None, "/", 1234),
        )
        captured = []

        def fail_connection(transport: messaging.PublisherTransport) -> None:
            captured.append(transport.client)
            msg = "stop before network"
            raise OSError(msg)

        for url, user, password, vhost, port in cases:
            with (
                self.subTest(url=url),
                patch.object(
                    messaging.PublisherTransport,
                    "establish_connection",
                    autospec=True,
                    side_effect=fail_connection,
                ) as establish,
                self.assertRaises(messaging.FedoraMessagingPublishError),
            ):
                messaging.FedoraMessagingAddon.publish_message(self.message, url, None)
                establish.assert_called_once()
            connection = captured[-1]
            assert connection is not None  # ruff: ignore[assert]
            self.assertEqual(connection.userid, user)
            self.assertEqual(connection.password, password)
            self.assertEqual(connection.virtual_host, vhost)
            self.assertEqual(connection.port, port)
            self.assertFalse(connection.alt)

    def test_fork_discards_inherited_connection_and_lock(self) -> None:
        self.publish()
        original_lock = messaging.FEDORA_MESSAGING_PUBLISH_LOCK
        self.addCleanup(
            setattr, messaging, "FEDORA_MESSAGING_PUBLISH_LOCK", original_lock
        )
        inherited_socket = self.connection._connection.transport.sock  # ruff: ignore[private-member-access]
        messaging.reset_publisher_after_fork()
        inherited_socket.close.assert_called_once()
        inherited_socket.shutdown.assert_not_called()
        self.addCleanup(messaging.PUBLISHER.close)
        self.connection.collect.assert_called_once()
        self.assertIsNone(messaging.PUBLISHER.connection)
        self.assertIsNone(messaging.PUBLISHER.configuration)
        self.assertIsNot(messaging.FEDORA_MESSAGING_PUBLISH_LOCK, original_lock)

    def test_close_removes_cached_state(self) -> None:
        self.publish()
        messaging.close_publisher()
        self.connection.collect.assert_called_once()
        self.assertIsNone(self.state.connection)
        self.assertIsNone(self.state.configuration)

    def test_tls_probe_checks_peer_before_handshake(self) -> None:
        from django.core.exceptions import ValidationError  # ruff: ignore[import-outside-top-level]

        with (
            patch.object(messaging.FedoraMessagingAddon, "_tls_context") as context,
            patch.object(messaging.socket, "create_connection"),
            patch.object(
                messaging,
                "validate_connected_peer",
                side_effect=ValidationError("private peer"),
            ),
            self.assertRaisesMessage(
                messaging.FedoraMessagingConfigurationError, "private peer"
            ),
        ):
            messaging.FedoraMessagingAddon.validate_broker_tls("amqps://broker.example")
        context.return_value.wrap_socket.assert_not_called()

    def test_confirmation_reads_obey_remaining_budget(self) -> None:
        self.state.deadline = 10
        with (
            patch.object(self.clock, "monotonic", return_value=8),
            patch.object(messaging.KombuAMQPConnection, "blocking_read") as read,
        ):
            connection = messaging.DeadlineConnection()
            connection.blocking_read(timeout=30)
        read.assert_called_once_with(2)

    def test_timeout_reporting_is_throttled(self) -> None:
        with patch.object(messaging.cache, "add", side_effect=[True, False]):
            self.assertTrue(
                messaging.FedoraMessagingAddon._should_report_publish_error(  # ruff: ignore[private-member-access]
                    TimeoutError(), "amqp://broker.example", None
                )
            )
            self.assertFalse(
                messaging.FedoraMessagingAddon._should_report_publish_error(  # ruff: ignore[private-member-access]
                    TimeoutError(), "amqp://broker.example", None
                )
            )


class PublisherSocketTest(SimpleTestCase):
    def setUp(self) -> None:
        self.clock = MagicMock(wraps=time)
        clock_patch = patch.object(messaging, "time", self.clock)
        clock_patch.start()
        self.addCleanup(clock_patch.stop)
        self.state = messaging.PublisherState()
        self.state.deadline = 5
        patcher = patch.object(messaging, "PUBLISHER", self.state)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.state.close)

    def test_address_attempts_share_deadline(self) -> None:
        transport = messaging.DeadlineTCPTransport(
            "broker.example:5672", connect_timeout=5
        )
        entries = [
            (
                messaging.socket.AF_INET,
                messaging.socket.SOCK_STREAM,
                6,
                "",
                ("192.0.2.1", 5672),
            )
        ] * 3
        with (
            patch.object(messaging.socket, "getaddrinfo", return_value=entries),
            patch.object(messaging.socket, "socket") as create_socket,
            patch.object(self.clock, "monotonic", side_effect=[0, 3, 5]),
            self.assertRaises(TimeoutError),
        ):
            create_socket.return_value.connect.side_effect = TimeoutError("unreachable")
            transport.connect()
        self.assertEqual(create_socket.call_count, 2)
        self.assertEqual(
            create_socket.return_value.settimeout.call_args_list, [call(5), call(2)]
        )
        self.assertEqual(create_socket.return_value.close.call_count, 2)
        self.assertIsNone(transport.sock)

    def test_resolution_exhausts_budget_before_socket_creation(self) -> None:
        connection = messaging.DeadlineConnection(
            host="broker.example:5672", connect_timeout=5
        )
        with (
            patch.object(
                messaging.socket,
                "getaddrinfo",
                return_value=[
                    (
                        messaging.socket.AF_INET,
                        messaging.socket.SOCK_STREAM,
                        6,
                        "",
                        ("192.0.2.1", 5672),
                    )
                ],
            ),
            patch.object(messaging.socket, "socket") as create_socket,
            patch.object(self.clock, "monotonic", return_value=5),
            self.assertRaises(TimeoutError),
        ):
            connection.connect()
        create_socket.assert_not_called()

    def test_tls_uses_budget_remaining_after_tcp_and_wrapping(self) -> None:
        now = 0.0
        raw = MagicMock()
        wrapped = MagicMock()
        wrapped.write.side_effect = len

        def connect(address: tuple) -> None:
            nonlocal now
            now = 3

        def wrap(sock: object, **kwargs: object) -> MagicMock:
            nonlocal now
            now = 4
            return wrapped

        raw.connect.side_effect = connect
        transport = messaging.DeadlineSSLTransport(
            "broker.example:5671", connect_timeout=5
        )
        with (
            patch.object(
                messaging.socket,
                "getaddrinfo",
                return_value=[
                    (
                        messaging.socket.AF_INET,
                        messaging.socket.SOCK_STREAM,
                        6,
                        "",
                        ("192.0.2.1", 5671),
                    )
                ],
            ),
            patch.object(messaging.socket, "socket", return_value=raw),
            patch.object(self.clock, "monotonic", side_effect=lambda: now),
            patch.object(transport, "_wrap_socket", side_effect=wrap),
        ):
            transport.connect()
        raw.connect.assert_called_once()
        wrapped.settimeout.assert_called_once_with(1)
        wrapped.do_handshake.assert_called_once()
        transport.close()
        wrapped.close.assert_called_once()
        wrapped.unwrap.assert_not_called()
        wrapped.shutdown.assert_not_called()

    def test_failed_handshake_closes_socket(self) -> None:
        transport = messaging.DeadlineSSLTransport(
            "broker.example:5671", connect_timeout=5
        )
        wrapped = MagicMock()
        wrapped.do_handshake.side_effect = TimeoutError("handshake timed out")
        transport.sock = MagicMock()
        with (
            patch.object(transport, "_connect"),
            patch.object(transport, "_wrap_socket", return_value=wrapped),
            patch.object(self.clock, "monotonic", return_value=4),
            self.assertRaises(TimeoutError),
        ):
            transport.connect()
        wrapped.close.assert_called_once()
        wrapped.unwrap.assert_not_called()
        self.assertIsNone(transport.sock)

    def test_socket_reads_preserve_shorter_timeouts(self) -> None:
        for timeout, expected in ((None, 3), (0, 0), (1, 1), (10, 3)):
            with self.subTest(timeout=timeout):
                transport = messaging.DeadlineTCPTransport("broker.example:5672")
                sock = MagicMock()
                sock.gettimeout.return_value = timeout
                sock.recv.return_value = b"data"
                transport.sock = sock
                with patch.object(self.clock, "monotonic", return_value=2):
                    self.assertEqual(transport._deadline_recv(4), b"data")  # ruff: ignore[private-member-access]
                sock.settimeout.assert_called_once_with(expected)
                transport.close()

    def test_empty_broker_poll_allows_confirmed_publish(self) -> None:
        for transport_type in (
            messaging.DeadlineTCPTransport,
            messaging.DeadlineSSLTransport,
        ):
            with self.subTest(transport=transport_type.__name__):
                self.check_confirmed_publish_after_empty_poll(transport_type)

    def check_confirmed_publish_after_empty_poll(
        self, transport_type: type[messaging.DeadlineTCPTransport]
    ) -> None:
        now = 0.0
        current_timeout = None
        self.state.deadline = 5
        connection = messaging.DeadlineConnection(confirm_publish=True)
        connection.client_properties["capabilities"] = {"connection.blocked": True}
        writer = MagicMock()
        # py-amqp's stubs omit the setters for these connection hooks.
        connection.frame_writer = writer  # type: ignore[misc]
        handler = frame_handler(connection, connection.on_inbound_method)
        connection.on_inbound_frame = handler  # type: ignore[misc]
        channel = connection.Channel(connection, channel_id=1)
        channel._confirm_selected = True  # type: ignore[attr-defined]  # ruff: ignore[private-member-access]
        payload = pack(">HHQ?", *spec.Basic.Ack, 1, False)
        frame = pack(">BHI", 1, 1, len(payload)) + payload + b"\xce"
        sock = MagicMock()

        def set_timeout(value: float | None) -> None:
            nonlocal current_timeout
            current_timeout = value

        def receive(size: int) -> bytes:
            nonlocal now, frame
            if current_timeout == 0:
                raise BlockingIOError(errno.EWOULDBLOCK, "no broker event")
            if not writer.called:
                now += current_timeout or 5
                msg = "empty broker poll used publish budget"
                raise TimeoutError(msg)
            now += 0.1
            data, frame = frame[:size], frame[size:]
            return data

        sock.gettimeout.side_effect = lambda: current_timeout
        sock.settimeout.side_effect = set_timeout
        sock.recv.side_effect = receive
        transport = transport_type("broker.example:5672")
        transport.sock = sock
        connection.transport = transport  # type: ignore[misc]
        with (
            patch.object(self.clock, "monotonic", side_effect=lambda: now),
            patch.object(transport, "_wrap_socket", return_value=sock, create=True),
        ):
            transport._setup_transport()  # ruff: ignore[private-member-access]
            channel.basic_publish(
                Message(b"data"),
                exchange="amq.topic",
                routing_key="weblate.test",
                timeout=5,
                confirm_timeout=5,
            )
        writer.assert_called_once()
        self.assertEqual(writer.call_args.args[2], spec.Basic.Publish)
        self.assertLess(now, self.state.deadline)
        self.assertEqual(frame, b"")
        transport.close()

    def test_partial_frame_reads_stop_at_deadline(self) -> None:
        for transport_type in (
            messaging.DeadlineTCPTransport,
            messaging.DeadlineSSLTransport,
        ):
            with self.subTest(transport=transport_type.__name__):
                self.check_partial_frame(transport_type, timeout=2)

    def test_partial_frame_reads_complete_within_budget(self) -> None:
        for transport_type in (
            messaging.DeadlineTCPTransport,
            messaging.DeadlineSSLTransport,
        ):
            with self.subTest(transport=transport_type.__name__):
                self.check_partial_frame(transport_type, timeout=5)

    def check_partial_frame(
        self, transport_type: type[messaging.DeadlineTCPTransport], timeout: int
    ) -> None:
        now = 0.0
        self.state.deadline = timeout
        payload = b"data"
        frame = pack(">BHI", 1, 1, len(payload)) + payload + b"\xce"
        fragments = iter(bytes([value]) for value in frame)
        sock = MagicMock()
        current_timeout = None

        def set_timeout(value: float | None) -> None:
            nonlocal current_timeout
            current_timeout = value

        sock.gettimeout.side_effect = lambda: current_timeout
        sock.settimeout.side_effect = set_timeout

        def receive(size: int) -> bytes:
            nonlocal now
            now += 0.25
            return next(fragments)

        sock.recv.side_effect = receive
        transport = transport_type("broker.example:5672")
        transport.sock = sock
        with (
            patch.object(self.clock, "monotonic", side_effect=lambda: now),
            patch.object(transport, "_wrap_socket", return_value=sock, create=True),
        ):
            transport._setup_transport()  # ruff: ignore[private-member-access]
            sock.settimeout.reset_mock()
            if timeout == 2:
                with self.assertRaises(TimeoutError):
                    transport.read_frame()
                self.assertEqual(now, 2)
                self.assertEqual(sock.recv.call_count, 8)
            else:
                self.assertEqual(transport.read_frame(), (1, 1, payload))
                self.assertEqual(now, 3)
            self.assertEqual(
                sock.settimeout.call_args_list,
                [call(timeout - index * 0.25) for index in range(sock.recv.call_count)],
            )
        transport.close()

    def test_discard_collects_tls_connection_without_unwrap(self) -> None:
        from kombu import Connection  # ruff: ignore[import-outside-top-level]

        transport = messaging.DeadlineSSLTransport("broker.example:5671")
        sock = MagicMock()
        transport.sock = sock
        underlying = messaging.DeadlineConnection()
        underlying.transport = transport  # type: ignore[misc]
        connection = Connection(transport=messaging.PublisherTransport)
        connection._connection = underlying  # type: ignore[attr-defined]  # ruff: ignore[private-member-access]
        connection.transport.client = connection
        self.state.connection = connection
        self.state.disconnect()
        sock.close.assert_called_once()
        sock.unwrap.assert_not_called()
        sock.shutdown.assert_not_called()
        self.assertIsNone(self.state.connection)
        self.assertIsNone(transport.sock)
