# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""File sync for local repositories."""

from __future__ import annotations

from pathlib import Path
from typing import cast
from unittest.mock import Mock, patch

from django.db import DatabaseError, connection
from django.db.models.signals import post_save
from django.test.utils import CaptureQueriesContext

from weblate.auth.models import get_anonymous
from weblate.trans.actions import ActionEvents
from weblate.trans.models import Component, PendingUnitChange, Unit
from weblate.trans.models.unit import UnitQuerySet
from weblate.trans.tests.test_views import ComponentTestCase
from weblate.trans.tests.utils import create_another_user
from weblate.trans.util import PLURAL_SEPARATOR
from weblate.utils.hash import calculate_hash
from weblate.utils.state import STATE_TRANSLATED


def make_local(component: Component) -> Component:
    """Use the shared Git fixture as a local repository."""
    root = Path(component.full_path)
    for filename in root.rglob("*"):
        if filename.is_symlink() and not filename.resolve().is_relative_to(root):
            filename.unlink()
    Component.objects.filter(pk=component.pk).update(vcs="local", repo="local:")
    component.refresh_from_db()
    component.drop_repository_cache()
    return component


class FileSyncSnapshotTest(ComponentTestCase):
    def prepare_units(self, count: int) -> None:
        translation = self.get_translation()
        self.component.translation_set.exclude(pk=translation.pk).update(filename="")
        template = dict(translation.unit_set.order_by("pk").values()[0])
        template.pop("id")
        Unit.objects.bulk_create(
            [
                Unit(
                    **{
                        **template,
                        "source": f"Reapply snapshot {index}",
                        "id_hash": calculate_hash(f"Reapply snapshot {index}", ""),
                    }
                )
                for index in range(count - translation.unit_set.count())
            ]
        )
        translation.unit_set.update(details={"custom": ["保留"], "disk_identity": {}})

    def test_snapshot_batches_preserve_unit_data(self) -> None:
        self.prepare_units(1002)
        units = self.get_translation().unit_set.all()
        before = {unit.pk: unit for unit in units.all()}
        write_batch = UnitQuerySet._bulk_update_values  # ruff: ignore[private-member-access]
        batches: list[int] = []

        def record_batch(
            queryset: UnitQuerySet, batch: list[Unit], fields: tuple[str, ...]
        ) -> None:
            self.assertEqual(queryset.db, connection.alias)
            self.assertEqual(fields, ("details",))
            batches.append(len(batch))
            write_batch(queryset, batch, fields)

        notifications = Mock()
        post_save.connect(notifications, sender=Unit, weak=False)
        self.addCleanup(post_save.disconnect, notifications, sender=Unit)
        with (
            patch.object(
                UnitQuerySet,
                "_bulk_update_values",
                autospec=True,
                side_effect=record_batch,
            ),
            CaptureQueriesContext(connection) as queries,
        ):
            self.assertTrue(
                self.component.do_file_sync(self.get_request(), do_commit=False)
            )
        self.assertEqual(batches, [500, 500, 2])
        notifications.assert_not_called()
        self.assertEqual(
            sum('FROM "trans_unit"' in query["sql"] for query in queries), 1
        )
        for unit in units.all():
            original = before[unit.pk]
            expected_details = {
                **original.details,
                "disk_state": Unit.get_disk_state(
                    target=original.target,
                    state=original.state,
                    explanation=original.explanation,
                    automatically_translated=original.automatically_translated,
                ),
            }
            self.assertEqual(unit.details, expected_details)
            for field in Unit._meta.concrete_fields:  # ruff: ignore[private-member-access]
                if field.name != "details":
                    self.assertEqual(
                        getattr(unit, field.attname), getattr(original, field.attname)
                    )
        self.assertEqual(PendingUnitChange.objects.filter(unit__in=units).count(), 1002)

    def test_existing_snapshots_and_pending_authorship(self) -> None:
        self.prepare_units(10)
        units = self.get_translation().unit_set.all()
        unit = units.order_by("pk")[0]
        details = {**unit.details, "disk_state": {"target": "Original disk value"}}
        units.filter(pk=unit.pk).update(details=details)
        author = create_another_user()
        unit.change_set.create(
            action=ActionEvents.CHANGE, user=self.user, author=author
        )
        self.assertTrue(
            self.component.do_file_sync(self.get_request(), do_commit=False)
        )
        unit.refresh_from_db()
        self.assertEqual(unit.details, details)
        pending = PendingUnitChange.objects.get(unit=unit)
        self.assertEqual(pending.author_id, author.pk)
        self.assertEqual(pending.metadata["actor_id"], self.user.pk)
        self.assertEqual(pending.target, unit.target)
        self.assertEqual(pending.explanation, unit.explanation)
        self.assertEqual(pending.state, unit.state)
        self.assertEqual(
            pending.automatically_translated, unit.automatically_translated
        )
        self.assertEqual(pending.source_unit_explanation, unit.source_unit.explanation)
        self.assertFalse(pending.add_unit)
        self.assertTrue(
            PendingUnitChange.objects.filter(unit__in=units)
            .exclude(unit=unit)
            .filter(author=get_anonymous())
            .exists()
        )
        self.assertEqual(
            self.component.change_set.get(action=ActionEvents.FORCE_SYNC).user_id,
            self.user.pk,
        )
        with patch.object(UnitQuerySet, "_bulk_update_values") as writer:
            self.assertTrue(
                self.component.do_file_sync(self.get_request(), do_commit=False)
            )
        writer.assert_not_called()
        self.assertEqual(PendingUnitChange.objects.filter(unit__in=units).count(), 20)

    def test_disabled_snapshots_still_create_pending_changes(self) -> None:
        self.prepare_units(10)
        units = self.get_translation().unit_set.all()
        before = list(units.order_by("pk").values())
        with patch.object(UnitQuerySet, "_bulk_update_values") as writer:
            self.assertTrue(
                self.component.do_file_sync(
                    self.get_request(), do_commit=False, store_disk_state=False
                )
            )
        writer.assert_not_called()
        self.assertEqual(list(units.order_by("pk").values()), before)
        self.assertEqual(PendingUnitChange.objects.filter(unit__in=units).count(), 10)

    def test_snapshot_failure_rolls_back_pending_changes(self) -> None:
        self.prepare_units(1002)
        units = self.get_translation().unit_set.all()
        before = list(units.order_by("pk").values())
        pending_before = PendingUnitChange.objects.count()
        changes_before = self.component.change_set.count()
        write_batch = UnitQuerySet._bulk_update_values  # ruff: ignore[private-member-access]
        batches: list[int] = []

        def fail_final_batch(
            queryset: UnitQuerySet, batch: list[Unit], fields: tuple[str, ...]
        ) -> None:
            batches.append(len(batch))
            if len(batches) == 3:
                self.assertEqual(
                    units.filter(details__has_key="disk_state").count(), 1000
                )
                self.assertEqual(
                    PendingUnitChange.objects.count(), pending_before + 1001
                )
                msg = "Snapshot write failed"
                raise DatabaseError(msg)
            write_batch(queryset, batch, fields)

        with (
            self.captureOnCommitCallbacks() as callbacks,
            patch.object(
                UnitQuerySet,
                "_bulk_update_values",
                autospec=True,
                side_effect=fail_final_batch,
            ),
            self.assertRaisesMessage(DatabaseError, "Snapshot write failed"),
        ):
            self.component.do_file_sync(self.get_request())
        self.assertEqual(batches, [500, 500, 2])
        self.assertEqual(list(units.order_by("pk").values()), before)
        self.assertEqual(PendingUnitChange.objects.count(), pending_before)
        self.assertEqual(self.component.change_set.count(), changes_before)
        self.assertEqual(callbacks, [])


