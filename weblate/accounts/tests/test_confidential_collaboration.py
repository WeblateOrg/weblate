# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Acceptance tests for the documented confidential collaboration configuration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, cast
from unittest.mock import patch
from uuid import uuid4

from django.core import mail
from django.test.utils import override_settings
from django.urls import reverse

from weblate.accounts.data import NotificationFrequency, NotificationScope
from weblate.accounts.models import Subscription
from weblate.accounts.notifications import NewCommentNotificaton
from weblate.accounts.tasks import send_mails
from weblate.accounts.visibility import can_view_contributor
from weblate.addons.models import Addon
from weblate.addons.webhooks import WebhookAddon
from weblate.api.serializers import (
    ChangeSerializer,
    CommentSerializer,
    SuggestionSerializer,
)
from weblate.auth.data import SELECTION_ALL
from weblate.auth.models import (
    Group,
    Permission,
    Role,
    TeamMembership,
    User,
    get_anonymous,
)
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Comment, Project, Report, Suggestion
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.trans.tests.utils import clear_users_cache, create_test_addon
from weblate.trans.views.reports import collect_report_data
from weblate.utils.state import STATE_APPROVED, STATE_TRANSLATED
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from django.core.mail import EmailMultiAlternatives

    from weblate.accounts.tasks import OutgoingEmail


