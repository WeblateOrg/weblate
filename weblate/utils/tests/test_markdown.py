#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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


from django.test import SimpleTestCase, TestCase

from weblate.auth.models import User
from weblate.utils.markdown import render_markdown


class MarkdownTestCase(SimpleTestCase):
    def test_link(self):
        self.assertEqual(
            '<p><a rel="ugc" href="https://weblate.org/">link</a></p>\n',
            render_markdown("[link](https://weblate.org/)"),
        )

    def test_js(self):
        self.assertEqual(
            "<p>link</p>\n", render_markdown('<a href="javascript:alert()">link</a>')
        )


class MarkdownMentionTestCase(TestCase):
    def test_mention(self):
        User.objects.create(username="testuser", full_name="Full Name")
        self.assertEqual(
            '<p><strong><a rel="ugc" href="/user/testuser/" '
            'title="Full Name">@testuser</a></strong> really?</p>\n',
            render_markdown("@testuser really?"),
        )
