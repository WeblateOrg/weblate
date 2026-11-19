# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
from contextlib import suppress
from threading import Event

from asgiref.sync import sync_to_async
from django.test import SimpleTestCase

from weblate.machinery.admission import complete_provider_call, machinery_slot


class MachineryAdmissionTest(SimpleTestCase):
    async def test_cancellation_retains_slot_until_sync_provider_finishes(self) -> None:
        loop = asyncio.get_running_loop()
        started = asyncio.Event()
        release = Event()

        def blocking_provider() -> None:
            loop.call_soon_threadsafe(started.set)
            if not release.wait(timeout=5):
                self.fail("Synchronous provider was not released")

        async def request() -> None:
            async with machinery_slot(999, 1000) as admitted:
                self.assertTrue(admitted)
                await complete_provider_call(
                    sync_to_async(blocking_provider, thread_sensitive=False)()
                )

        task = asyncio.create_task(request())
        try:
            await asyncio.wait_for(started.wait(), timeout=5)
            task.cancel()
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=0.05)
            task.cancel()
            async with machinery_slot(999, 1000) as second:
                self.assertTrue(second)
                async with machinery_slot(999, 1000) as excess:
                    self.assertFalse(excess)
        finally:
            release.set()
            with suppress(asyncio.CancelledError):
                await task
        async with (
            machinery_slot(999, 1000) as first,
            machinery_slot(999, 1000) as second,
        ):
            self.assertTrue(first)
            self.assertTrue(second)

    async def test_capacity_is_scoped_and_released(self) -> None:
        async with (
            machinery_slot(991, 992) as first,
            machinery_slot(991, 992) as second,
        ):
            self.assertTrue(first)
            self.assertTrue(second)
            async with machinery_slot(991, 992) as excess:
                self.assertFalse(excess)
            async with machinery_slot(991, 993) as other_provider:
                self.assertTrue(other_provider)
            async with machinery_slot(994, 992) as other_user:
                self.assertTrue(other_user)
        async with machinery_slot(991, 992) as available:
            self.assertTrue(available)

    async def test_cancellation_releases_slot(self) -> None:
        ready = asyncio.Event()

        async def request() -> None:
            async with machinery_slot(995, 996) as admitted:
                self.assertTrue(admitted)
                ready.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(request())
        await ready.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        async with (
            machinery_slot(995, 996) as first,
            machinery_slot(995, 996) as second,
        ):
            self.assertTrue(first)
            self.assertTrue(second)

    async def test_exception_releases_slot(self) -> None:
        with self.assertRaisesRegex(ValueError, "provider failed"):
            async with machinery_slot(997, 998):
                msg = "provider failed"
                raise ValueError(msg)
        async with (
            machinery_slot(997, 998) as first,
            machinery_slot(997, 998) as second,
        ):
            self.assertTrue(first)
            self.assertTrue(second)
