# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os.path
from datetime import timedelta
from io import StringIO
from unittest.mock import patch
from uuid import UUID

from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import models
from django.template.loader import render_to_string
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone
from lxml import html

from weblate.auth.models import Group, Permission, Role, TeamMembership, User
from weblate.billing.models import (
    Billing,
    BillingEvent,
    Invoice,
    Plan,
    record_project_billing_workspace,
)
from weblate.billing.tasks import (
    billing_check,
    billing_notify,
    filter_with_projects,
    inactive_recurring_check,
    notify_expired,
    perform_removal,
    schedule_removal,
)
from weblate.lang.models import Language
from weblate.trans.alerts.community import (
    MissingTranslationInstructions,
)
from weblate.trans.models import (
    Component,
    PendingUnitChange,
    Project,
    Translation,
    Unit,
)
from weblate.trans.tests.test_models import BaseTestCase, RepoTestCase
from weblate.trans.tests.utils import (
    create_another_user,
    create_test_billing,
    create_test_user,
)
from weblate.workspaces.models import (
    WORKSPACE_NAME_LENGTH,
    WORKSPACE_PROJECT_CREATORS_GROUP,
    Workspace,
)

TEST_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test-data")


class BillingTest(BaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user = create_test_user()
        self.billing = create_test_billing(self.user, invoice=False)
        self.plan = self.billing.plan
        self.invoice = Invoice.objects.create(
            billing=self.billing,
            start=timezone.now().date() - timedelta(days=2),
            end=timezone.now().date() + timedelta(days=2),
            amount=10,
            ref="00000",
        )
        self.projectnum = 0
        self.componentnum = 0

    def refresh_from_db(self) -> None:
        self.billing = Billing.objects.get(pk=self.billing.pk)

    def add_project(self):
        name = f"test{self.projectnum}"
        self.projectnum += 1
        project = Project.objects.create(
            name=name, slug=name, access_control=Project.ACCESS_PROTECTED
        )
        self.billing.add_project(project)
        return project

    def add_component(
        self,
        project,
        remote_revision: str,
        *,
        linked_component=None,
        repo: str = "https://example.org/repo.git",
        vcs: str = "git",
    ):
        name = f"component{self.componentnum}"
        self.componentnum += 1
        [component] = Component.objects.bulk_create(
            [
                Component(
                    name=name,
                    slug=name,
                    project=project,
                    vcs=vcs,
                    repo=repo,
                    filemask="po/*.po",
                    file_format="po",
                    linked_component=linked_component,
                    remote_revision=remote_revision,
                )
            ]
        )
        return component

    @staticmethod
    def patch_remote_commit_dates(commit_dates):
        def get_last_remote_commit(component):
            commit_date = commit_dates.get(component.remote_revision)
            if commit_date is None:
                return None
            if isinstance(commit_date, dict):
                return commit_date
            return {"committerdate": commit_date}

        return patch.object(
            Component,
            "get_last_remote_commit",
            autospec=True,
            side_effect=get_last_remote_commit,
        )

    def add_pending_change(self, component, timestamp):
        source_language = component.source_language
        target_language = Language.objects.get(code="cs")
        source_translation = Translation.objects.create(
            component=component,
            language=source_language,
            language_code=source_language.code,
            plural=source_language.plural,
            filename="po/en.po",
        )
        target_translation = Translation.objects.create(
            component=component,
            language=target_language,
            language_code=target_language.code,
            plural=target_language.plural,
            filename="po/cs.po",
        )
        source_unit = Unit(
            translation=source_translation,
            id_hash=1,
            source="Hello",
            target="Hello",
            position=1,
        )
        source_unit.save(only_save=True, run_checks=False)
        target_unit = Unit(
            translation=target_translation,
            id_hash=1,
            source="Hello",
            target="Ahoj",
            position=1,
            source_unit=source_unit,
        )
        target_unit.save(only_save=True, run_checks=False)
        return PendingUnitChange.store_unit_change(
            target_unit,
            author=self.user,
            timestamp=timestamp,
            store_disk_state=False,
        )

    @staticmethod
    def set_alert_timestamp(component, name, timestamp):
        component.add_alert(name)
        component.alert_set.filter(name=name).update(timestamp=timestamp)

    def test_view_billing(self) -> None:
        self.add_project()
        # Not authenticated
        response = self.client.get(reverse("billing"))
        self.assertEqual(302, response.status_code)

        # Random user
        User.objects.create_user("foo", "foo@example.org", "bar")
        self.client.login(username="foo", password="bar")
        response = self.client.get(reverse("billing"))
        self.assertNotContains(response, "Current plan")

        # Owner
        self.client.login(username=self.user.username, password="testpassword")
        response = self.client.get(reverse("billing"), follow=True)
        self.assertRedirects(response, self.billing.get_absolute_url())
        self.assertContains(response, "Current plan")

        # Admin
        self.user.is_superuser = True
        self.user.save()
        response = self.client.get(reverse("billing"))
        self.assertContains(response, "Workspace")

    def test_customer_name(self) -> None:
        self.client.login(username=self.user.username, password="testpassword")
        billing_url = reverse("billing-detail", kwargs={"pk": self.billing.pk})

        response = self.client.get(billing_url)
        self.assertNotContains(response, "Customer name")

        self.billing.customer_name = "Acme Billing LLC"
        workspace_id = self.billing.workspace_id
        self.billing.save(update_fields=["customer_name"])
        self.assertEqual(str(self.billing), f"Acme Billing LLC ({self.plan})")
        self.billing.workspace.refresh_from_db()
        self.assertEqual(self.billing.workspace_id, workspace_id)
        self.assertEqual(self.billing.workspace.name, "Acme Billing LLC")

        response = self.client.get(billing_url)
        self.assertContains(response, "Customer name")
        self.assertContains(response, "Acme Billing LLC")

        self.user.is_superuser = True
        self.user.save()
        response = self.client.get(reverse("billing"))
        self.assertContains(response, "Customer")
        self.assertContains(response, "Acme Billing LLC")

    @override_settings(OFFER_HOSTING=True)
    def test_billing_overview_shows_component_alerts(self) -> None:
        self.plan.price = 0
        self.plan.save(update_fields=["price"])
        project = self.add_project()
        project.web = "https://example.org/"
        project.access_control = Project.ACCESS_PUBLIC
        project.save(update_fields=["web", "access_control"])
        component = self.add_component(project, "000000")
        Component.objects.filter(pk=component.pk).update(
            license="GPL-3.0-or-later", inherit_license=False
        )
        component.add_alert("BillingLimit")
        component.add_alert("MissingTranslationInstructions")
        component.add_alert("RecommendedXgettextAddon")
        component.alert_set.filter(name="MissingTranslationInstructions").update(
            dismissed=True
        )

        self.refresh_from_db()
        self.assertTrue(self.billing.valid_libre)

        verbose = MissingTranslationInstructions.verbose
        MissingTranslationInstructions.verbose = "<strong>Escaped alert</strong>"
        self.client.login(username=self.user.username, password="testpassword")
        try:
            response = self.client.get(self.billing.get_absolute_url())
        finally:
            MissingTranslationInstructions.verbose = verbose

        self.assertContains(response, "Your billing plan has exceeded its limits.")
        self.assertContains(response, "&lt;strong&gt;Escaped alert&lt;/strong&gt;")
        self.assertNotContains(response, "<strong>Escaped alert</strong>")
        self.assertContains(response, "Enable add-on:")
        self.assertContains(response, "<br />")
        self.assertContains(response, f"{component.get_absolute_url()}?alerts=1#alerts")
        self.assertContains(response, "dismissed")

    @override_settings(OFFER_HOSTING=True)
    def test_no_libre_alert_omits_component_alerts(self) -> None:
        self.plan.price = 0
        self.plan.save(update_fields=["price"])
        project = self.add_project()
        project.web = "https://example.org/"
        project.access_control = Project.ACCESS_PUBLIC
        project.save(update_fields=["web", "access_control"])
        component = self.add_component(project, "000000")
        Component.objects.filter(pk=component.pk).update(
            license="GPL-3.0-or-later", inherit_license=False
        )
        component.add_alert("BillingLimit")

        content = render_to_string(
            "trans/alert/nolibreconditions.html", {"component": component}
        )

        self.assertIn(
            "This project does no longer fit into Libre hosting conditions.", content
        )
        self.assertNotIn("Your billing plan has exceeded its limits.", content)
        self.assertNotIn(f"{component.get_absolute_url()}?alerts=1#alerts", content)

    @override_settings(OFFER_HOSTING=True)
    def test_billing_overview_compacts_component_checklist(self) -> None:
        self.plan.price = 0
        self.plan.save(update_fields=["price"])
        project = self.add_project()
        project.web = "https://example.org/"
        project.access_control = Project.ACCESS_PUBLIC
        project.save(update_fields=["web", "access_control"])
        passing_component = self.add_component(project, "000000")
        Component.objects.filter(pk=passing_component.pk).update(
            license="GPL-3.0-or-later", inherit_license=False
        )
        Component.objects.filter(pk=passing_component.pk).update(
            agreement="Contributor agreement", inherit_agreement=False
        )
        self.add_component(project, "000001")

        self.refresh_from_db()
        self.client.login(username=self.user.username, password="testpassword")
        response = self.client.get(self.billing.get_absolute_url())
        content = response.content.decode()

        self.assertContains(response, "Missing license")
        self.assertContains(
            response, '<span class="badge text-bg-danger">Missing license</span>'
        )
        self.assertContains(response, "Contributor license agreement")
        self.assertNotIn('data-bs-target="#libre-check-', content)
        self.assertNotIn("libre-check-", content)

    def test_limit_projects(self) -> None:
        self.assertTrue(self.billing.in_limits)
        self.add_project()
        self.refresh_from_db()
        self.assertTrue(self.billing.in_limits)
        project = self.add_project()
        self.refresh_from_db()
        self.assertFalse(self.billing.in_limits)
        with self.captureOnCommitCallbacks(execute=True):
            project.delete()
        self.refresh_from_db()
        self.assertTrue(self.billing.in_limits)

    def test_add_project_flushes_cached_properties(self) -> None:
        self.assertEqual(self.billing.count_projects, 0)
        self.assertTrue(self.billing.libre_checklist_without_alerts)
        self.assertIn("count_projects", self.billing.__dict__)
        self.assertIn("libre_checklist_without_alerts", self.billing.__dict__)

        self.add_project()

        self.assertNotIn("count_projects", self.billing.__dict__)
        self.assertNotIn("libre_checklist_without_alerts", self.billing.__dict__)
        self.assertEqual(self.billing.count_projects, 1)

    def test_add_project_updates_workspace_directly(self) -> None:
        project = Project.objects.create(
            name="direct-update",
            slug="direct-update",
            access_control=Project.ACCESS_PROTECTED,
        )

        with patch.object(Project, "save", side_effect=AssertionError):
            self.billing.add_project(project)

        project.refresh_from_db()
        self.assertEqual(project.workspace_id, self.billing.workspace_id)

    def test_add_project_updates_billing_instance(self) -> None:
        billing = Billing.objects.create(plan=self.plan)
        project = Project.objects.create(
            name="new-project",
            slug="new-project",
            access_control=Project.ACCESS_PROTECTED,
        )

        billing.add_project(project)

        self.assertFalse(billing.paid)
        billing.invoice_set.create(
            amount=10,
            start=timezone.now().date() - timedelta(days=1),
            end=timezone.now().date() + timedelta(days=1),
        )
        billing.refresh_from_db()
        self.assertTrue(billing.paid)

    def test_project_billings_uses_project_database(self) -> None:
        project = Project(
            name="database-project",
            slug="database-project",
            workspace_id=UUID("00000000-0000-0000-0000-000000000001"),
        )
        # ruff: ignore[private-member-access]
        project._state.db = "other"

        with patch.object(Billing.objects, "db_manager") as db_manager:
            manager = db_manager.return_value
            manager.filter.return_value = ["billing"]

            self.assertEqual(project.billings, ["billing"])

        db_manager.assert_called_once_with("other")
        manager.filter.assert_called_once_with(workspace_id=project.workspace_id)

    def test_add_project_rejects_unsaved_billing(self) -> None:
        billing = Billing(plan=self.plan)
        project = Project.objects.create(
            name="unsaved-billing",
            slug="unsaved-billing",
            access_control=Project.ACCESS_PROTECTED,
        )

        with self.assertRaisesRegex(ValidationError, "saved"):
            billing.add_project(project)

        project.refresh_from_db()
        self.assertIsNone(project.workspace_id)

    def test_workspace_can_not_be_changed(self) -> None:
        workspace = self.billing.workspace
        self.billing.workspace = None
        with self.assertRaises(ValidationError):
            self.billing.save()
        self.refresh_from_db()
        self.assertEqual(self.billing.workspace_id, workspace.pk)

        other = Billing.objects.create(plan=self.plan)
        self.billing.workspace = other.workspace
        with self.assertRaises(ValidationError):
            self.billing.save()
        self.refresh_from_db()
        self.assertEqual(self.billing.workspace_id, workspace.pk)

    def test_workspace_validation_uses_original_workspace(self) -> None:
        with self.assertNumQueries(0):
            self.billing.validate_workspace()

    def test_default_workspace_name_truncated(self) -> None:
        billing = Billing.objects.create(
            plan=self.plan, customer_name="x" * (WORKSPACE_NAME_LENGTH + 10)
        )

        self.assertEqual(billing.workspace.name, "x" * WORKSPACE_NAME_LENGTH)
        self.assertEqual(len(billing.workspace.name), WORKSPACE_NAME_LENGTH)
        self.assertIsInstance(billing.workspace_id, UUID)
        self.assertTrue(billing.workspace.name_managed)

    def test_customer_name_used_for_workspace(self) -> None:
        billing = Billing.objects.create(
            plan=self.plan, customer_name="Acme Billing LLC"
        )

        self.assertEqual(billing.workspace.name, "Acme Billing LLC")
        self.assertTrue(billing.workspace.name_managed)

    def test_customer_name_updates_workspace_after_plan_change(self) -> None:
        paid_plan = Plan.objects.create(
            name="Paid plan", slug="paid-plan", price=29, yearly_price=299
        )
        workspace_id = self.billing.workspace_id

        self.billing.plan = paid_plan
        self.billing.customer_name = "Acme Billing LLC"
        self.billing.save(update_fields=["plan", "customer_name"])

        self.billing.workspace.refresh_from_db()
        self.assertEqual(self.billing.workspace_id, workspace_id)
        self.assertEqual(self.billing.workspace.name, "Acme Billing LLC")
        self.assertTrue(self.billing.workspace.name_managed)

    def test_customer_name_baseline_ignores_unsaved_field(self) -> None:
        billing = Billing.objects.create(plan=self.plan)

        billing.customer_name = "Acme Billing LLC"
        billing.payment = {"id": "payment-id"}
        billing.save(update_fields=["payment"])
        billing.save(update_fields=["customer_name"])

        billing.workspace.refresh_from_db()
        self.assertEqual(billing.workspace.name, "Acme Billing LLC")

    def test_customer_name_preserves_manual_workspace_name(self) -> None:
        paid_plan = Plan.objects.create(
            name="Manual paid plan",
            slug="manual-paid-plan",
            price=29,
            yearly_price=299,
        )
        self.billing.workspace.name = "Manual workspace name"
        self.billing.workspace.save(update_fields=["name"])

        self.billing.plan = paid_plan
        self.billing.customer_name = "Acme Billing LLC"
        self.billing.save(update_fields=["plan", "customer_name"])

        self.billing.workspace.refresh_from_db()
        self.assertEqual(self.billing.workspace.name, "Manual workspace name")
        self.assertFalse(self.billing.workspace.name_managed)

    def test_billing_demo_with_existing_workspace(self) -> None:
        workspace = Workspace.objects.create(name="Billing Demo")
        Project.objects.create(
            name="Billing Demo", slug="billing-demo", workspace=workspace
        )

        call_command("billing_demo")

        billing = Billing.objects.get(workspace=workspace)
        self.assertEqual(billing.plan.slug, "160k")

        call_command("billing_demo")

        self.assertEqual(Billing.objects.filter(workspace=workspace).count(), 1)

    def test_commands(self) -> None:
        out = StringIO()
        call_command("billing_check", stdout=out)
        self.assertEqual(out.getvalue(), "")
        self.add_project()
        self.add_project()
        out = StringIO()
        call_command("billing_check", stdout=out)
        self.assertEqual(
            out.getvalue(),
            "Following billings are over limit:\n * test0, test1 (Basic plan)\n",
        )
        out = StringIO()
        call_command("billing_check", "--valid", stdout=out)
        self.assertEqual(out.getvalue(), "")
        self.invoice.delete()
        out = StringIO()
        call_command("billing_check", stdout=out)
        self.assertEqual(
            out.getvalue(),
            "Following billings are over limit:\n"
            " * test0, test1 (Basic plan)\n"
            "Following billings are past due date:\n"
            " * test0, test1 (Basic plan)\n",
        )
        call_command("billing_check", "--notify", stdout=out)
        self.assertEqual(len(mail.outbox), 1)

    def test_billing_notify(self) -> None:
        self.assertEqual(len(mail.outbox), 0)
        self.add_project()
        self.add_project()
        billing_notify()
        self.assertEqual(len(mail.outbox), 1)

    def test_billing_notify_users_are_workspace_admins(self) -> None:
        project_creator = create_another_user(suffix="-creator")
        workspace_groups = self.billing.workspace.setup_groups()
        project_creator.add_team(
            None, workspace_groups[WORKSPACE_PROJECT_CREATORS_GROUP]
        )

        notify_users = list(self.billing.get_notify_users())
        self.assertEqual(set(notify_users), {self.user})
        expected_language = self.user.profile.language
        with self.assertNumQueries(0):
            self.assertEqual(
                [user.profile.language for user in notify_users], [expected_language]
            )

    @override_settings(EMAIL_SUBJECT_PREFIX="")
    def test_inactive_recurring_warning_and_disable(self) -> None:
        project = self.add_project()
        self.add_component(project, "old")
        self.billing.payment = {"recurring": "payment"}
        self.billing.save(update_fields=["payment"])

        with self.patch_remote_commit_dates(
            {"old": timezone.now() - timedelta(days=200)}
        ):
            inactive_recurring_check()

        self.refresh_from_db()
        self.assertIn("recurring", self.billing.payment)
        self.assertIsNotNone(self.billing.inactive_recurring_notification)
        self.assertIsNotNone(self.billing.inactive_recurring_latest_commit)
        self.assertIsNotNone(self.billing.inactive_recurring_disable)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            "Recurring payment will be disabled for inactive projects",
        )
        self.assertIn("manually", mail.outbox[0].body)
        scheduled_log = self.billing.billinglog_set.get(
            event=BillingEvent.INACTIVE_RECURRING_SCHEDULED
        )
        self.assertTrue(scheduled_log.details["automatic"])
        self.assertIn("latest_commit", scheduled_log.details)
        self.assertIn("planned_disable", scheduled_log.details)

        self.billing.inactive_recurring_disable = timezone.now() - timedelta(days=1)
        self.billing.save(update_fields=["inactive_recurring_disable"])

        with self.patch_remote_commit_dates(
            {"old": timezone.now() - timedelta(days=200)}
        ):
            inactive_recurring_check()

        self.refresh_from_db()
        self.assertNotIn("recurring", self.billing.payment)
        self.assertIsNone(self.billing.inactive_recurring_notification)
        self.assertIsNone(self.billing.inactive_recurring_latest_commit)
        self.assertIsNone(self.billing.inactive_recurring_disable)
        log = self.billing.billinglog_set.get(event=BillingEvent.DISABLED_RECURRING)
        self.assertTrue(log.details["automatic"])

    def test_inactive_recurring_keeps_active_projects(self) -> None:
        project = self.add_project()
        self.add_component(project, "new")
        self.billing.payment = {"recurring": "payment"}
        self.billing.inactive_recurring_latest_commit = timezone.now() - timedelta(
            days=200
        )
        self.billing.inactive_recurring_notification = timezone.now()
        self.billing.inactive_recurring_disable = timezone.now() + timedelta(days=30)
        self.billing.save(
            update_fields=[
                "payment",
                "inactive_recurring_latest_commit",
                "inactive_recurring_notification",
                "inactive_recurring_disable",
            ]
        )

        with self.patch_remote_commit_dates(
            {"new": timezone.now() - timedelta(days=10)}
        ):
            inactive_recurring_check()

        self.refresh_from_db()
        self.assertIn("recurring", self.billing.payment)
        self.assertIsNone(self.billing.inactive_recurring_notification)
        self.assertIsNone(self.billing.inactive_recurring_latest_commit)
        self.assertIsNone(self.billing.inactive_recurring_disable)

    def test_inactive_recurring_uses_commit_date(self) -> None:
        project = self.add_project()
        self.add_component(project, "new-commit")
        self.billing.payment = {"recurring": "payment"}
        self.billing.save(update_fields=["payment"])

        with self.patch_remote_commit_dates(
            {
                "new-commit": {
                    "authordate": timezone.now() - timedelta(days=200),
                    "commitdate": timezone.now() - timedelta(days=10),
                }
            }
        ):
            inactive_recurring_check()

        self.refresh_from_db()
        self.assertIn("recurring", self.billing.payment)
        self.assertIsNone(self.billing.inactive_recurring_notification)
        self.assertIsNone(self.billing.inactive_recurring_latest_commit)
        self.assertIsNone(self.billing.inactive_recurring_disable)

    @override_settings(EMAIL_SUBJECT_PREFIX="")
    def test_inactive_recurring_uses_pending_weblate_changes(self) -> None:
        project = self.add_project()
        self.add_pending_change(
            self.add_component(project, "new-upstream"),
            timezone.now() - timedelta(days=200),
        )
        self.billing.payment = {"recurring": "payment"}
        self.billing.save(update_fields=["payment"])

        with self.patch_remote_commit_dates(
            {"new-upstream": timezone.now() - timedelta(days=10)}
        ):
            inactive_recurring_check()

        self.refresh_from_db()
        self.assertIn("recurring", self.billing.payment)
        self.assertIsNone(self.billing.inactive_recurring_latest_commit)
        self.assertIsNotNone(self.billing.inactive_recurring_oldest_pending_change)
        self.assertIsNotNone(self.billing.inactive_recurring_disable)
        self.assertIn("pending translation changes", mail.outbox[0].body)
        scheduled_log = self.billing.billinglog_set.get(
            event=BillingEvent.INACTIVE_RECURRING_SCHEDULED
        )
        self.assertIsNone(scheduled_log.details["latest_commit"])
        self.assertIn("oldest_pending_change", scheduled_log.details)

    @override_settings(EMAIL_SUBJECT_PREFIX="")
    def test_inactive_recurring_uses_repository_changes_alert(self) -> None:
        project = self.add_project()
        component = self.add_component(project, "new-upstream")
        self.set_alert_timestamp(
            component, "RepositoryChanges", timezone.now() - timedelta(days=200)
        )
        self.billing.payment = {"recurring": "payment"}
        self.billing.save(update_fields=["payment"])

        with self.patch_remote_commit_dates(
            {"new-upstream": timezone.now() - timedelta(days=10)}
        ):
            inactive_recurring_check()

        self.refresh_from_db()
        self.assertIn("recurring", self.billing.payment)
        self.assertIsNone(self.billing.inactive_recurring_latest_commit)
        self.assertIsNotNone(self.billing.inactive_recurring_repository_changes)
        self.assertIsNotNone(self.billing.inactive_recurring_disable)
        self.assertIn("repository changes waiting", mail.outbox[0].body)

    @override_settings(EMAIL_SUBJECT_PREFIX="")
    def test_inactive_recurring_uses_push_failure_alert(self) -> None:
        project = self.add_project()
        component = self.add_component(project, "new-upstream")
        self.set_alert_timestamp(
            component, "PushFailure", timezone.now() - timedelta(days=200)
        )
        self.billing.payment = {"recurring": "payment"}
        self.billing.save(update_fields=["payment"])

        with self.patch_remote_commit_dates(
            {"new-upstream": timezone.now() - timedelta(days=10)}
        ):
            inactive_recurring_check()

        self.refresh_from_db()
        self.assertIn("recurring", self.billing.payment)
        self.assertIsNone(self.billing.inactive_recurring_latest_commit)
        self.assertIsNotNone(self.billing.inactive_recurring_push_failure)
        self.assertIsNotNone(self.billing.inactive_recurring_disable)
        self.assertIn("unable to push repository changes", mail.outbox[0].body)

    def test_inactive_recurring_skips_unknown_upstream_date(self) -> None:
        project = self.add_project()
        self.add_component(project, "unknown")
        self.billing.payment = {"recurring": "payment"}
        self.billing.save(update_fields=["payment"])

        with self.patch_remote_commit_dates({}):
            inactive_recurring_check()

        self.refresh_from_db()
        self.assertIn("recurring", self.billing.payment)
        self.assertIsNone(self.billing.inactive_recurring_notification)
        self.assertIsNone(self.billing.inactive_recurring_latest_commit)
        self.assertIsNone(self.billing.inactive_recurring_disable)

    @override_settings(EMAIL_SUBJECT_PREFIX="")
    def test_inactive_recurring_uses_repo_components(self) -> None:
        project = self.add_project()
        old = self.add_component(project, "old")
        self.add_component(project, "local", vcs="local", repo="local:")
        self.add_component(
            project,
            "",
            linked_component=old,
            repo=old.get_repo_link_url(),
        )
        self.billing.payment = {"recurring": "payment"}
        self.billing.save(update_fields=["payment"])

        with self.patch_remote_commit_dates(
            {
                "old": timezone.now() - timedelta(days=200),
                "local": None,
                "": None,
            }
        ) as mocked:
            inactive_recurring_check()

        self.refresh_from_db()
        self.assertIsNotNone(self.billing.inactive_recurring_notification)
        self.assertIsNotNone(self.billing.inactive_recurring_latest_commit)
        self.assertIsNotNone(self.billing.inactive_recurring_disable)
        self.assertEqual(mocked.call_count, 1)

    @override_settings(EMAIL_SUBJECT_PREFIX="")
    def test_inactive_recurring_clears_stale_schedule(self) -> None:
        project = self.add_project()
        self.add_component(project, "old")
        self.billing.payment = {"recurring": "payment"}
        self.billing.inactive_recurring_notification = timezone.now() - timedelta(
            days=30
        )
        self.billing.inactive_recurring_latest_commit = timezone.now() - timedelta(
            days=200
        )
        self.billing.inactive_recurring_disable = timezone.now() - timedelta(days=1)
        self.plan.yearly_price = 0
        self.plan.save(update_fields=["yearly_price"])
        self.billing.save(
            update_fields=[
                "payment",
                "inactive_recurring_notification",
                "inactive_recurring_latest_commit",
                "inactive_recurring_disable",
            ]
        )

        with self.patch_remote_commit_dates(
            {"old": timezone.now() - timedelta(days=200)}
        ):
            inactive_recurring_check()

        self.refresh_from_db()
        self.assertIn("recurring", self.billing.payment)
        self.assertIsNone(self.billing.inactive_recurring_notification)
        self.assertIsNone(self.billing.inactive_recurring_latest_commit)
        self.assertIsNone(self.billing.inactive_recurring_disable)
        cleared_log = self.billing.billinglog_set.get(
            event=BillingEvent.INACTIVE_RECURRING_CLEARED
        )
        self.assertTrue(cleared_log.details["automatic"])
        self.assertIn("planned_disable", cleared_log.details)

        self.plan.yearly_price = 199
        self.plan.save(update_fields=["yearly_price"])
        with self.patch_remote_commit_dates(
            {"old": timezone.now() - timedelta(days=200)}
        ):
            inactive_recurring_check()

        self.refresh_from_db()
        self.assertIn("recurring", self.billing.payment)
        self.assertIsNotNone(self.billing.inactive_recurring_notification)
        self.assertIsNotNone(self.billing.inactive_recurring_latest_commit)
        self.assertGreater(self.billing.inactive_recurring_disable, timezone.now())

    def test_invoice_validation(self) -> None:
        invoice = Invoice(
            billing=self.billing,
            start=self.invoice.start,
            end=self.invoice.end,
            amount=30,
        )
        # Full overlap
        with self.assertRaises(ValidationError):
            invoice.clean()

        # Start overlap
        invoice.start = self.invoice.end + timedelta(days=1)
        with self.assertRaises(ValidationError):
            invoice.clean()

        # Zero interval
        invoice.end = self.invoice.end + timedelta(days=1)
        with self.assertRaises(ValidationError):
            invoice.clean()

        # Valid after existing
        invoice.end = self.invoice.end + timedelta(days=2)
        invoice.clean()

        # End overlap
        invoice.start = self.invoice.start - timedelta(days=4)
        invoice.end = self.invoice.end
        with self.assertRaises(ValidationError):
            invoice.clean()

        # Valid before existing
        invoice.end = self.invoice.start - timedelta(days=1)
        invoice.clean()

        # Validation of existing
        self.invoice.clean()

    @override_settings(INVOICE_PATH_LEGACY=TEST_DATA)
    def test_download(self) -> None:
        self.add_project()
        # Unauthenticated
        response = self.client.get(
            reverse("invoice-download", kwargs={"pk": self.invoice.pk})
        )
        self.assertEqual(302, response.status_code)
        # Not owner
        User.objects.create_user("foo", "foo@example.org", "bar")
        self.client.login(username="foo", password="bar")
        response = self.client.get(
            reverse("invoice-download", kwargs={"pk": self.invoice.pk})
        )
        self.assertEqual(403, response.status_code)
        # Owner
        self.client.login(username=self.user.username, password="testpassword")
        response = self.client.get(
            reverse("invoice-download", kwargs={"pk": self.invoice.pk})
        )
        self.assertContains(response, "PDF-INVOICE")
        # Invoice without file
        invoice = Invoice.objects.create(
            billing=self.billing,
            start=timezone.now().date() - timedelta(days=2),
            end=timezone.now().date() + timedelta(days=2),
            amount=10,
        )
        response = self.client.get(
            reverse("invoice-download", kwargs={"pk": invoice.pk})
        )
        self.assertEqual(404, response.status_code)
        # Invoice with non existing file
        invoice.ref = "NON"
        invoice.save()
        response = self.client.get(
            reverse("invoice-download", kwargs={"pk": invoice.pk})
        )
        self.assertEqual(404, response.status_code)

    @override_settings(EMAIL_SUBJECT_PREFIX="")
    def test_expiry(self) -> None:
        self.add_project()

        # Paid
        schedule_removal()
        notify_expired()
        perform_removal()
        self.assertEqual(len(mail.outbox), 0)
        self.refresh_from_db()
        self.assertIsNone(self.billing.removal)
        self.assertTrue(self.billing.paid)
        self.assertEqual(self.billing.state, Billing.STATE_ACTIVE)
        self.assertEqual(self.billing.count_projects, 1)

        # Not paid
        self.invoice.start -= timedelta(days=14)
        self.invoice.end -= timedelta(days=14)
        self.invoice.save()
        schedule_removal()
        notify_expired()
        perform_removal()
        self.assertEqual(len(mail.outbox), 1)
        self.refresh_from_db()
        self.assertIsNone(self.billing.removal)
        self.assertEqual(self.billing.state, Billing.STATE_ACTIVE)
        self.assertTrue(self.billing.paid)
        self.assertEqual(self.billing.count_projects, 1)
        self.assertEqual(mail.outbox.pop().subject, "Your billing plan has expired")

        # Not paid for long
        self.invoice.start -= timedelta(days=30)
        self.invoice.end -= timedelta(days=30)
        self.invoice.save()
        schedule_removal()
        notify_expired()
        perform_removal()
        self.assertEqual(len(mail.outbox), 1)
        self.refresh_from_db()
        self.assertIsNotNone(self.billing.removal)
        self.assertEqual(self.billing.state, Billing.STATE_ACTIVE)
        self.assertFalse(self.billing.paid)
        self.assertEqual(self.billing.count_projects, 1)
        self.assertEqual(
            mail.outbox.pop().subject,
            "Your translation project is scheduled for removal",
        )

        # Final removal
        self.billing.removal = timezone.now() - timedelta(days=30)
        self.billing.save(skip_limits=True)
        perform_removal()
        self.refresh_from_db()
        self.assertEqual(self.billing.state, Billing.STATE_TERMINATED)
        self.assertFalse(self.billing.paid)
        self.assertEqual(self.billing.count_projects, 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox.pop().subject, "Your translation project was removed"
        )

    @override_settings(EMAIL_SUBJECT_PREFIX="")
    def test_trial(self) -> None:
        self.billing.state = Billing.STATE_TRIAL
        self.billing.save(skip_limits=True)
        self.billing.invoice_set.all().delete()
        self.add_project()

        # No expiry set
        billing_check()
        notify_expired()
        perform_removal()
        self.refresh_from_db()
        self.assertEqual(self.billing.state, Billing.STATE_TRIAL)
        self.assertTrue(self.billing.paid)
        self.assertEqual(self.billing.count_projects, 1)
        self.assertIsNone(self.billing.removal)
        self.assertEqual(len(mail.outbox), 0)

        # Future expiry
        self.billing.expiry = timezone.now() + timedelta(days=30)
        self.billing.save(skip_limits=True)
        billing_check()
        notify_expired()
        perform_removal()
        self.refresh_from_db()
        self.assertEqual(self.billing.state, Billing.STATE_TRIAL)
        self.assertTrue(self.billing.paid)
        self.assertEqual(self.billing.count_projects, 1)
        self.assertIsNone(self.billing.removal)
        self.assertEqual(len(mail.outbox), 0)

        # Close expiry
        self.billing.expiry = timezone.now() + timedelta(days=1)
        self.billing.save(skip_limits=True)
        billing_check()
        notify_expired()
        perform_removal()
        self.refresh_from_db()
        self.assertEqual(self.billing.state, Billing.STATE_TRIAL)
        self.assertTrue(self.billing.paid)
        self.assertEqual(self.billing.count_projects, 1)
        self.assertIsNone(self.billing.removal)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox.pop().subject, "Your trial period is about to expire"
        )

        # Past expiry
        self.billing.expiry = timezone.now() - timedelta(days=1)
        self.billing.save(skip_limits=True)
        billing_check()
        notify_expired()
        perform_removal()
        self.refresh_from_db()
        self.assertEqual(self.billing.state, Billing.STATE_TRIAL)
        self.assertTrue(self.billing.paid)
        self.assertEqual(self.billing.count_projects, 1)
        self.assertIsNone(self.billing.expiry)
        self.assertIsNotNone(self.billing.removal)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox.pop().subject,
            "Your translation project is scheduled for removal",
        )

        # There should be notification sent when removal is scheduled
        billing_check()
        notify_expired()
        perform_removal()
        self.refresh_from_db()
        self.assertEqual(self.billing.state, Billing.STATE_TRIAL)
        self.assertTrue(self.billing.paid)
        self.assertEqual(self.billing.count_projects, 1)
        self.assertIsNotNone(self.billing.removal)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox.pop().subject,
            "Your translation project is scheduled for removal",
        )

        # Removal
        self.billing.removal = timezone.now() - timedelta(days=1)
        self.billing.save(skip_limits=True)
        billing_check()
        perform_removal()
        self.refresh_from_db()
        self.assertEqual(self.billing.state, Billing.STATE_TERMINATED)
        self.assertFalse(self.billing.paid)
        self.assertEqual(self.billing.count_projects, 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox.pop().subject, "Your translation project was removed"
        )

    def test_free_trial(self) -> None:
        self.plan.price = 0
        self.plan.yearly_price = 0
        self.plan.save()
        self.test_trial()

    def test_remove_project(self) -> None:
        second_user = create_another_user()
        third_user = create_another_user(suffix="-3")
        project = self.add_project()
        project.add_user(second_user, "Administration")
        project.add_user(third_user, "Translate")
        project.delete()
        self.assertEqual(
            set(
                self.billing.workspace.get_owners_group().user_set.values_list(
                    "username", flat=True
                )
            ),
            {self.user.username, second_user.username},
        )

    def test_project_workspace_change_updates_previous_billing(self) -> None:
        project = self.add_project()
        self.add_project()
        self.refresh_from_db()
        self.assertFalse(self.billing.in_limits)
        other = Billing.objects.create(plan=self.plan)

        project.workspace = other.workspace
        project.save(update_fields=["workspace"])

        self.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.billing.count_projects, 1)
        self.assertTrue(self.billing.in_limits)
        self.assertEqual(other.count_projects, 1)
        self.assertTrue(other.in_limits)

    def test_project_billing_workspace_recording_ignores_unrelated_updates(
        self,
    ) -> None:
        project = self.add_project()
        project.billing_previous_workspace_id = self.billing.workspace_id

        with self.assertNumQueries(0):
            record_project_billing_workspace(Project, project, update_fields={"name"})

        self.assertIsNone(project.billing_previous_workspace_id)

        project.billing_previous_workspace_id = self.billing.workspace_id
        with self.assertNumQueries(0):
            record_project_billing_workspace(Project, project)

        self.assertIsNone(project.billing_previous_workspace_id)

    def test_project_billing_workspace_recording_tracks_workspace_change(self) -> None:
        project = self.add_project()
        other = Billing.objects.create(plan=self.plan)
        project.workspace = other.workspace

        with self.assertNumQueries(0):
            record_project_billing_workspace(Project, project)

        self.assertEqual(
            project.billing_previous_workspace_id,
            self.billing.workspace_id,
        )

    def test_project_billing_workspace_recording_tracks_deferred_workspace_change(
        self,
    ) -> None:
        project = Project.objects.defer("workspace").get(pk=self.add_project().pk)
        other = Billing.objects.create(plan=self.plan)
        project.workspace_id = other.workspace_id

        self.assertIs(project.billing_original_workspace_id, models.DEFERRED)
        with self.assertNumQueries(1):
            record_project_billing_workspace(Project, project)

        self.assertEqual(
            project.billing_previous_workspace_id,
            self.billing.workspace_id,
        )

    def test_filter_with_projects_uses_exists(self) -> None:
        queryset = filter_with_projects(Billing.objects.all())
        query = str(queryset.query).upper()

        self.assertIn("EXISTS", query)
        self.assertNotIn("DISTINCT", query)

    def test_transfer_project_updates_previous_billing(self) -> None:
        project = self.add_project()
        self.add_project()
        self.refresh_from_db()
        self.assertFalse(self.billing.in_limits)
        other = Billing.objects.create(plan=self.plan)

        other.transfer_project(project)

        self.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.billing.count_projects, 1)
        self.assertTrue(self.billing.in_limits)
        self.assertEqual(other.count_projects, 1)
        self.assertTrue(other.in_limits)

    def test_merge(self) -> None:
        other = Billing.objects.create(plan=self.billing.plan)
        project = self.add_project()
        project2 = self.add_project()
        limited_user = create_another_user("-limited")
        custom_user = create_another_user("-custom")
        source_group = self.billing.workspace.setup_groups()[
            WORKSPACE_PROJECT_CREATORS_GROUP
        ]
        limited_user.add_team(None, source_group)
        source_membership = TeamMembership.objects.get(
            group=source_group, user=limited_user
        )
        source_membership.limit_languages.add(Language.objects.get(code="cs"))
        custom_role = Role.objects.create(name="Custom workspace editor")
        custom_role.permissions.add(Permission.objects.get(codename="workspace.edit"))
        custom_group = Group.objects.create(
            name="Custom workspace team", defining_workspace=self.billing.workspace
        )
        custom_group.roles.add(custom_role)
        custom_user.add_team(None, custom_group)
        self.refresh_from_db()
        self.assertFalse(self.billing.in_limits)
        self.billing.payment = {"all": [{"charge": "source-payment"}]}
        self.billing.save()
        Invoice.objects.create(
            billing=other,
            start=timezone.now().date() - timedelta(days=2),
            end=timezone.now().date() + timedelta(days=2),
            amount=10,
            ref="00001",
        )

        self.user.is_superuser = True
        self.user.save()
        self.client.login(username=self.user.username, password="testpassword")

        response = self.client.get(
            reverse("billing-detail", kwargs={"pk": self.billing.pk})
        )
        self.assertContains(response, "Merge with billing")

        response = self.client.get(
            reverse("billing-merge", kwargs={"pk": self.billing.pk}),
            {"other": other.pk},
        )
        self.assertContains(response, "Confirm merge")
        merge_url = reverse("billing-merge", kwargs={"pk": self.billing.pk})
        forms = html.fromstring(response.content).xpath(
            f'//form[@method="post" and @action="{merge_url}"]'
        )
        self.assertEqual(len(forms), 1)
        form = forms[0]
        self.assertEqual(form.xpath('.//input[@name="other"]/@value'), [str(other.pk)])
        self.assertTrue(form.xpath('.//input[@name="csrfmiddlewaretoken"]'))
        self.assertTrue(form.xpath('.//input[@name="confirm"]'))
        self.assertTrue(
            form.xpath('.//input[@type="submit" and @value="Confirm merge"]')
        )

        response = self.client.post(
            reverse("billing-merge", kwargs={"pk": self.billing.pk}),
            {"other": other.pk},
        )
        self.assertRedirects(
            response, reverse("billing-detail", kwargs={"pk": self.billing.pk})
        )

        with patch.object(Billing, "transfer_project", side_effect=AssertionError):
            response = self.client.post(
                reverse("billing-merge", kwargs={"pk": self.billing.pk}),
                {"other": other.pk, "confirm": 1},
            )
        self.assertRedirects(
            response, reverse("billing-detail", kwargs={"pk": other.pk})
        )

        self.assertEqual(other.invoice_set.count(), 2)
        other.refresh_from_db()
        self.assertEqual(other.payment["all"], [{"charge": "source-payment"}])
        project.refresh_from_db()
        project2.refresh_from_db()
        self.assertEqual(project.workspace_id, other.workspace_id)
        self.assertEqual(project2.workspace_id, other.workspace_id)
        self.refresh_from_db()
        other = Billing.objects.get(pk=other.pk)
        self.assertEqual(self.billing.count_projects, 0)
        self.assertTrue(self.billing.in_limits)
        self.assertEqual(other.count_projects, 2)
        self.assertFalse(other.in_limits)
        target_group = other.workspace.setup_groups()[WORKSPACE_PROJECT_CREATORS_GROUP]
        target_membership = TeamMembership.objects.get(
            group=target_group, user=limited_user
        )
        self.assertEqual(
            list(target_membership.limit_languages.values_list("code", flat=True)),
            ["cs"],
        )
        target_custom_group = other.workspace.defined_groups.get(name=custom_group.name)
        self.assertEqual(set(target_custom_group.roles.all()), {custom_role})
        self.assertTrue(target_custom_group.user_set.filter(pk=custom_user.pk).exists())

    def test_workspace_access_controls_billing_view(self) -> None:
        second_user = create_another_user()
        project_creator = create_another_user(suffix="-creator")
        workspace_editor = create_another_user(suffix="-editor")
        workspace_groups = self.billing.workspace.setup_groups()
        project_creator.add_team(
            None, workspace_groups[WORKSPACE_PROJECT_CREATORS_GROUP]
        )
        workspace_edit = Role.objects.create(name="Workspace edit")
        workspace_edit.permissions.set(
            Permission.objects.filter(codename="workspace.edit")
        )
        workspace_editors = Group.objects.create(
            name="Workspace editors",
            defining_workspace=self.billing.workspace,
        )
        workspace_editors.roles.add(workspace_edit)
        workspace_editor.add_team(None, workspace_editors)
        billing_url = reverse("billing-detail", kwargs={"pk": self.billing.pk})

        # No access for different user
        self.client.login(username=second_user.username, password="testpassword")

        response = self.client.get(billing_url)
        self.assertEqual(response.status_code, 403)

        # Project creation access does not grant billing access
        self.client.login(username=project_creator.username, password="testpassword")

        response = self.client.get(billing_url)
        self.assertEqual(response.status_code, 403)

        # Workspace edit access grants billing access
        self.client.login(username=workspace_editor.username, password="testpassword")

        response = self.client.get(billing_url)
        self.assertContains(response, "Billing plan")

        # Access for workspace owner
        self.client.login(username=self.user.username, password="testpassword")

        response = self.client.get(billing_url)
        self.assertContains(response, "Billing plan")
        self.assertNotContains(response, "Billing admins", status_code=200)


