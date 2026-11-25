# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

from celery.exceptions import Retry
from django.db import connection, transaction
from django.template import Context, Template
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from django.utils import timezone
from lxml.html import fromstring

from weblate.accounts.tests.visibility import VisibilityPermissions
from weblate.auth.data import SELECTION_ALL
from weblate.auth.models import (
    Group,
    Permission,
    Role,
    TeamMembership,
    User,
    get_anonymous,
)
from weblate.lang.models import Language
from weblate.metrics.aggregation import history, translation_history
from weblate.metrics.contributors import contributor_ranking, load_ranked_contributors
from weblate.metrics.models import ContributorCollection, ContributorCount, Metric
from weblate.metrics.tasks import collect_translation_metrics
from weblate.trans.actions import ActionEvents
from weblate.trans.models import (
    Category,
    Change,
    Component,
    ComponentLink,
    Project,
    Translation,
)
from weblate.trans.models.change import dt_as_day_range
from weblate.trans.tests.test_views import FixtureTestCase
from weblate.utils.lock import AdvisoryLock, WeblateLockTimeoutError
from weblate.utils.stats import CategoryLanguage, ProjectLanguage, WorkspaceLanguage
from weblate.workspaces.models import Workspace

if TYPE_CHECKING:
    from datetime import date

    from weblate.metrics.contributors import ContributorScope


