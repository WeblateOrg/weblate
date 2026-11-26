# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from concurrent.futures import ThreadPoolExecutor
from operator import is_
from threading import Barrier
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from weblate.auth.models import User
from weblate.utils.markdown import MAX_MENTION_USERS, get_mention_users, render_markdown


class MarkdownTestCase(SimpleTestCase):
    def test_get_mentions_deduplicated_and_limited(self) -> None:
        mentions = ["@Duplicate", "@DUPLICATE", "@duplicate"]
        mentions.extend(f"@user{index}" for index in range(MAX_MENTION_USERS))

        with patch("weblate.utils.markdown.User.objects.filter") as filter_mock:
            get_mention_users(" ".join(mentions))

        filter_mock.assert_called_once()
        query = filter_mock.call_args.args[0]
        self.assertEqual(
            query.children,
            [
                ("username", "Duplicate"),
                *(
                    ("username", f"user{index}")
                    for index in range(MAX_MENTION_USERS - 1)
                ),
            ],
        )

    def test_link(self) -> None:
        self.assertEqual(
            '<p><a rel="ugc" target="_blank" '
            'href="https://weblate.org/">link</a></p>\n',
            render_markdown("[link](https://weblate.org/)"),
        )
        self.assertEqual(
            '<p><a rel="ugc" target="_blank" href="https://e.com/%22%20'
            'onclick=%22alert(1)">link</a></p>\n',
            render_markdown('[link](<https://e.com/" onclick="alert(1)>)'),
        )

    def test_raw_html_is_displayed_as_text(self) -> None:
        self.assertEqual(
            "<p>&lt;div&gt;before &lt;a href=&quot;javascript:alert()&quot;&gt;"
            "link&lt;/a&gt; after&lt;/div&gt;</p>\n",
            render_markdown(
                '<div>before <a href="javascript:alert()">link</a> after</div>'
            ),
        )

    def test_intra_emphasis(self) -> None:
        self.assertEqual(
            "<p>foo<strong>bar</strong>baz</p>\n", render_markdown("foo**bar**baz")
        )

    def test_parser_failure_fallback(self) -> None:
        with (
            patch(
                "weblate.utils.markdown.MarkdownIt.render",
                side_effect=IndexError("string index out of range"),
            ),
            patch("weblate.utils.markdown.report_error") as report_error,
        ):
            self.assertEqual(
                "<p>**markdown**<br>&lt;script&gt;</p>",
                render_markdown("**markdown**\n<script>"),
            )
        report_error.assert_called_once_with("Markdown rendering failed")

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
            "<p>ftp://invalid.link</p>\n",
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
            "<p>email@incomplete</p>\n", render_markdown("<email@incomplete>")
        )
        self.assertEqual(
            "<p>mailto:email@incomplete</p>\n",
            render_markdown("<mailto:email@incomplete>"),
        )
        self.assertHTMLEqual(
            '<p><a rel="ugc" target="_blank" href="https://doomwiki.org/wiki/Chex_Quest_cheat_codes#:~:text=davidbrus">https://doomwiki.org/wiki/Chex_Quest_cheat_codes#:~:text=davidbrus</a></p>',
            render_markdown(
                "https://doomwiki.org/wiki/Chex_Quest_cheat_codes#:~:text=davidbrus"
            ),
        )

    def test_image(self) -> None:
        self.assertEqual("<p>title</p>\n", render_markdown("![title](invalid.link)"))
        self.assertEqual(
            '<p><img src="http://valid.link" alt="title"></p>\n',
            render_markdown("![title](http://valid.link)"),
        )
        self.assertEqual(
            '<p><img src="http://valid.link/empty-title" alt=""></p>\n',
            render_markdown("![](http://valid.link/empty-title)"),
        )
        self.assertEqual(
            '<p><img src="https://valid.link" alt="title"></p>\n',
            render_markdown("![title](https://valid.link)"),
        )
        self.assertEqual(
            '<p><img src="https://e.com/%22%20onerror=%22alert(1)" alt="title"></p>\n',
            render_markdown('![title](<https://e.com/" onerror="alert(1)>)'),
        )
        self.assertEqual(
            '<p><img src="https://valid.link" alt="ti &quot;tle" '
            'title="quot&quot;ed"></p>\n',
            render_markdown("![ti \"tle](https://valid.link 'quot\"ed')"),
        )

    def test_plain_link(self) -> None:
        self.assertEqual(
            '<p>This is <a rel="ugc" target="_blank" href="https://weblate.org">https://weblate.org</a></p>\n',
            render_markdown("This is https://weblate.org"),
        )
        self.assertEqual(
            '<p>This is <a rel="ugc" target="_blank" href="https://example.com/">https://example.com/</a></p>\n',
            render_markdown("This is https://example.com/"),
        )
        self.assertEqual(
            '<p>This is <a rel="ugc" target="_blank" href="https://example.com">https://example.com</a>)</p>\n',
            render_markdown("This is https://example.com)"),
        )
        self.assertEqual(
            '<p>This is <a rel="ugc" target="_blank" href="https://example.com">https://example.com</a>).</p>\n',
            render_markdown("This is https://example.com)."),
        )

    def test_plain_link_underscore(self) -> None:
        self.assertEqual(
            '<p><a rel="ugc" target="_blank" href="https://en.wikipedia.org/wiki/Celery_(software)">https://en.wikipedia.org/wiki/Celery_(software)</a></p>\n',
            render_markdown("https://en.wikipedia.org/wiki/Celery_(software)"),
        )
        self.assertEqual(
            '<p><a rel="ugc" target="_blank" href="https://en.wikipedia.org/wiki/Celery_(software)">https://en.wikipedia.org/wiki/Celery_(software)</a> link</p>\n',
            render_markdown("https://en.wikipedia.org/wiki/Celery_(software) link"),
        )
        self.assertEqual(
            '<p>See <a rel="ugc" target="_blank" href="https://en.wikipedia.org/wiki/Celery_(software)">https://en.wikipedia.org/wiki/Celery_(software)</a>.</p>\n',
            render_markdown("See https://en.wikipedia.org/wiki/Celery_(software)."),
        )

    def test_plain_link_inside_code_and_link_label(self) -> None:
        self.assertHTMLEqual(
            "<p><code>https://example.com/</code> "
            '<a rel="ugc" target="_blank" href="https://weblate.org/">'
            "https://example.com/</a></p>",
            render_markdown(
                "`https://example.com/` [https://example.com/](https://weblate.org/)"
            ),
        )

    def test_plain_link_requires_http_scheme(self) -> None:
        text = (
            "example.com 192.0.2.1 user@example.com ftp://example.com/ "
            "//example.com/ mailto:user@example.com"
        )
        self.assertEqual(f"<p>{text}</p>\n", render_markdown(text))

    def test_raw_html_around_markdown_and_inside_code(self) -> None:
        self.assertHTMLEqual(
            "<p>&lt;span&gt;<strong>bold</strong>&lt;/span&gt; "
            "<code>&lt;span&gt;</code></p>",
            render_markdown("<span>**bold**</span> `<span>`"),
        )

    def test_rejected_destinations(self) -> None:
        for text, label in (
            ("[link](//example.com/)", "link"),
            ("[link](/other/)", "link"),
            ("[link](mailto:valid@example.com)", "link"),
            ('[**Read** `<guide>`](ftp://example.com/ "Title")', "Read &lt;guide&gt;"),
            ('![**Alt** `<text>`](ftp://example.com/ "Title")', "Alt &lt;text&gt;"),
            ("![image](mailto:valid@example.com)", "image"),
            ("![image](data:image/png;base64,AA==)", "image"),
            ('![](ftp://example.com/ "Title")', ""),
        ):
            with self.subTest(text=text):
                self.assertEqual(f"<p>{label}</p>\n", render_markdown(text))

    def test_table_alignment(self) -> None:
        self.assertHTMLEqual(
            '<table><thead><tr><th align="left">A</th><th align="right">B</th>'
            '</tr></thead><tbody><tr><td align="left"><s>C</s></td>'
            '<td align="right">D</td></tr></tbody></table>',
            render_markdown("| A | B |\n| --- | ---: |\n| ~~C~~ | D |"),
        )

    def test_concurrent_rendering(self) -> None:
        mentioned = User(username="testuser", full_name='Full "Name"')
        other_viewer = User(username="other")
        workers = Barrier(4)

        def render(index: int) -> str:
            if index < workers.parties:
                workers.wait(timeout=10)
            return render_markdown(
                f"@testuser مرحبا [site][ref]\n\n[ref]: https://example.com/{index}",
                viewer=mentioned if index % 2 else other_viewer,
            )

        with (
            patch("weblate.utils.markdown.get_mention_users", return_value=[mentioned]),
            patch(
                "weblate.utils.markdown.can_view_profile",
                side_effect=is_,
            ),
            ThreadPoolExecutor(max_workers=workers.parties) as pool,
        ):
            results = list(pool.map(render, range(16)))

        for index, rendered in enumerate(results):
            self.assertIn(f'href="https://example.com/{index}"', rendered)
            if index % 2:
                self.assertIn(
                    '<strong><bdi><a rel="ugc" target="_blank" '
                    'href="/user/testuser/" title="Full &quot;Name&quot;">'
                    "@testuser</a></bdi></strong>",
                    rendered,
                )
            else:
                self.assertIn("<p>@testuser مرحبا ", rendered)
                self.assertNotIn("/user/testuser/", rendered)