class LocalFileSyncTest(ComponentTestCase):
    def create_component(self) -> Component:
        return make_local(self.create_tbx())

    def test_reapply_existing_units_does_not_rewrite_file(self) -> None:
        translation = self.get_translation()
        filename = Path(cast("str", translation.get_filename()))
        original = filename.read_bytes()
        self.assertTrue(
            self.component.do_file_sync(self.get_request(), do_commit=False)
        )
        with self.component.repository.lock:
            self.assertFalse(
                translation._commit_pending(  # ruff: ignore[private-member-access]
                    "file-sync", None
                )
            )
        self.assertEqual(filename.read_bytes(), original)

    def test_reapply_recreates_units_in_existing_files(self) -> None:
        translation = self.get_translation()
        unit = translation.unit_set.order_by("pk")[0]
        store = translation.load_store()
        store.delete_unit(store.find_unit(unit.context, unit.source)[0].unit)
        store.save()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(self.component.do_file_sync(self.get_request()))
        restored = translation.load_store().find_unit(unit.context, unit.source)[0]
        self.assertEqual(restored.target, unit.target)

    def test_reapply_recreates_unit_with_older_pending_edit(self) -> None:
        translation = self.get_translation()
        unit = translation.unit_set.order_by("pk")[0]
        target = "Recovered pending translation"
        Unit.objects.filter(pk=unit.pk).update(target=target, state=STATE_TRANSLATED)
        pending = PendingUnitChange.build_unit_change(
            unit=unit,
            author=self.user,
            target=target,
            explanation=unit.explanation,
            state=STATE_TRANSLATED,
            source_unit_explanation=unit.source_unit.explanation,
            automatically_translated=False,
        )
        pending.save()
        store = translation.load_store()
        store.delete_unit(store.find_unit(unit.context, unit.source)[0].unit)
        store.save()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(self.component.do_file_sync(self.get_request()))
        unit.refresh_from_db()
        self.assertEqual(unit.target, target)
        self.assertEqual(unit.state, STATE_TRANSLATED)
        self.assertEqual(
            translation.load_store().find_unit(unit.context, unit.source)[0].target,
            target,
        )
        self.assertEqual(
            sum(
                stored.context == unit.context and stored.source == unit.source
                for stored in translation.load_store().all_units
            ),
            1,
        )
        self.assertFalse(PendingUnitChange.objects.filter(unit=unit).exists())

    def test_reapply_recreates_missing_files(self) -> None:
        translation = self.get_translation()
        unit = translation.unit_set.order_by("pk")[0]
        Path(cast("str", translation.get_filename())).unlink()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(self.component.do_file_sync(self.get_request()))
        restored = translation.load_store().find_unit(unit.context, unit.source)[0]
        self.assertEqual(restored.target, unit.target)


