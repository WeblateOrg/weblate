# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re
from functools import reduce

import mistletoe
from django.db.models import Q
from mistletoe import span_token

from weblate.auth.models import User

MENTION_RE = re.compile(r"(?<!\w)(@[\w.@+-]+)\b")


def get_mention_users(text):
    """Return IDs of users mentioned in the text."""
    matches = MENTION_RE.findall(text)
    if not matches:
        return User.objects.none()
    return User.objects.filter(
        reduce(lambda acc, x: acc | Q(username=x[1:]), matches, Q())
    )


class SkipHtmlSpan(span_token.HtmlSpan):
    """A token that strips HTML tags from the content."""

    pattern = re.compile(f"{span_token._open_tag}|{span_token._closing_tag}")
    parse_inner = False
    content: str

    def __init__(self, match):
        self.content = ""


class SaferWeblateHtmlRenderer(mistletoe.HtmlRenderer):
    """
    A renderer which adds a layer of protection against malicious input.

    1. Check if the URL is valid based on scheme and content
    2. Strip HTML tags from the content.
    """

    _allowed_url_re = re.compile(r"^https?://", re.IGNORECASE)

    def __init__(self, *args, **kwargs):
        super().__init__(SkipHtmlSpan, process_html_tokens=False)

    def render_skip_html_span(self, token: SkipHtmlSpan) -> str:
        """
        Render a skip HTML span token.

        Return the content of the token, without any HTML tags.
        """
        return token.content

    def render_link(self, token: span_token.Link) -> str:
        """
        Render a link token.

        If the URL is valid, add the necessary attributes to make it open in a new tab.
        """
        if self.check_url(token.target):
            result = super().render_link(token)
            return result.replace(' href="', ' rel="ugc" target="_blank" href="')
        return self.escape_html_text(f"[{token.title}]({token.target})")

    def render_auto_link(self, token: span_token.AutoLink) -> str:
        """
        Render an auto link token.

        If the URL is valid, render the auto link as usual.
        Otherwise, escape the URL.
        """

        def valid_email(email: str) -> bool:
            """Check if an email address is valid."""
            pattern = re.compile(
                r"(mailto:)?[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
            )
            return bool(pattern.match(email))

        if self.check_url(token.target) or valid_email(token.target):
            return super().render_auto_link(token)
        return self.escape_html_text(f"<{token.target}>")

    def render_image(self, token: span_token.Image) -> str:
        """
        Render an image token.

        If the URL is valid, add the necessary attributes to the image tag.
        Otherwise, escape the URL.
        """
        if self.check_url(token.src):
            return super().render_image(token)
        return self.escape_html_text(f"![{token.title}]({token.src})")

    def check_url(self, url: str) -> bool:
        """Check if an url is valid or not  the scheme."""
        if url.startswith("/user/"):
            return True
        return bool(self._allowed_url_re.match(url))


def render_markdown(text):
    users = {u.username.lower(): u for u in get_mention_users(text)}
    parts = MENTION_RE.split(text)
    for pos, part in enumerate(parts):
        if not part.startswith("@"):
            continue
        username = part[1:].lower()
        if username in users:
            user = users[username]
            parts[pos] = (
                f'**[{part}]({user.get_absolute_url()} "{user.get_visible_name()}")**'
            )
    text = "".join(parts)
    with SaferWeblateHtmlRenderer() as renderer:
        return renderer.render(mistletoe.Document(text))
