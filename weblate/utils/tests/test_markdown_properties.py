# Copyright © Weblate contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from html.parser import HTMLParser
from unittest.mock import patch

from hypothesis import example, given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import SimpleTestCase

from weblate.utils.markdown import render_markdown

_MARKDOWN_DANGEROUS_TAGS = frozenset(
    {
        "base",
        "embed",
        "form",
        "iframe",
        "link",
        "math",
        "meta",
        "object",
        "script",
        "style",
        "svg",
        "template",
    }
)
_MARKDOWN_DANGEROUS_ATTRS = frozenset({"srcdoc", "style"})
_MARKDOWN_URL_ATTRS = frozenset(
    {"action", "background", "formaction", "href", "poster", "src", "xlink:href"}
)
_MARKDOWN_DANGEROUS_URL_SCHEMES = frozenset({"data", "javascript", "vbscript"})
_MARKDOWN_XSS_PROBE_TEMPLATES = (
    "<script>{payload}</script>",
    '<img src=x onerror="{payload}">',
    "<svg><script>{payload}</script></svg>",
    "[link](javascript:{payload})",
    "[link](data:text/html,{payload})",
    "![image](javascript:{payload})",
    "<javascript:{payload}>",
    '[link](<https://example.com/" onclick="{payload}>)',
    '![image](<https://example.com/" onerror="{payload}>)',
)


class MarkdownSafetyParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.issues: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._check_tag(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._check_tag(tag, attrs)

    def _check_tag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in _MARKDOWN_DANGEROUS_TAGS:
            self.issues.append(f"dangerous <{normalized_tag}> tag")

        for raw_name, value in attrs:
            attr = raw_name.lower()
            if attr.startswith("on"):
                self.issues.append(f"event handler attribute {raw_name!r}")
            if attr in _MARKDOWN_DANGEROUS_ATTRS:
                self.issues.append(f"dangerous attribute {raw_name!r}")
            if value is not None and attr in _MARKDOWN_URL_ATTRS:
                scheme = _compact_url_for_xss_check(value).partition(":")[0]
                if scheme in _MARKDOWN_DANGEROUS_URL_SCHEMES:
                    self.issues.append(f"dangerous {raw_name!r} URL scheme")


def _compact_url_for_xss_check(value: str) -> str:
    return "".join(
        char
        for char in value.lower()
        if not char.isspace() and char > "\x1f" and char != "\x7f"
    ).lstrip()


def assert_safe_markdown(rendered: str) -> None:
    parser = MarkdownSafetyParser()
    parser.feed(rendered)
    parser.close()
    if parser.issues:
        issues = "; ".join(parser.issues[:3])
        msg = f"Unsafe markdown renderer output: {issues}"
        raise AssertionError(msg)


def build_xss_probe(payload: str) -> str:
    cleaned_payload = payload.replace("\x00", "")[:128] or "alert(1)"
    return "\n\n".join(
        template.format(payload=cleaned_payload)
        for template in _MARKDOWN_XSS_PROBE_TEMPLATES
    )


class MarkdownPropertyTest(SimpleTestCase):
    @settings(max_examples=100, derandomize=True, deadline=None)
    @given(st.text(max_size=512))
    @example("<b>Hello</b>\n[Weblate](https://weblate.org/)")
    @example('<img src=x onerror="alert(1)">')
    @example("[link](javascript:alert(1))")
    @example("[link](data:text/html,<script>alert(1)</script>)")
    @example('![image](<https://example.com/" onerror="alert(1)>)')
    def test_rendered_html_is_safe(self, text: str) -> None:
        with patch("weblate.utils.markdown.get_mention_users", return_value=[]):
            assert_safe_markdown(render_markdown(text))

    @settings(max_examples=100, derandomize=True, deadline=None)
    @given(st.text(max_size=128))
    @example("alert(1)")
    @example('" onclick="alert(1)')
    def test_xss_probes_are_safe(self, payload: str) -> None:
        with patch("weblate.utils.markdown.get_mention_users", return_value=[]):
            assert_safe_markdown(render_markdown(build_xss_probe(payload)))

    def test_safety_assertion_detects_xss(self) -> None:
        for html in (
            "<script>alert(1)</script>",
            '<img src="x" onerror="alert(1)">',
            '<a href="javascript:alert(1)">link</a>',
            '<a href="java\tscript:alert(1)">link</a>',
        ):
            with (
                self.subTest(html=html),
                self.assertRaisesRegex(
                    AssertionError, "Unsafe markdown renderer output"
                ),
            ):
                assert_safe_markdown(html)