class LocalCSVFileSyncTest(ComponentTestCase):
    def create_component(self) -> Component:
        return make_local(self.create_csv_mono())

    def test_plural_units_are_not_marked_for_creation(self) -> None:
        unit = self.component.source_translation.unit_set.order_by("pk")[0]
        Unit.objects.filter(pk=unit.pk).update(
            source=f"one{PLURAL_SEPARATOR}many",
        )
        self.assertTrue(
            self.component.do_file_sync(self.get_request(), do_commit=False)
        )
        pending = PendingUnitChange.objects.filter(unit=unit).latest("pk")
        self.assertFalse(pending.add_unit)


class LocalTemplateFileSyncTest(ComponentTestCase):
    def create_component(self) -> Component:
        return make_local(self.create_json_mono())

    def test_reapply_restores_source_file(self) -> None:
        source = self.component.source_translation
        units = list(source.unit_set.values_list("context", "source"))
        Path(source.get_filename()).unlink()
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(self.component.do_file_sync(self.get_request()))
        self.component.drop_template_store_cache()
        store = source.load_store()
        for context, text in units:
            self.assertEqual(store.find_unit(context, text)[0].source, text)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertTrue(self.component.do_file_sync(self.get_request()))
        self.component.drop_template_store_cache()
        self.assertEqual(len(list(source.load_store().content_units)), len(units))
        self.assertFalse(
            PendingUnitChange.objects.filter(unit__translation=source).exists()
        )
