# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Render user identities according to the current viewer's profile access."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django import template
from django.utils.html import format_html

from weblate.accounts.avatar import get_user_avatar_url, get_user_display
from weblate.accounts.visibility import can_view_contributor, can_view_profile
from weblate.utils.markdown import render_markdown

if TYPE_CHECKING:
    from django.contrib.auth.models import AnonymousUser
    from django.db.models import Model
    from django.template import Context

    from weblate.auth.models import User

register = template.Library()


def get_display_viewer(context: Context) -> User | AnonymousUser | None:
    """Use the request viewer, never a displayed user or a notification author."""
    if context.get("subscription_user"):
        return context["subscription_user"]
    if context.get("in_email") or context.get("profile_public_output"):
        return None
    if request := context.get("request"):
        return request.user
    return context.get("profile_viewer")


@register.simple_tag(takes_context=True)
def user_display(
    context: Context,
    user: User | None,
    icon: bool = True,
    link: bool = True,
    resource: Model | None = None,
) -> str:
    viewer = context.get("subscription_user") or get_display_viewer(context)
    if resource is not None and not can_view_contributor(viewer, resource):
        from django.utils.translation import gettext  # ruff: ignore[import-outside-top-level]

        return gettext("Contributor")
    return get_user_display(user, icon, link, viewer=viewer)


@register.simple_tag(takes_context=True)
def user_avatar(context: Context, user: User, size: int = 32) -> str:
    return get_user_avatar_url(user, size, viewer=get_display_viewer(context))


@register.simple_tag(takes_context=True)
def user_profile_access(context: Context, user: User) -> bool:
    return can_view_profile(get_display_viewer(context), user)


@register.simple_tag(takes_context=True)
def user_markdown(context: Context, text: str) -> str:
    return format_html(
        '<div class="markdown">{}</div>',
        render_markdown(text, viewer=get_display_viewer(context)),
    )


@register.simple_tag(takes_context=True)
def user_commit_author(context: Context, commit: dict) -> str:
    # ruff: ignore[import-outside-top-level]
    from weblate.trans.templatetags.translations import format_commit_author

    return format_commit_author(commit, viewer=get_display_viewer(context))


@register.simple_tag(takes_context=True)
def contributor_access(context: Context, resource: Model) -> bool:
    return can_view_contributor(
        context.get("subscription_user") or get_display_viewer(context), resource
    )
