# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

import os.path
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core import mail
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test.utils import override_settings
from django.urls import reverse
from django.utils import timezone

from weblate.auth.models import User
from weblate.billing.models import Billing, BillingEvent, Invoice, Plan
from weblate.billing.tasks import (
    billing_check,
    billing_notify,
    inactive_recurring_check,
    notify_expired,
    perform_removal,
    schedule_removal,
)
from weblate.lang.models import Language
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
        self.billing.projects.add(project)
        self.billing.owners.add(self.user)
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
        self.assertContains(response, "Owners")

    def test_limit_projects(self) -> None:
        self.assertTrue(self.billing.in_limits)
        self.add_project()
        self.refresh_from_db()
        self.assertTrue(self.billing.in_limits)
        project = self.add_project()
        self.refresh_from_db()
        self.assertFalse(self.billing.in_limits)
        project.delete()
        self.refresh_from_db()
        self.assertTrue(self.billing.in_limits)

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
        self.assertEqual(self.billing.projects.count(), 1)

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
        self.assertEqual(self.billing.projects.count(), 1)
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
        self.assertEqual(self.billing.projects.count(), 1)
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
        self.assertEqual(self.billing.projects.count(), 0)
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
        self.assertEqual(self.billing.projects.count(), 1)
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
        self.assertEqual(self.billing.projects.count(), 1)
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
        self.assertEqual(self.billing.projects.count(), 1)
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
        self.assertEqual(self.billing.projects.count(), 1)
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
        self.assertEqual(self.billing.projects.count(), 1)
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
        self.assertEqual(self.billing.projects.count(), 0)
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
            set(self.billing.owners.values_list("username", flat=True)),
            {self.user.username, second_user.username},
        )

    def test_merge(self) -> None:
        other = Billing.objects.create(plan=self.billing.plan)
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

        response = self.client.post(
            reverse("billing-merge", kwargs={"pk": self.billing.pk}),
            {"other": other.pk},
        )
        self.assertRedirects(
            response, reverse("billing-detail", kwargs={"pk": self.billing.pk})
        )

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

    def test_owners(self) -> None:
        second_user = create_another_user()
        billing_url = reverse("billing-detail", kwargs={"pk": self.billing.pk})

        # No access for different user
        self.client.login(username=second_user.username, password="testpassword")

        response = self.client.get(billing_url)
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            reverse("billing-owner-add", kwargs={"pk": self.billing.pk})
        )
        self.assertEqual(response.status_code, 403)

        response = self.client.post(
            reverse(
                "billing-owner-remove",
                kwargs={"pk": self.billing.pk, "user_id": self.user.pk},
            )
        )
        self.assertEqual(response.status_code, 403)

        # Access for owner
        self.client.login(username=self.user.username, password="testpassword")

        response = self.client.get(billing_url)
        self.assertContains(response, "Billing admins")

        # Add user
        response = self.client.post(
            reverse("billing-owner-add", kwargs={"pk": self.billing.pk}),
            {"user": "nonexisting-user"},
        )
        self.assertRedirects(response, billing_url)
        self.assertEqual(1, self.billing.owners.count())

        response = self.client.post(
            reverse("billing-owner-add", kwargs={"pk": self.billing.pk}),
            {"user": second_user.username},
        )
        self.assertRedirects(response, billing_url)
        self.assertEqual(2, self.billing.owners.count())
        self.assertEqual(
            {self.user.username, second_user.username},
            set(self.billing.owners.values_list("username", flat=True)),
        )
        # Add user (no-op)
        response = self.client.post(
            reverse("billing-owner-add", kwargs={"pk": self.billing.pk}),
            {"user": second_user.username},
        )
        self.assertRedirects(response, billing_url)
        self.assertEqual(2, self.billing.owners.count())
        self.assertEqual(
            {self.user.username, second_user.username},
            set(self.billing.owners.values_list("username", flat=True)),
        )

        # Delete user restricted for self
        response = self.client.post(
            reverse(
                "billing-owner-remove",
                kwargs={"pk": self.billing.pk, "user_id": self.user.pk},
            )
        )
        self.assertRedirects(response, billing_url)
        self.assertEqual(2, self.billing.owners.count())
        self.assertEqual(
            {self.user.username, second_user.username},
            set(self.billing.owners.values_list("username", flat=True)),
        )

        # Delete other user works
        response = self.client.post(
            reverse(
                "billing-owner-remove",
                kwargs={"pk": self.billing.pk, "user_id": second_user.pk},
            )
        )
        self.assertRedirects(response, billing_url)
        self.assertEqual(1, self.billing.owners.count())
        self.assertEqual(
            {self.user.username},
            set(self.billing.owners.values_list("username", flat=True)),
        )


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
        billing = user.billing_set.get()
        billing.projects.add(component.project)

        # Not valid for libre
        self.assertFalse(billing.valid_libre)
        response = self.client.post(
            billing.get_absolute_url(),
            {"request": "1", "message": "msg"},
            follow=True,
        )
        self.assertNotContains(response, "Pending approval")

        # Add missing license info
        component.project.component_set.update(license="GPL-3.0-or-later")
        billing = user.billing_set.get()

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
