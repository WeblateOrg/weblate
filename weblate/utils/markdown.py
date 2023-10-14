# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re
from functools import reduce

import mistletoe
from django.db.models import Q
from django.utils.safestring import mark_safe

from weblate.auth.models import User

MENTION_RE = re.compile(r"(@[\w.@+-]+)\b")


def get_mention_users(text):
    """Returns IDs of users mentioned in the text."""
    matches = MENTION_RE.findall(text)
    if not matches:
        return User.objects.none()
    return User.objects.filter(
        reduce(lambda acc, x: acc | Q(username=x[1:]), matches, Q())
    )


class WeblateHtmlRenderer(mistletoe.HTMLRenderer):
    def link(self, target, title, content):
        return f'<a href="{target}" rel="ugc" target="_blank" title="{title}">{content}</a>'

    def check_url(self, url, is_image_src=False):
        if url.startswith("/user/"):
            return True
        return super().check_url(url, is_image_src)

def render_markdown(text):
    users = {u.username.lower(): u for u in get_mention_users(text)}
    parts = MENTION_RE.split(text)
    for pos, part in enumerate(parts):
        if not part.startswith("@"):
            continue
        username = part[1:].lower()
        if username in users:
            user = users[username]
            parts[pos] = f'**[{part}]({user.get_absolute_url()} "{user.get_visible_name()}")**'
    text = "".join(parts)

    # Initialize the mistletoe renderer
    mistletoe_renderer = WeblateHtmlRenderer()

    markdown_content = mistletoe.markdown(text, renderer=mistletoe_renderer)
    return markdown_content
