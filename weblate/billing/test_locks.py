# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from queue import Queue
from threading import Event
from time import monotonic, sleep
from typing import TYPE_CHECKING
from unittest.mock import patch

from django.db import OperationalError, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from weblate.billing.models import Billing, BillingEvent, BillingLog, Plan
from weblate.billing.tasks import inactive_recurring_check, schedule_removal
from weblate.trans.tests.utils import (
    clear_users_cache,
    create_test_billing,
    create_test_user,
)

if TYPE_CHECKING:
    from collections.abc import Callable


class BillingLockTest(TransactionTestCase):
    def setUp(self) -> None:
        clear_users_cache()
        self.addCleanup(clear_users_cache)
        super().setUp()
        self.billing = create_test_billing(create_test_user(), invoice=False)

    def connected(
        self, action: Callable[[], None], pids: Queue[int] | None = None
    ) -> None:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET statement_timeout = '10s'")
                if pids is not None:
                    cursor.execute("SELECT pg_backend_pid()")
                    pids.put(cursor.fetchone()[0])
            action()
        finally:
            connection.close()

    def wait_for_blocked(self, pid: int) -> None:
        deadline = monotonic() + 5
        while monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute("SELECT cardinality(pg_blocking_pids(%s)) > 0", [pid])
                if cursor.fetchone()[0]:
                    return
            sleep(0.01)
        self.fail("The scheduler did not wait for the billing lock")

    def test_recurring_check_does_not_lock_shared_plan(self) -> None:
        Billing.objects.filter(pk=self.billing.pk).update(
            payment={"recurring": "payment"}
        )
        original = Billing.get_inactive_recurring_status

        def probe() -> None:
            with transaction.atomic():
                Plan.objects.select_for_update(nowait=True).get(pk=self.billing.plan_id)
            with (
                self.assertRaisesMessage(OperationalError, "could not obtain lock"),
                transaction.atomic(),
            ):
                Billing.objects.select_for_update(nowait=True).get(pk=self.billing.pk)

        def status(
            bill: Billing, now: datetime | None = None
        ) -> dict[str, datetime] | None:
            with ThreadPoolExecutor(max_workers=1) as executor:
                executor.submit(self.connected, probe).result(timeout=10)
            return original(bill, now)

        with patch.object(Billing, "get_inactive_recurring_status", status):
            inactive_recurring_check()

    def test_scheduler_releases_previous_account_lock(self) -> None:
        second = Billing.objects.create(plan=self.billing.plan)
        original = Billing.check_payment_status
        probed = False

        def probe() -> None:
            with transaction.atomic():
                Billing.objects.select_for_update(nowait=True).get(pk=self.billing.pk)
            with (
                self.assertRaisesMessage(OperationalError, "could not obtain lock"),
                transaction.atomic(),
            ):
                Billing.objects.select_for_update(nowait=True).get(pk=second.pk)

        def paid(bill: Billing, now: bool = False) -> bool:
            nonlocal probed
            if bill.pk == second.pk and not probed:
                probed = True
                with ThreadPoolExecutor(max_workers=1) as executor:
                    executor.submit(self.connected, probe).result(timeout=10)
            return original(bill, now)

        with patch.object(Billing, "check_payment_status", paid):
            schedule_removal()
        self.assertTrue(probed)
        for bill in (self.billing, second):
            bill.refresh_from_db()
            self.assertIsNotNone(bill.removal)
            self.assertEqual(
                bill.billinglog_set.filter(event=BillingEvent.UNPAID).count(), 1
            )
        self.assertEqual(self.billing.removal, second.removal)

    def test_overlapping_schedulers_do_not_duplicate_events(self) -> None:
        entered = Event()
        release = Event()
        pids: Queue[int] = Queue()
        original = Billing.check_payment_status

        def paid(bill: Billing, now: bool = False) -> bool:
            if not entered.is_set():
                entered.set()
                if not release.wait(10):
                    msg = "Scheduler was not released"
                    raise TimeoutError(msg)
            return original(bill, now)

        with (
            patch.object(Billing, "check_payment_status", paid),
            ThreadPoolExecutor(max_workers=2) as executor,
        ):
            first = executor.submit(self.connected, schedule_removal)
            try:
                self.assertTrue(entered.wait(5))
                second = executor.submit(self.connected, schedule_removal, pids)
                self.wait_for_blocked(pids.get(timeout=5))
            finally:
                release.set()
                first.result(timeout=10)
            second.result(timeout=10)
        self.assertEqual(
            self.billing.billinglog_set.filter(event=BillingEvent.UNPAID).count(), 1
        )

    def test_scheduler_rechecks_candidates_after_lock_wait(self) -> None:
        for change in ("state", "removal", "paid", "deleted"):
            with self.subTest(change=change):
                bill = Billing.objects.create(plan=self.billing.plan)
                billing_id = bill.pk
                pids: Queue[int] = Queue()
                with ThreadPoolExecutor(max_workers=1) as executor:
                    with transaction.atomic():
                        Billing.objects.select_for_update().get(pk=bill.pk)
                        future = executor.submit(self.connected, schedule_removal, pids)
                        self.wait_for_blocked(pids.get(timeout=5))
                        if change == "state":
                            Billing.objects.filter(pk=bill.pk).update(
                                state=Billing.STATE_TERMINATED
                            )
                        elif change == "removal":
                            Billing.objects.filter(pk=bill.pk).update(
                                removal=timezone.now()
                            )
                        elif change == "paid":
                            Billing.objects.filter(pk=bill.pk).update(
                                payment_mode=Billing.PaymentMode.EXTERNAL,
                                external_paid_until=timezone.now() + timedelta(days=30),
                            )
                        else:
                            bill.delete()
                    future.result(timeout=10)
                self.assertFalse(
                    BillingLog.objects.filter(
                        billing_id=billing_id, event=BillingEvent.UNPAID
                    ).exists()
                )
