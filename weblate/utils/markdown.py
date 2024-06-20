# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re
from functools import reduce

import mistletoe
from django.db.models import Q
from django.utils.safestring import mark_safe
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

    pattern = span_token._open_tag + r"|" + span_token._closing_tag
    parse_inner = False
    content: str

    def __init__(self, match):
        self.content = ""

    @classmethod
    def find(cls, string):
        return re.compile(cls.pattern, re.DOTALL).finditer(string)


class SafeWeblateHtmlRenderer(mistletoe.HtmlRenderer):
    """
    A subclass of :class:`mistletoe.HtmlRenderer` wich adds a layer of protection
    against malicious input:
    1. Check if the URL is valid based on scheme and content
    2. Strip HTML tags from the content.
    """

    _allowed_url_re = re.compile(r"^https?:", re.IGNORECASE)

    def __init__(self, *args, **kwargs):
        super().__init__(SkipHtmlSpan, process_html_tokens=False)

    def render_skip_html_span(self, token: SkipHtmlSpan) -> str:
        return token.content

    def render_link(self, token: span_token.Link) -> str:
        if self.check_url(token.target):
            result = super().render_link(token)
            return result.replace(' href="', ' rel="ugc" target="_blank" href="')
        return self.escape_html_text(f"[{token.title}]({token.target})")

    def render_auto_link(self, token: span_token.AutoLink) -> str:
        if self.check_url(token.target):
            return super().render_auto_link(token)
        return self.escape_html_text(f"<{token.target}>")

    def render_image(self, token: span_token.Image) -> str:
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
    with SafeWeblateHtmlRenderer() as renderer:
        return mark_safe(renderer.render(mistletoe.Document(text)))