class MarkdownMentionTestCase(TestCase):
    def test_mention(self) -> None:
        User.objects.create(username="testuser", full_name="Full Name")
        self.assertEqual(
            '<p><strong><bdi><a rel="ugc" target="_blank" href="/user/testuser/" '
            'title="Full Name">@testuser</a></bdi></strong> really?</p>\n',
            render_markdown("@testuser really?"),
        )

    def test_mention_rtl(self) -> None:
        User.objects.create(username="testuser", full_name="Full Name")
        self.assertEqual(
            '<p><strong><bdi><a rel="ugc" target="_blank" href="/user/testuser/" '
            'title="Full Name">@testuser</a></bdi></strong> مرحبا</p>\n',
            render_markdown("@testuser مرحبا"),
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

    def test_get_mentions_case_insensitive(self) -> None:
        user = User.objects.create(username="TestUser", full_name="Full Name")
        self.assertEqual(
            {user.pk},
            set(
                get_mention_users("@testUser, @invalid, @Testuser").values_list(
                    "pk", flat=True
                )
            ),
        )

    def test_get_mentions_preserves_unicode_spelling(self) -> None:
        user = User.objects.create(username="İ", full_name="Full Name")
        self.assertEqual(
            {user.pk},
            set(get_mention_users("@İ").values_list("pk", flat=True)),
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
