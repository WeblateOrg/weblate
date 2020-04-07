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


import re

import misaka
from django.utils.safestring import mark_safe

from weblate.auth.models import User

MENTION_RE = re.compile(r"@([\w.@+-]+)\b", re.UNICODE)


def get_mentions(text):
    for match in MENTION_RE.findall(text):
        try:
            yield User.objects.get(username=match, is_active=True)
        except User.DoesNotExist:
            continue


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
        "no-intra-emphasis",
        "tables",
        "autolink",
        "space-headers",
        "strikethrough",
        "superscript",
    ),
)


def render_markdown(text):
    for user in get_mentions(text):
        mention = "@{}".format(user.username)
        text = text.replace(
            mention,
            '**[{}]({} "{}")**'.format(
                mention, user.get_absolute_url(), user.get_visible_name()
            ),
        )
    return mark_safe(MARKDOWN(text))
