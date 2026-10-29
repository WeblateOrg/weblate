# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Database-side cleanup of disk-state bookkeeping."""

from __future__ import annotations

from unittest.mock import Mock

from django.db import connection, transaction
from django.db.models import Q
from django.db.models.signals import post_save
from django.db.transaction import TransactionManagementError
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext

from weblate.trans.models import Change, Component, PendingUnitChange, Translation, Unit
from weblate.trans.tests.test_views import ComponentTestCase


class DiskStateCleanupTest(ComponentTestCase):
    def test_cleanup_preserves_other_data_and_queryset_scope(self) -> None:
        units = list(self.translation.unit_set.order_by("pk"))
        unrelated = {"nested": {"disk_state": "保留"}, "custom": [1, None, True]}
        details = [
            {**unrelated, "disk_state": {}, "disk_identity": {"source": "Original"}},
            {**unrelated, "disk_state": {"target": "Disk target"}},
            {**unrelated, "disk_identity": {"source": "Keep identity"}},
            {},
        ]
        self.assertEqual(len(units), len(details))
        for unit, values in zip(units, details, strict=True):
            Unit.objects.filter(pk=unit.pk).update(details=values)
        source = self.component.source_translation.unit_set.order_by("pk")[0]
        Unit.objects.filter(pk=source.pk).update(details=details[0])
        component_units = Unit.objects.filter(translation__component=self.component)
        before = list(component_units.order_by("pk").values())
        change_count = Change.objects.count()
        pending_count = PendingUnitChange.objects.count()
        notifications = Mock()
        post_save.connect(notifications, sender=Unit, weak=False)
        self.addCleanup(post_save.disconnect, notifications, sender=Unit)

        with CaptureQueriesContext(connection) as queries:
            (
                Unit.objects.using(connection.alias)
                .filter(
                    translation__component=self.component, translation=self.translation
                )
                .clear_disk_state()
            )

        self.assertEqual(len(queries), 1)
        self.assertTrue(queries[0]["sql"].startswith("UPDATE "))
        expected = []
        cleaned_ids = {units[0].pk, units[1].pk}
        for row in before:
            if row["id"] in cleaned_ids:
                row["details"] = unrelated
            expected.append(row)
        self.assertEqual(list(component_units.order_by("pk").values()), expected)
        self.assertEqual(Change.objects.count(), change_count)
        self.assertEqual(PendingUnitChange.objects.count(), pending_count)
        notifications.assert_not_called()

    def test_cleanup_uses_current_database_details(self) -> None:
        unit = self.translation.unit_set.order_by("pk")[0]
        original = {"disk_state": {}, "disk_identity": {"source": "Original"}}
        Unit.objects.filter(pk=unit.pk).update(details=original)
        unit.refresh_from_db()
        # The caller's loaded unit is stale when another operation updates JSON.
        Unit.objects.filter(pk=unit.pk).update(details={**original, "new": "保留"})
        Unit.objects.filter(pk=unit.pk).clear_disk_state()
        unit.refresh_from_db()
        self.assertEqual(unit.details, {"new": "保留"})

    def test_cleanup_rolls_back(self) -> None:
        unit = self.translation.unit_set.order_by("pk")[0]
        original = {"disk_state": {}, "disk_identity": {}, "custom": True}
        Unit.objects.filter(pk=unit.pk).update(details=original)
        with transaction.atomic():
            Unit.objects.filter(pk=unit.pk).clear_disk_state()
            self.assertEqual(Unit.objects.get(pk=unit.pk).details, {"custom": True})
            transaction.set_rollback(True)
        unit.refresh_from_db()
        self.assertEqual(unit.details, original)

    def test_empty_cleanup(self) -> None:
        with self.assertNumQueries(1):
            self.translation.unit_set.clear_disk_state()
        with self.assertNumQueries(0):
            Unit.objects.none().clear_disk_state()

    def test_cleanup_keeps_units_with_remaining_pending_changes(self) -> None:
        first, second = list(self.translation.unit_set.order_by("pk")[:2])
        original = {"disk_state": {}, "disk_identity": {}, "custom": True}
        Unit.objects.filter(pk__in=[first.pk, second.pk]).update(details=original)
        pending = PendingUnitChange.build_unit_change(
            unit=second,
            author=self.user,
            user_id=self.user.pk,
            target=second.target,
            explanation=second.explanation,
            state=second.state,
            source_unit_explanation=second.source_unit.explanation,
            automatically_translated=second.automatically_translated,
        )
        pending.save()
        Translation.clear_committed_disk_states({first.pk, second.pk})
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.details, {"custom": True})
        self.assertEqual(second.details, original)
        self.assertTrue(PendingUnitChange.objects.filter(pk=pending.pk).exists())


class LinkedDiskStateCleanupTest(ComponentTestCase):
    def create_component(self) -> Component:
        return self.create_link()

    def test_cleanup_includes_linked_children(self) -> None:
        root = self.component.linked_component
        self.assertIsNotNone(root)
        selected = Unit.objects.filter(
            Q(translation__component=root)
            | Q(translation__component__linked_component=root)
        )
        selected.update(details={"disk_state": {}, "disk_identity": {}, "custom": True})
        self.assertTrue(selected.filter(translation__component=root).exists())
        self.assertTrue(selected.filter(translation__component=self.component).exists())
        with self.assertNumQueries(1):
            selected.clear_disk_state()
        self.assertEqual(
            list(selected.values_list("details", flat=True)),
            [{"custom": True}] * selected.count(),
        )


class DiskStateCleanupTransactionTest(TransactionTestCase):
    def test_cleanup_requires_transaction(self) -> None:
        with self.assertRaisesMessage(
            TransactionManagementError, "Disk-state cleanup requires a transaction."
        ):
            Unit.objects.clear_disk_state()
