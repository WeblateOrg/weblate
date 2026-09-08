# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from importlib import import_module
from threading import Barrier
from unittest import mock

from django.contrib.sessions.backends.db import SessionStore
from django.core import mail
from django.db import close_old_connections, connection
from django.db.migrations.loader import MigrationLoader
from django.test import Client, RequestFactory, TransactionTestCase
from django.urls import reverse
from django.utils.timezone import now
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice

from weblate.accounts.forms import TOTPTokenForm
from weblate.accounts.models import AuditLog
from weblate.accounts.tasks import cleanup_totp_enrollments
from weblate.accounts.utils import SESSION_SECOND_FACTOR_TOTP
from weblate.accounts.views import TOTPView
from weblate.auth.models import User
from weblate.trans.tests.test_views import FixtureTestCase


class TOTPEnrollmentTest(FixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.timestamp = int(now().timestamp())
        self.enterContext(mock.patch("time.time", return_value=self.timestamp))
        self.enterContext(
            mock.patch("django_otp.oath.time", return_value=self.timestamp)
        )

    def start_enrollment(self) -> tuple[TOTPDevice, dict]:
        response = self.client.get(reverse("totp"))
        self.assertEqual(response.status_code, 200)
        device = response.context["form"].device
        return device, {
            "enrollment": device.pk,
            "name": "New authenticator",
            "token": f"{totp(device.bin_key):06d}",
        }

    def test_replay_and_fresh_enrollment(self) -> None:
        device, payload = self.start_enrollment()
        session = self.client.session
        mail.outbox.clear()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("totp"), payload)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(SESSION_SECOND_FACTOR_TOTP, self.client.session)
        device.refresh_from_db()
        self.assertTrue(device.confirmed)
        self.assertEqual(device.name, payload["name"])
        self.assertEqual(len(mail.outbox), 1)

        self.assertEqual(self.client.post(reverse("totp"), payload).status_code, 400)
        # Another in-flight request can retain the old session snapshot.
        session.save()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("totp"), payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(TOTPDevice.objects.filter(user=self.user).count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            AuditLog.objects.filter(user=self.user, activity="twofactor-add").count(), 1
        )
        self.assertFalse(
            TOTPTokenForm(self.user, data={"otp_token": payload["token"]}).is_valid()
        )
        with (
            mock.patch("time.time", return_value=self.timestamp + 30),
            mock.patch("django_otp.oath.time", return_value=self.timestamp + 30),
            mock.patch(
                "django_otp.models.timezone.now",
                return_value=now() + timedelta(seconds=30),
            ),
        ):
            self.assertTrue(
                TOTPTokenForm(
                    self.user, data={"otp_token": f"{totp(device.bin_key):06d}"}
                ).is_valid()
            )
        fresh, _payload = self.start_enrollment()
        self.assertNotEqual(fresh.key, device.key)
        self.assertNotEqual(fresh.pk, device.pk)

    def test_pending_device_is_not_a_second_factor(self) -> None:
        device, _payload = self.start_enrollment()
        user = User.objects.get(pk=self.user.pk)
        self.assertFalse(user.profile.has_2fa)
        self.assertEqual(user.profile.second_factor_types, set())
        self.assertEqual(user.profile.second_factors, [])
        response = self.client.get(reverse("profile"))
        self.assertNotIn(device, response.context["totp_keys"])
        self.assertEqual(
            self.client.post(
                reverse("totp-detail", kwargs={"pk": device.pk}), {"delete": "1"}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("totp-detail", kwargs={"pk": device.pk}), {"name": "renamed"}
            ).status_code,
            404,
        )
        self.assertFalse(
            TOTPTokenForm(
                user, data={"otp_token": f"{totp(device.bin_key):06d}"}
            ).is_valid()
        )
        again, _payload = self.start_enrollment()
        self.assertEqual(again.pk, device.pk)

    def test_invalid_fields_do_not_consume_token(self) -> None:
        device, payload = self.start_enrollment()
        response = self.client.post(reverse("totp"), {**payload, "name": ""})
        self.assertEqual(response.status_code, 200)
        self.assertIn("name", response.context["form"].errors)
        device.refresh_from_db()
        self.assertEqual(device.last_t, -1)
        self.assertEqual(device.throttling_failure_count, 0)
        self.assertFalse(device.confirmed)
        self.assertEqual(self.client.post(reverse("totp"), payload).status_code, 302)

    def test_fresh_sessions_reuse_pending_enrollment(self) -> None:
        device, payload = self.start_enrollment()
        TOTPDevice.objects.filter(pk=device.pk).update(
            throttling_failure_count=2, throttling_failure_timestamp=now()
        )
        for _ in range(3):
            client = Client()
            client.force_login(self.user)
            response = client.get(reverse("totp"))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["form"].device.pk, device.pk)
            self.assertEqual(client.session[SESSION_SECOND_FACTOR_TOTP], device.pk)
        self.assertEqual(TOTPDevice.objects.filter(user=self.user).count(), 1)
        device.refresh_from_db()
        self.assertEqual(device.throttling_failure_count, 2)
        response = client.post(reverse("totp"), payload)
        self.assertIn("token", response.context["form"].errors)

    def test_get_removes_extra_pending_devices(self) -> None:
        expired = TOTPDevice.objects.create(user=self.user, confirmed=False)
        TOTPDevice.objects.filter(pk=expired.pk).update(
            created_at=now() - timedelta(days=2)
        )
        pending = TOTPDevice.objects.create(user=self.user, confirmed=False)
        extra = TOTPDevice.objects.create(user=self.user, confirmed=False)
        confirmed = TOTPDevice.objects.create(user=self.user)
        device, _payload = self.start_enrollment()
        self.assertEqual(device.pk, pending.pk)
        self.assertFalse(
            TOTPDevice.objects.filter(pk__in=[expired.pk, extra.pk]).exists()
        )
        self.assertTrue(TOTPDevice.objects.filter(pk=confirmed.pk).exists())

    def test_invalid_code_preserves_throttling(self) -> None:
        device, payload = self.start_enrollment()
        valid = {totp(device.bin_key, drift=drift) for drift in (-1, 0, 1)}
        invalid = next(token for token in range(4) if token not in valid)
        response = self.client.post(reverse("totp"), {**payload, "token": invalid})
        self.assertIn("token", response.context["form"].errors)
        device.refresh_from_db()
        self.assertFalse(device.confirmed)
        self.assertEqual(device.throttling_failure_count, 1)
        response = self.client.post(reverse("totp"), payload)
        self.assertIn("token", response.context["form"].errors)
        self.assertFalse(TOTPDevice.objects.get(pk=device.pk).confirmed)

    def test_invalid_enrollment_reference(self) -> None:
        device, payload = self.start_enrollment()
        other = User.objects.create_user("other-totp", "other@example.com")
        foreign = TOTPDevice.objects.create(user=other, confirmed=False)
        for enrollment in (None, "invalid", foreign.pk, device.pk + 1000):
            with self.subTest(enrollment=enrollment):
                data = {**payload, "enrollment": enrollment}
                if enrollment is None:
                    del data["enrollment"]
                self.assertEqual(
                    self.client.post(reverse("totp"), data).status_code, 400
                )
        session = self.client.session
        session[SESSION_SECOND_FACTOR_TOTP] = foreign.pk
        session.save()
        self.assertEqual(
            self.client.post(
                reverse("totp"), {**payload, "enrollment": foreign.pk}
            ).status_code,
            400,
        )
        self.assertFalse(TOTPDevice.objects.filter(confirmed=True).exists())

    def test_expiry_cleanup_and_legacy_session(self) -> None:
        device, payload = self.start_enrollment()
        old = now() - timedelta(days=2)
        TOTPDevice.objects.filter(pk=device.pk).update(created_at=old)
        confirmed = TOTPDevice.objects.create(user=self.user)
        TOTPDevice.objects.filter(pk=confirmed.pk).update(created_at=old)
        self.assertEqual(self.client.post(reverse("totp"), payload).status_code, 400)
        fresh, _payload = self.start_enrollment()
        cleanup_totp_enrollments()
        self.assertFalse(TOTPDevice.objects.filter(pk=device.pk).exists())
        self.assertTrue(TOTPDevice.objects.filter(pk=confirmed.pk).exists())
        self.assertTrue(TOTPDevice.objects.filter(pk=fresh.pk).exists())
        session = self.client.session
        del session[SESSION_SECOND_FACTOR_TOTP]
        session["weblate:second_factor:totp_key"] = device.key
        session.save()
        self.assertEqual(self.client.post(reverse("totp"), payload).status_code, 400)
        legacy_replacement, _payload = self.start_enrollment()
        self.assertNotEqual(legacy_replacement.key, device.key)
        self.assertNotIn("weblate:second_factor:totp_key", self.client.session)

    def test_replacement_failure_rolls_back(self) -> None:
        previous = TOTPDevice.objects.create(user=self.user, name="Old authenticator")
        device, payload = self.start_enrollment()
        original_create = AuditLog.objects.create

        def fail_removal_audit(user, request, activity, **params):
            if activity == "twofactor-remove":
                msg = "Simulated audit failure"
                raise RuntimeError(msg)
            return original_create(user, request, activity, **params)

        mail.outbox.clear()
        with (
            self.captureOnCommitCallbacks(execute=True) as callbacks,
            mock.patch.object(
                AuditLog.objects, "create", side_effect=fail_removal_audit
            ),
            self.assertRaisesMessage(RuntimeError, "Simulated audit failure"),
        ):
            self.client.post(reverse("totp"), {**payload, "remove_previous": "1"})
        device.refresh_from_db()
        self.assertFalse(device.confirmed)
        self.assertEqual(device.last_t, -1)
        self.assertTrue(TOTPDevice.objects.filter(pk=previous.pk).exists())
        self.assertFalse(
            AuditLog.objects.filter(user=self.user, activity="twofactor-add").exists()
        )
        self.assertEqual(callbacks, [])

    def migrate_duplicates(self) -> None:
        migration = import_module(
            "weblate.accounts.migrations.0036_deduplicate_totp_devices"
        )
        state = MigrationLoader(connection).project_state(
            [("accounts", "0036_deduplicate_totp_devices")]
        )
        with connection.schema_editor() as editor:
            migration.deduplicate_totp_devices(state.apps, editor)

    def test_duplicate_migration(self) -> None:
        first = TOTPDevice.objects.create(
            user=self.user, name="Keep this name", last_t=20
        )
        latest = now()
        duplicate = TOTPDevice.objects.create(
            user=self.user,
            key=first.key,
            drift=1,
            tolerance=2,
            last_t=10,
            last_used_at=latest,
            throttling_failure_count=3,
            throttling_failure_timestamp=latest,
        )
        older = TOTPDevice.objects.create(
            user=self.user,
            key=first.key,
            drift=-1,
            last_used_at=latest - timedelta(days=1),
        )
        distinct = TOTPDevice.objects.create(user=self.user, key=first.key, step=60)
        pending = TOTPDevice.objects.create(
            user=self.user, key=first.key, confirmed=False
        )
        other_key = TOTPDevice.objects.create(user=self.user)
        other_user = User.objects.create_user("migration-totp", "migration@example.com")
        foreign = TOTPDevice.objects.create(user=other_user, key=first.key)
        self.migrate_duplicates()
        self.migrate_duplicates()
        first.refresh_from_db()
        self.assertEqual(first.name, "Keep this name")
        self.assertEqual(first.last_t, 20)
        self.assertEqual(first.drift, 1)
        self.assertEqual(first.tolerance, 1)
        self.assertEqual(first.last_used_at, latest)
        self.assertEqual(first.throttling_failure_count, 3)
        self.assertEqual(first.throttling_failure_timestamp, latest)
        self.assertFalse(TOTPDevice.objects.filter(pk=duplicate.pk).exists())
        self.assertFalse(TOTPDevice.objects.filter(pk=older.pk).exists())
        for device in (distinct, pending, other_key, foreign):
            self.assertTrue(TOTPDevice.objects.filter(pk=device.pk).exists())

    def test_migration_prevents_replay_with_different_drift(self) -> None:
        first = TOTPDevice.objects.create(user=self.user, drift=-1)
        duplicate = TOTPDevice.objects.create(user=self.user, key=first.key, drift=1)
        self.migrate_duplicates()
        self.assertFalse(TOTPDevice.objects.filter(pk=duplicate.pk).exists())
        first.refresh_from_db()
        self.assertEqual(first.drift, -1)
        token = f"{totp(first.bin_key):06d}"
        self.assertTrue(TOTPTokenForm(self.user, data={"otp_token": token}).is_valid())
        self.assertFalse(TOTPTokenForm(self.user, data={"otp_token": token}).is_valid())


