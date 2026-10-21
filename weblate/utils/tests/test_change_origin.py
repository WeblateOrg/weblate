# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Never, cast
from unittest.mock import Mock

from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory, SimpleTestCase

from weblate.automation.context import automation_origin
from weblate.middleware import ChangeOriginMiddleware
from weblate.utils.change_origin import (
    acting_user_context,
    capture_change_origin,
    change_origin,
    change_origin_context,
    get_acting_user,
    get_change_origin,
    set_acting_user,
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


class ActingUserTest(SimpleTestCase):
    def setUp(self) -> None:
        from weblate.auth.models import User  # ruff: ignore[import-outside-top-level]

        self.user = User(pk=101, username="actor")
        self.other_user = User(pk=102, username="other-actor")

    def test_nested_actors_and_errors(self) -> None:
        with acting_user_context(self.user):
            with change_origin_context({"scope": "repository"}):
                self.assertIs(get_acting_user(), self.user)
            with acting_user_context(None):
                self.assertIsNone(get_acting_user())
            with self.assertRaises(ValueError), acting_user_context(self.other_user):
                self.assertIs(get_acting_user(), self.other_user)
                raise ValueError
            self.assertIs(get_acting_user(), self.user)
        self.assertIsNone(get_acting_user())

    def test_deferred_actor_snapshot(self) -> None:
        with acting_user_context(self.user):
            callback = capture_change_origin(get_acting_user)
        with acting_user_context(self.other_user):
            self.assertIs(callback(), self.user)
            self.assertIs(get_acting_user(), self.other_user)
        self.assertIsNone(get_acting_user())

    def test_project_token_normalization(self) -> None:
        principal = Mock()
        principal.get_token_user.return_value = self.user
        with acting_user_context(principal):
            self.assertIs(get_acting_user(), self.user)
        principal.get_token_user.assert_called_once_with()

    def test_request_cleanup(self) -> None:
        def response(request: HttpRequest) -> Never:
            self.assertIsNone(get_acting_user())
            set_acting_user(self.other_user)
            raise ValueError

        with acting_user_context(self.user):
            with self.assertRaises(ValueError):
                ChangeOriginMiddleware(response)(RequestFactory().get("/"))
            self.assertIs(get_acting_user(), self.user)

    def test_concurrent_requests(self) -> None:
        async def response(request: HttpRequest) -> HttpResponse:
            self.assertIsNone(get_acting_user())
            user = self.user if request.path == "/first/" else self.other_user
            set_acting_user(user)
            await asyncio.sleep(0)
            self.assertIs(get_acting_user(), user)
            return HttpResponse()

        middleware = ChangeOriginMiddleware(response)

        async def requests() -> None:
            factory = RequestFactory()
            await asyncio.gather(
                cast("Awaitable[HttpResponseBase]", middleware(factory.get("/first/"))),
                cast(
                    "Awaitable[HttpResponseBase]", middleware(factory.get("/second/"))
                ),
            )
            self.assertIsNone(get_acting_user())

        asyncio.run(requests())
