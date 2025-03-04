# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from django.test import TestCase

from weblate.auth.models import User
from weblate.utils.markdown import get_mention_users, render_markdown


class MarkdownTestCase(TestCase):
    def test_link(self) -> None:
        self.assertEqual(
            '<p><a rel="ugc" target="_blank" '
            'href="https://weblate.org/">link</a></p>\n',
            render_markdown("[link](https://weblate.org/)"),
        )

    def test_js(self) -> None:
        self.assertEqual(
            "<p>link</p>\n", render_markdown('<a href="javascript:alert()">link</a>')
        )
        self.assertEqual(
            "<p>link</p>\n",
            render_markdown(
                '<a href="javascript:alert()"><a href="javascript:alert()">link</a>'
            ),
        )
        self.assertEqual(
            "<p>link</p>\n",
            render_markdown(
                '<a href="javascript:alert()"><a href="javascript:alert()">link</a></a>'
            ),
        )
        self.assertEqual(
            "<p>link</p>\n",
            render_markdown('<div><a href="javascript:alert()">link</a></div>'),
        )
        self.assertEqual(
            "<p>before link after</p>\n",
            render_markdown(
                '<div>before <a href="javascript:alert()">link</a> after</div>'
            ),
        )

    def test_intra_emphasis(self) -> None:
        self.assertEqual(
            "<p>foo<strong>bar</strong>baz</p>\n", render_markdown("foo**bar**baz")
        )

    def test_autolink(self) -> None:
        self.assertEqual(
            '<p><a rel="ugc" target="_blank" href="http://valid.link">http://valid.link</a></p>\n',
            render_markdown("<http://valid.link>"),
        )
        self.assertEqual(
            '<p><a rel="ugc" target="_blank" href="https://valid.link">https://valid.link</a></p>\n',
            render_markdown("<https://valid.link>"),
        )
        self.assertEqual(
            "<p>&lt;invalid.link&gt;</p>\n", render_markdown("<invalid.link>")
        )
        self.assertEqual(
            "<p>&lt;ftp://invalid.link&gt;</p>\n",
            render_markdown("<ftp://invalid.link>"),
        )
        self.assertEqual(
            "<p>&lt;javascript:foo&gt;</p>\n", render_markdown("<javascript:foo>")
        )
        self.assertEqual(
            '<p><a rel="ugc" target="_blank" href="mailto:valid@email.com">valid@email.com</a></p>\n',
            render_markdown("<valid@email.com>"),
        )
        self.assertEqual(
            '<p><a rel="ugc" target="_blank" href="mailto:valid@email.com">mailto:valid@email.com</a></p>\n',
            render_markdown("<mailto:valid@email.com>"),
        )
        self.assertEqual(
            "<p>&lt;email@incomplete&gt;</p>\n", render_markdown("<email@incomplete>")
        )
        self.assertEqual(
            "<p>&lt;mailto:email@incomplete&gt;</p>\n",
            render_markdown("<mailto:email@incomplete>"),
        )

    def test_image(self) -> None:
        self.assertEqual(
            "<p>![](invalid.link)</p>\n", render_markdown("![title](invalid.link)")
        )
        self.assertEqual(
            '<p><img src="http://valid.link" alt="title" /></p>\n',
            render_markdown("![title](http://valid.link)"),
        )
        self.assertEqual(
            '<p><img src="http://valid.link/empty-title" alt="" /></p>\n',
            render_markdown("![](http://valid.link/empty-title)"),
        )
        self.assertEqual(
            '<p><img src="https://valid.link" alt="title" /></p>\n',
            render_markdown("![title](https://valid.link)"),
        )
        self.assertEqual(
            "<p>![](ftp://invalid.link)</p>\n",
            render_markdown("![title](ftp://invalid.link)"),
        )

    def test_plain_link(self) -> None:
        self.assertEqual(
            '<p>This is <a rel="ugc" target="_blank" href="https://weblate.org">https://weblate.org</a></p>\n',
            render_markdown("This is https://weblate.org"),
        )


class MarkdownMentionTestCase(TestCase):
    def test_mention(self) -> None:
        User.objects.create(username="testuser", full_name="Full Name")
        self.assertEqual(
            '<p><strong><a rel="ugc" target="_blank" href="/user/testuser/" '
            'title="Full Name">@testuser</a></strong> really?</p>\n',
            render_markdown("@testuser really?"),
        )

    def test_get_mentions(self) -> None:
        user = User.objects.create(username="testuser", full_name="Full Name")
        self.assertEqual(
            {user.pk},
            set(
                get_mention_users("@testuser, @invalid, @testuser").values_list(
                    "pk", flat=True
                )
            ),
        )

    def test_get_mentions_case_insentivite(self) -> None:
        user = User.objects.create(username="testuser", full_name="Full Name")
        self.assertEqual(
            {user.pk},
            set(
                get_mention_users("@testUser, @invalid, @Testuser").values_list(
                    "pk", flat=True
                )
            ),
        )

    def test_get_mentions_non_mention(self) -> None:
        self.assertEqual(
            set(),
            set(
                get_mention_users("trans@lists.fedoraproject.org").values_list(
                    "pk", flat=True
                )
            ),
        )
