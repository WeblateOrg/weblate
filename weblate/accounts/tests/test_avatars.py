# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for user handling."""

from io import BytesIO

import responses
from django.urls import reverse
from PIL import Image

from weblate.accounts import avatar
from weblate.auth.models import User
from weblate.trans.tests.test_views import FixtureTestCase

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

    @responses.activate
    def test_avatar(self) -> None:
        image = Image.new("RGB", (32, 32))
        storage = BytesIO()
        image.save(storage, "PNG")
        imagedata = storage.getvalue()
        responses.add(responses.GET, TEST_URL, body=imagedata)
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

    @responses.activate
    def test_avatar_error(self) -> None:
        responses.add(responses.GET, TEST_URL, status=503)
        # Choose different username to avoid using cache
        self.user.username = "test2"
        self.user.save()
        response = self.client.get(
            reverse("user_avatar", kwargs={"user": self.user.username, "size": 32})
        )
        self.assert_png(response)

    def test_anonymous_avatar(self) -> None:
        anonymous = User.objects.get(username="anonymous")
        # Anonymous user
        response = self.client.get(
            reverse("user_avatar", kwargs={"user": anonymous.username, "size": 32})
        )
        self.assertRedirects(
            response, "/static/weblate-32.png", fetch_redirect_response=False
        )

    def test_fallback_avatar(self) -> None:
        self.assert_png_data(avatar.get_fallback_avatar(32))
