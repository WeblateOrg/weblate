# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from weblate.auth.models import Group
from weblate.trans.models import Project, Report
from weblate.trans.tasks import cleanup_reports, generate_report
from weblate.trans.tests.test_reports import BaseReportsTest
from weblate.trans.tests.utils import create_another_user
from weblate.workspaces.models import Workspace


class StoredReportsTest(BaseReportsTest):
    def test_filter_access_preserves_queryset(self) -> None:
        other_user = create_another_user("-reports")
        self.user.is_superuser = False
        self.user.save(update_fields=["is_superuser"])
        own_report = Report.objects.create(
            creator=self.user,
            kind=Report.Kind.CREDITS,
            parameters={"own_data": True, "period": "own"},
            data={"payload": "own"},
        )
        Report.objects.create(
            creator=other_user,
            kind=Report.Kind.CREDITS,
            parameters={"period": "other"},
            data={"payload": "other"},
        )

        with patch.object(
            Report,
            "can_access",
            side_effect=AssertionError("Reports must be filtered in the database"),
        ):
            reports = (
                Report.objects.select_related("creator")
                .metadata()
                .filter_access(self.user)
            )

        with self.assertNumQueries(1):
            result = list(reports)
            self.assertEqual(result[0].creator.username, self.user.username)

        self.assertEqual(result, [own_report])
        self.assertEqual(result[0].get_deferred_fields(), {"data", "parameters"})

    def test_creator_access_tracks_current_report_permission(self) -> None:
        self.user.is_superuser = False
        self.user.save(update_fields=["is_superuser"])
        managers = Group.objects.get(name="Managers")
        self.user.groups.add(managers)
        self.user.clear_permissions_cache()
        report = Report.objects.create(
            creator=self.user,
            kind=Report.Kind.CREDITS,
            parameters={"own_data": False},
            component=self.component,
        )
        own_report = Report.objects.create(
            creator=self.user,
            kind=Report.Kind.CREDITS,
            parameters={"own_data": True},
            component=self.component,
        )
        self.assertTrue(self.user.has_perm("reports.view", self.component))

        self.user.groups.remove(managers)
        self.user.clear_permissions_cache()

        self.assertTrue(self.user.can_access_component(self.component))
        self.assertFalse(self.user.has_perm("reports.view", self.component))
        self.assertFalse(report.can_access(self.user))
        self.assertTrue(own_report.can_access(self.user))
        self.assertEqual(
            list(Report.objects.filter_access(self.user)),
            [own_report],
        )

    def test_filter_access_with_reports_permission(self) -> None:
        other_user = create_another_user("-reports")
        self.user.is_superuser = False
        self.user.save(update_fields=["is_superuser"])
        self.user.groups.add(Group.objects.get(name="Managers"))
        self.user.clear_permissions_cache()
        report = Report.objects.create(
            creator=other_user,
            kind=Report.Kind.CREDITS,
            component=self.component,
        )

        self.assertTrue(report.can_access(self.user))
        self.assertEqual(list(Report.objects.filter_access(self.user)), [report])

    def test_filter_access_with_workspace_reports_permission(self) -> None:
        other_user = create_another_user("-workspace-reports")
        self.user.is_superuser = False
        self.user.save(update_fields=["is_superuser"])
        workspace = Workspace.objects.create(name="Accessible reporting workspace")
        workspace.add_owner(self.user)
        self.user.clear_permissions_cache()
        report = Report.objects.create(
            creator=other_user,
            kind=Report.Kind.CREDITS,
            workspace=workspace,
        )

        self.assertTrue(self.user.has_perm("reports.view", workspace))
        self.assertTrue(report.can_access(self.user))
        self.assertEqual(list(Report.objects.filter_access(self.user)), [report])

    def test_api_report_list_pagination(self) -> None:
        Report.objects.bulk_create(
            [
                Report(creator=self.user, kind=Report.Kind.CREDITS)
                for _index in range(51)
            ]
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("api:report-list"), {"page_size": 10})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 51)
        self.assertEqual(len(response.json()["results"]), 10)
        self.assertIsNotNone(response.json()["next"])

    def test_web_report_list_pagination(self) -> None:
        Report.objects.bulk_create(
            [
                Report(
                    creator=self.user,
                    kind=Report.Kind.CREDITS,
                    component=self.component,
                )
                for _index in range(21)
            ]
        )
        self.client.force_login(self.user)

        response = self.client.get(self.component.get_absolute_url())
        report_page = response.context["generated_reports"]

        self.assertEqual(len(report_page), 20)
        self.assertTrue(report_page.has_next())

    def test_generate_and_render_report(self) -> None:
        now = timezone.now()
        self.add_change()
        result = generate_report(
            kind=Report.Kind.CREDITS,
            parameters={
                "start": (now - timedelta(days=1)).isoformat(),
                "end": (now + timedelta(days=1)).isoformat(),
                "language": "",
                "sort_by": "count",
                "sort_order": "descending",
                "own_data": False,
            },
            user_id=self.user.pk,
            scope_type="component",
            scope_id=str(self.component.pk),
        )
        report = Report.objects.get()
        self.assertEqual(result["url"], reverse("api:report-detail", args=[report.pk]))

        self.client.force_login(self.user)
        detail = self.client.get(reverse("api:report-detail", args=[report.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["data"], report.data)
        raw = self.client.get(reverse("api:report-json", args=[report.pk]))
        self.assertEqual(raw.status_code, 200)
        self.assertEqual(raw.json(), report.data)
        self.assertEqual(raw.headers["Content-Type"], "application/json")

        html = self.client.get(reverse("api:report-html", args=[report.pk]))
        self.assertEqual(html.status_code, 200)
        self.assertEqual(html.headers["Content-Type"], "text/html; charset=utf-8")

        rst = self.client.get(reverse("api:report-rst", args=[report.pk]))
        self.assertEqual(rst.status_code, 200)
        self.assertEqual(rst.headers["Content-Type"], "text/plain; charset=utf-8")
        for response in (raw, html, rst):
            self.assertIn("attachment;", response.headers["Content-Disposition"])

        web = self.client.get(reverse("report", args=[report.pk]))
        self.assertEqual(web.status_code, 200)
        self.assertContains(web, "Download JSON")
        self.assertContains(web, self.user.username)
        self.assertContains(
            web,
            date_format(timezone.localtime(report.created), "DATETIME_FORMAT"),
        )
        self.assertContains(web, self.project.get_absolute_url())
        self.assertContains(web, self.component.get_absolute_url())
        self.assertContains(web, html.content.decode())
        content = web.content.decode()
        self.assertLess(
            content.index('id="report-downloads"'),
            content.index('id="report-content"'),
        )

    def test_web_generation_redirects_to_stored_report(self) -> None:
        self.client.force_login(self.user)
        self.add_change()
        response = self.client.post(
            reverse("credits", kwargs={"path": self.component.get_url_path()}),
            {
                "period": "01/01/2000 - 01/01/2100",
                "sort_by": "count",
                "sort_order": "descending",
            },
        )
        report = Report.objects.get()
        self.assertRedirects(
            response,
            reverse("report", args=[report.pk]),
            fetch_redirect_response=False,
        )

        self.client.logout()
        response = self.client.get(self.component.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Past reports")

    def test_translator_work_report(self) -> None:
        now = timezone.now()
        generate_report(
            kind=Report.Kind.TRANSLATOR_WORK,
            parameters={
                "start": (now - timedelta(days=1)).isoformat(),
                "end": (now + timedelta(days=1)).isoformat(),
                "language": "",
                "min_changes": 0,
                "max_changes": 1000,
                "max_words": 10000,
                "own_data": False,
            },
            user_id=self.user.pk,
            scope_type="project",
            scope_id=str(self.project.pk),
        )
        report = Report.objects.get()
        self.assertEqual(report.kind, Report.Kind.TRANSLATOR_WORK)
        self.assertIn("metrics", report.data)
        self.assertEqual(
            report.data["filters"]["actions"],
            ["change", "new", "accept"],
        )

    def test_translator_work_excludes_inaccessible_components(self) -> None:
        self.add_change()
        self.component.restricted = True
        self.component.save(update_fields=["restricted"])
        self.user.is_superuser = False
        self.user.save(update_fields=["is_superuser"])
        self.user.groups.add(Group.objects.get(name="Managers"))
        self.user.clear_permissions_cache()
        self.assertTrue(self.user.has_perm("reports.view", self.project))
        self.assertFalse(self.user.can_access_component(self.component))
        now = timezone.now()

        generate_report(
            kind=Report.Kind.TRANSLATOR_WORK,
            parameters={
                "start": (now - timedelta(days=1)).isoformat(),
                "end": (now + timedelta(days=1)).isoformat(),
                "language": "",
                "min_changes": 0,
                "max_changes": 1000,
                "max_words": 10000,
                "own_data": False,
            },
            user_id=self.user.pk,
            scope_type="project",
            scope_id=str(self.project.pk),
        )

        self.assertEqual(Report.objects.get().data["user_days"]["included"], 0)

    def test_workspace_collection(self) -> None:
        workspace = Workspace.objects.create(name="Reporting workspace")
        self.project.workspace = workspace
        self.project.save(update_fields=["workspace"])
        now = timezone.now()
        generate_report(
            kind=Report.Kind.CONTRIBUTOR_STATS,
            parameters={
                "start": (now - timedelta(days=1)).isoformat(),
                "end": (now + timedelta(days=1)).isoformat(),
                "language": "",
                "sort_by": "count",
                "sort_order": "descending",
                "counting_mode": "unique",
                "own_data": False,
            },
            user_id=self.user.pk,
            scope_type="workspace",
            scope_id=str(workspace.pk),
        )
        self.assertEqual(Report.objects.get().workspace, workspace)
        self.client.force_login(self.user)
        response = self.client.get(workspace.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Translator work analysis")

    @override_settings(REPORT_EXPIRY=30)
    def test_cleanup_uses_current_setting(self) -> None:
        report = Report.objects.create(
            creator=self.user,
            kind=Report.Kind.CREDITS,
            parameters={},
            data=[],
        )
        Report.objects.filter(pk=report.pk).update(
            created=timezone.now() - timedelta(days=31)
        )
        cleanup_reports()
        self.assertFalse(Report.objects.filter(pk=report.pk).exists())

    @patch("weblate.api.views.generate_report.delay")
    def test_scoped_api_schedules_report(self, mocked_delay) -> None:
        mocked_delay.return_value = SimpleNamespace(id="report-task")
        self.client.force_login(self.user)
        now = timezone.now()
        response = self.client.post(
            reverse(
                "api:component-reports",
                kwargs={
                    "project__slug": self.project.slug,
                    "slug": self.component.slug,
                },
            ),
            {
                "kind": Report.Kind.CREDITS,
                "start": (now - timedelta(days=1)).isoformat(),
                "end": now.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(mocked_delay.call_args.kwargs["scope_type"], "component")
        self.assertEqual(
            mocked_delay.call_args.kwargs["scope_id"], str(self.component.pk)
        )

        response = self.client.post(
            reverse(
                "api:component-reports",
                kwargs={
                    "project__slug": self.project.slug,
                    "slug": self.component.slug,
                },
            ),
            {
                "kind": Report.Kind.CREDITS,
                "project": self.project.slug,
                "start": (now - timedelta(days=1)).isoformat(),
                "end": now.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            reverse("api:project-reports", args=[self.project.slug]),
            {
                "kind": Report.Kind.CREDITS,
                "start": (now - timedelta(days=1)).isoformat(),
                "end": now.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(mocked_delay.call_args.kwargs["scope_type"], "project")

        category = self.create_category(project=self.project)
        response = self.client.post(
            reverse("api:category-reports", args=[category.pk]),
            {
                "kind": Report.Kind.CREDITS,
                "start": (now - timedelta(days=1)).isoformat(),
                "end": now.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(mocked_delay.call_args.kwargs["scope_type"], "category")

        workspace = Workspace.objects.create(name="API reporting workspace")
        response = self.client.post(
            reverse("api:report-list"),
            {
                "kind": Report.Kind.CREDITS,
                "workspace": workspace.pk,
                "start": (now - timedelta(days=1)).isoformat(),
                "end": now.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(mocked_delay.call_args.kwargs["scope_type"], "workspace")

    @patch("weblate.api.views.generate_report.delay")
    def test_api_rejects_invalid_cost_query(self, mocked_delay) -> None:
        self.client.force_login(self.user)
        response = self.client.post(
            reverse(
                "api:component-reports",
                kwargs={
                    "project__slug": self.project.slug,
                    "slug": self.component.slug,
                },
            ),
            {"kind": Report.Kind.COST_ESTIMATE, "q": "state:["},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"][0]["attr"], "q")
        mocked_delay.assert_not_called()

    @patch("weblate.api.views.generate_report.delay")
    def test_api_rejects_invalid_component_scope(self, mocked_delay) -> None:
        self.client.force_login(self.user)
        now = timezone.now()
        response = self.client.post(
            reverse("api:report-list"),
            {
                "kind": Report.Kind.CREDITS,
                "component": "invalid",
                "start": (now - timedelta(days=1)).isoformat(),
                "end": now.isoformat(),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["errors"][0]["attr"], "component")
        mocked_delay.assert_not_called()

    @patch("weblate.api.views.generate_report.delay")
    def test_api_hides_inaccessible_project_scope(self, mocked_delay) -> None:
        private_project = self.create_project(
            name="Private report project",
            slug="private-report-project",
            access_control=Project.ACCESS_PRIVATE,
        )
        self.user.is_superuser = False
        self.user.save(update_fields=["is_superuser"])
        self.user.clear_permissions_cache()
        self.client.force_login(self.user)
        now = timezone.now()
        responses = []

        for project in (private_project.slug, "missing-report-project"):
            response = self.client.post(
                reverse("api:report-list"),
                {
                    "kind": Report.Kind.CREDITS,
                    "project": project,
                    "start": (now - timedelta(days=1)).isoformat(),
                    "end": now.isoformat(),
                },
            )
            self.assertEqual(response.status_code, 400)
            responses.append(response.json())

        self.assertEqual(responses[0], responses[1])
        mocked_delay.assert_not_called()

    def test_api_rejects_invalid_report_filters(self) -> None:
        self.client.force_login(self.user)

        for field, value in (
            ("workspace", "invalid"),
            ("category", "invalid"),
            ("component", "invalid"),
        ):
            with self.subTest(field=field):
                response = self.client.get(
                    reverse("api:report-list"),
                    {field: value},
                )

                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["errors"][0]["attr"], field)

    @patch("weblate.api.views.generate_report.delay")
    def test_api_ignores_translator_limits_for_other_reports(
        self, mocked_delay
    ) -> None:
        mocked_delay.return_value = SimpleNamespace(id="report-task")
        self.client.force_login(self.user)
        now = timezone.now()
        data = {
            "start": (now - timedelta(days=1)).isoformat(),
            "end": now.isoformat(),
            "min_changes": 10,
            "max_changes": 1,
        }

        response = self.client.post(
            reverse("api:report-list"),
            {"kind": Report.Kind.CREDITS, **data},
        )
        self.assertEqual(response.status_code, 202)

        response = self.client.post(
            reverse("api:report-list"),
            {"kind": Report.Kind.TRANSLATOR_WORK, **data},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(mocked_delay.call_count, 1)
