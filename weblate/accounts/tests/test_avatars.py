#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

"""Tests for user handling."""

from io import BytesIO

import responses
from django.urls import reverse
from PIL import Image

from weblate.accounts import avatar
from weblate.auth.models import User
from weblate.trans.tests.test_views import FixtureTestCase

TEST_URL = (
    "https://www.gravatar.com/avatar/"
    "55502f40dc8b7c769880b10874abc9d0?d=identicon&s=32"
)


class AvatarTest(FixtureTestCase):
    def setUp(self):
        super().setUp()
        self.user.email = "test@example.com"
        self.user.save()

    def test_avatar_for_email(self):
        url = avatar.avatar_for_email(self.user.email, size=32)
        self.assertEqual(TEST_URL, url)

    @responses.activate
    def test_avatar(self):
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
    def test_avatar_error(self):
        responses.add(responses.GET, TEST_URL, status=503)
        # Choose different username to avoid using cache
        self.user.username = "test2"
        self.user.save()
        response = self.client.get(
            reverse("user_avatar", kwargs={"user": self.user.username, "size": 32})
        )
        self.assert_png(response)

    def test_anonymous_avatar(self):
        anonymous = User.objects.get(username="anonymous")
        # Anonymous user
        response = self.client.get(
            reverse("user_avatar", kwargs={"user": anonymous.username, "size": 32})
        )
        self.assertRedirects(
            response, "/static/weblate-32.png", fetch_redirect_response=False
        )

    def test_fallback_avatar(self):
        self.assert_png_data(avatar.get_fallback_avatar(32))
