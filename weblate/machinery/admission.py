# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Admission for interactive provider requests across application workers."""

from __future__ import annotations

import asyncio
from contextlib import ExitStack, asynccontextmanager
from typing import TYPE_CHECKING

from asgiref.sync import sync_to_async

from weblate.utils.lock import WeblateLock, WeblateLockTimeoutError

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable


async def complete_provider_call[T](operation: Awaitable[T]) -> T:
    """Keep admission until provider work, including executor threads, finishes."""
    pending = asyncio.ensure_future(operation)
    try:
        return await asyncio.shield(pending)
    except asyncio.CancelledError:
        # Canceling a sync_to_async await cannot stop its running thread. Keep
        # waiting even if request shutdown delivers another cancellation.
        while not pending.done():
            try:
                await asyncio.shield(pending)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not pending.cancelled():
            pending.exception()
        raise


def acquire_slot(user_id: int, installation_id: int) -> ExitStack | None:
    for slot in range(2):
        lock = WeblateLock(
            scope="machinery-request",
            key=f"{user_id}-{installation_id}-{slot}",
            slug="Interactive machine translation",
            timeout=0,
        )
        acquired = ExitStack()
        try:
            acquired.enter_context(lock)
        except WeblateLockTimeoutError:
            continue
        return acquired
    return None


async def release_slot(lock: ExitStack | None) -> None:
    if lock is not None:
        release = asyncio.create_task(sync_to_async(lock.close)())
        try:
            await asyncio.shield(release)
        except asyncio.CancelledError:
            await release
            raise


@asynccontextmanager
async def machinery_slot(
    user_id: int, installation_id: int
) -> AsyncGenerator[bool, None]:
    """Reserve one of two slots, including cleanup if acquisition is canceled."""
    acquisition = asyncio.create_task(
        sync_to_async(acquire_slot)(user_id, installation_id)
    )
    try:
        lock = await asyncio.shield(acquisition)
    except asyncio.CancelledError:
        await release_slot(await acquisition)
        raise
    try:
        yield lock is not None
    finally:
        await release_slot(lock)
