# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from typing import Never
from unittest.mock import patch

from django.db import connection, transaction
from django.db.models.signals import post_delete

from weblate.billing.models import Billing
from weblate.screenshots.models import Screenshot
from weblate.trans.alerts.community import MissingScreenshots
from weblate.trans.alerts.registry import update_alerts
from weblate.trans.models import Alert, Category, Component
from weblate.trans.removal import (
    RemovalBatch,
    get_current_removal_batch,
    removal_batch_context,
)
from weblate.trans.tasks import (
    category_removal,
    component_removal,
    project_removal,
)
from weblate.trans.tests.test_models import RepoTestCase
from weblate.trans.tests.utils import create_test_billing, create_test_user


class RemovalAlertTest(RepoTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user = create_test_user()
        self.project = self.create_project()
        self.category = Category.objects.create(
            project=self.project, name="Removal", slug="removal"
        )
        self.component = self.create_po(project=self.project, category=self.category)
        self.survivor = self.create_po(
            project=self.create_project(name="Survivor", slug="survivor")
        )
        self.linked = self.create_link_existing(
            project=self.survivor.project,
            name="Linked",
        )

    def assert_removal_defers_alerts(self, kind: str) -> None:
        Screenshot.objects.bulk_create(
            [
                Screenshot(
                    name=f"Removal {index}",
                    translation=self.component.source_translation,
                )
                for index in range(3)
            ]
        )
        removed_ids = {self.component.pk, self.linked.pk}
        seen_screenshots = []

        def request_alerts(
            sender: type[Screenshot], instance: Screenshot, **kwargs: object
        ) -> None:
            component = instance.translation.component
            batch = get_current_removal_batch()
            if batch is None:
                self.fail("Removal context missing from screenshot deletion")
            self.assertTrue(removed_ids.issubset(batch.removed_component_ids))
            seen_screenshots.append(instance.pk)
            with self.assertNumQueries(0):
                update_alerts(component, {"MissingScreenshots"})
                component.update_alerts()
                component.add_alert("UpdateFailure", error="Removal test")
                component.delete_alert("UpdateFailure")
                update_alerts(self.survivor, {"MissingScreenshots"})
                update_alerts(self.survivor)
                self.survivor.update_alerts()
                batch.collect_linked_component(self.survivor.pk)

        post_delete.connect(request_alerts, sender=Screenshot)
        try:
            with (
                patch.object(MissingScreenshots, "check_component") as check,
                patch.object(Component, "_update_alerts", autospec=True) as refresh,
                self.captureOnCommitCallbacks(execute=True),
            ):
                if kind == "project":
                    project_removal.run(self.project.pk, self.user.pk, backup=False)
                elif kind == "category":
                    category_removal(self.category.pk, self.user.pk)
                else:
                    component_removal(self.component.pk, self.user.pk)
                connection.check_constraints()
                check.assert_not_called()
                refresh.assert_not_called()
            self.assertEqual(len(seen_screenshots), 3)
            self.assertFalse(Component.objects.filter(pk__in=removed_ids).exists())
            self.assertEqual(
                [call.args[0].pk for call in refresh.call_args_list],
                [self.survivor.pk],
            )
            self.assertIsNot(refresh.call_args.args[0], self.survivor)
            self.assertIsNone(get_current_removal_batch())
        finally:
            post_delete.disconnect(request_alerts, sender=Screenshot)

    def test_project_removal_defers_alerts(self) -> None:
        self.assert_removal_defers_alerts("project")

    def test_category_removal_defers_alerts(self) -> None:
        self.assert_removal_defers_alerts("category")

    def test_component_removal_defers_alerts(self) -> None:
        self.assert_removal_defers_alerts("component")

    def test_removal_logs_commit_and_filesystem_deletion(self) -> None:
        component_id = self.component.pk
        with (
            self.assertLogs("weblate", level="INFO") as logs,
            self.captureOnCommitCallbacks(execute=True),
        ):
            component_removal(component_id, self.user.pk)
        output = "\n".join(logs.output)
        self.assertIn("removal started", output)
        self.assertIn("removal directory deleted", output)
        self.assertIn("removal committed", output)
        self.assertIn(str(component_id), output)

    def test_removal_logs_failure_without_commit(self) -> None:
        original_delete = Component.delete

        def fail_after_delete(
            component: Component,
            using: str | None = None,
            keep_parents: bool = False,
        ) -> Never:
            original_delete(component, using=using, keep_parents=keep_parents)
            msg = "Failure after directory deletion"
            raise RuntimeError(msg)

        component_id = self.component.pk
        with (
            self.assertLogs("weblate", level="INFO") as logs,
            patch.object(
                Component, "delete", autospec=True, side_effect=fail_after_delete
            ),
            self.assertRaisesMessage(RuntimeError, "Failure after directory deletion"),
        ):
            component_removal(component_id, self.user.pk)
        self.assertTrue(Component.objects.filter(pk=component_id).exists())
        output = "\n".join(logs.output)
        self.assertIn("removal directory deleted", output)
        self.assertIn("failed before commit", output)
        self.assertNotIn("removal committed", output)

    def test_removal_rollback_discards_alert_refreshes(self) -> None:
        Screenshot.objects.create(
            name="Rollback", translation=self.component.source_translation
        )

        def fail_removal(
            sender: type[Screenshot], instance: Screenshot, **kwargs: object
        ) -> None:
            update_alerts(self.survivor)
            self.survivor.update_alerts()
            msg = "Abort removal"
            raise RuntimeError(msg)

        post_delete.connect(fail_removal, sender=Screenshot)
        try:
            with (
                self.captureOnCommitCallbacks(execute=True) as callbacks,
                self.assertRaisesMessage(RuntimeError, "Abort removal"),
            ):
                project_removal.run(self.project.pk, self.user.pk, backup=False)
            self.assertEqual(callbacks, [])
            self.assertTrue(Component.objects.filter(pk=self.component.pk).exists())
            self.assertIsNone(get_current_removal_batch())
        finally:
            post_delete.disconnect(fail_removal, sender=Screenshot)

    def test_alert_mutations_on_survivors_are_preserved(self) -> None:
        batch = RemovalBatch()
        batch.mark_component(self.component.pk)
        with removal_batch_context(batch):
            self.survivor.add_alert("BillingLimit")
            self.assertTrue(
                self.survivor.alert_set.filter(name="BillingLimit").exists()
            )
            self.survivor.delete_alert("BillingLimit")
            self.assertFalse(
                self.survivor.alert_set.filter(name="BillingLimit").exists()
            )

    def test_billing_alert_refresh_is_deferred_and_reloads_state(self) -> None:
        billing = create_test_billing(self.user, invoice=False)
        billing.plan.limit_projects = 0
        billing.plan.save(update_fields=["limit_projects"])
        billing.add_project(self.project)
        billing.add_project(self.survivor.project)
        batch = RemovalBatch()
        batch.mark_component(self.component.pk)
        with (
            patch.object(
                Billing,
                "update_alerts",
                autospec=True,
                side_effect=Billing.update_alerts,
            ) as refresh,
            self.captureOnCommitCallbacks(execute=True),
            transaction.atomic(),
        ):
            with removal_batch_context(batch), self.assertNumQueries(0):
                billing.update_alerts()
                billing.update_alerts()
            Billing.objects.filter(pk=billing.pk).update(in_limits=False)
            self.assertFalse(Alert.objects.filter(name="BillingLimit").exists())
            transaction.on_commit(batch.flush)
        self.assertEqual(refresh.call_count, 3)
        self.assertIsNot(refresh.call_args.args[0], billing)
        self.assertTrue(self.survivor.alert_set.filter(name="BillingLimit").exists())

    def test_screenshot_deletion_outside_removal_recalculates_alerts(self) -> None:
        screenshot = Screenshot.objects.create(
            name="Standalone", translation=self.component.source_translation
        )
        with patch.object(
            MissingScreenshots, "check_component", return_value=False
        ) as check:
            screenshot.delete()
        check.assert_called_once()
