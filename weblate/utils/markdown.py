# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import html
import re
from functools import reduce
from threading import local
from typing import TYPE_CHECKING, cast

from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q
from django.utils.html import linebreaks
from django.utils.safestring import mark_safe
from markdown_it import MarkdownIt
from markdown_it.token import Token

from weblate.accounts.visibility import can_view_profile
from weblate.auth.models import User
from weblate.utils.errors import report_error

if TYPE_CHECKING:
    from django.contrib.auth.models import AnonymousUser
    from django.db.models import QuerySet
    from markdown_it.renderer import RendererHTML
    from markdown_it.rules_core import StateCore

MENTION_RE = re.compile(r"(?<!\w)(@[\w.@+-]+)\b")
MAX_MENTION_USERS = 100
HTTP_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
EMAIL_AUTOLINK_RE = re.compile(r"mailto:[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_parsers = local()


def get_mention_users(text: str) -> QuerySet[User]:
    """Return IDs of users mentioned in the text."""
    usernames: dict[str, str] = {}
    for match in MENTION_RE.finditer(text):
        username = match[1][1:]
        usernames.setdefault(username.lower(), username)
        if len(usernames) == MAX_MENTION_USERS:
            break
    if not usernames:
        return User.objects.none()
    return User.objects.filter(
        reduce(
            lambda query, username: query | Q(username=username),
            usernames.values(),
            Q(),
        )
    )


def _allowed_url(url: str) -> bool:
    return url.startswith("/user/") or bool(HTTP_URL_RE.match(url))


def _prepare_inline_tokens(tokens: list[Token], state: StateCore) -> list[Token]:
    unlinked_mentions: frozenset[str] = state.env["unlinked_mentions"]
    renderer = cast("RendererHTML", state.md.renderer)
    prepared: list[Token] = []
    links: list[tuple[Token, int]] = []
    for index, token in enumerate(tokens):
        if token.type == "link_open":
            links.append((token, len(prepared)))
        elif token.type == "link_close":
            opening, start = links.pop()
            href = str(opening.attrs.get("href", ""))
            is_autolink = opening.markup == "autolink"
            if not _allowed_url(href) and not (
                is_autolink and EMAIL_AUTOLINK_RE.fullmatch(href)
            ):
                label = renderer.renderInlineAsText(
                    prepared[start + 1 :], state.md.options, state.env
                )
                prepared[start:] = [Token("text", "", 0, content=label)]
                continue
            opening.attrs = {"rel": "ugc", "target": "_blank", **opening.attrs}
            if href.startswith("/user/"):
                # Keep the leading @ beside the username in right-to-left text.
                prepared.insert(start, Token("bdi_open", "bdi", 1))
                prepared.extend((token, Token("bdi_close", "bdi", -1)))
                continue
        elif token.type == "image":
            src = str(token.attrs.get("src", ""))
            if not _allowed_url(src):
                label = renderer.renderInlineAsText(
                    token.children, state.md.options, state.env
                )
                token = Token("text", "", 0, content=label)
        elif token.type == "strong_open":
            following = tokens[index + 1 : index + 3]
            if (
                len(following) == 2
                and following[0].type == "text"
                and following[0].content in unlinked_mentions
                and following[1].type == "strong_close"
            ):
                prepared.append(Token("bdi_open", "bdi", 1))
                following[1].meta["isolate_mention"] = True
        prepared.append(token)
        if token.meta.get("isolate_mention"):
            prepared.append(Token("bdi_close", "bdi", -1))
    return prepared


def _prepare_rendering(state: StateCore) -> None:
    for token in state.tokens:
        if token.type == "inline" and token.children:
            token.children = _prepare_inline_tokens(token.children, state)
        elif token.type in {"th_open", "td_open"}:
            style = str(token.attrs.pop("style", ""))
            token.attrSet("align", style.removeprefix("text-align:") or "left")


def _get_parser() -> MarkdownIt:
    # Rule caches are initialized lazily by markdown-it-py.
    parser: MarkdownIt | None = getattr(_parsers, "markdown", None)
    if parser is None:
        parser = MarkdownIt("js-default", {"linkify": True})
        linkify = parser.linkify
        if linkify is None:
            msg = "Markdown rendering requires linkify-it-py."
            raise ImproperlyConfigured(msg)
        linkify.set({"fuzzy_link": False, "fuzzy_email": False, "fuzzy_ip": False})
        for scheme in ("ftp:", "mailto:", "//"):
            linkify.add(scheme, None)
        parser.core.ruler.after("text_join", "prepare_rendering", _prepare_rendering)
        _parsers.markdown = parser
    return parser


def render_markdown(text: str, *, viewer: User | AnonymousUser | None = None) -> str:
    """Render Markdown to HTML with viewer-specific user mentions."""
    original_text = text
    users = {u.username.lower(): u for u in get_mention_users(text)}
    unlinked_mentions: set[str] = set()
    parts = MENTION_RE.split(text)
    for pos, part in enumerate(parts):
        if not part.startswith("@"):
            continue
        username = part[1:].lower()
        if username in users:
            user = users[username]
            if can_view_profile(viewer, user):
                title = html.escape(user.get_visible_name().replace("\\", "\\\\"))
                parts[pos] = f'**[{part}]({user.get_absolute_url()} "{title}")**'
            else:
                # Keep mentions isolated in RTL text even without a profile link.
                unlinked_mentions.add(part)
                parts[pos] = f"**{part}**"
    text = "".join(parts)
    try:
        rendered = _get_parser().render(
            text, {"unlinked_mentions": frozenset(unlinked_mentions)}
        )
        # ruff: ignore[suspicious-mark-safe-usage]
        return mark_safe(rendered)
    except Exception:
        report_error("Markdown rendering failed")
        # ruff: ignore[suspicious-mark-safe-usage]
        return mark_safe(linebreaks(original_text, autoescape=True))
