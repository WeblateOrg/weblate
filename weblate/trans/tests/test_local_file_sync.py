# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""File sync for local repositories."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from weblate.trans.models import Component, PendingUnitChange, Unit
from weblate.trans.tests.test_views import ComponentTestCase
from weblate.trans.util import PLURAL_SEPARATOR
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