class ConfidentialCollaborationTest(FixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.administrator = self.user
        self.translation = self.component.translation_set.get(language__code="cs")
        self.unit = self.translation.unit_set.get(source="Hello, world!\n")
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.translation_review = True
        self.project.save(update_fields=["access_control", "translation_review"])
        self.project.add_user(self.administrator, "Administration")
        for codename in ("contribution.view_author", "vcs.access"):
            permission = Permission.objects.get(codename=codename)
            for role in Role.objects.filter(permissions=permission).exclude(
                name="Administration"
            ):
                role.permissions.remove(permission)
        for name in ("Guests", "Users"):
            Group.objects.get(name=name).roles.remove(
                *Role.objects.filter(name__in=("Discover users", "View user profiles"))
            )

        self.translators = [
            User.objects.create_user(
                f"contractor-{index}",
                f"contractor-{index}@example.org",
                full_name=f"Confidential Translator {index}",
            )
            for index in (1, 2)
        ]
        team = Group.objects.create(
            name="Confidential reviewers", language_selection=SELECTION_ALL
        )
        team.projects.add(self.project)
        team.roles.add(Role.objects.get(name="Review strings"))
        for user in self.translators:
            user.groups.add(team, Group.objects.get(name="Users"))
            TeamMembership.objects.get(user=user, group=team).limit_languages.add(
                self.translation.language
            )
        for user in (*self.translators, self.administrator):
            user.profile.language = "en"
            user.profile.save(update_fields=["language"])
            user.profile.languages.add(self.translation.language)
        clear_users_cache()
        for user in (*self.translators, self.administrator, get_anonymous()):
            user.clear_permissions_cache()

    def test_translation_review_and_attribution(self) -> None:
        for actor in self.translators:
            self.assertTrue(actor.has_perm("unit.edit", self.unit))
            self.assertTrue(actor.has_perm("unit.review", self.unit))
            self.assertTrue(actor.has_perm("comment.add", self.unit))
            self.assertTrue(actor.has_perm("suggestion.add", self.unit))
            for permission in ("user.browse", "user.search", "user.profile"):
                self.assertFalse(actor.has_perm(permission))
            self.assertFalse(can_view_contributor(actor, self.unit))
            for permission in ("reports.view", "change.download", "vcs.access"):
                self.assertFalse(actor.has_perm(permission, self.translation))
            self.assertTrue(
                self.unit.translate(
                    actor, f"Translation {actor.pk}\n", STATE_TRANSLATED
                )
            )
            request = self.get_request(user=actor)
            comment = Comment.objects.add(
                request, self.unit, "A translation note", "translation"
            )
            suggestion, _result = Suggestion.objects.add(
                self.unit, [f"Suggested {actor.pk}\n"], request
            )
            if suggestion is None:
                self.fail("Suggestion was not created")
            change = self.unit.change_set.get(
                user=actor,
                target=f"Translation {actor.pk}\n",
            )
            for viewer in (*self.translators, self.administrator):
                with self.subTest(actor=actor.username, viewer=viewer.username):
                    request = self.get_request(user=viewer)
                    visible = viewer == self.administrator
                    context = {"request": request}
                    data = ChangeSerializer(change, context=context).data
                    self.assertEqual(data["user"] is not None, visible)
                    self.assertEqual(data["author"] is not None, visible)
                    self.assertEqual(
                        CommentSerializer(comment, context=context).data["user"]
                        is not None,
                        visible,
                    )
                    self.assertEqual(
                        SuggestionSerializer(suggestion, context=context).data["user"]
                        is not None,
                        visible,
                    )
                    self.client.force_login(viewer)
                    response = self.client.get(
                        reverse("api:change-detail", kwargs={"pk": change.pk})
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json()["user"] is not None, visible)
                    self.assertEqual(response.json()["author"] is not None, visible)
                    response = self.client.get(
                        self.translation.get_translate_url(),
                        {"checksum": self.unit.checksum},
                    )
                    self.assertEqual(response.status_code, 200)
                    if visible:
                        self.assertContains(response, actor.full_name)
                    elif viewer != actor:
                        self.assertNotContains(response, actor.full_name)
                        self.assertNotContains(response, actor.username)
                        self.assertNotContains(response, actor.email)
                        self.assertNotContains(response, actor.get_absolute_url())
                        profile = self.client.get(actor.get_absolute_url())
                        self.assertEqual(profile.status_code, 404)
            reviewer = next(user for user in self.translators if user != actor)
            suggestion.accept(self.get_request(user=reviewer), state=STATE_APPROVED)
            self.unit.refresh_from_db()
            self.assertEqual(self.unit.target, f"Suggested {actor.pk}\n")
            self.assertEqual(self.unit.state, STATE_APPROVED)
            change.refresh_from_db()
            self.assertEqual(change.user, actor)
            self.assertEqual(change.author, actor)

    def test_scoped_autocomplete(self) -> None:
        contributor = self.translators[1]
        self.unit.translate(
            contributor, "Autocomplete contribution\n", STATE_TRANSLATED
        )
        directory = Role.objects.get(name="Discover users")
        for viewer in (self.translators[0], self.administrator):
            for browse in (False, True):
                with self.subTest(viewer=viewer.username, browse=browse):
                    users = Group.objects.get(name="Users")
                    if browse:
                        users.roles.add(directory)
                    else:
                        users.roles.remove(directory)
                    viewer.clear_permissions_cache()
                    self.client.force_login(viewer)
                    for scope in (
                        {"unit": self.unit.pk},
                        {"q": f"contributes:{self.component.full_slug}"},
                        {"q": f"contributes:{self.project.slug}"},
                    ):
                        response = self.client.get(
                            reverse("api:user-list"),
                            {
                                "username": contributor.username,
                                "is_active": "1",
                                **scope,
                            },
                        )
                        self.assertEqual(response.status_code, 200)
                        names = [row["username"] for row in response.json()["results"]]
                        self.assertEqual(
                            contributor.username in names, viewer == self.administrator
                        )
                    response = self.client.get(self.component.get_absolute_url())
                    self.assertContains(
                        response,
                        f'data-contributor-search-query="contributes:{self.component.full_slug}"',
                    )
                    response = self.client.get(
                        reverse(
                            "changes", kwargs={"path": self.component.get_url_path()}
                        )
                    )
                    self.assertContains(response, 'data-contributor-autocomplete="1"')
                    for unit_id in ("invalid", 999999999):
                        response = self.client.get(
                            reverse("api:user-list"),
                            {"username": contributor.username, "unit": unit_id},
                        )
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.json()["results"], [])

        # A language-limited attribution grant restores only that language's mentions.
        Role.objects.get(name="Review strings").permissions.add(
            Permission.objects.get(codename="contribution.view_author")
        )
        viewer = self.translators[0]
        viewer.clear_permissions_cache()
        self.client.force_login(viewer)
        for unit, visible in (
            (self.unit, True),
            (
                self.component.source_translation.unit_set.get(source=self.unit.source),
                False,
            ),
        ):
            response = self.client.get(
                reverse("api:user-list"),
                {"username": contributor.username, "unit": unit.pk},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(bool(response.json()["results"]), visible)

    @override_settings(RATELIMIT_NOTIFICATION_LIMITS=[])
    def test_notifications_use_recipient_permissions(self) -> None:
        for user in (*self.translators, self.administrator):
            Subscription.objects.filter(
                user=user, notification="NewCommentNotificaton"
            ).delete()
            Subscription.objects.create(
                user=user,
                notification="NewCommentNotificaton",
                scope=NotificationScope.SCOPE_PROJECT,
                project=self.project,
                frequency=NotificationFrequency.FREQ_INSTANT,
            )
        for actor in self.translators:
            comment = Comment.objects.add(
                self.get_request(user=actor),
                self.unit,
                "Confidential workflow note",
                "translation",
            )
            change = self.unit.change_set.get(
                comment=comment, action=ActionEvents.COMMENT
            )
            outgoing: list[OutgoingEmail] = []
            NewCommentNotificaton(outgoing).notify_immediate(change)
            send_mails(outgoing)
            messages = {message.to[0]: message for message in mail.outbox}
            recipient = next(user for user in self.translators if user != actor)
            self.assertIn(recipient.email, messages)
            self.assertIn(self.administrator.email, messages)
            for user in (recipient, self.administrator):
                email = user.email
                if email is None:
                    self.fail("Notification recipient has no e-mail address")
                message = cast("EmailMultiAlternatives", messages[email])
                content = (
                    str(message.extra_headers)
                    + message.body
                    + str(message.alternatives)
                )
                if user == self.administrator:
                    self.assertIn(actor.full_name, content)
                else:
                    for identity in (
                        actor.username,
                        actor.full_name,
                        actor.email,
                        actor.get_absolute_url(),
                    ):
                        self.assertNotIn(identity, content)
            mail.outbox.clear()

    def test_trusted_disclosure_routes_are_scoped(self) -> None:
        workspace = Workspace.objects.create(name="Confidential workspace")
        other_workspace = Workspace.objects.create(name="Unrelated workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        other = Project.objects.create(
            name="Other confidential project",
            slug="other-confidential",
            access_control=Project.ACCESS_PRIVATE,
            workspace=other_workspace,
        )
        reports = [
            Report.objects.create(
                creator=self.administrator,
                project=project,
                kind=Report.Kind.CREDITS,
                parameters={"own_data": False},
                data=[
                    {
                        "Czech": [
                            {
                                "username": self.translators[1].username,
                                "full_name": self.translators[1].full_name,
                                "email": self.translators[1].email,
                                "change_count": 1,
                            }
                        ]
                    }
                ],
            )
            for project in (self.project, other)
        ]
        addons = {
            project.pk: create_test_addon(
                acting_user=self.administrator, project=project, name=WebhookAddon.name
            )
            for project in (self.project, other)
        }
        team = Group.objects.create(
            name="Scoped workspace operator", defining_workspace=workspace
        )
        team.roles.add(Role.objects.get(name="Workspace administration"))
        self.administrator.groups.add(team)
        self.administrator.clear_permissions_cache()
        workspace_reports = [
            Report.objects.create(
                creator=self.administrator,
                workspace=scope,
                kind=Report.Kind.CREDITS,
                parameters={"own_data": False},
                data=[],
            )
            for scope in (workspace, other_workspace)
        ]
        for viewer in (self.translators[0], self.administrator):
            self.client.force_login(viewer)
            for report in workspace_reports:
                allowed = (
                    viewer == self.administrator and report.workspace_id == workspace.pk
                )
                with self.subTest(
                    viewer=viewer.username, workspace=report.workspace_id
                ):
                    for route in ("report", "api:report-detail", "api:report-json"):
                        response = self.client.get(
                            reverse(route, kwargs={"pk": report.pk})
                        )
                        self.assertEqual(response.status_code, 200 if allowed else 404)
            for project, report in zip((self.project, other), reports, strict=True):
                allowed = viewer == self.administrator and project == self.project
                with self.subTest(viewer=viewer.username, project=project.slug):
                    for route in ("report", "api:report-detail", "api:report-json"):
                        response = self.client.get(
                            reverse(route, kwargs={"pk": report.pk})
                        )
                        self.assertEqual(response.status_code, 200 if allowed else 404)
                    for route, kwargs in (
                        ("changes-csv", {"path": project.get_url_path()}),
                        ("manage-access", {"project": project.slug}),
                        ("addons", {"path": project.get_url_path()}),
                        ("addon-detail", {"pk": addons[project.pk].pk}),
                        ("addon-logs", {"pk": addons[project.pk].pk}),
                        ("workspace-access", {"pk": project.workspace_id}),
                    ):
                        response = self.client.get(reverse(route, kwargs=kwargs))
                        if allowed:
                            self.assertEqual(response.status_code, 200)
                        else:
                            self.assertIn(response.status_code, (403, 404))
        own = Report.objects.create(
            creator=self.translators[0],
            project=self.project,
            kind=Report.Kind.CREDITS,
            parameters={"own_data": True},
            data=[],
        )
        self.assertTrue(own.can_access(self.translators[0]))
        self.assertFalse(own.can_access(self.translators[1]))
        self.unit.translate(
            self.translators[1], "Trusted integration\n", STATE_TRANSLATED
        )
        change = self.unit.change_set.get(target="Trusted integration\n")
        payload = WebhookAddon(Addon()).build_webhook_payload(change)
        self.assertEqual(payload["user"], self.translators[1].username)

    def test_report_generation_respects_scope_and_independent_permissions(self) -> None:
        user = self.translators[0]
        self.client.force_login(user)
        now = datetime.now(tz=UTC)
        parameters = {
            "kind": Report.Kind.CREDITS,
            "project": self.project.slug,
            "start": (now - timedelta(days=1)).isoformat(),
            "end": now.isoformat(),
        }
        # Mock only background scheduling; permission decisions use the actual roles.
        with patch("weblate.api.views.generate_report.delay") as generate:
            generate.return_value.id = str(uuid4())
            response = self.client.post(
                reverse("api:report-list"), parameters, content_type="application/json"
            )
            self.assertEqual(response.status_code, 202)
            self.assertTrue(generate.call_args.kwargs["parameters"]["own_data"])
            generate.reset_mock()
            response = self.client.post(
                reverse("api:report-list"),
                {**parameters, "kind": Report.Kind.TRANSLATOR_WORK},
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 403)
            generate.assert_not_called()

            role = Role.objects.create(name="Confidential report operator")
            role.permissions.set(
                Permission.objects.filter(
                    codename__in=("reports.view", "change.download")
                )
            )
            group = Group.objects.create(name="Confidential report operators")
            group.roles.add(role)
            group.projects.add(self.project)
            user.groups.add(group)
            user.clear_permissions_cache()
            self.assertFalse(can_view_contributor(user, self.unit))
            response = self.client.post(
                reverse("api:report-list"), parameters, content_type="application/json"
            )
            self.assertEqual(response.status_code, 202)
            self.assertFalse(generate.call_args.kwargs["parameters"]["own_data"])
            generate.reset_mock()
            other = Project.objects.create(
                name="Unrelated reports",
                slug="unrelated-reports",
                access_control=Project.ACCESS_PRIVATE,
            )
            response = self.client.post(
                reverse("api:report-list"),
                {**parameters, "project": other.slug},
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 400)
            generate.assert_not_called()
            parameters.pop("project")
            workspace = Workspace.objects.create(name="Unrelated report workspace")
            response = self.client.post(
                reverse("api:report-list"),
                {**parameters, "workspace": str(workspace.pk)},
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 400)
            generate.assert_not_called()

        actor = self.translators[1]
        self.unit.translate(actor, "Reported contribution\n", STATE_TRANSLATED)
        response = self.client.get(
            reverse("changes-csv", kwargs={"path": self.project.get_url_path()})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, actor.username)

    def test_own_data_report_contains_only_the_creator(self) -> None:
        for user in self.translators:
            self.unit.translate(
                user, f"Report contribution {user.pk}\n", STATE_TRANSLATED
            )
        now = datetime.now(tz=UTC)
        for own_data in (True, False):
            with self.subTest(own_data=own_data):
                data = collect_report_data(
                    Report.Kind.CREDITS,
                    {
                        "start": (now - timedelta(days=1)).isoformat(),
                        "end": (now + timedelta(days=1)).isoformat(),
                        "own_data": own_data,
                    },
                    self.translators[0],
                    self.project,
                )
                names = {
                    row["username"]
                    for language in data
                    for rows in language.values()
                    for row in rows
                }
                self.assertEqual(
                    names,
                    {
                        user.username
                        for user in (
                            self.translators[:1] if own_data else self.translators
                        )
                    },
                )
