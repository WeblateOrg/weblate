# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for user handling."""

from io import BytesIO
from unittest.mock import patch

import httpx2
from django.test import override_settings
from django.urls import reverse
from PIL import Image

from weblate.accounts import avatar
from weblate.accounts.apps import check_avatars
from weblate.auth.models import User
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.utils.tests import http_mock

TEST_URL = (
    "https://www.gravatar.com/avatar/55502f40dc8b7c769880b10874abc9d0?d=identicon&s=32"
)


class AvatarTest(FixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user.email = "test@example.com"
        self.user.save()

    def test_avatar_for_email(self) -> None:
        url = avatar.avatar_for_email(self.user.email, size=32)
        self.assertEqual(TEST_URL, url)

    @override_settings(STATIC_URL="https://cdn.example.com/static/")
    def test_fallback_avatar_uses_stable_url(self) -> None:
        self.assertEqual(
            avatar.get_fallback_avatar_url(32),
            "https://cdn.example.com/static/weblate-32.png",
        )
        self.assertEqual(
            avatar.get_fallback_avatar_url(32, "api"),
            "https://cdn.example.com/static/api-32.png",
        )

    @http_mock.activate
    def test_avatar(self) -> None:
        image = Image.new("RGB", (32, 32))
        storage = BytesIO()
        image.save(storage, "PNG")
        imagedata = storage.getvalue()
        http_mock.register("GET", TEST_URL, content=imagedata)
        # Real user
        response = self.client.get(
            reverse("user_avatar", kwargs={"user": self.user.username, "size": 32})
        )
        self.assert_png(response)
        self.assertEqual(response.content, imagedata)
        # Test caching
        response = self.client.get(
            reverse("user_avatar", kwargs={"user": self.user.username, "size": 32})
        )
        self.assert_png(response)
        self.assertEqual(response.content, imagedata)

    @http_mock.activate
    def test_avatar_error(self) -> None:
        http_mock.register("GET", TEST_URL, status_code=503)
        # Choose different username to avoid using cache
        self.user.username = "test2"
        self.user.save()
        response = self.client.get(
            reverse("user_avatar", kwargs={"user": self.user.username, "size": 32})
        )
        self.assert_png(response)

    @override_settings(ENABLE_AVATARS=True)
    def test_avatar_check_handles_http_error(self) -> None:
        with patch(
            "weblate.accounts.apps.download_avatar_image",
            side_effect=httpx2.ConnectError("Avatar service unavailable"),
        ):
            errors = list(check_avatars(app_configs=None, databases=None))

        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].id, "weblate.E018")

    @http_mock.activate
    def test_avatar_rejects_unsupported_size_before_fetch(self) -> None:
        response = self.client.get(
            reverse("user_avatar", kwargs={"user": self.user.username, "size": 999})
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(http_mock.calls), 0)

    def test_anonymous_avatar(self) -> None:
        anonymous = User.objects.get(username="anonymous")
        # Anonymous user
        response = self.client.get(
            reverse("user_avatar", kwargs={"user": anonymous.username, "size": 32})
        )
        self.assertRedirects(
            response,
            "/static/weblate-32.png",
            fetch_redirect_response=False,
            status_code=301,
        )

    def test_fallback_avatar(self) -> None:
        self.assert_png_data(avatar.get_fallback_avatar(32))