class TOTPEnrollmentConcurrencyTest(TransactionTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user = User.objects.create_user("concurrent-totp", "totp@example.com")
        self.timestamp = int(now().timestamp())
        self.enterContext(mock.patch("time.time", return_value=self.timestamp))
        self.enterContext(
            mock.patch("django_otp.oath.time", return_value=self.timestamp)
        )

    def submit_concurrently(
        self, devices: list[TOTPDevice], *, replace: bool
    ) -> list[int]:
        ready = Barrier(2)

        def submit(device: TOTPDevice) -> int:
            close_old_connections()
            try:
                request = RequestFactory().post(
                    reverse("totp"),
                    {
                        "enrollment": device.pk,
                        "name": f"Authenticator {device.pk}",
                        "token": f"{totp(device.bin_key):06d}",
                        "remove_previous": "1" if replace else "",
                    },
                )
                request.user = User.objects.get(pk=self.user.pk)
                # Independent snapshots of an already-loaded session, as in
                # concurrent requests before either session is saved.
                request.session = SessionStore()
                request.session[SESSION_SECOND_FACTOR_TOTP] = device.pk
                ready.wait(timeout=10)
                return TOTPView.as_view()(request).status_code
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(submit, device) for device in devices]
            return [future.result(timeout=20) for future in futures]

    def test_concurrent_gets_reuse_one_pending_enrollment(self) -> None:
        ready = Barrier(2)

        def start() -> int:
            close_old_connections()
            try:
                request = RequestFactory().get(reverse("totp"))
                request.user = User.objects.get(pk=self.user.pk)
                request.session = SessionStore()
                ready.wait(timeout=10)
                response = TOTPView.as_view()(request)
                self.assertEqual(response.status_code, 200)
                return request.session[SESSION_SECOND_FACTOR_TOTP]
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(start) for _ in range(2)]
            devices = [future.result(timeout=20) for future in futures]
        self.assertEqual(devices[0], devices[1])
        self.assertEqual(
            TOTPDevice.objects.filter(user=self.user, confirmed=False).count(), 1
        )

    def test_same_enrollment_completes_once(self) -> None:
        for replace in (False, True):
            with self.subTest(replace=replace):
                self.user.totpdevice_set.all().delete()
                AuditLog.objects.filter(user=self.user).delete()
                device = TOTPDevice.objects.create(user=self.user, confirmed=False)
                with mock.patch(
                    "weblate.accounts.models.notify_auditlog.delay"
                ) as notify:
                    statuses = self.submit_concurrently(
                        [device, device], replace=replace
                    )
                self.assertEqual(sorted(statuses), [302, 400])
                self.assertEqual(self.user.totpdevice_set.count(), 1)
                self.assertTrue(TOTPDevice.objects.get(pk=device.pk).confirmed)
                self.assertEqual(
                    AuditLog.objects.filter(
                        user=self.user, activity="twofactor-add"
                    ).count(),
                    1,
                )
                self.assertEqual(notify.call_count, 1)

    def test_distinct_replacements_leave_one_confirmed_device(self) -> None:
        devices = [
            TOTPDevice.objects.create(user=self.user, confirmed=False) for _ in range(2)
        ]
        with mock.patch("weblate.accounts.models.notify_auditlog.delay"):
            statuses = self.submit_concurrently(devices, replace=True)
        self.assertEqual(statuses, [302, 302])
        self.assertEqual(self.user.totpdevice_set.filter(confirmed=True).count(), 1)
        self.assertEqual(
            AuditLog.objects.filter(user=self.user, activity="twofactor-add").count(), 2
        )
        self.assertEqual(
            AuditLog.objects.filter(
                user=self.user, activity="twofactor-remove"
            ).count(),
            1,
        )