class ContributorRankingTest(FixtureTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.translation = self.component.translation_set.get(language__code="cs")
        self.editor = User.objects.create_user(
            "ranked-editor", "ranked-editor@example.org"
        )
        self.commenter = User.objects.create_user(
            "ranked-commenter", "ranked-commenter@example.org"
        )
        self.outsider = User.objects.create_user(
            "ranked-outsider", "ranked-outsider@example.org"
        )
        Change.objects.all().delete()

    def summary(self, user: User) -> tuple[int, int]:
        return ContributorCount.objects.values_list("contributions", "edits").get(
            translation=self.translation, user=user
        )

    @staticmethod
    def refresh_rankings(days: int = 0) -> None:
        collect_translation_metrics(
            (timezone.localdate() + timedelta(days=days)).isoformat()
        )

    def test_daily_rebuild_reflects_history_changes_and_deletions(self) -> None:
        change = Change.objects.create(
            translation=self.translation, user=self.editor, action=ActionEvents.NEW
        )
        Change.objects.bulk_create(
            [
                Change(
                    translation=self.translation,
                    user=self.editor,
                    action=ActionEvents.UPLOAD,
                ),
                Change(
                    translation=self.translation,
                    user=self.commenter,
                    action=ActionEvents.COMMENT,
                ),
                Change(
                    translation=self.translation,
                    user=self.outsider,
                    action=ActionEvents.COMMIT,
                ),
            ]
        )
        self.assertFalse(ContributorCount.objects.exists())
        self.refresh_rankings()
        self.assertTrue(ContributorCollection.is_ready())
        self.assertEqual(self.summary(self.editor), (2, 2))
        self.assertEqual(self.summary(self.commenter), (1, 0))
        self.assertFalse(ContributorCount.objects.filter(user=self.outsider).exists())

        changed = Change.objects.filter(pk=change.pk)
        with transaction.atomic():
            changed.update(user=self.commenter, action=ActionEvents.SUGGESTION)
            transaction.set_rollback(True)
        self.refresh_rankings(days=1)
        self.assertEqual(self.summary(self.editor), (2, 2))

        changed.update(user=self.commenter, action=ActionEvents.SUGGESTION)
        self.assertEqual(self.summary(self.editor), (2, 2))
        self.refresh_rankings(days=2)
        self.refresh_rankings(days=2)
        self.assertEqual(self.summary(self.editor), (1, 1))
        self.assertEqual(self.summary(self.commenter), (2, 0))
        Change.objects.filter(user=self.commenter).delete()
        self.refresh_rankings(days=3)
        self.assertFalse(ContributorCount.objects.filter(user=self.commenter).exists())

    def test_collection_retries_when_lock_is_busy(self) -> None:
        error = WeblateLockTimeoutError("busy", lock=AdvisoryLock(0, scope="test"))
        with (
            patch.object(AdvisoryLock, "__enter__", side_effect=error),
            patch.object(
                collect_translation_metrics, "retry", side_effect=Retry
            ) as retry,
            self.assertRaises(Retry),
        ):
            self.refresh_rankings()
        self.assertIs(retry.call_args.kwargs["exc"], error)
        self.assertFalse(ContributorCollection.is_ready())

    def test_unknown_ranking_scope_fails_closed(self) -> None:
        with self.assertRaisesMessage(TypeError, "Unsupported contributor scope"):
            contributor_ranking(self.user, cast("ContributorScope", object()))

    def test_combined_history_matches_existing_metrics(self) -> None:
        day = timezone.localdate()
        inactive = User.objects.create_user(
            "ranked-inactive", "ranked-inactive@example.org", is_active=False
        )
        bot = User.objects.create_user(
            "ranked-bot", "ranked-bot@example.org", is_bot=True
        )
        for user, action, days_ago in (
            (self.editor, ActionEvents.NEW, 30),
            (self.editor, ActionEvents.CHANGE, 1),
            (self.commenter, ActionEvents.SUGGESTION, 31),
            (self.outsider, ActionEvents.COMMIT, 1),
            (inactive, ActionEvents.NEW, 1),
            (bot, ActionEvents.NEW, 1),
            (get_anonymous(), ActionEvents.COMMENT, 1),
        ):
            change = Change.objects.create(
                translation=self.translation, user=user, action=action
            )
            timestamp, _end = dt_as_day_range(day - timedelta(days=days_ago))
            Change.objects.filter(pk=change.pk).update(timestamp=timestamp)
        ids = [self.translation.pk]
        baseline = history("translation", ids, day, connection.alias)
        self.assertEqual(
            baseline[self.translation.pk],
            {"changes": 5, "contributors": 2, "contributors_total": 3},
        )
        self.assertEqual(translation_history(ids, day, connection.alias), baseline)
        self.assertEqual(self.summary(self.editor), (2, 2))
        self.assertEqual(self.summary(self.commenter), (1, 0))
        self.assertFalse(ContributorCount.objects.filter(user=self.outsider).exists())

    def test_interrupted_collection_retries_from_last_committed_batch(self) -> None:
        translation_ids = list(
            Translation.objects.order_by("pk").values_list("pk", flat=True)
        )
        first, second, *_rest = translation_ids
        for translation_id in (first, second):
            Change.objects.create(
                translation_id=translation_id, user=self.editor, action=ActionEvents.NEW
            )
        collect_batch = Metric.objects.collect_batch
        attempted = []

        def interrupt(
            batch: tuple[Translation, ...],
            day: date,
            *,
            refresh_contributors: bool,
        ) -> None:
            attempted.append(batch[0].pk)
            collect_batch(batch, day, refresh_contributors=refresh_contributors)
            if len(attempted) == 2:
                msg = "Interrupted translation metrics"
                raise RuntimeError(msg)

        with patch("weblate.metrics.tasks.BATCH_SIZE", 1):
            with (
                patch.object(Metric.objects, "collect_batch", side_effect=interrupt),
                self.assertRaisesMessage(
                    RuntimeError, "Interrupted translation metrics"
                ),
            ):
                self.refresh_rankings()
            self.assertEqual(attempted, [first, second])
            state = ContributorCollection.objects.get(pk=1)
            self.assertEqual(state.cursor, first)
            self.assertFalse(ContributorCollection.is_ready())
            self.assertFalse(
                ContributorCount.objects.filter(translation_id=second).exists()
            )
            with patch.object(
                Metric.objects, "collect_batch", wraps=collect_batch
            ) as collect:
                self.refresh_rankings()
            self.assertEqual(
                [call.args[0][0].pk for call in collect.call_args_list],
                translation_ids[1:],
            )
        self.assertTrue(ContributorCollection.is_ready())
        self.assertEqual(ContributorCount.objects.filter(user=self.editor).count(), 2)

    def test_scopes_and_directory_permissions(self) -> None:
        project = Project.objects.create(slug="ranking-project", name="Ranking project")
        (parent,) = Category.objects.bulk_create(
            [Category(project=project, slug="parent", name="Parent")]
        )
        (category,) = Category.objects.bulk_create(
            [Category(project=project, category=parent, slug="child", name="Child")]
        )
        ComponentLink.objects.create(
            project=project, category=category, component=self.component
        )
        for user, action in (
            (self.editor, ActionEvents.CHANGE),
            (self.commenter, ActionEvents.SUGGESTION),
        ):
            Change.objects.create(
                translation=self.translation, user=user, action=action
            )
        other = self.component.translation_set.exclude(
            language=self.translation.language
        )
        other_translation = other.get(language__code="en")
        Change.objects.create(
            translation=other_translation,
            user=self.outsider,
            action=ActionEvents.BULK_EDIT,
        )
        profile = User.objects.create_user("contributors", "contributors@example.org")
        self.assertEqual(resolve(profile.get_absolute_url()).url_name, "user_page")
        self.refresh_rankings()

        language = self.translation.language
        for scope in (
            self.project,
            ProjectLanguage(project, language),
            parent,
            CategoryLanguage(parent, language),
            CategoryLanguage(category, language),
            self.component,
            self.translation,
            language,
        ):
            with self.subTest(scope=scope):
                url = reverse("contributor_list", kwargs={"path": scope.get_url_path()})
                response = self.client.get(url)
                self.assertContains(response, self.editor.username)
                self.assertContains(response, self.commenter.username)
                counts = dict(response.context["object_list"])
                self.assertEqual(counts[self.editor.pk], 1)
                self.assertEqual(counts[self.commenter.pk], 0)
                if scope is self.translation or isinstance(
                    scope, (Language, ProjectLanguage, CategoryLanguage)
                ):
                    self.assertNotIn(self.outsider.pk, counts)

        with VisibilityPermissions(directory="scoped"):
            self.assertEqual(
                self.client.get(
                    reverse(
                        "contributor_list", kwargs={"path": language.get_url_path()}
                    )
                ).status_code,
                404,
            )
        self.assertEqual(self.client.get("/contributors/nonexistent/").status_code, 404)
        self.assertEqual(
            self.client.get(
                "/contributors/-/workspace/00000000-0000-0000-0000-000000000000/"
            ).status_code,
            404,
        )

    def test_shared_translation_requires_attribution_permission(self) -> None:
        project = Project.objects.create(slug="ranking-shared", name="Ranking shared")
        (category,) = Category.objects.bulk_create(
            [Category(project=project, slug="shared", name="Shared")]
        )
        ComponentLink.objects.create(
            project=project, category=category, component=self.component
        )
        Change.objects.create(
            translation=self.translation, user=self.editor, action=ActionEvents.CHANGE
        )
        self.refresh_rankings()
        self.assertEqual(
            list(contributor_ranking(self.user, category)), [(self.editor.pk, 1)]
        )
        self.project.access_control = Project.ACCESS_PRIVATE
        self.project.save(update_fields=["access_control"])
        self.outsider.clear_permissions_cache()
        self.assertEqual(list(contributor_ranking(self.outsider, category)), [])

    @VisibilityPermissions(directory="scoped")
    def test_workspace_rankings(self) -> None:
        workspace = Workspace.objects.create(name="Ranking workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        second_project = Project.objects.create(
            workspace=workspace, slug="ranking-workspace-second", name="Second project"
        )
        external = Project.objects.create(
            slug="ranking-external", name="External project"
        )
        language = self.translation.language
        linked, unlinked = Component.objects.bulk_create(
            [
                Component(
                    project=external, slug=slug, name=slug, source_language=language
                )
                for slug in ("linked", "unlinked")
            ]
        )
        ComponentLink.objects.bulk_create(
            [
                ComponentLink(component=linked, project=project)
                for project in (self.project, second_project)
            ]
        )
        linked_translation, unlinked_translation = Translation.objects.bulk_create(
            [
                Translation(
                    component=component, language=language, plural=language.plural
                )
                for component in (linked, unlinked)
            ]
        )
        other_language = self.component.translation_set.get(language__code="en")
        for translation, user in (
            (self.translation, self.editor),
            (other_language, self.editor),
            (linked_translation, self.commenter),
            (unlinked_translation, self.outsider),
        ):
            Change.objects.create(
                translation=translation, user=user, action=ActionEvents.CHANGE
            )

        language_scope = WorkspaceLanguage(workspace, language)
        scope_url = reverse(
            "contributor_list", kwargs={"path": language_scope.get_url_path()}
        )
        self.assertContains(
            self.client.get(language_scope.get_absolute_url()), scope_url
        )
        self.refresh_rankings()

        for scope, own_edits in ((workspace, 2), (language_scope, 1)):
            with self.subTest(scope=scope):
                url = reverse("contributor_list", kwargs={"path": scope.get_url_path()})
                response = self.client.get(url)
                self.assertEqual(
                    dict(response.context["object_list"]),
                    {self.editor.pk: own_edits, self.commenter.pk: 1},
                )
                overview = self.client.get(scope.get_absolute_url())
                self.assertContains(overview, "Most active translators")
                self.assertContains(overview, url)

        external.access_control = Project.ACCESS_PRIVATE
        external.save(update_fields=["access_control"])
        self.client.force_login(self.outsider)
        response = self.client.get(scope_url)
        self.assertEqual(list(response.context["object_list"]), [(self.editor.pk, 1)])
        hidden = Workspace.objects.create(name="Hidden ranking workspace")
        denied = self.client.get(
            reverse("contributor_list", kwargs={"path": hidden.get_url_path()})
        )
        self.assertEqual(denied.status_code, 404)
        self.assertIn("private", denied.headers["Cache-Control"])
        self.assertIn("no-store", denied.headers["Cache-Control"])

    def test_language_grants_filter_counts_before_aggregation(self) -> None:
        other_translation = self.component.translation_set.get(language__code="en")
        for translation, user in (
            (self.translation, self.editor),
            (other_translation, self.editor),
            (other_translation, self.commenter),
        ):
            Change.objects.create(
                translation=translation, user=user, action=ActionEvents.CHANGE
            )
        self.refresh_rankings()

        permission = Permission.objects.get(codename="contribution.view_author")
        for role in Role.objects.filter(permissions=permission):
            role.permissions.remove(permission)
        role = Role.objects.create(name="Ranking attribution")
        role.permissions.add(permission)
        group = Group.objects.create(
            name="Ranking attribution", language_selection=SELECTION_ALL
        )
        group.roles.add(role)
        group.components.add(self.component)
        self.user.groups.add(group)
        membership = TeamMembership.objects.get(user=self.user, group=group)
        membership.limit_languages.add(self.translation.language)
        self.user.clear_permissions_cache()
        self.assertEqual(
            list(contributor_ranking(self.user, self.project)), [(self.editor.pk, 1)]
        )
        group.roles.clear()
        self.user.clear_permissions_cache()
        self.assertEqual(list(contributor_ranking(self.user, self.project)), [])

    def test_dashboard_and_rendering_query_count(self) -> None:
        url = reverse("contributor_list", kwargs={"path": self.project.get_url_path()})
        response = self.client.get(url)
        self.assertContains(response, "Contributor rankings are being prepared.")
        breadcrumbs = fromstring(response.content).xpath(
            '//ol[@class="breadcrumb"]/li[@aria-current="page"]/text()'
        )
        self.assertEqual(breadcrumbs, ["Contributors"])
        users = (self.editor, self.commenter, self.outsider)
        for user in users:
            Change.objects.create(
                translation=self.translation, user=user, action=ActionEvents.CHANGE
            )
        self.refresh_rankings()
        self.assertContains(
            self.client.get(self.project.get_absolute_url()), "Most active translators"
        )
        self.assertContains(
            self.client.get(self.translation.language.get_absolute_url()),
            "Most active translators",
        )
        project_language = ProjectLanguage(self.project, self.translation.language)
        self.assertContains(
            self.client.get(project_language.get_absolute_url()),
            "Most active translators",
        )

        template = Template(
            "{% load user_display %}{% for row in contributors %}"
            "{% user_display row.user %}{% endfor %}"
        )
        ranking = contributor_ranking(self.user, self.translation)
        for size in (1, len(users)):
            with (
                self.subTest(size=size),
                CaptureQueriesContext(connection) as queries,
            ):
                contributors = load_ranked_contributors(ranking[:size])
                template.render(
                    Context({"contributors": contributors, "profile_viewer": self.user})
                )
            self.assertEqual(len(contributors), size)
            self.assertEqual(
                [query["sql"].count('"trans_change"') for query in queries], [0, 0]
            )

    def test_stable_pagination_and_hidden_accounts(self) -> None:
        self.refresh_rankings()
        users = User.objects.bulk_create(
            [User(username=f"rank-tie-{index}") for index in range(51)]
        )
        ContributorCount.objects.bulk_create(
            [
                ContributorCount(
                    translation=self.translation, user=user, contributions=1, edits=1
                )
                for user in users
            ]
        )
        for fields in ({"is_active": False}, {"is_bot": True}):
            user = User.objects.create(
                username=f"rank-hidden-{next(iter(fields))}", **fields
            )
            ContributorCount.objects.create(
                translation=self.translation, user=user, contributions=20, edits=20
            )

        url = reverse(
            "contributor_list", kwargs={"path": self.translation.get_url_path()}
        )
        self.client.force_login(self.outsider)
        with VisibilityPermissions(directory="all"):
            first_page = self.client.get(url)
            second_page = self.client.get(url, {"page": 2})
        self.assertEqual(
            list(first_page.context["object_list"]),
            [(user.pk, 1) for user in users[:50]],
        )
        self.assertEqual(list(second_page.context["object_list"]), [(users[50].pk, 1)])
