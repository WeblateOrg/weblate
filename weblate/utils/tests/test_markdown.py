# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.test import TestCase

from weblate.auth.models import User
from weblate.utils.markdown import get_mention_users, render_markdown


class MarkdownTestCase(TestCase):
    def test_link(self):
        self.assertEqual(
            '<p><a rel="ugc" target="_blank" '
            'href="https://weblate.org/">link</a></p>\n',
            render_markdown("[link](https://weblate.org/)"),
        )

    def test_js(self):
        self.assertEqual(
            "<p>link</p>\n", render_markdown('<a href="javascript:alert()">link</a>')
        )

    def test_intra_emphasis(self):
        self.assertEqual(
            "<p>foo<strong>bar</strong>baz</p>\n", render_markdown("foo**bar**baz")
        )


class MarkdownMentionTestCase(TestCase):
    def test_mention(self):
        User.objects.create(username="testuser", full_name="Full Name")
        self.assertEqual(
            '<p><strong><a rel="ugc" target="_blank" href="/user/testuser/" '
            'title="Full Name">@testuser</a></strong> really?</p>\n',
            render_markdown("@testuser really?"),
        )

    def test_get_mentions(self):
        user = User.objects.create(username="testuser", full_name="Full Name")
        self.assertEqual(
            {user.pk},
            set(
                get_mention_users("@testuser, @invalid, @testuser").values_list(
                    "pk", flat=True
                )
            ),
        )

    def test_get_mentions_case_insentivite(self):
        user = User.objects.create(username="testuser", full_name="Full Name")
        self.assertEqual(
            {user.pk},
            set(
                get_mention_users("@testUser, @invalid, @Testuser").values_list(
                    "pk", flat=True
                )
            ),
        )

    def test_get_mentions_non_mention(self):
        self.assertEqual(
            set(),
            set(
                get_mention_users("trans@lists.fedoraproject.org").values_list(
                    "pk", flat=True
                )
            ),
        )
