# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re
from functools import reduce

import mistletoe
from mistletoe import span_token
from django.db.models import Q
from django.utils.safestring import mark_safe

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
    pattern = span_token._open_tag + r'|' + span_token._closing_tag
    parse_inner = False
    content: str
    precedence = 4
    
    def __init__(self, match):
        self.content = ''

    @classmethod
    def find(cls, string):
        return re.compile(cls.pattern, re.DOTALL).finditer(string)


class SafeWeblateHtmlRenderer(mistletoe.HtmlRenderer):

    def __init__(self, *args, **kwargs):
        super().__init__(SkipHtmlSpan, process_html_tokens=False)

    def render_link(self, token: span_token.Link) -> str:
        result = super().render_link(token)
        return result.replace(' href="', ' rel="ugc" target="_blank" href="')

    def render_skip_html_span(self, token: SkipHtmlSpan) -> str:
        return token.content


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