class HostingTest(RepoTestCase):
    def get_user(self):
        user = User.objects.create_user(
            username="testuser", password="testpassword", full_name="Test User"
        )
        user.full_name = "First Second"
        user.email = "noreply@example.com"
        user.save()
        return user

    @override_settings(
        OFFER_HOSTING=True,
        ADMINS_HOSTING=["noreply@example.com"],
    )
    def test_hosting(self) -> None:
        """Test for hosting form with enabled hosting."""
        Plan.objects.create(price=0, slug="libre", name="Libre")
        user = self.get_user()
        self.client.login(username="testuser", password="testpassword")
        response = self.client.get(reverse("hosting"))
        self.assertContains(response, "trial")

        # Creating a trial
        response = self.client.post(reverse("trial"), {"plan": "libre"}, follow=True)
        self.assertContains(response, "Create project")
        # Flush outbox
        mail.outbox = []

        # Add component to a trial
        component = self.create_component()
        billing = Billing.objects.get(workspace__defined_groups__memberships__user=user)
        billing.add_project(component.project)

        # Not valid for libre
        self.assertFalse(billing.valid_libre)
        response = self.client.post(
            billing.get_absolute_url(),
            {"request": "1", "message": "msg"},
            follow=True,
        )
        self.assertNotContains(response, "Pending approval")

        # Add missing license info
        component.project.component_set.update(
            license="GPL-3.0-or-later", inherit_license=False
        )
        billing = Billing.objects.get(workspace__defined_groups__memberships__user=user)

        # Valid for libre
        self.assertTrue(billing.valid_libre)
        response = self.client.post(
            billing.get_absolute_url(),
            {"request": "1", "message": "msg"},
            follow=True,
        )
        self.assertContains(response, "Pending approval")

        # Verify message
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "[Weblate] Hosting request for Test")
        self.assertIn("testuser", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ["noreply@example.com"])

        # Non-admin approval
        response = self.client.post(
            billing.get_absolute_url(),
            {"approve": "1"},
            follow=True,
        )
        self.assertContains(response, "Pending approval")

        # Admin extension
        user.is_superuser = True
        user.save()
        response = self.client.post(
            billing.get_absolute_url(),
            {"extend": "1"},
            follow=True,
        )
        self.assertContains(response, "Pending approval")

        # Admin approval
        user.is_superuser = True
        user.save()
        response = self.client.post(
            billing.get_absolute_url(),
            {"approve": "1"},
            follow=True,
        )
        self.assertNotContains(response, "Pending approval")
