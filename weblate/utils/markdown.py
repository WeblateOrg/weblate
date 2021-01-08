#
# Copyright © 2012 - 2021 Michal Čihař <michal@cihar.com>
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


import re
from functools import reduce

import misaka
from django.db.models import Q
from django.utils.safestring import mark_safe

from weblate.auth.models import User

MENTION_RE = re.compile(r"(@[\w.@+-]+)\b", re.UNICODE)


def get_mention_users(text):
    """Returns IDs of users mentioned in the text."""
    matches = MENTION_RE.findall(text)
    if not matches:
        return User.objects.none()
    return User.objects.filter(
        reduce(lambda acc, x: acc | Q(username=x[1:]), matches, Q())
    )


class WeblateHtmlRenderer(misaka.SaferHtmlRenderer):
    def link(self, content, raw_url, title=""):
        result = super().link(content, raw_url, title)
        return result.replace(' href="', ' rel="ugc" href="')

    def check_url(self, url, is_image_src=False):
        if url.startswith("/user/"):
            return True
        return super().check_url(url, is_image_src)


RENDERER = WeblateHtmlRenderer()
MARKDOWN = misaka.Markdown(
    RENDERER,
    extensions=(
        "fenced-code",
        "tables",
        "autolink",
        "space-headers",
        "strikethrough",
        "superscript",
    ),
)


def render_markdown(text):
    users = {u.username.lower(): u for u in get_mention_users(text)}
    parts = MENTION_RE.split(text)
    for pos, part in enumerate(parts):
        if not part.startswith("@"):
            continue
        username = part[1:].lower()
        if username in users:
            user = users[username]
            parts[pos] = '**[{}]({} "{}")**'.format(
                part, user.get_absolute_url(), user.get_visible_name()
            )
    text = "".join(parts)
    return mark_safe(MARKDOWN(text))
