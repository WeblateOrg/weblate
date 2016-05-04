# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2016 Michal Čihař <michal@cihar.com>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

"""
Tests for user handling.
"""

from unittest import SkipTest
from django.core.urlresolvers import reverse
from django.contrib.auth.models import User

from weblate.accounts import avatar
from weblate.trans.tests.test_views import ViewTestCase


class AvatarTest(ViewTestCase):
    def setUp(self):
        super(AvatarTest, self).setUp()
        self.user.email = 'test@example.com'
        self.user.save()

    def assert_url(self):
        url = avatar.avatar_for_email(self.user.email)
        self.assertEqual(
            'https://seccdn.libravatar.org/avatar/'
            '55502f40dc8b7c769880b10874abc9d0',
            url.split('?')[0]
        )

    def test_avatar_for_email_own(self):
        backup = avatar.HAS_LIBRAVATAR
        try:
            avatar.HAS_LIBRAVATAR = False
            self.assert_url()
        finally:
            avatar.HAS_LIBRAVATAR = backup

    def test_avatar_for_email_libravatar(self):
        if not avatar.HAS_LIBRAVATAR:
            raise SkipTest('Libravatar not installed')
        self.assert_url()

    def test_avatar(self):
        # Real user
        response = self.client.get(
            reverse(
                'user_avatar',
                kwargs={'user': self.user.username, 'size': 32}
            )
        )
        self.assertPNG(response)
        # Test caching
        response = self.client.get(
            reverse(
                'user_avatar',
                kwargs={'user': self.user.username, 'size': 32}
            )
        )
        self.assertPNG(response)

    def test_anonymous_avatar(self):
        anonymous = User.objects.get(username='anonymous')
        # Anonymous user
        response = self.client.get(
            reverse(
                'user_avatar',
                kwargs={'user': anonymous.username, 'size': 32}
            )
        )
        self.assertRedirects(
            response, '/static/weblate-32.png',
            fetch_redirect_response=False
        )

    def test_fallback_avatar(self):
        self.assertPNGData(
            avatar.get_fallback_avatar(32)
        )
