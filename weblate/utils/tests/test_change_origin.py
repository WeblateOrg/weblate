# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Never, cast

from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, SimpleTestCase

from weblate.automation.context import automation_origin
from weblate.middleware import ChangeOriginMiddleware
from weblate.utils.change_origin import (
    capture_change_origin,
    change_origin,
    change_origin_context,
    get_change_origin,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from django.http import HttpResponseBase


class ChangeOriginTest(SimpleTestCase):
    def test_deferred_automation_context(self) -> None:
        with change_origin_context(
            {"scope": "automation", "automation": {"addon_id": 12, "activity_id": 34}}
        ):
            self.assertEqual(automation_origin.get(), 34)
            callback = capture_change_origin(
                lambda: (get_change_origin(), automation_origin.get())
            )
        self.assertIsNone(automation_origin.get())
        with change_origin_context(
            {"scope": "automation", "automation": {"addon_id": 56, "activity_id": 78}}
        ):
            origin, activity = callback()
            self.assertEqual(origin["automation"], {"addon_id": 12, "activity_id": 34})
            self.assertEqual(activity, 34)
            self.assertEqual(automation_origin.get(), 78)
        self.assertIsNone(automation_origin.get())

    def test_nested_scopes_and_errors(self) -> None:
        with change_origin_context({"scope": "api"}):
            with (
                self.assertRaisesMessage(ValueError, "failed"),
                change_origin_context({"scope": "repository"}),
            ):
                self.assertEqual(get_change_origin(), {"scope": "repository"})
                msg = "failed"
                raise ValueError(msg)
            self.assertEqual(get_change_origin(), {"scope": "api"})
        self.assertIsNone(change_origin.get())
        self.assertEqual(get_change_origin(), {"scope": "system"})

    def test_deferred_snapshot(self) -> None:
        with change_origin_context(
            {"scope": "api", "token": {"type": "personal", "id": "stable-id"}}
        ):
            callback = capture_change_origin(get_change_origin)
            snapshot = get_change_origin()
            snapshot["token"]["id"] = "modified"
        self.assertEqual(callback()["token"]["id"], "stable-id")
        self.assertIsNone(change_origin.get())

    def test_request_cleanup(self) -> None:
        def response(request: HttpRequest) -> Never:
            self.assertEqual(get_change_origin(), {"scope": "ui"})
            change_origin.set({"scope": "api"})
            msg = "failed"
            raise ValueError(msg)

        middleware = ChangeOriginMiddleware(response)
        with self.assertRaisesMessage(ValueError, "failed"):
            middleware(RequestFactory().get("/api/units/"))
        self.assertIsNone(change_origin.get())

    def test_concurrent_requests(self) -> None:
        async def response(request: HttpRequest) -> HttpResponse:
            self.assertEqual(get_change_origin(), {"scope": "ui"})
            if request.path == "/api/units/":
                change_origin.set({"scope": "api"})
            await asyncio.sleep(0)
            expected = "api" if request.path == "/api/units/" else "ui"
            self.assertEqual(get_change_origin(), {"scope": expected})
            return HttpResponse()

        middleware = ChangeOriginMiddleware(response)

        async def requests() -> None:
            factory = RequestFactory()
            await asyncio.gather(
                cast(
                    "Awaitable[HttpResponseBase]",
                    middleware(factory.get("/api/units/")),
                ),
                cast(
                    "Awaitable[HttpResponseBase]",
                    middleware(factory.get("/translate/")),
                ),
            )
            self.assertIsNone(change_origin.get())

        asyncio.run(requests())
