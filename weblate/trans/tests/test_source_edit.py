# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse

from weblate.formats.base import UnitNotFoundError
from weblate.formats.source_edit import find_identity
from weblate.trans.models import Component, Unit
from weblate.trans.models.project import CommitPolicyChoices
from weblate.trans.source_edit import edit_source
from weblate.trans.tests.test_views import ViewTestCase
from weblate.trans.tests.utils import create_another_user
from weblate.trans.util import split_plural
from weblate.utils.state import FUZZY_STATES, STATE_APPROVED, STATE_TRANSLATED


class SourceEditTest(ViewTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.make_manager()
        self.component.manage_units = True
        self.component.save()

    def source_unit(self) -> Unit:
        return self.get_unit().source_unit

    def test_edit_source(self) -> None:
        source = self.source_unit()
        old = {"source": source.source, "context": source.context}
        units = list(source.unit_set.all())
        translated = {unit.pk: unit.target for unit in units if not unit.is_source}
        updated = edit_source(
            source,
            self.user,
            content_hash=source.content_hash,
            source=["Updated source"],
        )
        self.assertEqual(updated.pk, source.pk)
        self.assertEqual(
            set(updated.unit_set.values_list("pk", flat=True)),
            {unit.pk for unit in units},
        )
        for pk, target in translated.items():
            unit = Unit.objects.get(pk=pk)
            self.assertEqual(unit.target, target)
            if target:
                self.assertIn(unit.state, FUZZY_STATES)
            self.assertEqual(unit.details["disk_identity"], old)
        self.component.commit_pending("test", self.user)
        for pk, target in translated.items():
            unit = Unit.objects.get(pk=pk)
            self.assertNotIn("disk_identity", unit.details)
            backend = find_identity(
                unit.translation.store,
                {"source": "Updated source", "context": source.context},
            )
            self.assertEqual(backend.target, target)

    def test_repeated_edit_and_sync(self) -> None:
        source = self.source_unit()
        source = edit_source(
            source, self.user, content_hash=source.content_hash, source=["First edit"]
        )
        source.refresh_from_db()
        source = edit_source(
            source, self.user, content_hash=source.content_hash, source=["Second edit"]
        )
        for translation in self.component.translation_set.exclude(
            pk=source.translation_id
        ):
            translation.check_sync(force=True)
        source.refresh_from_db()
        self.assertEqual(source.source, "Second edit")
        self.component.commit_pending("test", self.user)
        for unit in source.unit_set.exclude(pk=source.pk):
            backend = unit.translation.store.find_unit(source.context, source.source)[0]
            self.assertEqual(backend.source, "Second edit")

    def test_stale_edit(self) -> None:
        source = self.source_unit()
        with self.assertRaises(ValidationError):
            edit_source(
                source,
                self.user,
                content_hash=source.content_hash + 1,
                source=["Updated"],
            )

    def test_api(self) -> None:
        source = self.source_unit()
        response = self.client.post(
            f"/api/units/{source.pk}/source/",
            {"content_hash": source.content_hash, "source": ["Updated source"]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        source.refresh_from_db()
        self.assertEqual(source.source, "Updated source")

    def test_dialog(self) -> None:
        source = self.source_unit()
        response = self.client.get(source.get_absolute_url())
        self.assertContains(response, "source-edit-modal")
        response = self.client.post(
            reverse("edit-source-unit", kwargs={"unit_id": source.pk}),
            {
                "content_hash": source.content_hash,
                "source_0": "Updated source",
                "context": source.context,
                "explanation": "",
            },
        )
        self.assertEqual(response.status_code, 302, response.content)

    def test_disabled(self) -> None:
        self.component.manage_units = False
        self.component.save()
        source = self.source_unit()
        response = self.client.post(
            f"/api/units/{source.pk}/source/",
            {
                "content_hash": source.content_hash,
                "source": split_plural(source.source),
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403, response.content)

    def test_noop(self) -> None:
        source = self.source_unit()
        count = source.change_set.count()
        edit_source(source, self.user, content_hash=source.content_hash)
        self.assertEqual(source.change_set.count(), count)
        self.assertFalse(source.unit_set.filter(pending_changes__isnull=False).exists())

    def test_translation_after_source_edit(self) -> None:
        unit = self.get_unit()
        source = unit.source_unit
        edit_source(
            source,
            self.user,
            content_hash=source.content_hash,
            source=["Changed source"],
        )
        unit.translate(self.user, "Changed translation", STATE_TRANSLATED)
        unit.refresh_from_db()
        self.assertEqual(unit.source, "Changed source")
        self.component.commit_pending("test", self.user)
        self.assertEqual(
            find_identity(
                unit.translation.store, {"source": unit.source, "context": unit.context}
            ).target,
            "Changed translation",
        )

    def test_commit_policy(self) -> None:
        self.project.commit_policy = CommitPolicyChoices.WITHOUT_NEEDS_EDITING
        self.project.save()
        unit = self.get_unit()
        unit.translate(self.user, "Translation", STATE_TRANSLATED)
        self.component.commit_pending("test", self.user)
        source = unit.source_unit
        edit_source(
            source,
            self.user,
            content_hash=source.content_hash,
            source=["Changed source"],
        )
        self.component.commit_pending("test", self.user)
        unit.refresh_from_db()
        self.assertTrue(unit.pending_changes.exists())
        self.assertIn("disk_identity", unit.details)
        unit.translate(self.user, "Reviewed", STATE_TRANSLATED)
        self.component.commit_pending("test", self.user)
        unit.refresh_from_db()
        self.assertFalse(unit.pending_changes.exists())
        self.assertEqual(
            find_identity(
                unit.translation.store, {"source": unit.source, "context": unit.context}
            ).target,
            "Reviewed",
        )

    def test_failed_write_blocks_later_edit(self) -> None:
        source = self.source_unit()
        source = edit_source(
            source, self.user, content_hash=source.content_hash, source=["First"]
        )
        edit_source(
            source, self.user, content_hash=source.content_hash, source=["Second"]
        )
        with patch(
            "weblate.trans.models.translation.edit_identity",
            side_effect=ValueError("Cannot edit"),
        ):
            self.component.commit_pending("test", self.user)
        self.assertTrue(source.unit_set.filter(pending_changes__isnull=False).exists())
        for item in source.unit_set.exclude(translation__filename=""):
            for pending in item.pending_changes.all():
                pending.metadata.pop("last_failed", None)
                pending.save()
        self.component.commit_pending("test", self.user)
        for item in source.unit_set.exclude(translation__filename=""):
            self.assertFalse(item.pending_changes.exists())

    def test_readonly(self) -> None:
        source = self.source_unit()
        source.extra_flags = "read-only"
        source.save()
        response = self.client.post(
            f"/api/units/{source.pk}/source/",
            {"content_hash": source.content_hash, "source": ["Changed"]},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

    def test_stale_dialog(self) -> None:
        source = self.source_unit()
        response = self.client.post(
            reverse("edit-source-unit", kwargs={"unit_id": source.pk}),
            {
                "content_hash": source.content_hash + 1,
                "source_0": "Changed",
                "context": source.context,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Reload it before editing", status_code=400)

    def test_explanation_only(self) -> None:
        source = self.source_unit()
        states = dict(source.unit_set.values_list("pk", "state"))
        edited = edit_source(
            source,
            self.user,
            content_hash=source.content_hash,
            explanation="Definition",
        )
        self.assertEqual(edited.explanation, "Definition")
        self.assertEqual(dict(edited.unit_set.values_list("pk", "state")), states)
        self.component.commit_pending("test", self.user)
        edited.refresh_from_db()
        self.assertEqual(edited.explanation, "Definition")

    def test_retry_after_written_file(self) -> None:
        source = self.source_unit()
        edit_source(
            source, self.user, content_hash=source.content_hash, source=["Changed"]
        )
        unit = Unit.objects.get(source_unit=source, translation=self.get_translation())
        change = unit.pending_changes.latest("pk")
        store = unit.translation.store
        unit.translation.update_pending_identity(
            store, unit, change, unit.details["disk_identity"]
        )
        store.save()
        self.component.commit_pending("retry", self.user)
        unit.refresh_from_db()
        self.assertFalse(unit.pending_changes.exists())

    def test_delete_pending_identity(self) -> None:
        self.project.commit_policy = CommitPolicyChoices.WITHOUT_NEEDS_EDITING
        self.project.save()
        unit = self.get_unit()
        unit.translate(self.user, "Translation", STATE_TRANSLATED)
        self.component.commit_pending("test", self.user)
        source = unit.source_unit
        old = {"source": source.source, "context": source.context}
        source = edit_source(
            source,
            self.user,
            content_hash=source.content_hash,
            source=["Changed source"],
            context="changed-key" if self.component.has_template() else source.context,
        )
        self.component.commit_pending("test", self.user)
        unit.refresh_from_db()
        self.assertTrue(unit.pending_changes.exists())
        translation = unit.translation
        source.translation.delete_unit(None, source)
        translation.drop_store_cache()
        with self.assertRaises(UnitNotFoundError):
            find_identity(translation.store, old)
        translation.check_sync(force=True)
        self.assertFalse(Unit.objects.filter(pk=unit.pk).exists())
        self.assertFalse(translation.unit_set.filter(source=old["source"]).exists())

    def test_retry_after_multiple_written_identities(self) -> None:
        source = self.source_unit()
        for value in ("First", "Second"):
            source = edit_source(
                source,
                self.user,
                content_hash=source.content_hash,
                source=[value],
                context=value if self.component.has_template() else source.context,
            )
        unit = Unit.objects.get(source_unit=source, translation=self.get_translation())
        translation = unit.translation
        changes = list(unit.pending_changes.order_by("pk"))
        self.assertEqual(len(changes), 2)
        with (
            self.assertRaisesMessage(RuntimeError, "Failure after file write"),
            transaction.atomic(),
        ):
            statuses = translation.update_units(
                changes, translation.store, self.user.get_author_name()
            )
            self.assertTrue(all(statuses.values()))
            msg = "Failure after file write"
            raise RuntimeError(msg)
        translation.drop_store_cache()
        self.assertEqual(
            find_identity(translation.store, changes[-1].metadata["identity"]).target,
            changes[-1].target,
        )
        self.component.commit_pending("retry", self.user)
        unit.refresh_from_db()
        self.assertFalse(unit.pending_changes.exists())
        self.assertNotIn("disk_identity", unit.details)
        self.assertEqual(
            find_identity(translation.store, changes[-1].metadata["identity"]).target,
            changes[-1].target,
        )

    def test_po_singular_plural_collisions(self) -> None:
        if self.component.file_format != "po":
            self.skipTest("Gettext identity collision rules")
        translation = self.component.source_translation
        for existing_plural, edited_plural in (
            (False, True),
            (True, False),
            (True, True),
        ):
            context = f"collision-{existing_plural}-{edited_plural}"
            other = translation.add_unit(
                None,
                context=context,
                source=["One", "Ones"] if existing_plural else ["One"],
                author=self.user,
            )
            edited = translation.add_unit(
                None,
                context=context,
                source=["Original", "Originals"] if edited_plural else ["Original"],
                author=self.user,
            )
            assert other is not None
            assert edited is not None
            self.component.commit_pending("test", self.user)
            for reserved in (False, True):
                if reserved:
                    for value in ("Intermediate", "Final"):
                        other = edit_source(
                            other,
                            self.user,
                            content_hash=other.content_hash,
                            source=[value, f"{value}s"] if existing_plural else [value],
                        )
                for value in ("One", "Intermediate") if reserved else ("One",):
                    with (
                        self.subTest(context=context, reserved=reserved, value=value),
                        self.assertRaises(ValidationError),
                    ):
                        edit_source(
                            edited,
                            self.user,
                            content_hash=edited.content_hash,
                            source=[value, "Others"] if edited_plural else [value],
                        )
            edited.refresh_from_db()
            self.assertEqual(split_plural(edited.source)[0], "Original")
            self.assertFalse(edited.pending_changes.exists())

    def test_add_reserved_identity(self) -> None:
        source = self.source_unit()
        original = {"source": source.source, "context": source.context}
        source = edit_source(
            source,
            self.user,
            content_hash=source.content_hash,
            source=["Intermediate source"],
            context="intermediate-key",
        )
        intermediate = {"source": source.source, "context": source.context}
        edit_source(
            source,
            self.user,
            content_hash=source.content_hash,
            source=["Final source"],
            context="final-key",
        )
        for reserved in (original, intermediate):
            for skip_existing in (False, True):
                with (
                    self.subTest(identity=reserved, skip_existing=skip_existing),
                    self.assertRaises(ValidationError),
                ):
                    source.translation.add_unit(
                        None,
                        context=reserved["context"],
                        source=reserved["source"],
                        author=self.user,
                        skip_existing=skip_existing,
                    )

    def test_retry_after_multiple_authors_write(self) -> None:
        other = create_another_user("source-retry")
        other.is_superuser = True
        other.save()
        source = self.source_unit()
        for value, author in (("First", self.user), ("Second", other)):
            source = edit_source(
                source,
                author,
                content_hash=source.content_hash,
                source=[value],
                context=value if self.component.has_template() else source.context,
            )
        unit = Unit.objects.get(source_unit=source, translation=self.get_translation())
        translation = unit.translation
        destination = unit.pending_changes.latest("pk").metadata["identity"]
        with (
            self.assertRaisesMessage(RuntimeError, "Second commit failed"),
            self.component.repository.lock,
            patch.object(
                translation,
                "git_commit",
                side_effect=[True, RuntimeError("Second commit failed")],
            ),
        ):
            translation._commit_pending("test", self.user)  # ruff: ignore[private-member-access]
        translation.drop_store_cache()
        self.assertEqual(
            find_identity(translation.store, destination).target, unit.target
        )
        self.assertEqual(unit.pending_changes.count(), 2)
        translation.commit_pending("retry", self.user)
        unit.refresh_from_db()
        self.assertFalse(unit.pending_changes.exists())
        self.assertNotIn("disk_identity", unit.details)
        self.assertEqual(
            find_identity(translation.store, destination).target, unit.target
        )

    def test_pending_addition(self) -> None:
        source = self.component.source_translation.add_unit(
            None, context="added", source="Added source", author=self.user
        )
        assert source is not None
        source = edit_source(
            source,
            self.user,
            content_hash=source.content_hash,
            source=["Edited before commit"],
        )
        self.component.commit_pending("test", self.user)
        for unit in source.unit_set.exclude(translation__filename=""):
            if self.component.has_template() and not unit.is_source and not unit.target:
                self.assertFalse(unit.pending_changes.exists())
                continue
            backend = find_identity(
                unit.translation.store,
                {"source": source.source, "context": source.context},
            )
            if unit.is_source or not self.component.has_template():
                self.assertEqual(backend.source, "Edited before commit")
            self.assertFalse(unit.pending_changes.exists())

    def test_plural_source(self) -> None:
        source = next(
            (
                unit
                for unit in self.component.source_translation.unit_set.all()
                if len(split_plural(unit.source)) > 1
            ),
            None,
        )
        if source is None:
            self.skipTest("Fixture has no plurals")
        values = split_plural(source.source)
        values[0] += " updated"
        source = edit_source(
            source, self.user, content_hash=source.content_hash, source=values
        )
        self.component.commit_pending("test", self.user)
        for unit in source.unit_set.exclude(translation__filename=""):
            self.assertFalse(unit.pending_changes.exists())
            self.assertEqual(
                unit.translation.store.find_unit(source.context, source.source)[
                    0
                ].source,
                source.source,
            )

    def test_multiple_authors(self) -> None:
        other = create_another_user("source-edit")
        other.is_superuser = True
        other.save()
        source = self.source_unit()
        source = edit_source(
            source, self.user, content_hash=source.content_hash, source=["First author"]
        )
        source = edit_source(
            source, other, content_hash=source.content_hash, source=["Second author"]
        )
        self.component.commit_pending("test", other)
        for unit in source.unit_set.exclude(translation__filename=""):
            self.assertFalse(unit.pending_changes.exists())
            self.assertEqual(
                unit.translation.store.find_unit(source.context, source.source)[
                    0
                ].source,
                "Second author",
            )


class MonolingualSourceEditTest(SourceEditTest):
    def create_component(self) -> Component:
        return self.create_json_mono()

    def test_approved_key_rename(self) -> None:
        self.project.source_review = True
        self.project.commit_policy = CommitPolicyChoices.APPROVED_ONLY
        self.project.save()
        source = self.source_unit()
        source.translate(self.user, source.target, STATE_APPROVED)
        self.component.commit_pending("approve", self.user)
        source.refresh_from_db()
        self.assertEqual(source.state, STATE_APPROVED)
        source = edit_source(
            source, self.user, content_hash=source.content_hash, context="approved-key"
        )
        self.assertEqual(source.state, STATE_APPROVED)
        self.assertEqual(source.pending_changes.latest("pk").state, STATE_APPROVED)
        self.component.commit_pending("rename", self.user)
        source.refresh_from_db()
        self.assertFalse(source.pending_changes.exists())
        self.assertNotIn("disk_identity", source.details)
        self.assertEqual(
            find_identity(
                source.translation.store,
                {"source": source.source, "context": "approved-key"},
            ).target,
            source.target,
        )

    def test_approved_source_text_requires_review(self) -> None:
        self.project.source_review = True
        self.project.commit_policy = CommitPolicyChoices.APPROVED_ONLY
        self.project.save()
        source = self.source_unit()
        source.translate(self.user, source.target, STATE_APPROVED)
        self.component.commit_pending("approve", self.user)
        source.refresh_from_db()
        original = source.target
        source = edit_source(
            source, self.user, content_hash=source.content_hash, source=["Unreviewed"]
        )
        self.assertEqual(source.state, STATE_TRANSLATED)
        self.assertEqual(source.pending_changes.latest("pk").state, STATE_TRANSLATED)
        self.component.commit_pending("edit", self.user)
        self.assertTrue(source.pending_changes.exists())
        self.assertEqual(
            find_identity(
                source.translation.store,
                {"source": original, "context": source.context},
            ).target,
            original,
        )
        source.translate(self.user, source.target, STATE_APPROVED)
        self.component.commit_pending("review", self.user)
        self.assertFalse(source.pending_changes.exists())

    def test_rename_key(self) -> None:
        source = self.source_unit()
        targets = {unit.pk: (unit.target, unit.state) for unit in source.unit_set.all()}
        updated = edit_source(
            source, self.user, content_hash=source.content_hash, context="renamed"
        )
        for unit in updated.unit_set.all():
            self.assertEqual((unit.target, unit.state), targets[unit.pk])
        self.component.commit_pending("test", self.user)
        for unit in updated.unit_set.all():
            self.assertEqual(
                find_identity(
                    unit.translation.store,
                    {"context": "renamed", "source": source.source},
                ).target,
                targets[unit.pk][0],
            )

    def test_reserved_key(self) -> None:
        source = self.source_unit()
        source = edit_source(
            source, self.user, content_hash=source.content_hash, context="intermediate"
        )
        edit_source(
            source, self.user, content_hash=source.content_hash, context="final"
        )
        other = self.component.source_translation.unit_set.exclude(pk=source.pk).first()
        with self.assertRaises(ValidationError):
            edit_source(
                other,
                self.user,
                content_hash=other.content_hash,
                context="intermediate",
            )

    def test_collision(self) -> None:
        source = self.source_unit()
        other = self.component.source_translation.unit_set.exclude(pk=source.pk).first()
        original = source.context
        with self.assertRaises(ValidationError):
            edit_source(
                source,
                self.user,
                content_hash=source.content_hash,
                context=other.context,
            )
        source.refresh_from_db()
        self.assertEqual(source.context, original)

    def test_absent_translation_stays_absent(self) -> None:
        unit = self.get_unit()
        source = unit.source_unit
        store = unit.translation.store
        backend = find_identity(
            store, {"source": source.source, "context": source.context}
        )
        store.delete_unit(backend.unit)
        store.save()
        unit.translation.drop_store_cache()
        unit.translation.check_sync(force=True)
        unit.refresh_from_db()
        self.assertEqual(unit.target, "")
        edit_source(
            source, self.user, content_hash=source.content_hash, context="renamed"
        )
        unit.refresh_from_db()
        self.assertFalse(unit.pending_changes.exists())
        self.component.commit_pending("test", self.user)
        with self.assertRaises(UnitNotFoundError):
            find_identity(
                unit.translation.store, {"source": source.source, "context": "renamed"}
            )


class GlossarySourceEditTest(ViewTestCase):
    def create_component(self) -> Component:
        return self.create_tbx(is_glossary=True, manage_units=True)

    def test_glossary_source_and_definition(self) -> None:
        self.make_manager()
        source = self.component.source_translation.unit_set.first()
        assert source is not None
        sources = split_plural(source.source)
        sources[0] += " updated"
        targets = dict(
            source.unit_set.exclude(pk=source.pk).values_list("pk", "target")
        )
        source = edit_source(
            source,
            self.user,
            content_hash=source.content_hash,
            source=sources,
            explanation="Definition",
        )
        self.component.commit_pending("test", self.user)
        for pk, target in targets.items():
            unit = Unit.objects.get(pk=pk)
            self.assertFalse(
                unit.pending_changes.exists(),
                list(unit.pending_changes.values("metadata")),
            )
            self.assertIn(
                (source.source, source.context),
                [
                    (entry.source, entry.context)
                    for entry in unit.translation.store.content_units
                ],
            )
            backend = find_identity(
                unit.translation.store,
                {"source": source.source, "context": source.context},
            )
            self.assertEqual(backend.target, target)
            self.assertEqual(backend.source_explanation, "Definition")
        source.refresh_from_db()
        self.assertEqual(source.explanation, "Definition")
