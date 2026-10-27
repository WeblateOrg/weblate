# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Profile visibility in generated user identities and mentions."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import AnonymousUser
from django.db.models import Value
from django.template import Context, Template
from django.template.loader import render_to_string
from django.test import RequestFactory, override_settings
from django.urls import reverse
from lxml.html import fromstring

from weblate.accounts.avatar import (
    get_fallback_avatar_url,
    get_user_avatar_url,
    get_user_display,
)
from weblate.accounts.models import Profile, VerifiedEmail
from weblate.accounts.notifications import NewAnnouncementNotificaton
from weblate.auth.models import User, get_anonymous
from weblate.trans.actions import ActionEvents
from weblate.trans.feeds import BaseFeed
from weblate.trans.models import Announcement, Change
from weblate.trans.templatetags.translations import format_last_changes_content
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.utils.markdown import get_mention_users, render_markdown

if TYPE_CHECKING:
    from django.core.handlers.wsgi import WSGIRequest


@override_settings(ENABLE_AVATARS=True)
class UserDisplayTest(FixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.target = User.objects.create_user(
            "display-target", "display@example.org", full_name="<Target & Name>"
        )

    def request_for(self, viewer: User | AnonymousUser) -> WSGIRequest:
        request = RequestFactory().get("/")
        request.user = viewer
        return request

    def assert_profile_display(self, rendered: str, *, accessible: bool) -> None:
        self.assertIn(self.target.username, rendered)
        avatar_url = reverse(
            "user_avatar", kwargs={"user": self.target.username, "size": 32}
        )
        document = fromstring(rendered)
        links = {urlsplit(url).path for url in document.xpath(".//@href")}
        images = {urlsplit(url).path for url in document.xpath(".//@src")}
        if accessible:
            self.assertIn(self.target.get_absolute_url(), links)
            self.assertIn(avatar_url, images)
        else:
            self.assertNotIn(self.target.get_absolute_url(), links)
            self.assertNotIn(avatar_url, images)
            self.assertIn(urlsplit(get_fallback_avatar_url(32)).path, images)

    def test_display_policy_matrix(self) -> None:
        for policy in ("public", "authenticated", "admins"):
            for viewer in (None, AnonymousUser(), self.user, self.target):
                with (
                    self.subTest(policy=policy, viewer=viewer),
                    override_settings(USER_PROFILE_VISIBILITY=policy),
                ):
                    accessible = (
                        policy == "public"
                        or viewer == self.target
                        or (
                            policy == "authenticated"
                            and viewer is not None
                            and viewer.is_authenticated
                        )
                    )
                    rendered = get_user_display(self.target, link=True, viewer=viewer)
                    self.assert_profile_display(rendered, accessible=accessible)
                    self.assertIn("&lt;Target &amp; Name&gt;", rendered)
                    self.assertNotIn("<Target & Name>", rendered)

    @override_settings(USER_PROFILE_VISIBILITY="admins")
    def test_global_permissions_and_self_access(self) -> None:
        for permission in ("user.view", "user.edit"):
            with (
                self.subTest(permission=permission),
                patch.object(
                    self.user,
                    "has_perm",
                    side_effect=lambda perm, expected=permission: perm == expected,
                ),
            ):
                self.assert_profile_display(
                    get_user_display(self.target, link=True, viewer=self.user),
                    accessible=True,
                )
        self.user.is_superuser = True
        self.assert_profile_display(
            get_user_display(self.target, link=True, viewer=self.user), accessible=True
        )

    @override_settings(USER_PROFILE_VISIBILITY="admins")
    def test_missing_user_disabled_icons_and_avatar_sizes(self) -> None:
        rendered = get_user_display(None, link=True)
        self.assertNotIn("href=", rendered)
        self.assertIn(get_fallback_avatar_url(32), rendered)
        for size in (24, 32, 80, 128):
            with self.subTest(size=size):
                self.assertEqual(
                    get_user_avatar_url(self.target, size, viewer=self.user),
                    get_fallback_avatar_url(size),
                )
        with override_settings(ENABLE_AVATARS=False):
            rendered = get_user_display(self.target, link=True, viewer=self.user)
            self.assertNotIn("<img", rendered)
            self.assertNotIn("href=", rendered)
            self.assertIn(self.target.username, rendered)

    @override_settings(USER_PROFILE_VISIBILITY="admins")
    def test_template_uses_request_not_displayed_user(self) -> None:
        template = Template("{% load user_display %}{% user_display user %}")
        for viewer, accessible in (
            (self.target, True),
            (self.user, False),
            (self.target, True),
        ):
            with self.subTest(viewer=viewer):
                self.assert_profile_display(
                    template.render(
                        Context(
                            {"request": self.request_for(viewer), "user": self.target}
                        )
                    ),
                    accessible=accessible,
                )
        self.assert_profile_display(
            template.render(Context({"user": self.target})), accessible=False
        )

    @override_settings(USER_PROFILE_VISIBILITY="admins")
    def test_user_cards_and_contributor_list(self) -> None:
        for viewer, accessible in ((self.user, False), (self.target, True)):
            request = self.request_for(viewer)
            with self.subTest(viewer=viewer):
                cards = render_to_string(
                    "snippets/user-list.html",
                    {"object_list": [self.target], "page_obj": None},
                    request=request,
                )
                self.assertIn(self.target.username, cards)
                if accessible:
                    self.assertIn(f'href="{self.target.get_absolute_url()}"', cards)
                    self.assertIn(
                        get_user_avatar_url(self.target, 128, viewer=viewer), cards
                    )
                else:
                    self.assertNotIn(self.target.get_absolute_url(), cards)
                    self.assertIn(get_fallback_avatar_url(128), cards)
                    self.assertIn('<div class="user-list-item">', cards)
                contributors = render_to_string(
                    "snippets/info-users.html",
                    {"user_list": [self.target], "user_title": "Contributors"},
                    request=request,
                )
                self.assert_profile_display(contributors, accessible=accessible)

    @override_settings(USER_PROFILE_VISIBILITY="admins")
    def test_management_row_uses_request_viewer(self) -> None:
        rendered = render_to_string(
            "trans/project-access-row.html",
            {"user": self.target, "object": self.project},
            request=self.request_for(self.user),
        )
        self.assertIn(self.target.username, rendered)
        self.assertNotIn(self.target.get_absolute_url(), rendered)

    def test_information_panel_preserves_viewer(self) -> None:
        self.project.instructions = f"Instructions for @{self.target.username}"
        self.project.all_admins = User.objects.filter(pk=self.target.pk)
        self.project.all_reviewers = User.objects.filter(pk=self.target.pk)
        self.component.agreement = f"Agreement with @{self.target.username}"
        self.component.inherit_agreement = False
        admin = User.objects.create_user("info-panel-admin", is_superuser=True)
        template = Template(
            "{% load translations metrics %}"
            "{% show_info project=project component=component "
            "stats=project.stats metrics=project|metrics %}"
        )
        for policy in ("public", "authenticated", "admins"):
            for viewer in (get_anonymous(), self.user, self.target, admin):
                with (
                    self.subTest(policy=policy, viewer=viewer),
                    override_settings(USER_PROFILE_VISIBILITY=policy),
                ):
                    rendered = template.render(
                        Context(
                            {
                                "user": viewer,
                                "project": self.project,
                                "component": self.component,
                            }
                        )
                    )
                    accessible = (
                        policy == "public"
                        or viewer in {self.target, admin}
                        or (policy == "authenticated" and viewer.is_authenticated)
                    )
                    self.assert_profile_display(rendered, accessible=accessible)
                    markdown = fromstring(rendered).find_class("markdown")
                    self.assertEqual(len(markdown), 2)
                    for content in markdown:
                        self.assertIn(
                            f"@{self.target.username}", content.text_content()
                        )
                        self.assertEqual(
                            self.target.get_absolute_url() in content.xpath(".//@href"),
                            accessible,
                        )

    def test_information_panel_contributor_links(self) -> None:
        template = Template(
            "{% load translations metrics %}"
            "{% show_info project=project component=component "
            "stats=project.stats metrics=project|metrics %}"
        )
        for component in (None, self.component):
            scope = component.full_slug if component else self.project.slug
            for mode in ("all", "scoped", "disabled"):
                for permission in (None, "user.view", "user.edit"):
                    with (
                        self.subTest(scope=scope, mode=mode, permission=permission),
                        override_settings(USER_DIRECTORY_VISIBILITY=mode),
                        patch.object(
                            self.user,
                            "has_perm",
                            side_effect=lambda name, _obj=None, expected=permission: (
                                name == expected
                            ),
                        ),
                    ):
                        rendered = template.render(
                            Context(
                                {
                                    "user": self.user,
                                    "project": self.project,
                                    "component": component,
                                }
                            )
                        )
                        queries = [
                            parse_qs(url.query)["q"][0].strip()
                            for href in fromstring(rendered).xpath(".//@href")
                            if (url := urlsplit(href)).path == reverse("user_list")
                            and url.query
                        ]
                        expected = (
                            [f"contributes:{scope}"]
                            if permission or mode in {"all", "scoped"}
                            else []
                        )
                        self.assertEqual(queries, expected)

    def test_information_panel_browse_all_users(self) -> None:
        Profile.objects.filter(user=self.target).update(translated=1)
        top_users = Profile.objects.filter(user=self.target).annotate(
            translated_width=Value(100)
        )
        template = Template(
            "{% load translations metrics %}"
            "{% show_info stats=project.stats metrics=project|metrics "
            "top_users=top_users total_translations=1 %}"
        )
        for mode in ("all", "scoped", "disabled"):
            for permission in (None, "user.view", "user.edit"):
                with (
                    self.subTest(mode=mode, permission=permission),
                    override_settings(USER_DIRECTORY_VISIBILITY=mode),
                    patch.object(
                        self.user,
                        "has_perm",
                        side_effect=lambda name, _obj=None, expected=permission: (
                            name == expected
                        ),
                    ),
                ):
                    rendered = template.render(
                        Context(
                            {
                                "user": self.user,
                                "project": self.project,
                                "top_users": top_users,
                            }
                        )
                    )
                    self.assertIn(self.target.username, rendered)
                    self.assertEqual(
                        reverse("user_list") in fromstring(rendered).xpath(".//@href"),
                        bool(permission) or mode == "all",
                    )

    @override_settings(USER_PROFILE_VISIBILITY="admins")
    def test_mentions_and_preview(self) -> None:
        text = f"@{self.target.username} مرحبا"
        for viewer, accessible in (
            (self.target, True),
            (self.user, False),
            (None, False),
        ):
            with self.subTest(viewer=viewer):
                rendered = render_markdown(text, viewer=viewer)
                self.assertIn(f"@{self.target.username}", rendered)
                self.assertIn("<bdi>", rendered)
                self.assertEqual("href=" in rendered, accessible)
                self.assertNotIn("<Target & Name>", rendered)
        preview = render_to_string(
            "js/markdown-preview.html",
            {"text": text},
            request=self.request_for(self.user),
        )
        self.assertIn(self.target.username, preview)
        self.assertNotIn(self.target.get_absolute_url(), preview)
        self.assertEqual(list(get_mention_users(text)), [self.target])

    def create_comment_change(self) -> Change:
        translation = self.component.translation_set.get(language__code="cs")
        return Change.objects.create(
            action=ActionEvents.COMMENT,
            user=self.target,
            author=self.target,
            unit=translation.unit_set.order_by("id")[0],
            details={"comment": f"@{self.target.username} مرحبا"},
        )

    def test_announcement_banner_mentions(self) -> None:
        admin = User.objects.create_user("display-admin", is_superuser=True)
        viewers = (get_anonymous(), self.user, self.target, admin)
        for scope, arguments in (
            ({}, ""),
            ({"project": self.project}, "project=project"),
            ({"component": self.component}, "component=component"),
        ):
            announcement = Announcement.objects.create(
                user=self.user, message=f"@{self.target.username} مرحبا", **scope
            )
            template = Template(
                "{% load translations %}{% announcements " + arguments + " %}"
            )
            for policy in ("public", "authenticated", "admins"):
                for viewer in viewers:
                    with (
                        self.subTest(scope=scope, policy=policy, viewer=viewer),
                        override_settings(USER_PROFILE_VISIBILITY=policy),
                    ):
                        rendered = template.render(Context({"user": viewer, **scope}))
                        self.assertIn(f"@{self.target.username}", rendered)
                        self.assertIn("<bdi>", rendered)
                        links = fromstring(rendered).xpath(".//@href")
                        accessible = (
                            policy == "public"
                            or viewer in {self.target, admin}
                            or (policy == "authenticated" and viewer.is_authenticated)
                        )
                        self.assertEqual(
                            self.target.get_absolute_url() in links, accessible
                        )
            announcement.delete()

    @override_settings(USER_PROFILE_VISIBILITY="admins")
    def test_history_and_digest(self) -> None:
        change = self.create_comment_change()
        for viewer, accessible in (
            (self.target, True),
            (self.user, False),
            (self.target, True),
        ):
            with self.subTest(viewer=viewer):
                rendered = render_to_string(
                    "snippets/last-changes-content.html",
                    format_last_changes_content([change], viewer),
                )
                self.assert_profile_display(rendered, accessible=accessible)
                self.assertIn(f"@{self.target.username}", rendered)
        digest = render_to_string(
            "mail/digest.html",
            {
                **NewAnnouncementNotificaton([]).get_context(changes=[change]),
                "user": self.target,
                "subject": "Test digest",
            },
            request=self.request_for(self.target),
        )
        self.assert_profile_display(digest, accessible=False)
        self.assertIn(f"@{self.target.username}", digest)

    def test_email_preview_and_feed_use_public_access(self) -> None:
        change = self.create_comment_change()
        for policy in ("public", "authenticated", "admins"):
            with (
                self.subTest(policy=policy),
                override_settings(USER_PROFILE_VISIBILITY=policy),
            ):
                email = render_to_string(
                    "mail/new_announcement.html",
                    {
                        **NewAnnouncementNotificaton([]).get_context(change),
                        "subject": "Test announcement",
                        "announcement": SimpleNamespace(
                            message=f"@{self.target.username}"
                        ),
                    },
                    request=self.request_for(self.target),
                )
                self.assert_profile_display(email, accessible=policy == "public")
                self.assertIn(f"@{self.target.username}", email)
                feed_author = BaseFeed().item_author_name(change)
                self.assertIn(self.target.username, feed_author)
                self.assertEqual("href=" in feed_author, policy == "public")

    @override_settings(USER_PROFILE_VISIBILITY="admins")
    def test_git_author(self) -> None:
        social = self.target.social_auth.create(
            provider="email", uid=self.target.email, id_key="email"
        )
        VerifiedEmail.objects.create(social=social, email=self.target.email)
        template = Template("{% load user_display %}{% user_commit_author commit %}")
        commit = {
            "author_email": self.target.email,
            "author_name": self.target.full_name,
        }
        for viewer, accessible in ((self.user, False), (self.target, True)):
            with self.subTest(viewer=viewer):
                rendered = template.render(
                    Context({"request": self.request_for(viewer), "commit": commit})
                )
                self.assert_profile_display(rendered, accessible=accessible)
